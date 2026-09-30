"""Main async test-case generation pipeline."""
from src.agents._shared import *  # noqa: F401,F403


class GenerateMixin:
    async def async_generate_test_cases(self,apiKey,serviceProvider,model,sa_info,state: State,request_time_for_storing_1_tc_in_MD,return_generated_payload=False):
        model=model
        momgo_license_id = f"optimize_{self.env}_{self.license_id}" if self.env else f"optimize_{self.license_id}"
        retrieved_info = "No relevant data found"
        toonPurpose = ""
        counter_ref = [1]
        counter_lock = asyncio.Lock()
        retrieved_info_text = ""
        flow_summary= ""
        selected_image_names=[]
        source_of_data = ("Image" if self.is_image else "Video" if self.is_video
                            else "File" if self.is_file else "Jira" if self.is_jira
                            else "Figma" if self.is_figma else "aiDataSource")

        register_job(
            unique_id=self.unique_id,
            prompt_id=self.prompt_id,
            session_id=self.session_id,
            task=asyncio.current_task(),
        )

        output_folder = "output_folder"
        os.makedirs(output_folder, exist_ok=True)


        async def _finalize_cancelled(follow_up=None):
            """Persist cancelled status with TC count, tokens, and follow-up."""
            try:
                mtc = get_manual_test_case()
                tc_count = getattr(self, "_total_testcase_count", 0) or 0
                input_tokens = getattr(self, "_total_input_tokens", 0) or 0
                output_tokens = getattr(self, "_total_output_tokens", 0) or 0
                self._follow_up = follow_up
                total_tokens = input_tokens + output_tokens
                mtc.save_prompt_db(
                    session_id=self.session_id,
                    unique_id=self.unique_id,
                    dateTime=self.dateTime,
                    session_name=self.session_name,
                    user_input=self.user_input,
                    license_id=self.license_id,
                    project_id=self.project_id,
                    prompt_id=self.prompt_id,
                    user_id=self.user_id,
                    count=self.count,
                    script_type=self.script_type,
                    input_type=self.input_type,
                    file_name=self.file_name,
                    file_content=self.file_content,
                    test_case_count=tc_count,
                    user_input_tokens=input_tokens,
                    total_output_tokens=output_tokens,
                    total_tokens_consumed=total_tokens,
                    apiKey=self.apikey,
                    serviceProvider=self.serviceProvider,
                    model=self.model,
                    images_path=self.images_path,
                    image_content=self.image_content,
                    video_name=self.video_name,
                    image_data=None,
                    prompt_type=self.prompt_type,
                    mongoCollectionName=momgo_license_id,
                    branch_id=self.branch_id,
                    error_message=None,
                    follow_up=follow_up,
                    generation_status="cancelled",
                )
                self._cancel_finalized = True
                logger.info(
                    f"Cancelled generation finalized | prompt_id={self.prompt_id} "
                    f"test_case_count={tc_count} tokens={total_tokens} "
                    f"follow_up={'yes' if follow_up else 'no'}"
                )
            except Exception as finalize_err:
                logger.error(f"Failed to finalize cancelled generation: {finalize_err}", exc_info=True)
                try:
                    mtc = get_manual_test_case()
                    mtc.mark_generation_cancelled(
                        unique_id=self.unique_id,
                        license_id=momgo_license_id,
                        input_tokens=getattr(self, "_total_input_tokens", 0) or 0,
                        output_tokens=getattr(self, "_total_output_tokens", 0) or 0,
                        test_case_count=getattr(self, "_total_testcase_count", 0) or 0,
                        follow_up=follow_up,
                    )
                    self._cancel_finalized = True
                except Exception:
                    pass
            raise GenerationCancelled(unique_id=self.unique_id)

        async def _build_follow_up_for_partial(
            followUpData,
            ts_count,
            generated_tc_count,
            selected_files,
            purpose_info,
            retrieved_info,
            flow_output_summary,
            total_input_tokens,
            total_output_tokens,
        ):
            """Generate follow-up questions from whatever testcases were produced before cancel."""
            followUp = None
            if return_generated_payload or generated_tc_count <= 0:
                return followUp, total_input_tokens, total_output_tokens
            try:
                logger.info(
                    f"Follow-up after terminate | generatedTcCount={generated_tc_count} "
                    f"prompt_id={self.prompt_id}"
                )
                if self.is_jira or self.is_file or self.is_image or self.is_video or self.is_figma:
                    if self.is_image:
                        Content = self.image_content
                        attachmentType = "image"
                    elif self.is_file:
                        Content = self.file_content
                        attachmentType = "file"
                    elif self.is_video:
                        Content = video_followup_content
                        attachmentType = "video"
                    elif self.is_jira:
                        Content = self.file_content
                        attachmentType = "jira"
                    else:
                        Content = flow_output_summary
                        attachmentType = "figma"
                    systemPrompt, userPrompt = attachmentFollowUpPrompt(
                        self.chatContext,
                        ExtractedContent=Content,
                        followUpData=followUpData,
                        userQuery=self.user_input,
                        userSpecifedTcCount=ts_count,
                        generatedTcCount=generated_tc_count,
                        type=attachmentType,
                    )
                else:
                    purpose = self.chosenFiles(filenames=selected_files, data=purpose_info)
                    systemPrompt, userPrompt = followUpPrompt(
                        self.chatContext,
                        filesInfo=purpose,
                        retrievedContent=retrieved_info,
                        followUpData=followUpData,
                        userQuery=self.user_input,
                        userSpecifedTcCount=ts_count,
                        generatedTcCount=generated_tc_count,
                    )
                followUpResponse, inputTokens, outputTokens = await LLMClient.generate_async(
                    serviceProvider=serviceProvider,
                    model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                    apiKey=apiKey,
                    system_prompt=systemPrompt,
                    user_prompt=userPrompt,
                    sa_info=sa_info,
                    resourceId=self.resourceId,
                    resource=self.resource,
                    temperature=0.1,
                    response_format=None,
                    return_usage=True,
                    max_tokens=65000,
                    unique_id=self.unique_id,
                    mongoCollectionName=momgo_license_id,
                )
                # followUpResponse = json.loads(followUpResponse)

                try:
                    # Case 1: Already valid JSON
                    followUpResponse = json.loads(followUpResponse)
                    logger.info("FollowUpResponse Parsed Successfully")

                except json.JSONDecodeError:
                    logger.info("FollowUpResponse Failed Parsed | Trying with Rrgex Match")
                    # Case 2: Model returned text + JSON
                    match = re.search(r'(\[[\s\S]*\])\s*$', followUpResponse)

                    if match:
                        followUpResponse = json.loads(match.group(1))
                        logger.info("FollowUpResponse Patten Matched Successfully")
                    else:
                        logger.error(
                            "Unable to extract JSON from followUpResponse: %r",
                            followUpResponse
                        )
                        followUpResponse = None
                followUp = "Manual test cases generated successfully. What can I do next?\n" + "\n".join(
                    f"{i}. {item}" for i, item in enumerate(followUpResponse, start=1)
                )
                total_input_tokens += inputTokens
                total_output_tokens += outputTokens
            except Exception as follow_up_err:
                logger.error(f"Follow-up generation after terminate failed: {follow_up_err}", exc_info=True)
            return followUp, total_input_tokens, total_output_tokens

        def _check_cancel_with_mongo():
            """Memory check + sync from Mongo for multi-worker terminate."""
            check_cancelled(self.unique_id)
            try:
                mtc = get_manual_test_case()
                col = mtc.load_collection_for_user_prompt(license_id=momgo_license_id)
                doc = col.find_one({"_id": self.unique_id}, {"generation_status": 1})
                if doc:
                    mark_cancelled_from_mongo(self.unique_id, doc.get("generation_status"))
                    check_cancelled(self.unique_id)
            except GenerationCancelled:
                raise
            except Exception as sync_err:
                logger.debug(f"Cancel Mongo sync skipped: {sync_err}")

        #global summary fetching
        try:
            _check_cancel_with_mongo()
            total_input_tokens = 0
            total_output_tokens = 0
            toon_video_content=None
            total_tokens = 0
            toon_video_content=None
            followUp=None
            selected_files = []
            purpose_info=""
            if self.qdrant_client is not None:
                collections_response = await self.qdrant_client.get_collections()
                collections = collections_response.collections
                existing_collections = [c.name for c in collections]
            else:
                existing_collections = []
            try:
                if self.is_file:
                    total_input_tokens= self.file_content.get("input_token", 0)
                    total_output_tokens=self.file_content.get("output_token", 0)
                    self.file_content=self.file_content.get("file_content", 0)
                if self.is_image:
                    total_input_tokens+=self.Image_Input_token
                    total_output_tokens+=self.Image_Output_token
                if self.is_jira:
                    if self.Jira_Input_token:
                        total_input_tokens += self.Jira_Input_token
                    if self.Jira_Output_token:
                        total_output_tokens += self.Jira_Output_token
                    
                if not (self.is_jira or self.is_image or self.is_file or self.is_video or self.is_figma):
                    if self.collection_name not in existing_collections:
                        logger.info(f"⚠️ Collection {self.collection_name} does not exist.")
                        retrieved_info = await web_search_fallback_or_raise(
                            reason="missing_collection",
                            user_input=self.user_input,
                        )
                        source_of_data = "WebSearch"
                    else:
                        #------MASTER SUMMARY RETRIEVAL---------
                        summary_filter = Filter(
                            must=[
                                FieldCondition(
                                    key="chunk_index",
                                    match=MatchValue(value=-1)
                                )
                            ]
                        )
                        results = None
                        for attempt in range(3):
                            try:
                                results, next_page = await self.qdrant_client.scroll(
                                    collection_name=self.collection_name,
                                    scroll_filter=summary_filter,
                                    limit=1
                                )
                                break
                            except Exception as scroll_err:
                                logger.warning(f"Qdrant scroll attempt {attempt + 1} failed: {scroll_err}")
                                if attempt == 2:
                                    raise scroll_err
                                await asyncio.sleep(0.5)
                        if results:
                            logger.info("MasterSummary found")
                            retrieved_info = results[0].payload
                            purpose_info = {
                            "files": [
                                {
                                    "fileName": file.get("fileName"),
                                    "purpose": file.get("purpose")
                                }
                                for file in retrieved_info.get("files", [])
                            ]
                        }
                            toonPurpose = encode(purpose_info)

                        else:
                            logger.warning("No MasterSummary found")
                                
                        result = None
                        ragResult = None
                        ScenarioSuggestionResponse = None
                        prompt_batches = []
                            #-------DATA SELECTOR----------
                        try:
                            dataselector_start_time = time.time()
                            systemPrompt,userPrompt,responseFormat=dataSelectorPrompt(self.user_input,toonPurpose, self.chatContext)
                    
                            dataSelectorResponse,input_tokens, output_tokens=await LLMClient.generate_async(serviceProvider,
                                                                                        model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                        apiKey=apiKey,
                                                                                        system_prompt=systemPrompt, 
                                                                                        user_prompt=userPrompt,
                                                                                        sa_info=sa_info,
                                                                                        resource=self.resource,
                                                                                        resourceId=self.resourceId,
                                                                                        temperature=0.3,
                                                                                        response_format=responseFormat,
                                                                                        return_usage=True,
                                                                                        max_tokens=2048,  # DataSelector only returns small structured JSON
                                                                                        unique_id=self.unique_id,
                                                                                        mongoCollectionName=momgo_license_id
                                                                                        )
                            if serviceProvider:
                                total_input_tokens+=input_tokens
                                total_output_tokens+=output_tokens
                                
                            if isinstance(dataSelectorResponse, list) and len(dataSelectorResponse) > 0:
                                dataSelectorResponse = dataSelectorResponse[0]
                                
                            if isinstance(dataSelectorResponse, str):
                                result = TestCaseResponse.model_validate_json(dataSelectorResponse)
                            else:
                                result = TestCaseResponse.model_validate(dataSelectorResponse)
                            

                            ts_count= result.count
                            ts_types=', '.join(result.testCaseType) if result.testCaseType else 'all types'
                            
                        
                            logger.info("DataSelector selected test suites.")
                            dataselector_end_time = time.time()  # end timestamp
                            dataSelector_duration = dataselector_end_time - dataselector_start_time
                            dataselector_time_json={
                               "title": "Time taken to dataselector",
                                "duration_in_seconds": dataSelector_duration

                            }
                            # with open(os.path.join(output_folder, "1_DataSelector.json"), "w", encoding="utf-8") as f:
                            #     json.dump(dataSelectorResponse, f, ensure_ascii=False, indent=4)
                            # with open(os.path.join(output_folder, "Time_taken_by_all.json"), "a", encoding="utf-8") as f:
                            #     json.dump(dataselector_time_json,f, ensure_ascii=False, indent=4) 
                            logging.info(f"DataSelector Timing | Duration: {dataSelector_duration:.3f}s")


                        except Exception as e:
                            logger.error(f"DataSelector Failed:{e}")
                            raise
                                    
                            #-------PROMPT RECONSTRUCTION----------
                            
                        if not result or not getattr(result, "filesName", None):
                            logger.warning("Query is out of scope — skipping RAG query generation.")
                            retrieved_info = await web_search_fallback_or_raise(
                                reason="out_of_scope",
                                user_input=self.user_input,
                            )
                            source_of_data = "WebSearch"
                        else:
                            try:
                                prompt_reconstrcutor_start_time = time.time()
                                # selected_files = list(getattr(result, "filesName", []) or [])
                                selected_files = result.filesName
                                promptReconstructor_info = {
                                    "files": [
                                        {
                                            "fileName": file.get("fileName"),
                                            "full_description": file.get("full_description")
                                        }
                                        for file in retrieved_info.get("files", [])
                                        if file.get("fileName") in selected_files
                                    ]
                                }

                                toonDescription=encode(promptReconstructor_info)
                                systemPrompt, userPrompt, responseFormat = promptReconstructor(
                                    user_input=self.user_input,
                                    toonDescription=toonDescription,
                                    selected_files=selected_files,     
                                    test_case_types= ts_types,
                                    summary=self.chatContext
                                )
                                promptReconstructorResponse,input_tokens, output_tokens=await LLMClient.generate_async(serviceProvider=serviceProvider,
                                                                                        model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                        apiKey=apiKey,
                                                                                        system_prompt=systemPrompt, 
                                                                                        user_prompt=userPrompt,
                                                                                        sa_info=sa_info,
                                                                                        resourceId=self.resourceId,
                                                                                        resource=self.resource,
                                                                                        temperature=0.3,
                                                                                        response_format=responseFormat,
                                                                                        return_usage=True,
                                                                                        max_tokens=4096,  # PromptReconstructor: RAG queries must finish as valid JSON
                                                                                        unique_id=self.unique_id,
                                                                                        mongoCollectionName=momgo_license_id
                                                                                        )
                                if serviceProvider:
                                    total_input_tokens+=input_tokens
                                    total_output_tokens+=output_tokens
                                
                                if isinstance(promptReconstructorResponse, str):
                                    ragResult = RAGQueryResponse.model_validate_json(promptReconstructorResponse)

                                elif isinstance(RAGQueryResponse, list) and len(RAGQueryResponse) > 0:
                                    ragResult = RAGQueryResponse[0]
                                
                                else:
                                    ragResult = RAGQueryResponse.model_validate(promptReconstructorResponse)
                                if ragResult is None:
                                    logger.info("RAGQueryResponse validation returned None")
                                    ragResult=self.user_input

                                    # ragResult = RAGQueryResponse.model_validate(promptReconstructorResponse)
                                prompt_reconstrcutor_end_time = time.time()  # end timestamp
                                prompt_reconstrcutor_duration = prompt_reconstrcutor_end_time - prompt_reconstrcutor_start_time
                                prompt_reconstrcutor_time_json={
                                   "title": "Time taken to prompt reconstructor",
                                    "duration_in_seconds": prompt_reconstrcutor_duration
                                }
                                # with open(os.path.join(output_folder, "2_PromptReconstructor.json"), "w", encoding="utf-8") as f:
                                #     json.dump(promptReconstructorResponse, f, ensure_ascii=False, indent=4)
                                # with open(os.path.join(output_folder, "Time_taken_by_all.json"), "a", encoding="utf-8") as f:
                                #     json.dump(prompt_reconstrcutor_time_json,f, ensure_ascii=False, indent=4) 
                                logger.info(f"PromptReconstrution Timing | Duration: {prompt_reconstrcutor_duration:.3f}s")

                            except Exception as e:
                                logger.error(f"PromptReconstruction Failed:{e}")
                                raise

                                #-------RETRIEVAL----------
                            try:
                                start_time = time.time()
                                final_chunks = []
                                scored_hits: list[float] = []
                                seen_modules = set()
                                seen_chunks = set()  # ← NEW
                                file_chunks_map = {}

                                # ---- Launch TestCaseCount in PARALLEL with Retrieval ----
                                if not (return_generated_payload or getattr(self, 'return_generated_payload', False)):
                                    _tc_sys, _tc_user, _tc_fmt = Test_Count_Prompt(self.user_input, serviceProvider)
                                    _test_count_task = asyncio.create_task(
                                        LLMClient.generate_async(
                                            serviceProvider=serviceProvider,
                                            model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                            apiKey=apiKey,
                                            system_prompt=_tc_sys,
                                            user_prompt=_tc_user,
                                            sa_info=sa_info,
                                            resourceId=self.resourceId,
                                            resource=self.resource,
                                            temperature=0.1,
                                            response_format=_tc_fmt,
                                            return_usage=True,
                                            max_tokens=2048,
                                            unique_id=self.unique_id,
                                            mongoCollectionName=momgo_license_id
                                        )
                                    )
                                    logger.info("TestCaseCount task launched in parallel with Retrieval")
                                # ----------------------------------------------------------

                                logger.info("Moving Towards Retrieving part ...")

                                # Step 1: Flatten all RAG queries while preserving file association
                                flattened_queries = []
                                for file_name, query_list in ragResult.rag_queries.items():
                                    file_chunks_map[file_name] = []
                                    for query in query_list:
                                        flattened_queries.append({
                                            "file_name": file_name,
                                            "query": query
                                        })

                                if flattened_queries:
                                    # Step 2: Batch-embed all queries in a single encode() call
                                    embed_start = time.time()
                                    queries_to_embed = [item["query"] for item in flattened_queries]
                                    unique_queries = list(dict.fromkeys(queries_to_embed))
                                    unique_vectors = await asyncio.to_thread(
                                        self.embeddings.embed_documents, unique_queries
                                    )
                                    query_to_vec = dict(zip(unique_queries, unique_vectors))
                                    vectors = [query_to_vec[q] for q in queries_to_embed]
                                    logger.info(f"Retrieval | Batch-embedded {len(unique_queries)} unique queries (from {len(queries_to_embed)} total) in {time.time() - embed_start:.3f}s")

                                    # Step 3: Build one QueryRequest per query
                                    batch_requests = [
                                        models.QueryRequest(
                                            query=vectors[i],
                                            filter=models.Filter(
                                                must=[
                                                    models.FieldCondition(
                                                        key="fileName",
                                                        match=models.MatchValue(value=item["file_name"])
                                                    )
                                                ],
                                                must_not=[
                                                    models.FieldCondition(
                                                        key="chunk_index",
                                                        match=models.MatchValue(value=-1)
                                                    )
                                                ]
                                            ),
                                            limit=2,
                                            with_payload=True
                                            )
                                        for i, item in enumerate(flattened_queries)
                                    ]

                                    # Step 4: Single batch request with retry logic for transient disconnects
                                    qdrant_start = time.time()
                                    max_qdrant_retries = 3
                                    batch_responses = None
                                    for attempt in range(max_qdrant_retries):
                                        try:
                                            batch_responses = await self.qdrant_client.query_batch_points(
                                                collection_name=self.collection_name,
                                                requests=batch_requests
                                            )
                                            break
                                        except Exception as qdrant_err:
                                            logger.warning(f"Qdrant batch query attempt {attempt + 1} failed: {qdrant_err}")
                                            if attempt == max_qdrant_retries - 1:
                                                raise qdrant_err
                                            await asyncio.sleep(0.5)
                                    logger.info(f"Retrieval | Qdrant batch query took {time.time() - qdrant_start:.3f}s")

                                    # Step 5-8: Process responses with identical dedup & module-uniqueness logic
                                    for item, response in zip(flattened_queries, batch_responses):
                                        file_name = item["file_name"]
                                        for hit in response.points:
                                            if hit.score is not None:
                                                scored_hits.append(hit.score)
                                            payload = hit.payload
                                            m_name = payload.get("moduleName") or payload.get("module_name")
                                            chunk_idx = payload.get("chunk_index")

                                            unique_key = (file_name, chunk_idx)

                                            if unique_key in seen_chunks:
                                                continue

                                            # Optional: also enforce module uniqueness
                                            if m_name and m_name in seen_modules:
                                                continue

                                            seen_chunks.add(unique_key)
                                            if m_name:
                                                seen_modules.add(m_name)

                                            file_chunks_map[file_name].append(payload)

                                for file_name, chunks in file_chunks_map.items():
                                    chunks.sort(key=lambda x: x.get('chunk_index', 0))
                                    final_chunks.extend(chunks)

                                rag_queries_flat = [
                                    query
                                    for query_list in ragResult.rag_queries.values()
                                    for query in query_list
                                ]

                                if not final_chunks:
                                    logger.warning(
                                        "No retrieved chunks found | high_score_hits=%s",
                                        sum(1 for s in scored_hits if s is not None and s >= 0),
                                    )
                                    retrieved_info = await web_search_fallback_or_raise(
                                        reason="empty_chunks",
                                        user_input=self.user_input,
                                        rag_queries=rag_queries_flat,
                                    )
                                    source_of_data = "WebSearch"
                                elif not qdrant_is_sufficient(scored_hits):
                                    logger.warning(
                                        "Qdrant retrieval insufficient | high_score_hits=%s scores=%s",
                                        sum(1 for s in scored_hits if s is not None),
                                        scored_hits[:10],
                                    )
                                    retrieved_info = await web_search_fallback_or_raise(
                                        reason="low_score",
                                        user_input=self.user_input,
                                        rag_queries=rag_queries_flat,
                                    )
                                    source_of_data = "WebSearch"
                                else:
                                    # Encode
                                    tooned_final_chunks = encode(final_chunks)
                                    end_time = time.time()
                                    duration = end_time - start_time
                                    logger.info(
                                        f"Retrieval Timing | Duration: {duration:.3f}s"
                                    )

                                    retrieved_info = tooned_final_chunks
                            except Exception as e:
                                logger.error(f"Retrieval Failed:{e}")
                                raise 
                            retrieval_end_time = time.time()  # end timestamp
                            retrieval_duration = retrieval_end_time - start_time
                            retrieval_time_json={
                                   "title": "Time taken to qdrant retrieval",
                                    "duration_in_seconds": retrieval_duration
                                }
                            # with open(os.path.join(output_folder, "3_Qdrant_Retrieval.txt"), "w", encoding="utf-8") as f:
                            #     f.write(retrieved_info)
                            # with open(os.path.join(output_folder, "Time_taken_by_all.json"), "a", encoding="utf-8") as f:
                            #     json.dump(retrieval_time_json,f, ensure_ascii=False, indent=4) 
                                
                if self.is_figma:
                    page_names=self.page_name
                    instance_name=self.instance_name
                    retrieved_info = []
                    retrieved_info_text = ""
                    flow_summary= ""
                    retrived_individual_flow_summary = []
                    is_e2e_case_global = False
                    e2e_page_flow = ""
                    retrived_image_flow = None
                    end_to_end_page_flow=None
                    
                    print("this is userinput:",self.user_input)
                    if self.collection_name not in existing_collections:
                        logger.info(f"⚠️ Collection {self.collection_name} does not exist.")
                        raise CollectionNotFoundError()
                    else:
                        logger.info(f"The collection is Found :{self.collection_name}")
                        for page_name in page_names:
                            if self.user_input is None or self.user_input == "":
                                self.user_input=f"Generate the test cases for {page_name}"
                            try:
                                logger.info(f"Fetching the main flow of page from the qdrant")
                                flow_data=await get_page_flow(page_name,self.collection_name,self.qdrant_client,instance_name)
                            except Exception as e:
                                logger.warning(f"Fail to extract the data of page flow from Qdrant:{e}")
                            
                            if not flow_data:
                                flow_output_summary="FlowSummary: Not found"
                            else:
                                flow_summary=f"FlowSummary: {flow_data['FlowSummary']}"
                                flow_output_summary = flow_summary
                            try:
                                logger.info(f"Started generating the flow and image")
                                systemPrompt, userPrompt, responseFormat=Generate_required_flow_img(flow_output_summary,self.user_input,page_name)
                                retrived_image_flow, input_tokens, output_tokens=await LLMClient.generate_async(serviceProvider=serviceProvider,
                                                                                    model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                    apiKey=apiKey,
                                                                                    system_prompt=systemPrompt, 
                                                                                    user_prompt=userPrompt,
                                                                                    sa_info=sa_info,
                                                                                    resourceId=self.resourceId,
                                                                                    resource=self.resource,
                                                                                    temperature=0.1,
                                                                                    response_format=responseFormat,
                                                                                    return_usage=True,
                                                                                    max_tokens=65000,  
                                                                                    unique_id=self.unique_id,
                                                                                    mongoCollectionName=momgo_license_id
                                                                                    )
                                total_input_tokens+=input_tokens
                                total_output_tokens+=output_tokens
                                if isinstance(retrived_image_flow, list) and len(retrived_image_flow) > 0:
                                    retrived_image_flow = retrived_image_flow[0]
                                
                                if isinstance(retrived_image_flow, str):
                                    retrived_image_flow = FlowImageResponse.model_validate_json(retrived_image_flow)
                                else:
                                    retrived_image_flow = FlowImageResponse.model_validate(retrived_image_flow)
                            except Exception as e:
                                logger.warning(f"Fail for generating the flow and images name:{e}")
                                raise
                            
                            flow_name = retrived_image_flow.FlowName
                            images = retrived_image_flow.Images
                            generated_images = [img.strip() for img in images]
                            e2e = retrived_image_flow.end_to_end
                            chunks_image = []
                            all_flow_summary = []
                            selected_image_names = []
                            if len(flow_name)==0 and len(generated_images)==0:
                                is_e2e_case_global = True
                                try:
                                    logger.info("Taking end to end summary of page")
                                    end_to_end_page_flow=await retrive_e2e(collection_name=self.collection_name,page_name=page_name,q_client=self.qdrant_client,instance_name=instance_name)
                                except Exception as e:
                                    logger.warning(f"Fail to extract end to end flow from qdrant {e}")   
                                try:
                                    end_to_end_all_image=await retrive_e2e_image(collection_name=self.collection_name,page_name=page_name,q_client=self.qdrant_client,instance_name=instance_name)
                                except Exception as e:
                                    logger.warning("Fail to fetch the data Page image name from qdrant:{e} ")
                                try:
                                    systemPrompt, userPrompt, responseFormat=Generate_image_for_e2e(end_to_end_page_flow, end_to_end_all_image)
                                    e2e_required_images, input_tokens, output_tokens=await LLMClient.generate_async(serviceProvider=serviceProvider,
                                                                                    model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                    apiKey=apiKey,
                                                                                    system_prompt=systemPrompt, 
                                                                                    user_prompt=userPrompt,
                                                                                    sa_info=sa_info,
                                                                                    resourceId=self.resourceId,
                                                                                    resource=self.resource,
                                                                                    temperature=0.1,
                                                                                    response_format=responseFormat,
                                                                                    return_usage=True,
                                                                                    max_tokens=65000,  
                                                                                    unique_id=self.unique_id,
                                                                                    mongoCollectionName=momgo_license_id
                                                                                    )
                                    total_input_tokens+=input_tokens
                                    total_output_tokens+=output_tokens
                                    if isinstance(e2e_required_images, list) and len(e2e_required_images) > 0:
                                        e2e_required_images = e2e_required_images[0]
                                    
                                    if isinstance(retrived_image_flow, str):
                                        e2e_required_images = E2EImageResponse.model_validate_json(e2e_required_images)
                                    else:
                                        e2e_required_images = E2EImageResponse.model_validate(e2e_required_images)
                                       
                                except Exception as e:
                                    logger.warning(f"Fail to generate the image name:{f}")
                                    raise
                                
                                images_from_flow = e2e_required_images.Images
                                print("this are the selected image for the e2e:",images_from_flow)
                                images_from_flow = [img.strip() for img in images_from_flow]
                                selected_image_names.extend(images_from_flow)

                                try:
                                    logger.info(f"Retrieve the image chunk from qdrant")
                                    image = None
                                    for image in images_from_flow:
                                        chunk = await retrive_chunk(collection_name=self.collection_name,page_name=page_name,image_name=image,q_client=self.qdrant_client,instance_name=instance_name)
                                        if chunk:
                                            chunks_image.append(chunk)
                                    e2e_page_flow=(end_to_end_page_flow)
                                except Exception as e:
                                    logger.warning(f"Fail to retrive the image chunk from the qdrant:{e}")

                            else:
                                for flow in flow_name:
                                    try:
                                        logger.info(f"Fetching the Individual flow summary from qdrant")
                                        individual_flow_summary=await retrive_flow(collection_name=self.collection_name,page_name=page_name,flow=flow,q_client=self.qdrant_client,instance_name=instance_name)
                                        logger.info(f"Successfully Fetching the Individual flow summary from qdrant")
                                    except Exception as e:
                                        logger.info(f"Fail to Fetching the Individual flow summary from qdrant")
                                    if individual_flow_summary:
                                        all_flow_summary.append(individual_flow_summary)

                                selected_image_names.extend(generated_images)

                                for generated_images in images:
                                    chunk = await retrive_chunk(collection_name=self.collection_name,page_name=page_name,image_name=generated_images,q_client=self.qdrant_client,instance_name=instance_name)
                                    if chunk:
                                        chunks_image.append(chunk)
                                    # print("this is chunk of the image:",chunks_image)
                                retrived_individual_flow_summary.extend(all_flow_summary)
                            relevent_hits =chunks_image or []
                            if relevent_hits:
                                merged_content = []
                                for hit in relevent_hits:
                                    if not hit:
                                        continue
                                    text=hit.get("text")
                                    source=hit.get("source","Unknown Source")
                                    chunk_id=hit.get("chunk_id","N/A")
                                    page_image=hit.get("page_image")

                                    if isinstance(text,list):
                                        line=" ".join(text)
                                    
                                    if isinstance(text,str):
                                        line=text.strip()
                                        if line:
                                            clean_line = line.replace('\n', ' ')
                                            merged_content.append(f"this is image summary: {clean_line}")
                                retrieved_info.extend(merged_content)
                                retrieved_info_text = "\n".join(retrieved_info)       
                        if  is_e2e_case_global:
                            flow_summary= e2e_page_flow
                        else:
                            flow_summary= retrived_individual_flow_summary  

                if self.is_video:
                    if self.user_input is None or self.user_input=="":
                        self.user_input="Generate the test cases for the video"

                    if self.collection_name not in existing_collections:
                        logger.info(f"⚠️ Collection {self.collection_name} does not exist.")
                        raise CollectionNotFoundError()
                    else:
                        logger.info(f"The collection is found : {self.collection_name}")
                        print("This is video name:",self.video_name)
                    try:
                        logger.info(f"retriving the data selector chunk")
                        flow_selector_chunk,all_module_names=await video_flow_selector(video_name=self.video_name,collection_name=self.collection_name, q_client=self.qdrant_client)
                    except Exception as e:
                        logger.error(f"Fail to retrive the data from the qdrant:{e}")
                        raise

                    try:
                        logger.info("running the dataselector LLM")
                        selector_system_prompt,selector_user_prompt,selector_responseFormat=video_data_selector(flow_selector_chunk, self.user_input)
                        selector_output, input_tokens, output_tokens=await LLMClient.generate_async(serviceProvider=serviceProvider,
                                                                                model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                apiKey=apiKey,
                                                                                system_prompt=selector_system_prompt, 
                                                                                user_prompt=selector_user_prompt,
                                                                                sa_info=sa_info,
                                                                                resourceId=self.resourceId,
                                                                                resource=self.resource,
                                                                                temperature=0.1,
                                                                                response_format=selector_responseFormat,
                                                                                return_usage=True,
                                                                                max_tokens=65000,  
                                                                                unique_id=self.unique_id,
                                                                                mongoCollectionName=momgo_license_id                                                            
                                                                                )
                        total_input_tokens+=input_tokens
                        total_output_tokens+=output_tokens
                        if isinstance(selector_output, list) and len(selector_output) > 0:
                            selector_output = selector_output[0] 
                        if isinstance(selector_output, str):
                            video_result = ModuleVideoRouterResponse.model_validate_json(selector_output)
                        else:
                            video_result = ModuleVideoRouterResponse.model_validate(selector_output)
                        logger.info("Done Initilizing Dataselector for video process")
                    except Exception as e:
                        logger.error(f"Dataselector fail:{e}")
                        raise

                    try:
                        logger.info("Fetching the e2e flow for all calls")
                        end_to_end_flow=await video_e2e_retrieval(video_name=self.video_name,collection_name=self.collection_name, q_client=self.qdrant_client)
                        video_followup_content = end_to_end_flow
                    except Exception as e:
                        logger.error(f"Fail to fetch the e2e flow:{e}")
                        raise   
                    
                    try:
                        logger.info("Fetching the audio from qdrant")
                        audio_flow= await video_audio_retrieval(video_name=self.video_name,collection_name=self.collection_name, q_client=self.qdrant_client)
                    except Exception as e:
                        logger.error(f"Fail to fetch the audio flow:{e}")
                        raise
                    print(audio_flow)

                    if audio_flow:
                        for audios_flow in audio_flow:
                            audioed_flow=audios_flow["audio_flow"]
                        for extract_e2e in end_to_end_flow:
                            extracted_e2e=extract_e2e["end_to_end_flow"]  
                            system_prompt,user_prompt,response_fromat=Merge_EndToEnd_Audio_Prompt(extracted_e2e, audioed_flow, serviceProvider)    
                            e2e_audio_output, input_tokens, output_tokens=await LLMClient.generate_async(serviceProvider=serviceProvider,
                                                                                                            model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                                            apiKey=apiKey,
                                                                                                            system_prompt=system_prompt, 
                                                                                                            user_prompt=user_prompt,
                                                                                                            sa_info=sa_info,
                                                                                                            resourceId=self.resourceId,
                                                                                                            resource=self.resource,
                                                                                                            temperature=0.1,
                                                                                                            response_format=response_fromat,
                                                                                                            return_usage=True,
                                                                                                            max_tokens=65000,  
                                                                                                            unique_id=self.unique_id,
                                                                                                            mongoCollectionName=momgo_license_id                                                            
                                                                                                            )  
                            if isinstance(e2e_audio_output, str):
                                e2e_audio_output = json.loads(e2e_audio_output)
                            if isinstance(e2e_audio_output, list) and e2e_audio_output:
                                e2e_audio_output = e2e_audio_output[0]
                            if isinstance(e2e_audio_output, dict) and "completed_end_to_end_flow" in e2e_audio_output:
                                extract_e2e["end_to_end_flow"] = e2e_audio_output["completed_end_to_end_flow"]
                             

                    
                    try:
                        selected_flow_data=[]
                        if len(video_result.module_name)>0 and video_result.end_to_end==False and video_result.all_flow==False:
                            logger.info("Extracting the module from the Qdrant")
                            for module in video_result.module_name:
                                logger.info("Fetching the flow")
                                summary_flow=await video_flow_retrieval(video_name=self.video_name,collection_name=self.collection_name, q_client=self.qdrant_client,module_name=module)
                                selected_flow_data.append(summary_flow)
                    except Exception as e:
                        logger.error(f"Fail to fetch flow:{e}")
                        raise

                    try:
                        all_flow_data=[]
                        if len(video_result.module_name)==0 and video_result.end_to_end==False and video_result.all_flow==True:
                            logger.info("Fetching all flow for genric query")
                            for module in all_module_names:
                                individual_flow=await video_flow_retrieval(video_name=self.video_name,collection_name=self.collection_name, q_client=self.qdrant_client,module_name=module)
                                all_flow_data.append(individual_flow)
                    except Exception as e:
                        logger.error(f"Fail to fetch all flow:{e}")
                        raise
                            
                try:
                    try:        
                        #---------test count and types extraction from user query---------
                        logger.info("test count and types extraction Started")

                        test_count_start_time = time.time()
                        if return_generated_payload or getattr(self, 'return_generated_payload', False):
                            ts_count = 1
                            ts_types = ["take the scenarios from the user input and generate only one testcase"]
                            logger.info("Skipped TestCaseCount LLM call due to return_generated_payload=True; hardcoded ts_count=1")
                        else:
                            try:
                                # Collect result from the task already running in parallel with Retrieval
                                if '_test_count_task' in dir() or '_test_count_task' in locals():
                                    test_output, input_tokens, output_tokens = await _test_count_task
                                    logger.info("TestCaseCount collected from parallel task")
                                else:
                                    systemPrompt, userPrompt, responseFormat = Test_Count_Prompt(self.user_input, serviceProvider)
                                    test_output, input_tokens, output_tokens = await LLMClient.generate_async(
                                        serviceProvider=serviceProvider,
                                        model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                        apiKey=apiKey,
                                        system_prompt=systemPrompt,
                                        user_prompt=userPrompt,
                                        sa_info=sa_info,
                                        resourceId=self.resourceId,
                                        resource=self.resource,
                                        temperature=0.1,
                                        response_format=responseFormat,
                                        return_usage=True,
                                        max_tokens=2048,
                                        unique_id=self.unique_id,
                                        mongoCollectionName=momgo_license_id
                                    )
                            except Exception as _tc_err:
                                logger.warning(f"Parallel TestCaseCount failed, retrying: {_tc_err}")
                                systemPrompt, userPrompt, responseFormat = Test_Count_Prompt(self.user_input, serviceProvider)
                                test_output, input_tokens, output_tokens = await LLMClient.generate_async(
                                    serviceProvider=serviceProvider,
                                    model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                    apiKey=apiKey,
                                    system_prompt=systemPrompt,
                                    user_prompt=userPrompt,
                                    sa_info=sa_info,
                                    resourceId=self.resourceId,
                                    resource=self.resource,
                                    temperature=0.1,
                                    response_format=responseFormat,
                                    return_usage=True,
                                    max_tokens=2048,
                                    unique_id=self.unique_id,
                                    mongoCollectionName=momgo_license_id
                                )
                            if serviceProvider:
                                total_input_tokens += input_tokens
                                total_output_tokens += output_tokens
                        
                            if isinstance(test_output, dict):
                                if 'number' in test_output and 'count' not in test_output:
                                    test_output['count'] = test_output['number']

                                if 'testCaseType' in test_output and 'testCaseTypes' not in test_output:
                                    val = test_output['testCaseType']
                                    if isinstance(val, str):
                                        val = [val] if val else []
                                    test_output['testCaseTypes'] = val
                                elif 'test_case_type' in test_output and 'testCaseTypes' not in test_output:
                                    val = test_output['test_case_type']
                                    if isinstance(val, str):
                                        val = [val] if val else []
                                    test_output['testCaseTypes'] = val
                                elif 'type' in test_output and 'testCaseTypes' not in test_output:
                                    val = test_output['type']
                                    if isinstance(val, str):
                                        val = [val] if val else []
                                    test_output['testCaseTypes'] = val
                            logger.info("all filtering is done for test case count")
                            if isinstance(test_output, str):
                                test_output_result = TestCaseCountResponse.model_validate_json(test_output)

                            elif isinstance(test_output, list) and len(test_output) > 0:
                                test_output_result = test_output[0]
                            else:
                                test_output_result = TestCaseCountResponse.model_validate(test_output)
                            if isinstance(test_output_result, dict):
                                ts_count = test_output_result.get("count", 0)
                                ts_types = test_output_result.get("testCaseTypes") or test_output_result.get("testCaseType") or []
                            else:
                                ts_count = test_output_result.count
                                ts_types = test_output_result.testCaseTypes
                            ts_count, ts_types = self.merge_query_counts(self.user_input, ts_count, ts_types)
                            logger.info(f"\033[93mTestCaseCount:{ts_count}\033[0m")
                            logger.info(f"\033[93mTestCaseTypes:{ts_types}\033[0m")
                        test_count_end_time = time.time()  # end timestamp
                        test_count_duration = test_count_end_time - test_count_start_time
                        test_count_time_json={
                            "title": "Time taken to test case count",
                            "duration_in_seconds": test_count_duration
                        }
                        # with open(os.path.join(output_folder, "4_TestCount.json"), "w", encoding="utf-8") as f:
                        #     json.dump(test_output_result.model_dump(), f, ensure_ascii=False, indent=4)
                        # with open(os.path.join(output_folder, "Time_taken_by_all.json"), "a", encoding="utf-8") as f:
                            # json.dump(test_count_time_json, f, ensure_ascii=False, indent=4)
                    except Exception as e:
                        logger.error(f"Test count and types extraction Failed:{e}")
                        ts_count, ts_types = self.merge_query_counts(self.user_input, 0, [])
                        if ts_count <= 0:
                            raise
                        logger.info(f"Using parsed query count after extractor failure | count={ts_count} types={ts_types}")

                    #-------PER-TYPE SCENARIO + MTC PIPELINES----------
                    image_user_input = ""
                    if self.is_image:
                        image_user_input = self.user_input if self.user_input else """
                        Analyze the provided image summaries and identify whether the screens belong to the same application or workflow. 
                        If the images are connected, understand the end-to-end user journey, navigation flow, validations, and interactions between screens. 
                        Generate comprehensive manual test scenarios covering functional, edge, integration, and user flow validations based on the combined screen context. 
                        Ensure the scenarios reflect realistic user behavior and dependencies across the related images"""
                        logger.debug("=================>")
                        logger.debug(image_user_input)
                        logger.debug("=================>")

                    logger.info(f"filecontent:{self.file_content}")
                    logger.info(f"totalInputToken:{total_input_tokens}")
                    logger.info(f"totalOutToken:{total_output_tokens}")
                except GenerationCancelled:
                    raise
                except Exception as e:
                    logger.error(f"Pre-pipeline setup Failed:{e}")
                    raise
                #-------TYPE PIPELINES (Prompt Mapping → LLM → MTC → MongoDB)----------
                all_start=time.time()
                try:
                    logger.info("Type pipelines started | stage-1 functional/edge/integration in parallel, then e2e")

                    start_time = time.time()

                    router = PromptRouter(
                        json_template=json.dumps(self.json_template, indent=2),
                        serviceProvider=serviceProvider,
                        is_image=self.is_image,
                        is_file=self.is_file,
                        is_video=self.is_video,
                        is_figma=self.is_figma,
                        is_jira=self.is_jira,
                    )

                    type_ctx = {
                        "check_cancel": _check_cancel_with_mongo,
                        "apiKey": apiKey,
                        "serviceProvider": serviceProvider,
                        "model": model,
                        "sa_info": sa_info,
                        "momgo_license_id": momgo_license_id,
                        "retrieved_info": retrieved_info,
                        "flow_summary": flow_summary,
                        "retrieved_info_text": retrieved_info_text,
                        "selected_image_names": selected_image_names,
                        "image_user_input": image_user_input,
                        "return_generated_payload": return_generated_payload,
                        "request_time_for_storing_1_tc_in_MD": request_time_for_storing_1_tc_in_MD,
                        "counter_ref": counter_ref,
                        "counter_lock": counter_lock,
                        "source_of_data": source_of_data,
                        "router": router,
                        "ts_types": ts_types,
                        "ts_count": ts_count,
                        "token_totals": [total_input_tokens, total_output_tokens],
                        "state": state,
                        "followUpData": {"functional": {}, "edge": {}, "integration": {}, "e2e": {}},
                        "idCounter": {"functional": 1, "edge": 1, "integration": 1, "e2e": 1},
                        "processing_tasks": [],
                        "batch_results": [],
                        "generation_was_cancelled": False,
                        "first_batch_logged": False,
                        "all_start": all_start,
                        "early_payload": None,
                        "prompt_batch_count": 0,
                        # "output_folder": output_folder,
                        "is_video":self.is_video,
                        "video_route_result": locals().get("video_result"),
                        "end_to_end_flow": locals().get("end_to_end_flow"),
                        "selected_flow_data": locals().get("selected_flow_data", []),
                        "all_flow_data": locals().get("all_flow_data", []),
                    }

                    await self.fan_out_type_pipelines(type_ctx)

                    # with open(os.path.join(output_folder, "5_Scenario_Generation.json"), "w", encoding="utf-8") as f:
                    #     json.dump(type_ctx.get("generated_scenarios") if type_ctx.get("generated_scenarios") else {}, f, ensure_ascii=False, indent=4)

                    if type_ctx.get("early_payload") is not None:
                        return type_ctx["early_payload"]

                    total_input_tokens, total_output_tokens = type_ctx["token_totals"]
                    state = type_ctx["state"]
                    followUpData = type_ctx["followUpData"]
                    processing_tasks = type_ctx["processing_tasks"]
                    batch_results = type_ctx["batch_results"]
                    generation_was_cancelled = type_ctx["generation_was_cancelled"]
                    prompt_batch_count = type_ctx["prompt_batch_count"]

                    if generation_was_cancelled or is_cancelled(self.unique_id):
                        self._total_input_tokens = total_input_tokens
                        self._total_output_tokens = total_output_tokens
                        self._total_testcase_count = max(counter_ref[0] - 1, 0)
                        if processing_tasks:
                            await asyncio.gather(*processing_tasks, return_exceptions=True)
                            self._total_testcase_count = max(counter_ref[0] - 1, 0)
                        followUp, total_input_tokens, total_output_tokens = await _build_follow_up_for_partial(
                            followUpData=followUpData,
                            ts_count=ts_count,
                            generated_tc_count=self._total_testcase_count,
                            selected_files=selected_files,
                            purpose_info=purpose_info,
                            retrieved_info=retrieved_info,
                            flow_output_summary=(
                                locals().get("video_followup_content")
                                if self.is_video
                                else locals().get("flow_output_summary")
                            ),
                            total_input_tokens=total_input_tokens,
                            total_output_tokens=total_output_tokens,
                        )
                        self._total_input_tokens = total_input_tokens
                        self._total_output_tokens = total_output_tokens
                        await _finalize_cancelled(follow_up=followUp)

                    if not prompt_batch_count:
                        logger.warning("No prompt batches available for execution")
                    else:
                        failed_errors = [r.get("error") for r in batch_results if not r.get("success")]
                        if len(failed_errors) == prompt_batch_count and prompt_batch_count > 0:
                            raise ValueError(failed_errors[0] if failed_errors[0] else "Unable to process your request. Please retry generating the manual test cases.")
                        error_message_val=None
                        api_error=None
                        
                        
                        if failed_errors:
                            raw_err = failed_errors[0] if failed_errors[0] else ""
                            api_error = build_api_error(raw_err, serviceProvider)

                        if return_generated_payload:
                            followUp = None
                        elif api_error and api_error.responseCode in {401, 413, 429}:
                            error_message_val = api_error.message
                            followUp = None
                        else:
                            _check_cancel_with_mongo()
                            if not return_generated_payload:
                                logger.info(f"followUp Got Triggered")
                                if self.is_jira or self.is_file or self.is_image or self.is_video or self.is_figma:
                                    if self.is_image:
                                        Content = self.image_content
                                        attachmentType = "image"
                                    elif self.is_file:
                                        Content = self.file_content
                                        attachmentType = "file"
                                    elif self.is_video:
                                        Content = video_followup_content
                                        attachmentType = "video"
                                    elif self.is_jira:
                                        Content = self.file_content
                                        attachmentType = "jira"
                                    elif self.is_figma:
                                        Content = flow_output_summary
                                        attachmentType = "figma"

                                    systemPrompt, userPrompt = attachmentFollowUpPrompt(self.chatContext,ExtractedContent=Content,followUpData=followUpData,userQuery=self.user_input,userSpecifedTcCount=ts_count,generatedTcCount=counter_ref[0]-1,type=attachmentType,)
                                else:
                                    purpose = self.chosenFiles(filenames=selected_files,data=purpose_info)
                                    systemPrompt, userPrompt = followUpPrompt(self.chatContext,filesInfo=purpose,retrievedContent=retrieved_info,followUpData=followUpData,userQuery=self.user_input,userSpecifedTcCount=ts_count,generatedTcCount=counter_ref[0]-1,)
                                followUpData=encode(followUpData)
                                followUpResponse, inputTokens, outputTokens=await LLMClient.generate_async(serviceProvider=serviceProvider,
                                                                                    model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                    apiKey=apiKey,
                                                                                    system_prompt=systemPrompt, 
                                                                                    user_prompt=userPrompt,
                                                                                    sa_info=sa_info,
                                                                                    resourceId=self.resourceId,
                                                                                    resource=self.resource,
                                                                                    temperature=0.1,
                                                                                    response_format=None,
                                                                                    return_usage=True,
                                                                                    max_tokens=65000,  
                                                                                    unique_id=self.unique_id,
                                                                                    mongoCollectionName=momgo_license_id                                                            
                                                                                    )
                                # followUpResponse = json.loads(followUpResponse)
                                try:
                                    # Case 1: Already valid JSON
                                    followUpResponse = json.loads(followUpResponse)
                                    logger.info("FollowUpResponse Parsed Successfully")
                
                                except json.JSONDecodeError:
                                    logger.info("FollowUpResponse Failed Parsed | Trying with Rrgex Match")
                                    # Case 2: Model returned text + JSON
                                    match = re.search(r'(\[[\s\S]*\])\s*$', followUpResponse)
                
                                    if match:
                                        followUpResponse = json.loads(match.group(1))
                                        logger.info("FollowUpResponse Patten Matched Successfully")
                                    else:
                                        logger.error(
                                            "Unable to extract JSON from followUpResponse: %r",
                                            followUpResponse
                                        )
                                        followUpResponse = None
                                followUp = "Manual test cases generated successfully. What can I do next?\n" + "\n".join(
                                    f"{i}. {item}" for i, item in enumerate(followUpResponse, start=1)
                                )
                                total_input_tokens+=inputTokens
                                total_output_tokens+=outputTokens
                                total_tokens = total_input_tokens + total_output_tokens
                                              
                        # with open(os.path.join(output_folder, "followUpResponse.txt"), "w", encoding="utf-8") as f:
                        #     f.write(str(followUp))
                        if processing_tasks:
                            try:
                                logger.info("Awaiting all background DB tasks to finish...")
                                await asyncio.gather(*processing_tasks)
                                logger.info("All background DB tasks completed successfully.")
                                total_testcase_count=counter_ref[0]-1

                                logger.info(f"totalTestCasesCount:{total_testcase_count}")
                                logger.info(f"total input tokens:{total_input_tokens}")
                                logger.info(f"total output tokens:{total_output_tokens}")
                                logger.info(f"total token=====>:{total_tokens}")
                                mtc = get_manual_test_case()
                                

                                mtc.save_prompt_db(
                                    session_id=self.session_id,
                                    unique_id=self.unique_id,
                                    dateTime=self.dateTime,
                                    session_name=self.session_name,
                                    user_input=self.user_input,
                                    license_id=self.license_id,                                        
                                    project_id=self.project_id,
                                    prompt_id=self.prompt_id,
                                    user_id=self.user_id,
                                    count=self.count,
                                    script_type=self.script_type,
                                    input_type=self.input_type,
                                    file_name=self.file_name,
                                    file_content=self.file_content,
                                    test_case_count=total_testcase_count,   
                                    user_input_tokens=total_input_tokens,
                                    total_output_tokens=total_output_tokens,
                                    total_tokens_consumed=total_tokens,
                                    apiKey=self.apikey,
                                    serviceProvider=self.serviceProvider,
                                    model=self.model,
                                    images_path=self.images_path,
                                    image_content=self.image_content,
                                    video_name=self.video_name,
                                    image_data=None,
                                    prompt_type=self.prompt_type,
                                    mongoCollectionName=momgo_license_id,
                                    branch_id=self.branch_id,
                                    error_message=error_message_val,
                                    follow_up=followUp
                                )
                
                            except Exception:
                                logger.exception("Error while awaiting DB tasks")
                                raise
                        end_time = time.time()
                        duration = end_time - start_time
                        logger.info(f"MtcGeneration Timing | Duration: {duration:.3f}s")

                except GenerationCancelled:
                    raise
                except Exception as e:
                    logging.error(f"MTC Generation Failed: {e}")  
                    raise
                all_end=time.time()
                all_duration=all_end-all_start
                mtc_generation_time={
                    "title": "Time taken to generate MTC",
                    "duration_in_seconds": all_duration
                }
                # with open(os.path.join(output_folder, "6_MTC_Generation.json"), "w", encoding="utf-8") as f:
                #     json.dump(batch_results, f, ensure_ascii=False, indent=4)
                with open(os.path.join(output_folder, "7_Final_MTC_Format.json"), "w", encoding="utf-8") as f:
                    json.dump(state.corrected_testcases if hasattr(state, "corrected_testcases") and state.corrected_testcases else {}, f, ensure_ascii=False, indent=4)
                # with open(os.path.join(output_folder, "Time_taken_for_image.json"), "a", encoding="utf-8") as f:
                #     json.dump(mtc_generation_time,f, ensure_ascii=False, indent=4)          
                
                self._total_input_tokens = total_input_tokens
                self._total_output_tokens = total_output_tokens
                self._total_testcase_count = counter_ref[0] - 1
                if not return_generated_payload:
                    logger.info(f"MTC Generation MetaData | "f"sourceOfData: {source_of_data} | "f"promptID: {self.prompt_id} | "f"testCaseCount: {self._total_testcase_count} | "f"totalInputToken: {self._total_input_tokens} | "f"totalOutputToken: {self._total_output_tokens} | "f"totalToken: {self._total_input_tokens + self._total_output_tokens} | "f"timeTakenForGeneration: {all_duration:.3f}s | "f"PromptType: {self.prompt_type} | "f"UserQUery: {self.user_input}")
                if return_generated_payload:
                    if isinstance(state.corrected_testcases, dict):
                        state.corrected_testcases["total_input_tokens"] = total_input_tokens
                        state.corrected_testcases["total_output_tokens"] = total_output_tokens
                    return self.build_generated_mtc_payload(state)
                return state

            except GenerationCancelled:
                raise
                                            
            except CollectionNotFoundError:
                try:
                    _check_cancel_with_mongo()
                    logger.info("Remoted to Generic MTC(s) Generator")
                    followUp=None
                    prompt_type = self.prompt_type.lower()
                    
                    # Ensure ts_count is extracted
                    if 'ts_count' not in locals():
                        if return_generated_payload or getattr(self, 'return_generated_payload', False):
                            ts_count = 1
                            ts_types = ["take the scenarios from the user input and generate only one testcase"]
                        else:
                            try:
                                if '_test_count_task' in dir() or '_test_count_task' in locals():
                                    test_output, input_tokens, output_tokens = await _test_count_task
                                else:
                                    systemPrompt, userPrompt, responseFormat = Test_Count_Prompt(self.user_input, serviceProvider)
                                    test_output, input_tokens, output_tokens = await LLMClient.generate_async(
                                        serviceProvider=serviceProvider,
                                        model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                        apiKey=apiKey,
                                        system_prompt=systemPrompt,
                                        user_prompt=userPrompt,
                                        sa_info=sa_info,
                                        resourceId=self.resourceId,
                                        resource=self.resource,
                                        temperature=0.1,
                                        response_format=responseFormat,
                                        return_usage=True,
                                        max_tokens=2048,
                                        unique_id=self.unique_id,
                                        mongoCollectionName=momgo_license_id
                                    )
                                
                                if isinstance(test_output, dict):
                                    if 'number' in test_output and 'count' not in test_output: test_output['count'] = test_output['number']
                                    if 'testCaseType' in test_output and 'testCaseTypes' not in test_output:
                                        val = test_output['testCaseType']
                                        test_output['testCaseTypes'] = [val] if isinstance(val, str) else (val or [])
                                    elif 'test_case_type' in test_output and 'testCaseTypes' not in test_output:
                                        val = test_output['test_case_type']
                                        test_output['testCaseTypes'] = [val] if isinstance(val, str) else (val or [])
                                    elif 'type' in test_output and 'testCaseTypes' not in test_output:
                                        val = test_output['type']
                                        test_output['testCaseTypes'] = [val] if isinstance(val, str) else (val or [])
                                
                                if isinstance(test_output, str):
                                    test_output_result = TestCaseCountResponse.model_validate_json(test_output)
                                elif isinstance(test_output, list) and len(test_output) > 0:
                                    test_output_result = test_output[0]
                                else:
                                    test_output_result = TestCaseCountResponse.model_validate(test_output)
                                if isinstance(test_output_result, dict):
                                    ts_count = test_output_result.get("count", 0)
                                    ts_types = test_output_result.get("testCaseTypes") or []
                                else:
                                    ts_count = test_output_result.count
                                    ts_types = test_output_result.testCaseTypes
                                ts_count, ts_types = self.merge_query_counts(self.user_input, ts_count, ts_types)
                            except Exception as e:
                                logger.error(f"Generic Test count extraction failed: {e}")
                                ts_count, ts_types = self.merge_query_counts(self.user_input, 0, [])
                                if ts_count <= 0:
                                    ts_count = 1
                                    ts_types = []

                    ts_count, ts_types = self.merge_query_counts(
                        self.user_input,
                        ts_count,
                        ts_types if 'ts_types' in locals() else [],
                    )

                    if ts_count <= 10:
                        # [EXISTING SINGLE-CALL LOGIC]

                        rules_map = {
                            "web": nonPreprocessedFileWebMtc,
                            "android": nonPreprocessedFileAndroidMtc,
                            "webmobileandroid": nonPreprocessedFileWebMobileMtc,
                            "ios": nonPreprocessedFileIosMtc
                        }              
                        retrieved_info = "This is Generic user Query"
                        logger.warning("Retrieved info is set to default message as no relevant information was retrieved from vector database.")
                        rules = rules_map.get(prompt_type)
                        if rules is None:
                            raise ValueError(f"Unknown prompt_type: {self.prompt_type}")

                        if self.count == 1:
                            system_prompt = rules
                        else:
                            redis_history = AgentMemoryOperation().get_session_history(self.prompt_id)
                            if redis_history:
                                system_prompt = f"""{rules}

You are provided with a summary of previously generated test cases (memory).
This memory represents ALL test coverage that already exists.

==============================
EXISTING TEST CASE NAMES (STRICTLY FORBIDDEN — DO NOT REGENERATE):
{redis_history}
==============================

MANDATORY DEDUPLICATION RULES:
- Do NOT generate any test case whose name, behavior, logic path, or intent overlaps with the above list.
- Do NOT reword, rephrase, or restructure any existing test case.
- Treat semantically similar tests as duplicates even if wording differs.

CRITICAL OBJECTIVE:
Generate ENTIRELY NEW test cases that expand coverage beyond what already exists.

Before generating:
1. Analyze the memory and identify: covered features · covered input ranges · covered states · covered error paths.
2. Identify explicit COVERAGE GAPS.
3. Only generate test cases that fill at least one uncovered gap.
"""
                            else:
                                system_prompt = rules
                        userPrompt=GenericUserquery(self.user_input, serviceProvider, template=json.dumps(self.json_template, indent=2), chatContext=self.chatContext or "", ts_count=ts_count)
                        responseFormat = {"type": "json_object"}
                        if serviceProvider in ["DefaultFireFlink", "Groq", "OpenAi"]:
                            def add_additional_properties_false(schema):
                                if isinstance(schema, dict):
                                    if schema.get("type") == "object":
                                        schema["additionalProperties"] = False
                                    if "properties" in schema:
                                        for v in schema["properties"].values():
                                            add_additional_properties_false(v)
                                    if "items" in schema:
                                        add_additional_properties_false(schema["items"])
                                return schema

                            from genson import SchemaBuilder
                            builder = SchemaBuilder()
                            builder.add_object(self.json_template)
                            generated_schema = builder.to_schema()
                            generated_schema.pop("$schema", None)
                            generated_schema = add_additional_properties_false(generated_schema)

                            responseFormat = {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": "schema_name",
                                    "strict": True,
                                    "schema": generated_schema
                                }
                            }
                        
                        generic_llm_start = time.time()
                        response, generic_input_tokens, generic_output_tokens = await LLMClient.generate_async(
                                                serviceProvider=serviceProvider,
                                                model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                apiKey=apiKey,
                                                sa_info=sa_info,
                                                resourceId=self.resourceId,
                                                resource=self.resource,
                                                system_prompt=system_prompt,
                                                user_prompt=userPrompt,
                                                temperature=0.4,
                                                response_format=responseFormat, 
                                                return_usage=True,
                                                max_tokens=65000,
                                                unique_id=self.unique_id,
                                                mongoCollectionName=momgo_license_id
                                            )
                        
                        generic_input_tokens += total_input_tokens
                        generic_output_tokens += total_output_tokens

                        if isinstance(response, dict) and "Test Cases" in response and isinstance(response["Test Cases"], list):
                            if ts_count > 0 and len(response["Test Cases"]) > ts_count:
                                logger.info(f"Overshoot in generic flow: got {len(response['Test Cases'])}, trimming to requested {ts_count} test cases")
                                response["Test Cases"] = response["Test Cases"][:ts_count]

                        result={
                                "success": True,
                                "batch_number":1,
                                "response": response,
                                "input_tokens": generic_input_tokens,
                                "output_tokens":generic_output_tokens
                            }
                        
                        if not return_generated_payload:
                            followUpData = {}
                            id_counter = 1
                            for tc in result["response"]["Test Cases"]:
                                test_case_id = f"Test Case {id_counter}"
                                id_counter += 1
                                followUpData[test_case_id] = (
                                    f"Test Case Name: {tc.get('Test Case Name', '')} | "
                                    f"Description: {tc.get('Description', '')}"
                                )
                            if not self.session_name:
                                summary= result.get("response", {}).get("summary")
                                if summary:
                                    self.session_name = summary
                                    self.update_session_name(momgo_license_id,
                                                            self.unique_id,
                                                            self.session_id,
                                                            self.prompt_id,
                                                            self.count,
                                                            self.session_name)                                   
                        
                        counter_ref_generic = counter_ref
                        counter_lock_generic = counter_lock
                        result["test_type"] = "generic"
                        
                        if return_generated_payload:
                            state = self.set_return_payload_state(state, response)
                            final_response = state.corrected_testcases
                        else:
                            state,_,_,generic_batch_corrected = await process_llm_results([result],counter_ref_generic, counter_lock_generic,state,self.key_corrector,self.TopLevelModel, self.prompt_type)
                            final_response = generic_batch_corrected
                        
                        if return_generated_payload:
                            self._total_testcase_count =  1
                            self._total_input_tokens = generic_input_tokens
                            self._total_output_tokens = generic_output_tokens
                            logger.info(f"MTC Generation ATC pipeLine | "f"sourceOfData: GenericSource | "f"promptID: {self.prompt_id} | "f"testCaseCount: {self._total_testcase_count} | "f"totalInputToken: {self._total_input_tokens} | "f"totalOutputToken: {self._total_output_tokens} | "f"totalToken: {self._total_input_tokens + self._total_output_tokens} | "f"PromptType: {self.prompt_type} | "f"UserQUery: {self.user_input}")
                            return self.build_generated_mtc_payload(state)         

                        await process_llm_response(
                                                response=final_response,
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
                                                mongoCollectionName=momgo_license_id,
                                                request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
                                                branch_id=self.branch_id
                                                    )
                        
                        total_testcase_count_generic=counter_ref_generic[0]-1    
                        mtc = get_manual_test_case()
                        
                        if not return_generated_payload:
                            systemPrompt,userPrompt=genericFollowup(summary=self.chatContext,
                                                                    followUpData=followUpData,
                                                                    userQuery=self.user_input,
                                                                    userSpecifedTcCount=ts_count,
                                                                    generatedTcCount=total_testcase_count_generic)
                            followUpResponse, inputTokens, outputTokens=await LLMClient.generate_async(serviceProvider=serviceProvider,
                                                                                model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                                                                apiKey=apiKey,
                                                                                system_prompt=systemPrompt, 
                                                                                user_prompt=userPrompt,
                                                                                sa_info=sa_info,
                                                                                resourceId=self.resourceId,
                                                                                resource=self.resource,
                                                                                temperature=0.1,
                                                                                response_format=None,
                                                                                return_usage=True,
                                                                                max_tokens=65000,  
                                                                                unique_id=self.unique_id,
                                                                                mongoCollectionName=momgo_license_id                                                            
                                                                                )
                            try:
                                followUpResponse = json.loads(followUpResponse)
                            except json.JSONDecodeError:
                                match = re.search(r'(\[[\s\S]*\])\s*$', followUpResponse)
                                if match:
                                    followUpResponse = json.loads(match.group(1))
                                else:
                                    followUpResponse = None
                            followUp = "Manual test cases generated successfully. What can I do next?\n" + "\n".join(
                                f"{i}. {item}" for i, item in enumerate(followUpResponse or [], start=1)
                            )
                           
                            
                            generic_input_tokens+=inputTokens
                            generic_output_tokens+=outputTokens

                        mtc.save_prompt_db(
                            session_id=self.session_id,
                            unique_id=self.unique_id,
                            dateTime=self.dateTime,
                            session_name=self.session_name,
                            user_input=self.user_input,
                            license_id=self.license_id,                                        
                            project_id=self.project_id,
                            prompt_id=self.prompt_id,
                            user_id=self.user_id,
                            count=self.count,
                            script_type=self.script_type,
                            input_type=self.input_type,
                            file_name=self.file_name,
                            file_content=self.file_content,
                            test_case_count=total_testcase_count_generic,   
                            user_input_tokens=generic_input_tokens,
                            total_output_tokens=generic_output_tokens,
                            total_tokens_consumed=generic_input_tokens + generic_output_tokens,
                            apiKey=self.apikey,
                            serviceProvider=self.serviceProvider,
                            model=self.model,
                            images_path=self.images_path,
                            image_content=self.image_content,
                            video_name=self.video_name,
                            image_data=None,
                            prompt_type=self.prompt_type,
                            mongoCollectionName=momgo_license_id,
                            branch_id=self.branch_id,
                            error_message=None,
                            follow_up=followUp
                        )
                        self._total_input_tokens = generic_input_tokens
                        self._total_output_tokens = generic_output_tokens
                        self._total_testcase_count = counter_ref_generic[0] - 1
                        if not return_generated_payload:
                            logger.info(f"MTC Generation MetaData | "f"sourceOfData: GenericSource | "f"promptID: {self.prompt_id} | "f"testCaseCount: {total_testcase_count_generic} | "f"totalInputToken: {generic_input_tokens} | "f"totalOutputToken: {generic_output_tokens} | "f"totalToken: {generic_input_tokens + generic_output_tokens} | "f"PromptType: {self.prompt_type} | "f"UserQUery: {self.user_input}")
                        return state

                    else:
                        # [NEW BATCHED GENERIC LOGIC]
                        logger.info("Executing Generic Batched Pipeline (ts_count > 10)")

                        
                        systemPrompt, userPrompt, responseFormat = GenericScenarioSuggestion(
                            self.user_input, prompt_type, ts_count, ts_types, summary=self.chatContext
                        )
                        
                        if self.count >= 2:
                            redis_history = AgentMemoryOperation().get_session_history(self.prompt_id)
                            if redis_history:
                                regenerate_system_prompt = f"""
### MANDATORY DEDUPLICATION PROTOCOL
You are strictly prohibited from generating scenarios that overlap with the existing test suite.

#### 1. EXISTING TEST MEMORY (HISTORY)
<history>
{redis_history}
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
                                systemPrompt = regenerate_system_prompt + systemPrompt

                        scenarios_response, scenarios_input_tokens, scenarios_output_tokens = await LLMClient.generate_async(
                            serviceProvider=serviceProvider,
                            model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                            apiKey=apiKey,
                            system_prompt=systemPrompt,
                            user_prompt=userPrompt,
                            sa_info=sa_info,
                            resourceId=self.resourceId,
                            resource=self.resource,
                            temperature=0.5,
                            response_format=responseFormat,
                            return_usage=True,
                            max_tokens=65000,
                            unique_id=self.unique_id,
                            mongoCollectionName=momgo_license_id
                        )
                        
                        if isinstance(scenarios_response, str):
                            try:
                                ScenarioSuggestionResponse = json.loads(scenarios_response)
                            except Exception:
                                ScenarioSuggestionResponse = json.loads(repair_json(scenarios_response))
                        elif isinstance(scenarios_response, list) and len(scenarios_response) > 0:
                            ScenarioSuggestionResponse = scenarios_response[0]
                        else:
                            ScenarioSuggestionResponse = scenarios_response or {}

                        total_scenarios = sum(len(v) for k, v in ScenarioSuggestionResponse.items() if isinstance(v, list))
                        logger.info(f"Generic Scenarios generated — total: {total_scenarios}, required: {ts_count}")

                        # Post-processing count enforcement
                        if ts_count > 0 and total_scenarios != ts_count:
                            if total_scenarios > ts_count:
                                excess = total_scenarios - ts_count
                                for type_key in ["edge", "functional", "integration", "e2e"]:
                                    if excess <= 0:
                                        break
                                    current = ScenarioSuggestionResponse.get(type_key, [])
                                    trimmable = min(len(current), excess)
                                    ScenarioSuggestionResponse[type_key] = current[:len(current) - trimmable]
                                    excess -= trimmable
                            elif total_scenarios < ts_count:
                                remaining = ts_count - total_scenarios
                                fb_sys, fb_user, fb_format = GenericFallBackScenarioSuggestion(
                                    self.user_input, prompt_type, ts_count, ts_types, ScenarioSuggestionResponse, total_scenarios, remaining, summary=self.chatContext
                                )
                                if self.count >= 2:
                                    redis_history = AgentMemoryOperation().get_session_history(self.prompt_id)
                                    if redis_history:
                                        fb_sys = regenerate_system_prompt + fb_sys

                                fallback_response, fb_in, fb_out = await LLMClient.generate_async(
                                    serviceProvider=serviceProvider,
                                    model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                    apiKey=apiKey,
                                    system_prompt=fb_sys,
                                    user_prompt=fb_user,
                                    sa_info=sa_info,
                                    resourceId=self.resourceId,
                                    resource=self.resource,
                                    temperature=0.2,
                                    response_format=fb_format,
                                    return_usage=True,
                                    max_tokens=65000,
                                    unique_id=self.unique_id,
                                    mongoCollectionName=momgo_license_id
                                )
                                scenarios_input_tokens += fb_in
                                scenarios_output_tokens += fb_out
                                if isinstance(fallback_response, str):
                                    try:
                                        FallbackResponse = json.loads(fallback_response)
                                    except Exception:
                                        FallbackResponse = json.loads(repair_json(fallback_response))
                                else:
                                    FallbackResponse = fallback_response or {}

                                for type_key in ["functional", "edge", "integration", "e2e"]:
                                    if isinstance(FallbackResponse.get(type_key, []), list):
                                        if type_key not in ScenarioSuggestionResponse or not isinstance(ScenarioSuggestionResponse[type_key], list):
                                            ScenarioSuggestionResponse[type_key] = []
                                        ScenarioSuggestionResponse[type_key].extend(FallbackResponse.get(type_key, []))

                                total_after_merge = sum(len(v) for v in ScenarioSuggestionResponse.values() if isinstance(v, list))
                                if total_after_merge > ts_count:
                                    excess = total_after_merge - ts_count
                                    for type_key in ["edge", "functional", "integration", "e2e"]:
                                        if excess <= 0:
                                            break
                                        current = ScenarioSuggestionResponse.get(type_key, [])
                                        trimmable = min(len(current), excess)
                                        ScenarioSuggestionResponse[type_key] = current[:len(current) - trimmable]
                                        excess -= trimmable


                        router = PromptRouter(
                            json_template=json.dumps(self.json_template, indent=2),
                            serviceProvider=serviceProvider,
                            is_image=False, is_file=False, is_video=False, is_figma=False, is_jira=False
                        )
                        batched_payloads = self.create_type_batches(ScenarioSuggestionResponse, batch_size=5)
                        prompt_batches = []
                        for batch in batched_payloads:
                            if prompt_type.lower() == "web":
                                prompt_payload = router.build_batch_prompt_generic_web(batch)
                            elif prompt_type.lower() == "android":
                                prompt_payload = router.build_batch_prompt_generic_mobile(batch)
                            elif prompt_type.lower() == "ios":
                                prompt_payload = router.build_batch_prompt_generic_ios(batch)
                            prompt_batches.append(prompt_payload)
                        
                        # Generate MTC
                        semaphore = asyncio.Semaphore(5)
                        async def execute_prompt_batch(prompt_batch):
                            input_tokens = 0
                            output_tokens = 0
                            responseFormat = {"type": "json_schema"}
                            if serviceProvider in ["DefaultFireFlink", "Groq", "OpenAi"]:
                                def add_additional_properties_false(schema):
                                    if isinstance(schema, dict):
                                        if schema.get("type") == "object": schema["additionalProperties"] = False
                                        if "properties" in schema:
                                            for v in schema["properties"].values(): add_additional_properties_false(v)
                                        if "items" in schema: add_additional_properties_false(schema["items"])
                                    return schema
                                from genson import SchemaBuilder
                                builder = SchemaBuilder()
                                builder.add_object(json.loads(prompt_batch["json_template"]))
                                generated_schema = builder.to_schema()
                                generated_schema.pop("$schema", None)
                                generated_schema = add_additional_properties_false(generated_schema)
                                responseFormat = {
                                    "type": "json_schema",
                                    "json_schema": {
                                        "name": "schema_name",
                                        "strict": True,
                                        "schema": generated_schema
                                    }
                                }

                            try:
                                response, b_in, b_out = await LLMClient.generate_async(
                                    serviceProvider=serviceProvider,
                                    model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                    apiKey=apiKey,
                                    sa_info=sa_info,
                                    resourceId=self.resourceId,
                                    resource=self.resource,
                                    system_prompt=prompt_batch["system_prompt"],
                                    user_prompt=prompt_batch["user_prompt"],
                                    temperature=0.4,
                                    response_format=responseFormat, 
                                    return_usage=True,
                                    max_tokens=65000,
                                    unique_id=self.unique_id,
                                    mongoCollectionName=momgo_license_id
                                )
                                return {
                                    "success": True,
                                    "test_type": prompt_batch["test_type"],
                                    "batch_number": prompt_batch["batch_number"],
                                    "response": response,
                                    "input_tokens": b_in,
                                    "output_tokens": b_out
                                }
                            except Exception as e:
                                logger.error(f"Generic Batch {prompt_batch.get('batch_number')} failed: {e}")
                                return {
                                    "success": False,
                                    "test_type": prompt_batch.get("test_type"),
                                    "batch_number": prompt_batch.get("batch_number"),
                                    "response": None,
                                    "error": str(e),
                                    "input_tokens": input_tokens,
                                    "output_tokens": output_tokens
                                }

                        async def guarded_call(prompt_batch):
                            async with semaphore:
                                return await execute_prompt_batch(prompt_batch)

                        tasks = [
                            asyncio.create_task(guarded_call(batch))
                            for batch in prompt_batches
                        ]

                        processing_tasks = []
                        batch_results = []
                        total_input_tokens = scenarios_input_tokens
                        total_output_tokens = scenarios_output_tokens
                        followUpData = {}
                        id_counter = 1

                        for future in asyncio.as_completed(tasks):
                            if is_cancelled(self.unique_id):
                                for t in tasks:
                                    if not t.done():
                                        t.cancel()
                                break
                            try:
                                result = await future
                                batch_results.append(result)

                                if not result.get("success"):
                                    logger.error(f"Batch {result.get('batch_number')} failed: {result.get('error')}")
                                    continue

                                if not return_generated_payload:
                                    tc_list = result.get("response", {}).get("Test Cases", []) if isinstance(result.get("response"), dict) else []
                                    for tc in tc_list:
                                        test_case_id = f"Test Case {id_counter}"
                                        id_counter += 1
                                        tc_name = tc.get('Test Case Name') or tc.get('testCaseName') or tc.get('name') or tc.get('title') or ""
                                        tc_desc = tc.get('Description') or tc.get('description') or ""
                                        followUpData[test_case_id] = f"Test Case Name: {tc_name} | Description: {tc_desc}"

                                    if not self.session_name:
                                        summary = result.get("response", {}).get("summary")
                                        if summary:
                                            self.session_name = summary
                                            asyncio.get_event_loop().run_in_executor(
                                                None,
                                                self.update_session_name,
                                                momgo_license_id,
                                                self.unique_id,
                                                self.session_id,
                                                self.prompt_id,
                                                self.count,
                                                self.session_name
                                            )

                                current_batch_corrected = None
                                try:
                                    logger.info(f"Processing Generic Batch {result.get('batch_number')} | Type:{result.get('test_type')}")
                                    if return_generated_payload:
                                        state = self.set_return_payload_state(state, result.get("response", {}))
                                    else:
                                        state, b_in_tokens, b_out_tokens, current_batch_corrected = await process_llm_results(
                                            [result], counter_ref, counter_lock, state, self.key_corrector, self.TopLevelModel, self.prompt_type
                                        )
                                        total_input_tokens += b_in_tokens + result.get("input_tokens", 0)
                                        total_output_tokens += b_out_tokens + result.get("output_tokens", 0)

                                except Exception as e:
                                    logger.exception(f"Processing failed for generic batch {result.get('batch_number')}: {e}")
                                    continue

                                if return_generated_payload:
                                    self._total_testcase_count = 1
                                    self._total_input_tokens = total_input_tokens + result.get("input_tokens", 0)
                                    self._total_output_tokens = total_output_tokens + result.get("output_tokens", 0)
                                    logger.info(f"MTC Generation ATC pipeLine | "f"sourceOfData: GenericSource | "f"promptID: {self.prompt_id} | "f"testCaseCount: {self._total_testcase_count} | "f"totalInputToken: {self._total_input_tokens} | "f"totalOutputToken: {self._total_output_tokens} | "f"totalToken: {self._total_input_tokens + self._total_output_tokens} | "f"PromptType: {self.prompt_type} | "f"UserQUery: {self.user_input}")
                                    return self.build_generated_mtc_payload(state)

                                if not return_generated_payload and current_batch_corrected:
                                    try:
                                        db_task = asyncio.create_task(
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
                                                mongoCollectionName=momgo_license_id,
                                                request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
                                                branch_id=self.branch_id
                                            )
                                        )
                                        processing_tasks.append(db_task)
                                    except Exception:
                                        logger.exception(f"DB task creation failed for generic batch {result.get('batch_number')}")
                                    logger.info(f"Generic Batch {result.get('batch_number')} | Type:{result.get('test_type')} processed and sent to DB")

                            except asyncio.CancelledError:
                                break
                            except Exception as e:
                                logger.exception(f"Unexpected error in generic batch future: {e}")

                        if processing_tasks:
                            await asyncio.gather(*processing_tasks, return_exceptions=True)

                        total_testcase_count = counter_ref[0] - 1
                        mtc = get_manual_test_case()

                        if not return_generated_payload:
                            systemPrompt, userPrompt = genericFollowup(
                                summary=self.chatContext,
                                followUpData=followUpData,
                                userQuery=self.user_input,
                                userSpecifedTcCount=ts_count,
                                generatedTcCount=total_testcase_count,
                            )
                            followUpResponse, in_tok, out_tok = await LLMClient.generate_async(
                                serviceProvider=serviceProvider,
                                model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                                apiKey=apiKey,
                                system_prompt=systemPrompt, 
                                user_prompt=userPrompt,
                                sa_info=sa_info,
                                resourceId=self.resourceId,
                                resource=self.resource,
                                temperature=0.1,
                                response_format=None,
                                return_usage=True,
                                max_tokens=65000,
                                unique_id=self.unique_id,
                                mongoCollectionName=momgo_license_id
                            )
                            try:
                                followUpResponse = json.loads(followUpResponse)
                            except json.JSONDecodeError:
                                match = re.search(r'(\[[\s\S]*\])\s*$', followUpResponse)
                                if match: followUpResponse = json.loads(match.group(1))
                                else: followUpResponse = None
                            
                            followUp = "Manual test cases generated successfully. What can I do next?\n" + "\n".join(
                                f"{i}. {item}" for i, item in enumerate(followUpResponse or [], start=1)
                            )
                           
                            logger.info(followUp)
                            total_input_tokens += in_tok
                            total_output_tokens += out_tok
                        mtc.save_prompt_db(
                            session_id=self.session_id,
                            unique_id=self.unique_id,
                            dateTime=self.dateTime,
                            session_name=self.session_name,
                            user_input=self.user_input,
                            license_id=self.license_id,                                        
                            project_id=self.project_id,
                            prompt_id=self.prompt_id,
                            user_id=self.user_id,
                            count=self.count,
                            script_type=self.script_type,
                            input_type=self.input_type,
                            file_name=self.file_name,
                            file_content=self.file_content,
                            test_case_count=total_testcase_count,   
                            user_input_tokens=total_input_tokens,
                            total_output_tokens=total_output_tokens,
                            total_tokens_consumed=total_input_tokens + total_output_tokens,
                            apiKey=self.apikey,
                            serviceProvider=self.serviceProvider,
                            model=self.model,
                            images_path=self.images_path,
                            image_content=self.image_content,
                            video_name=self.video_name,
                            image_data=None,
                            prompt_type=self.prompt_type,
                            mongoCollectionName=momgo_license_id,
                            branch_id=self.branch_id,
                            error_message=None,
                            follow_up=followUp
                        )
                        self._total_input_tokens = total_input_tokens
                        self._total_output_tokens = total_output_tokens
                        self._total_testcase_count = total_testcase_count
                        if not return_generated_payload:
                            logger.info(f"MTC Generation MetaData | "f"sourceOfData: GenericSource | "f"promptID: {self.prompt_id} | "f"testCaseCount: {total_testcase_count} | "f"totalInputToken: {total_input_tokens} | "f"totalOutputToken: {total_output_tokens} | "f"totalToken: {total_input_tokens + total_output_tokens} | "f"PromptType: {self.prompt_type} | "f"UserQUery: {self.user_input}")
                        return state

                except GenerationCancelled:
                    raise
                except Exception as e:
                    logger.error(f"Generic part failed: {e}")
                    raise                                                               
        except GenerationCancelled:
            raise
        except asyncio.CancelledError:
            logger.info(f"Generation task cancelled | unique_id={self.unique_id}")
            if not getattr(self, "_cancel_finalized", False):
                try:
                    mtc = get_manual_test_case()
                    mtc.mark_generation_cancelled(
                        unique_id=self.unique_id,
                        license_id=momgo_license_id,
                        input_tokens=getattr(self, "_total_input_tokens", 0) or 0,
                        output_tokens=getattr(self, "_total_output_tokens", 0) or 0,
                        test_case_count=getattr(self, "_total_testcase_count", 0) or 0,
                        follow_up=getattr(self, "_follow_up", None),
                    )
                    self._cancel_finalized = True
                except Exception:
                    pass
            raise GenerationCancelled(unique_id=self.unique_id)
        except Exception as e:
            logger.error(f"MTC GENERATION FAILED: {e}")
            raise
        finally:
            self._total_input_tokens = locals().get("generic_input_tokens", locals().get("total_input_tokens", 0))
            self._total_output_tokens = locals().get("generic_output_tokens", locals().get("total_output_tokens", 0))
            
            try:
                total_tokens = self._total_input_tokens + self._total_output_tokens
                if total_tokens > 0 and self.serviceProvider == "DefaultFireFlink":
                    # mtc = get_manual_test_case()
                    asyncio.create_task(update_ai_service_instance_token_usage(
                        mongo_url=None,
                        license_id=self.license_id,
                        service_provider=self.serviceProvider,
                        tokens=total_tokens
                    ))
                    logger.info(f"Token deduction triggered for service provider {self.serviceProvider} | license_id={self.license_id} | tokens={total_tokens}")
            except Exception as e:
                logger.error(f"Error triggering token deduction: {e}")
                
            unregister_job(self.unique_id)

