"""Per-type MTC pipelines: Prompt Mapping → LLM → MTC → MongoDB."""
from src.agents._shared import *  # noqa: F401,F403
from src.agents.count_parser import parse_user_testcase_request

CANONICAL_TYPES = ("functional", "edge", "integration", "e2e")
PREFIX_MAP = {"functional": "FR", "edge": "ED", "integration": "IN", "e2e": "E2E"}
TYPE_ALIASES = {
    "functional": "functional",
    "function": "functional",
    "edge": "edge",
    "edge case": "edge",
    "edgecase": "edge",
    "edge_case": "edge",
    "integration": "integration",
    "e2e": "e2e",
    "end to end": "e2e",
    "end-to-end": "e2e",
    "end_to_end": "e2e",
    "endtoend": "e2e",
    "end 2 end": "e2e",
}


def _add_additional_properties_false(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
        if "properties" in schema:
            for value in schema["properties"].values():
                _add_additional_properties_false(value)
        if "items" in schema:
            _add_additional_properties_false(schema["items"])
    return schema


def _cancel_pending_tasks(tasks):
    for task in tasks:
        if task and not task.done():
            task.cancel()


def _response_as_dict(response):
    if isinstance(response, dict):
        return response
    if isinstance(response, str):
        try:
            parsed = json.loads(response)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


class TypePipelineMixin:
    def _canonical_type(self, raw):
        key = str(raw or "").strip().lower()
        if not key:
            return None
        if key in TYPE_ALIASES:
            return TYPE_ALIASES[key]
        head = key.split(":", 1)[0].strip()
        return TYPE_ALIASES.get(head)

    def normalize_requested_types(self, ts_types):
        """Map user/LLM type entries onto functional/edge/integration/e2e."""
        requested = []
        if not ts_types:
            return requested

        entries = ts_types if isinstance(ts_types, (list, tuple)) else [ts_types]
        for entry in entries:
            if isinstance(entry, str):
                raw = entry
            elif isinstance(entry, dict):
                raw = entry.get("type") or entry.get("test_type") or ""
            else:
                raw = getattr(entry, "type", "") or ""
            key = self._canonical_type(raw)
            if key and key not in requested:
                requested.append(key)
        return requested

    def per_type_requested_counts(self, ts_types):
        """Return {type: n} for types the user asked for with an explicit quantity."""
        counts = {}
        if not ts_types:
            return counts
        entries = ts_types if isinstance(ts_types, (list, tuple)) else [ts_types]
        for entry in entries:
            if isinstance(entry, str):
                continue
            if isinstance(entry, dict):
                raw = entry.get("type") or entry.get("test_type") or ""
                n = entry.get("count", 0)
            else:
                raw = getattr(entry, "type", "") or ""
                n = getattr(entry, "count", 0)
            key = self._canonical_type(raw)
            try:
                n = int(n or 0)
            except (TypeError, ValueError):
                n = 0
            if not key or n <= 0:
                continue
            counts[key] = counts.get(key, 0) + n
        return counts

    def reconcile_requested_count(self, ts_count, ts_types):
        """Prefer the sum of per-type counts when the user specified them."""
        per_type = self.per_type_requested_counts(ts_types)
        if per_type:
            return sum(per_type.values())
        try:
            return int(ts_count or 0)
        except (TypeError, ValueError):
            return 0

    def merge_query_counts(self, user_input, ts_count, ts_types):
        """Prefer quantities parsed from the user query over the LLM extractor."""
        parsed_count, parsed_types = parse_user_testcase_request(user_input or "")
        if parsed_types:
            total = sum(int(item.get("count") or 0) for item in parsed_types)
            logger.info(
                f"Query count parser override | count={total} types={parsed_types}"
            )
            return total, parsed_types
        llm_count = self.reconcile_requested_count(ts_count, ts_types)
        if parsed_count > 0:
            logger.info(
                f"Query count parser overall | count={parsed_count} llm_count={llm_count}"
            )
            # Overall N with no typed quantities: do not keep LLM-invented types.
            return parsed_count, []
        return llm_count, ts_types or []

    def map_prompts_for_type(self, test_type, scenarios, ctx):
        """Prompt mapping for a single test type."""
        router = ctx["router"]
        batched_payloads = self.create_type_batches({test_type: scenarios}, batch_size=5)
        if ctx.get("limit_first_batch") and batched_payloads:
            batched_payloads = batched_payloads[:1]

        retrieved = ctx.get("retrieved_info") or ""
        grounding = self._web_search_grounding_prefix(ctx).strip()
        if grounding:
            retrieved = f"{grounding}\n\n{retrieved}"
        mapping_kwargs = {
            "retrieved_content": retrieved,
            "image_content": self.image_content or "",
            "is_image": self.is_image,
            "file_content": self.file_content or "",
            "is_file": self.is_file,
            "end_to_end_flow": ctx.get("end_to_end_flow"),
            "is_video": self.is_video,
            "is_jira": self.is_jira,
            "is_figma": self.is_figma,
            "all_flow_summary": ctx.get("flow_summary") or "",
            "image_chunks_figma": ctx.get("retrieved_info_text") or "",
            "image_names": ctx.get("selected_image_names") or "",
        }

        prompt_batches = []
        platform = (self.prompt_type or "").lower()
        for batch in batched_payloads:
            if platform == "web":
                prompt_payload = router.build_batch_prompt_web(batch=batch, **mapping_kwargs)
            elif platform == "android":
                prompt_payload = router.build_batch_prompt_mobile(batch=batch, **mapping_kwargs)
            elif platform == "ios":
                prompt_payload = router.build_batch_prompt_ios(batch=batch, **mapping_kwargs)
            else:
                logger.warning(
                    f"Unknown prompt_type '{self.prompt_type}' — skipping {test_type} mapping"
                )
                continue
            prompt_batches.append(prompt_payload)
        return prompt_batches

    def _build_batch_response_format(self, prompt_batch, serviceProvider):
        response_format = {"type": "json_schema"}
        if serviceProvider not in ["DefaultFireFlink", "Groq", "OpenAi"]:
            return response_format

        from genson import SchemaBuilder

        builder = SchemaBuilder()
        builder.add_object(json.loads(prompt_batch["json_template"]))
        generated_schema = builder.to_schema()
        generated_schema.pop("$schema", None)
        generated_schema = _add_additional_properties_false(generated_schema)
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "schema_name",
                "strict": True,
                "schema": generated_schema,
            },
        }

    async def execute_prompt_batch(self, prompt_batch, ctx):
        """LLM call for one mapped prompt batch."""
        serviceProvider = ctx["serviceProvider"]
        input_tokens = 0
        output_tokens = 0
        response_format = self._build_batch_response_format(prompt_batch, serviceProvider)
        try:
            response, input_tokens, output_tokens = await LLMClient.generate_async(
                serviceProvider=serviceProvider,
                model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else ctx["model"],
                apiKey=ctx["apiKey"],
                sa_info=ctx["sa_info"],
                resourceId=self.resourceId,
                resource=self.resource,
                system_prompt=prompt_batch["system_prompt"],
                user_prompt=prompt_batch["user_prompt"],
                temperature=0.4,
                response_format=response_format,
                return_usage=True,
                max_tokens=65000,
                unique_id=self.unique_id,
                mongoCollectionName=ctx["momgo_license_id"],
            )
            logger.info(
                f"response Generated successfully | Type:{prompt_batch.get('test_type')} "
                f"| Batch:{prompt_batch.get('batch_number')}"
            )
            return {
                "success": True,
                "test_type": prompt_batch["test_type"],
                "batch_number": prompt_batch["batch_number"],
                "response": response,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        except (GenerationCancelled, asyncio.CancelledError):
            raise
        except Exception as e:
            logger.error(
                f"Batch {prompt_batch.get('batch_number')} | Type:{prompt_batch.get('test_type')} failed: {e}"
            )
            return {
                "success": False,
                "test_type": prompt_batch.get("test_type"),
                "batch_number": prompt_batch.get("batch_number"),
                "response": None,
                "error": str(e),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

    async def _guarded_execute(self, prompt_batch, ctx):
        async with ctx["semaphore"]:
            return await self.execute_prompt_batch(prompt_batch, ctx)

    def _cancel_sibling_pipelines(self, ctx):
        _cancel_pending_tasks((ctx.get("type_tasks") or {}).values())

    async def _process_type_batch_result(self, result, ctx, batch_tasks):
        """Correct, persist, and record one successful LLM batch for a type."""
        return_generated_payload = ctx["return_generated_payload"]
        ctx["batch_results"].append(result)

        if not ctx["first_batch_logged"] and result.get("success"):
            ctx["first_batch_logged"] = True
            duration_first_batch = time.time() - ctx["all_start"]
            logger.info(
                f"TIMING | First batch of test cases generated by LLM "
                f"(Batch {result.get('batch_number')} | Type: {result.get('test_type')}) "
                f"| Duration: {duration_first_batch:.3f}s"
            )

        if not result.get("success"):
            logger.error(
                f"Batch {result.get('batch_number')} failed: {result.get('error')}"
            )
            return None

        result = self._apply_type_quota(result, ctx)
        test_type = result["test_type"]
        prefix = PREFIX_MAP.get(test_type, "TC")
        response_data = _response_as_dict(result.get("response"))
        if not response_data.get("Test Cases"):
            logger.info(
                f"{test_type} batch {result.get('batch_number')} dropped — type quota already filled"
            )
            return None

        if not return_generated_payload:
            for tc in response_data.get("Test Cases", []) or []:
                if not isinstance(tc, dict):
                    continue
                test_case_id = f"{prefix}-{ctx['idCounter'][test_type]:03d}"
                ctx["idCounter"][test_type] += 1
                tc_name = (
                    tc.get("Test Case Name")
                    or tc.get("testCaseName")
                    or tc.get("name")
                    or tc.get("title")
                    or ""
                )
                tc_desc = tc.get("Description") or tc.get("description") or ""
                if test_type in ctx["followUpData"]:
                    ctx["followUpData"][test_type][test_case_id] = (
                        f"Test Case Name: {tc_name} | Description: {tc_desc}"
                    )

            try:
                if not self.session_name:
                    summary = response_data.get("summary")
                    if summary:
                        self.session_name = summary
                        logger.info("UpdateSessionName Called (fire-and-forget)")
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            self.update_session_name,
                            ctx["momgo_license_id"],
                            self.unique_id,
                            self.session_id,
                            self.prompt_id,
                            self.count,
                            self.session_name,
                        )
            except Exception as e:
                logger.info(f"UpdatingSessionName Failed : {e}")

        current_batch_corrected = None
        try:
            logger.info(
                f"Processing Batch {result.get('batch_number')} | Type:{result.get('test_type')}"
            )
            if return_generated_payload:
                ctx["state"] = self.set_return_payload_state(
                    ctx["state"], result.get("response", {})
                )
            else:
                state, input_tokens, output_tokens, current_batch_corrected = await process_llm_results(
                    [result],
                    ctx["counter_ref"],
                    ctx["counter_lock"],
                    ctx["state"],
                    self.key_corrector,
                    self.TopLevelModel,
                    self.prompt_type,
                )
                ctx["state"] = state
                ctx["token_totals"][0] += input_tokens
                ctx["token_totals"][1] += output_tokens
        except Exception as e:
            logger.exception(
                f"Processing failed for batch {result.get('batch_number')} | Type:{result.get('test_type')}: {e}"
            )
            return None

        if return_generated_payload:
            self._total_testcase_count = 1
            self._total_input_tokens = ctx["token_totals"][0] + result.get("input_tokens", 0)
            self._total_output_tokens = ctx["token_totals"][1] + result.get("output_tokens", 0)
            logger.info(
                f"MTC Generation ATC PipeLine | sourceOfData: {ctx['source_of_data']} | "
                f"promptID: {self.prompt_id} | testCaseCount: {self._total_testcase_count} | "
                f"totalInputToken: {self._total_input_tokens} | "
                f"totalOutputToken: {self._total_output_tokens} | "
                f"totalToken: {self._total_input_tokens + self._total_output_tokens} | "
                f"PromptType: {self.prompt_type} | UserQUery: {self.user_input}"
            )
            ctx["early_payload"] = self.build_generated_mtc_payload(ctx["state"])
            _cancel_pending_tasks(batch_tasks)
            self._cancel_sibling_pipelines(ctx)
            return "early_payload"

        if is_cancelled(self.unique_id):
            ctx["generation_was_cancelled"] = True
            _cancel_pending_tasks(batch_tasks)
            self._cancel_sibling_pipelines(ctx)
            return "cancelled"

        if not return_generated_payload:
            try:
                task = asyncio.create_task(
                    process_llm_response(
                        response=current_batch_corrected,
                        unique_id=self.unique_id,
                        template=self.original_template,
                        license_id=self.license_id,
                        session_id=self.session_id,
                        session_name=self.session_name,
                        project_id=self.project_id,
                        prompt_id=self.prompt_id,
                        count=self.count,
                        script_type=self.script_type,
                        input_type=self.input_type,
                        template_id=self.template_id,
                        is_modified=self.is_modified,
                        mongoCollectionName=ctx["momgo_license_id"],
                        request_time_for_storing_1_tc_in_MD=ctx["request_time_for_storing_1_tc_in_MD"],
                        branch_id=self.branch_id,
                    )
                )
                ctx["processing_tasks"].append(task)
            except Exception:
                logger.exception(
                    f"DB task creation failed for batch {result.get('batch_number')} | Type:{result.get('test_type')}"
                )
            logger.info(
                f"Batch {result.get('batch_number')}| Type:{result.get('test_type')} processed and sent to DB"
            )
        return None

    def _extract_response_test_cases(self, response):
        data = _response_as_dict(response)
        if isinstance(response, list):
            return [tc for tc in response if isinstance(tc, dict)], {"Test Cases": response}
        for key in ("Test Cases", "testCases", "testcases", "TestCases", "manual_testcase", "manual_testcases"):
            raw = data.get(key)
            if isinstance(raw, list) and raw:
                cases = [tc for tc in raw if isinstance(tc, dict)]
                if cases:
                    data["Test Cases"] = cases
                    return cases, data
        return [], data

    def _apply_type_quota(self, result, ctx):
        """Keep at most `type_quota[type]` persisted TCs so 1 scenario cannot inflate the user count."""
        test_type = result.get("test_type")
        quota = (ctx.get("type_quota") or {}).get(test_type) or 0
        if quota <= 0 or not test_type:
            return result

        stored = ctx.setdefault("type_tc_stored", {t: 0 for t in CANONICAL_TYPES})
        already = stored.get(test_type, 0)
        remaining = quota - already
        test_cases, response = self._extract_response_test_cases(result.get("response"))

        if remaining <= 0:
            response["Test Cases"] = []
            result["response"] = response
            return result

        if len(test_cases) > remaining:
            logger.info(
                f"{test_type} TC overshoot: LLM returned {len(test_cases)}, "
                f"keeping {remaining} (quota={quota}, already={already})"
            )
            test_cases = test_cases[:remaining]

        response["Test Cases"] = test_cases
        result["response"] = response
        stored[test_type] = already + len(test_cases)
        return result

    def split_type_quota(self, ts_count, ts_types, return_generated_payload=False):
        """Assign per-type quotas. Unspecified N stays on functional; typed counts keep their mix."""
        requested = self.normalize_requested_types(ts_types)
        per_type = self.per_type_requested_counts(ts_types)
        stage1_all = ["functional", "edge", "integration"]
        want_e2e = not requested or "e2e" in requested
        stage1 = [t for t in stage1_all if not requested or t in requested]
        quota = {t: 0 for t in CANONICAL_TYPES}

        if return_generated_payload:
            pick = stage1[0] if stage1 else "functional"
            quota[pick] = 1
            return quota, [pick], False

        if per_type:
            for test_type, n in per_type.items():
                quota[test_type] = min(max(int(n), 0), 100)
            stage1 = [t for t in stage1_all if quota[t] > 0]
            run_e2e = quota["e2e"] > 0
            return quota, stage1, run_e2e

        n = int(ts_count or 0)
        if not stage1 and want_e2e:
            quota["e2e"] = n
            return quota, [], True

        if n <= 0:
            return quota, stage1, want_e2e

        # User asked for N test cases with no type: keep all N on functional.
        # Splitting across edge/integration/e2e often yields empty image/video scenarios
        # and the stored total falls short of N.
        if not requested:
            quota["functional"] = min(n, 100)
            return quota, ["functional"], False

        e2e_n = 0
        if want_e2e and n >= 4:
            e2e_n = max(1, n // 5)
        rest = n - e2e_n
        quota["e2e"] = e2e_n

        if stage1:
            base, extra = divmod(rest, len(stage1))
            for i, test_type in enumerate(stage1):
                quota[test_type] = base + (1 if i < extra else 0)
        elif want_e2e:
            quota["e2e"] = n

        return quota, stage1, want_e2e and (quota["e2e"] > 0 or n <= 0)

    def _web_search_grounding_prefix(self, ctx):
        if (ctx or {}).get("source_of_data") != "WebSearch":
            return ""
        return """
### WEB SEARCH GROUNDING (MANDATORY)
DOCUMENT CONTENT is public web-search snippets for the user query — not project documents.

Grounding rules:
1. Build scenarios only from modules, fields, and user flows named in DOCUMENT CONTENT.
2. Ignore off-topic snippets that do not match the user query (for example unrelated AWS products, IAP, or generic pages that are not the target app).
3. Do not invent UI, labels, or validations that are not in the snippets (do not assume email format errors, password-strength rules, account icons, or required-field messages unless a snippet describes them).
4. Valid / invalid / empty field coverage applies ONLY to fields explicitly present in the snippets.
5. Prefer concrete flows from the snippets (search, product, cart, checkout, etc.) over generic login templates.
"""

    def _apply_scenario_prefixes(self, system_prompt, ctx):
        extra = (self._web_search_grounding_prefix(ctx) or "") + (self._regenerate_scenario_prefix() or "")
        if extra:
            return extra + (system_prompt or "")
        return system_prompt

    def _regenerate_scenario_prefix(self):
        if getattr(self, "count", 1) == 1:
            return ""
        history = AgentMemoryOperation().get_session_history(self.prompt_id)
        return f"""
    ### MANDATORY DEDUPLICATION PROTOCOL
    You are strictly prohibited from generating scenarios that overlap with the existing test suite.

    #### 1. EXISTING TEST MEMORY (HISTORY)
    <history>
    {history}
    </history>

    #### 2. THE "LOGICAL IDENTITY" RULE
    A scenario is considered a DUPLICATE and MUST BE EXCLUDED if:
    - It validates the same field, business rule, or logic path as any entry in the <history>.
    - It merely changes the "frame structure," wording, or sentence order of an existing test.
    - It represents a "Happy Path" that is already covered, even if the new version is more detailed.

    #### 3. FRAME STRUCTURE NEUTRALITY
    Do not be fooled by formatting. If the "Actual Test Intent" (e.g., Validating Email Format) is already in the memory, do not generate it again using a different sequence or description.

    #### 4. TASK: FILL THE DELTA
    Your goal is to act as a **Coverage Gap Filler**.
    - Step A: Analyze <history> to find what logic is ALREADY covered.
    - Step B: Identify the "Delta" (the missing fields, negative states, or integration hops in the current Document Content).
    - Step C: Generate scenarios ONLY for the Delta identified in Step B.

    ---
    ### PROCEED TO SCENARIO GENERATION RULES:"""

    def _build_scenario_prompts(self, test_type, quota, ctx):
        """Build scenario LLM prompts for a single type using existing source-specific templates."""
        ts_types = [test_type]
        ts_count = quota or 0
        summary = self.chatContext
        user_input = self.user_input

        if self.is_video:
            video_result = ctx.get("video_route_result")
            end_to_end_flow = ctx.get("end_to_end_flow")
            selected_flow_data = ctx.get("selected_flow_data", [])
            all_flow_data = ctx.get("all_flow_data", [])

            if video_result is None:
                raise ValueError("Video route result is missing")   

            if video_result.end_to_end:
                system_prompt, user_prompt, response_format = (
                    Videoe2eScenarioSuggestion(
                        userInput=user_input,
                        End_to_End=end_to_end_flow,
                        promptType=self.prompt_type,
                        tsCount=ts_count,
                    )
                )

            elif video_result.module_name:
                system_prompt, user_prompt, response_format = (
                    VideoflowScenarioSuggestion(
                        userInput=user_input,
                        selected_flow=selected_flow_data,
                        End_to_End=end_to_end_flow,
                        promptType=self.prompt_type,
                        tsCount=ts_count,
                    )
                )

            elif video_result.all_flow:
                logger.info("Generating scenarios from all video flows")
                system_prompt, user_prompt, response_format = (
                    VideoallflowScenarioSuggestion(
                        userInput=user_input,
                        selected_flow=all_flow_data,
                        End_to_End=end_to_end_flow,
                        promptType=self.prompt_type,
                        tsCount=ts_count,
                    )
                )
            else:
                raise ValueError("Video route did not select a valid flow")

        elif self.is_image:
            image_user_input = ctx.get("image_user_input") or user_input
            system_prompt, user_prompt, response_format = ImageScenarioSuggestion(
                userInput=image_user_input,
                imageContent=self.image_content,
                promptType=self.prompt_type,
                tsCount=ts_count,
                tsTypes=ts_types,
                summary=summary,
            )
        elif self.is_file:
            system_prompt, user_prompt, response_format = FileScenarioSuggestion(
                user_input, self.file_content, self.prompt_type, ts_count, ts_types, summary=summary
            )
        elif self.is_jira:
            system_prompt, user_prompt, response_format = jira_scenario_generation(
                user_input, self.file_content, self.prompt_type, ts_count, ts_types, summary=summary
            )
        elif self.is_figma:
            system_prompt, user_prompt, response_format = FigmaScenarioSuggestion(
                user_input,
                ctx.get("flow_summary"),
                ctx.get("retrieved_info_text"),
                promptType=self.prompt_type,
                tsCount=ts_count,
                tsTypes=ts_types,
                summary=summary,
            )
        else:
            system_prompt, user_prompt, response_format = ScenarioSuggestion(
                user_input, ctx.get("retrieved_info"), self.prompt_type, ts_count, ts_types, summary=summary
            )

        return self._apply_scenario_prefixes(system_prompt, ctx), user_prompt, response_format

    def _extract_type_scenarios(self, payload, test_type):
        data = _response_as_dict(payload)
        raw = data.get(test_type)
        if not isinstance(raw, list):
            raw = data.get("scenarios")
        if not isinstance(raw, list):
            return []
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()]

    async def _add_tokens(self, ctx, input_tokens, output_tokens):
        async with ctx["process_lock"]:
            ctx["token_totals"][0] += input_tokens or 0
            ctx["token_totals"][1] += output_tokens or 0

    async def _llm_scenarios(self, system_prompt, user_prompt, response_format, ctx):
        serviceProvider = ctx["serviceProvider"]
        async with ctx["semaphore"]:
            response, input_tokens, output_tokens = await LLMClient.generate_async(
                serviceProvider=serviceProvider,
                model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else ctx["model"],
                apiKey=ctx["apiKey"],
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                sa_info=ctx["sa_info"],
                resourceId=self.resourceId,
                resource=self.resource,
                temperature=0.5,
                response_format=response_format,
                return_usage=True,
                max_tokens=65000,
                unique_id=self.unique_id,
                mongoCollectionName=ctx["momgo_license_id"],
            )
        await self._add_tokens(ctx, input_tokens, output_tokens)
        if isinstance(response, list) and response:
            response = response[0]
        return response

    async def generate_scenarios_for_type(self, test_type, ctx):
        """Scenario LLM for one type only, then trim/fallback to that type's quota."""
        quota = (ctx.get("type_quota") or {}).get(test_type, 0)
        logger.info(f"{test_type} scenario generation started | quota={quota or 'content-based'}")
        started = time.time()

        system_prompt, user_prompt, response_format = self._build_scenario_prompts(test_type, quota, ctx)
        scenarios = []
        for attempt in range(2):
            response = await self._llm_scenarios(system_prompt, user_prompt, response_format, ctx)
            scenarios = self._extract_type_scenarios(response, test_type)
            if scenarios:
                break
            logger.info(f"{test_type} scenario generation empty — retry {attempt + 1}")

        if quota > 0 and len(scenarios) > quota:
            logger.info(f"{test_type} overshoot {len(scenarios)} → trim to {quota}")
            scenarios = scenarios[:quota]

        if quota > 0 and len(scenarios) < quota:
            remaining = quota - len(scenarios)
            logger.info(f"{test_type} shortfall {len(scenarios)}/{quota} — fallback requesting {remaining}")
            current = {t: [] for t in CANONICAL_TYPES}
            current[test_type] = list(scenarios)
            ts_types = [test_type]
            if self.is_video:
                fb_system, fb_user, fb_format = FallBackScenarioSuggestionVideo(
                    userinput=self.user_input,
                    end_to_end_flow=ctx.get("end_to_end_flow"),
                    selected_flow_data=ctx.get("selected_flow_data", []),
                    all_flow_data=ctx.get("all_flow_data", []),
                    prompt_type=self.prompt_type,
                    ts_count=quota,
                    ts_types=ts_types,
                    ScenarioSuggestionResponse=current,
                    total_scenarios=len(scenarios),
                    remaining=remaining,
                )
            elif self.is_figma:
                fb_system, fb_user, fb_format = FallBackScenarioSuggestionFigma(
                    self.user_input,
                    ctx.get("flow_summary"),
                    ctx.get("retrieved_info_text"),
                    self.prompt_type,
                    quota,
                    ts_types,
                    current,
                    len(scenarios),
                    remaining,
                )
                
            else:
                fb_system, fb_user, fb_format = FallBackScenarioSuggestion(
                    self.user_input,
                    ctx.get("retrieved_info"),
                    self.image_content,
                    self.file_content,
                    self.prompt_type,
                    quota,
                    ts_types,
                    current,
                    len(scenarios),
                    remaining,
                    summary=self.chatContext,
                )
            fb_system = self._apply_scenario_prefixes(fb_system, ctx)
            fallback = await self._llm_scenarios(fb_system, fb_user, fb_format, ctx)
            extra = self._extract_type_scenarios(fallback, test_type)
            scenarios.extend(extra)
            if len(scenarios) > quota:
                scenarios = scenarios[:quota]

        logger.info(
            f"{test_type} scenarios generated | count={len(scenarios)} | Duration: {time.time() - started:.3f}s"
        )
        return scenarios

    def _e2e_coverage_block(self, ctx):
        lines = []
        for test_type in ("functional", "edge", "integration"):
            for scenario in ctx.get("generated_scenarios", {}).get(test_type) or []:
                lines.append(f"[{test_type} scenario] {scenario}")
            for tc_id, desc in (ctx.get("followUpData") or {}).get(test_type, {}).items():
                lines.append(f"[{test_type} TC {tc_id}] {desc}")
        return "\n".join(lines) or "None generated yet"

    async def generate_e2e_scenarios(self, ctx):
        """Stage-2 E2E scenarios composed from completed F/E/I scenarios and TCs."""
        quota = (ctx.get("type_quota") or {}).get("e2e", 0)
        logger.info(f"e2e scenario generation started | quota={quota or 'content-based'}")
        coverage = self._e2e_coverage_block(ctx)
        system_prompt, user_prompt, response_format = self._build_scenario_prompts("e2e", quota, ctx)
        system_prompt = f"""### E2E COMPOSITION RULES (STAGE 2)
Functional, Edge, and Integration coverage already exists. Do NOT repeat those atomic tests.
Use them as building blocks for full user journeys (entry → feature chain → business outcome).

### ALREADY COVERED
{coverage}

Generate ONLY the `e2e` array. Leave functional, edge, and integration as empty arrays.

{system_prompt}"""
        response = await self._llm_scenarios(system_prompt, user_prompt, response_format, ctx)
        scenarios = self._extract_type_scenarios(response, "e2e")
        if quota > 0:
            scenarios = scenarios[:quota]
        logger.info(f"e2e scenarios generated | count={len(scenarios)}")
        return scenarios

    async def run_full_type_pipeline(self, test_type, ctx):
        """One type, end-to-end: Scenario → Prompt Mapping → MTC LLM → MongoDB."""
        logger.info(f"{test_type} full pipeline started (scenario → MTC → Mongo)")
        if is_cancelled(self.unique_id):
            ctx["generation_was_cancelled"] = True
            return
        try:
            scenarios = await self.generate_scenarios_for_type(test_type, ctx)
        except (GenerationCancelled, asyncio.CancelledError):
            ctx["generation_was_cancelled"] = True
            self._cancel_sibling_pipelines(ctx)
            return
        async with ctx["process_lock"]:
            ctx.setdefault("generated_scenarios", {})[test_type] = scenarios
            # self._dump_scenarios(ctx)
        if not scenarios:
            logger.warning(f"{test_type} produced no scenarios — skip MTC")
            return
        await self.run_type_pipeline(test_type, scenarios, ctx)

    async def run_type_pipeline(self, test_type, scenarios, ctx):
        """One type: Prompt Mapping → LLM → MTC → MongoDB."""
        type_start = time.time()
        logger.info(f"{test_type} MTC pipeline started | scenarios={len(scenarios)}")

        try:
            if is_cancelled(self.unique_id):
                ctx["generation_was_cancelled"] = True
                return
            mapping_start = time.time()
            prompt_batches = self.map_prompts_for_type(test_type, scenarios, ctx)
            async with ctx["process_lock"]:
                ctx["prompt_batch_count"] += len(prompt_batches)
            logger.info(
                f"{test_type} PromptMapping completed | batches={len(prompt_batches)} | "
                f"Duration: {time.time() - mapping_start:.3f}s"
            )
        except GenerationCancelled:
            ctx["generation_was_cancelled"] = True
            self._cancel_sibling_pipelines(ctx)
            return
        except Exception as e:
            logger.error(f"{test_type} PromptMapping Failed: {e}")
            return

        if not prompt_batches:
            logger.warning(f"{test_type} pipeline skipped — no prompt batches")
            return

        batch_tasks = [
            asyncio.create_task(self._guarded_execute(batch, ctx))
            for batch in prompt_batches
        ]

        try:
            for future in asyncio.as_completed(batch_tasks):
                if ctx.get("early_payload") is not None or ctx.get("generation_was_cancelled"):
                    _cancel_pending_tasks(batch_tasks)
                    break
                if is_cancelled(self.unique_id):
                    ctx["generation_was_cancelled"] = True
                    _cancel_pending_tasks(batch_tasks)
                    self._cancel_sibling_pipelines(ctx)
                    break
                try:
                    result = await future
                    async with ctx["process_lock"]:
                        if ctx.get("early_payload") is not None or ctx.get("generation_was_cancelled"):
                            _cancel_pending_tasks(batch_tasks)
                            break
                        outcome = await self._process_type_batch_result(result, ctx, batch_tasks)
                        if outcome in {"early_payload", "cancelled"}:
                            break
                except asyncio.CancelledError:
                    ctx["generation_was_cancelled"] = True
                    break
                except GenerationCancelled:
                    ctx["generation_was_cancelled"] = True
                    _cancel_pending_tasks(batch_tasks)
                    self._cancel_sibling_pipelines(ctx)
                    break
                except Exception as e:
                    logger.exception(f"Unexpected error while processing a {test_type} future: {e}")
        finally:
            _cancel_pending_tasks(batch_tasks)
            if batch_tasks:
                await asyncio.gather(*batch_tasks, return_exceptions=True)

        logger.info(
            f"{test_type} pipeline completed | Duration: {time.time() - type_start:.3f}s"
        )

    def _collect_pipeline_exceptions(self, type_tasks, results, ctx):
        for test_type, result in zip(type_tasks.keys(), results):
            if isinstance(result, GenerationCancelled):
                ctx["generation_was_cancelled"] = True
            elif isinstance(result, asyncio.CancelledError):
                ctx["generation_was_cancelled"] = True
            elif isinstance(result, Exception):
                logger.error(f"{test_type} pipeline failed: {result}")
                raise result

    def _stored_tc_total(self, ctx):
        stored = ctx.get("type_tc_stored") or {}
        return sum(int(v or 0) for v in stored.values())

    def _dedupe_scenarios(self, existing, extra, remaining):
        seen = {item.strip().lower() for item in existing if isinstance(item, str) and item.strip()}
        out = []
        for item in extra or []:
            if not isinstance(item, str):
                continue
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item.strip())
            if len(out) >= remaining:
                break
        return out

    def _fill_type_candidates(self, ctx):
        stored = ctx.get("type_tc_stored") or {}
        generated = ctx.get("generated_scenarios") or {}
        quota = ctx.get("type_quota") or {}
        proven, unused, failed = [], [], []
        for test_type in CANONICAL_TYPES:
            has_output = int(stored.get(test_type) or 0) > 0 or bool(generated.get(test_type))
            if has_output:
                proven.append(test_type)
            elif int(quota.get(test_type) or 0) > 0:
                failed.append(test_type)
            else:
                unused.append(test_type)
        proven.sort(key=lambda t: (0 if t == "functional" else 1, -int(stored.get(t) or 0)))
        unused.sort(key=lambda t: 0 if t == "functional" else 1)
        failed.sort(key=lambda t: 0 if t == "functional" else 1)
        ordered = []
        for test_type in proven + unused + failed:
            if test_type not in ordered:
                ordered.append(test_type)
        return ordered

    def _pick_fill_type(self, ctx, exclude=None):
        skip = set(exclude or [])
        for test_type in self._fill_type_candidates(ctx):
            if test_type not in skip:
                return test_type
        return None

    async def _request_fill_scenarios(self, ctx, fill_type, remaining, existing):
        current = {t: [] for t in CANONICAL_TYPES}
        current[fill_type] = existing
        ts_types = [fill_type]
        if self.is_video:
            fb_system, fb_user, fb_format = FallBackScenarioSuggestionVideo(
                userinput=self.user_input,
                end_to_end_flow=ctx.get("end_to_end_flow"),
                selected_flow_data=ctx.get("selected_flow_data", []),
                all_flow_data=ctx.get("all_flow_data", []),
                prompt_type=self.prompt_type,
                ts_count=remaining,
                ts_types=ts_types,
                ScenarioSuggestionResponse=current,
                total_scenarios=len(existing),
                remaining=remaining,
            )
        elif self.is_figma:
            fb_system, fb_user, fb_format = FallBackScenarioSuggestionFigma(
                self.user_input,
                ctx.get("flow_summary"),
                ctx.get("retrieved_info_text"),
                self.prompt_type,
                remaining,
                ts_types,
                current,
                len(existing),
                remaining,
                summary=self.chatContext,
            )
        else:
            fb_system, fb_user, fb_format = FallBackScenarioSuggestion(
                self.user_input,
                ctx.get("retrieved_info"),
                self.image_content,
                self.file_content,
                self.prompt_type,
                remaining,
                ts_types,
                current,
                len(existing),
                remaining,
                summary=self.chatContext,
            )
        fb_system = self._apply_scenario_prefixes(fb_system, ctx)
        fallback = await self._llm_scenarios(fb_system, fb_user, fb_format, ctx)
        extra = self._dedupe_scenarios(
            existing, self._extract_type_scenarios(fallback, fill_type), remaining
        )
        if extra:
            return extra

        quota_ctx = dict(ctx.get("type_quota") or {})
        prev_quota = quota_ctx.get(fill_type, 0)
        ctx["type_quota"] = {**quota_ctx, fill_type: remaining}
        try:
            if fill_type == "e2e":
                more = await self.generate_e2e_scenarios(ctx)
            else:
                more = await self.generate_scenarios_for_type(fill_type, ctx)
        finally:
            quota_ctx[fill_type] = prev_quota
            ctx["type_quota"] = quota_ctx
        return self._dedupe_scenarios(existing, more, remaining)

    async def _enforce_exact_testcase_count(self, ctx):
        """When the user asked for N test cases, fill a remaining shortfall."""
        if ctx.get("return_generated_payload"):
            return
        try:
            ts_count = int(ctx.get("ts_count") or 0)
        except (TypeError, ValueError):
            ts_count = 0
        if ts_count <= 0:
            return
        if ctx.get("generation_was_cancelled") or ctx.get("early_payload") is not None:
            return
        if is_cancelled(self.unique_id):
            ctx["generation_was_cancelled"] = True
            return

        total = self._stored_tc_total(ctx)
        logger.info(f"Exact-count check | requested={ts_count} stored={total}")
        if total >= ts_count:
            if total > ts_count:
                logger.info(
                    f"Exact-count overshoot {total} > {ts_count} — per-type quota already capped persisted TCs"
                )
            return

        remaining = ts_count - total
        tried = set()
        while remaining > 0:
            if is_cancelled(self.unique_id):
                ctx["generation_was_cancelled"] = True
                return
            fill_type = self._pick_fill_type(ctx, exclude=tried)
            if not fill_type:
                logger.warning(
                    f"Exact-count fill exhausted types — stored {self._stored_tc_total(ctx)}/{ts_count}"
                )
                break
            tried.add(fill_type)
            quota = ctx.setdefault("type_quota", {t: 0 for t in CANONICAL_TYPES})
            already = int((ctx.get("type_tc_stored") or {}).get(fill_type, 0) or 0)
            quota[fill_type] = already + remaining
            ctx["type_quota"] = quota
            existing = list((ctx.get("generated_scenarios") or {}).get(fill_type) or [])
            logger.info(
                f"Exact-count shortfall {self._stored_tc_total(ctx)}/{ts_count} — filling {remaining} via {fill_type}"
            )
            extra = await self._request_fill_scenarios(ctx, fill_type, remaining, existing)
            if not extra:
                logger.warning(f"Exact-count fill produced no extra {fill_type} scenarios")
                continue
            generated = ctx.setdefault("generated_scenarios", {})
            generated[fill_type] = existing + extra
            # self._dump_scenarios(ctx)
            await self.run_type_pipeline(fill_type, extra, ctx)
            remaining = ts_count - self._stored_tc_total(ctx)

        logger.info(
            f"Exact-count after fill | requested={ts_count} stored={self._stored_tc_total(ctx)}"
        )

    # def _dump_scenarios(self, ctx):
    #     folder = ctx.get("output_folder")
    #     if folder:
    #         try:
    #             with open(os.path.join(folder, "5_Scenario_Generation.json"), "w", encoding="utf-8") as f:
    #                 json.dump(ctx.get("generated_scenarios") or {}, f, ensure_ascii=False, indent=4)
    #         except Exception as e:
    #             logger.warning(f"Failed to dump scenarios to output_folder: {e}")

    async def fan_out_type_pipelines(self, ctx):
        """Stage 1: F/E/I in parallel (scenario → MTC → Mongo). Stage 2: E2E after they finish."""
        ctx.setdefault("semaphore", asyncio.Semaphore(5))
        ctx.setdefault("process_lock", asyncio.Lock())
        ctx.setdefault("followUpData", {t: {} for t in CANONICAL_TYPES})
        ctx.setdefault("idCounter", {t: 1 for t in CANONICAL_TYPES})
        ctx.setdefault("processing_tasks", [])
        ctx.setdefault("batch_results", [])
        ctx.setdefault("generation_was_cancelled", False)
        ctx.setdefault("first_batch_logged", False)
        ctx.setdefault("early_payload", None)
        ctx.setdefault("prompt_batch_count", 0)
        ctx.setdefault("limit_first_batch", False)
        ctx.setdefault("generated_scenarios", {})
        ctx.setdefault("type_tc_stored", {t: 0 for t in CANONICAL_TYPES})

        if not ctx.get("return_generated_payload"):
            ctx["ts_count"], ctx["ts_types"] = self.merge_query_counts(
                getattr(self, "user_input", "") or "",
                ctx.get("ts_count") or 0,
                ctx.get("ts_types"),
            )
        quota, stage1, run_e2e = self.split_type_quota(
            ctx.get("ts_count") or 0,
            ctx.get("ts_types"),
            ctx.get("return_generated_payload"),
        )
        ctx["type_quota"] = quota
        if ctx.get("return_generated_payload") and not self.is_jira:
            ctx["limit_first_batch"] = True

        if ctx.get("check_cancel"):
            ctx["check_cancel"]()

        logger.info(
            f"Stage-1 type pipelines | types={stage1} | quota={quota} | e2e_after={run_e2e}"
        )

        if stage1:
            type_tasks = {
                test_type: asyncio.create_task(
                    self.run_full_type_pipeline(test_type, ctx),
                    name=f"mtc-{test_type}",
                )
                for test_type in stage1
            }
            ctx["type_tasks"] = type_tasks
            results = await asyncio.gather(*type_tasks.values(), return_exceptions=True)
            self._collect_pipeline_exceptions(type_tasks, results, ctx)

        if ctx.get("early_payload") is not None or ctx.get("generation_was_cancelled"):
            return ctx

        if run_e2e and not ctx.get("return_generated_payload"):
            if is_cancelled(self.unique_id):
                ctx["generation_was_cancelled"] = True
                return ctx
            logger.info("Stage-2 E2E pipeline starting (after functional / edge / integration)")
            try:
                e2e_scenarios = await self.generate_e2e_scenarios(ctx)
            except (GenerationCancelled, asyncio.CancelledError):
                ctx["generation_was_cancelled"] = True
                return ctx
            ctx["generated_scenarios"]["e2e"] = e2e_scenarios
            # self._dump_scenarios(ctx)
            if e2e_scenarios:
                await self.run_type_pipeline("e2e", e2e_scenarios, ctx)
            else:
                logger.warning("E2E produced no scenarios — skip E2E MTC")

        if ctx.get("early_payload") is not None or ctx.get("generation_was_cancelled"):
            return ctx

        try:
            await self._enforce_exact_testcase_count(ctx)
        except (GenerationCancelled, asyncio.CancelledError):
            ctx["generation_was_cancelled"] = True
        except Exception as e:
            logger.error(f"Exact-count enforcement failed: {e}")

        return ctx
