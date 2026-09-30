"""Generation handlers for prompt, image, file, video, Figma, and Jira."""
from src.persistence._shared import *  # noqa: F401,F403
from src.persistence.embeddings import qdrant_client,qdrantAsyncClient  # noqa: F401,F403
from src.agents.helpers import update_ai_service_instance_token_usage
# from qdrant_client import QdrantClient,AsyncQdrantClient 

# qdrant_host = os.getenv("QDRANT_HOST")
# qdrant_port = int(os.getenv("QDRANT_PORT"))
# qdrant_client = QdrantClient(qdrant_host, port=qdrant_port, https=False, check_compatibility=False)
# async_qdrant_client = AsyncQdrantClient(qdrant_host, port=qdrant_port, https=False, timeout=60.0)

class GenerationHandlersMixin:
    async def handle_user_input_for_image(
        self,
        session_id,
        license_id,
        project_id,
        bearer_token,
        template,
        apiKey,
        serviceProvider,
        model,
        resourceId,
        resource,
        prompt_type,
        sa_info,
        user_input,
        session_name,
        count,
        prompt_id,
        user_id,
        input_type,
        script_type,
        is_modified,
        user_input_tokens,
        images_data,
        image_content,
        template_id,
        unique_id,
        dateTime,
        original_template,
        env,
        Image_Input_token,
        Image_Output_token,
        request_time_for_storing_1_tc_in_MD,
        branch_id,
        chatContext:Optional[str]= None,
        return_generated_payload=False,
        context_summary=None
    ):
        if env:
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else:
            mongoDb_license_id = f"optimize_{license_id}"
        try:
            images_path=[]
        except Exception as e:
            logger.error(f"Error in image preprocessing: {e}", exc_info=True)
            mongoDb_license_id = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
            await asyncio.to_thread(self.save_Error, unique_id=unique_id, error=str(e), mongoCollectionName=mongoDb_license_id)
            return {"success": False, "error": {"code": 500, "message": str(e)}}
            
        COLLECTION_NAME = None

        agent_operation = AgentOperation(
            json_template=template, 
            user_input=user_input,
            collection_name=COLLECTION_NAME,
            embeddings=self.embeddings,
            qdrant_client=None,
            session_id=session_id, 
            session_name=session_name,
            prompt_id=prompt_id,
            user_id=user_id,
            input_type=input_type,
            script_type=script_type,
            file_name=None,
            file_content=None,
            is_modified=is_modified,
            user_input_tokens=user_input_tokens,
            images_path=images_path,
            image_content=image_content,
            template_id=template_id,
            unique_id=unique_id,
            dateTime=dateTime,
            original_template=original_template,
            bearer_token=bearer_token,
            count=count,            
            memory=True, 
            is_jira=False,
            is_image =True,
            is_file=False,
            is_video=False,
            is_figma=False,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            prompt_type=prompt_type,
            sa_info=sa_info, 
            resourceId=resourceId,
            resource=resource,           
            env=env,
            branch_id=branch_id,
            chatContext=chatContext,
            video_name=None,
            video_content=None,
            license_id=license_id,
            project_id=project_id,
            return_generated_payload=return_generated_payload,
            context_summary=context_summary,
            Image_Input_token=Image_Input_token,
            Image_Output_token=Image_Output_token,
        )
        try:
            return await agent_operation.async_lang_graph_builder(
                apiKey,
                serviceProvider,
                model,
                sa_info,
                request_time_for_storing_1_tc_in_MD,
                return_generated_payload=return_generated_payload
            )
        except (GenerationCancelled, asyncio.CancelledError) as e:
            logger.info(f"Generation cancelled in handle_user_input_for_image | unique_id={unique_id}")
            if not getattr(agent_operation, "_cancel_finalized", False):
                mongoDb_license_id = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
                self.mark_generation_cancelled(
                    unique_id=unique_id,
                    license_id=mongoDb_license_id,
                    input_tokens=getattr(agent_operation, "_total_input_tokens", 0),
                    output_tokens=getattr(agent_operation, "_total_output_tokens", 0),
                    test_case_count=getattr(agent_operation, "_total_testcase_count", 0),
                    follow_up=getattr(agent_operation, "_follow_up", None),
                )
            if isinstance(e, asyncio.CancelledError):
                raise
            return None
        except Exception as e:
            if not return_generated_payload:
                self.save_generation_error(
                                            unique_id=unique_id,
                                            error=e,
                                            license_id=mongoDb_license_id,
                                            service_provider=serviceProvider,
                                            input_tokens=Image_Input_token if Image_Input_token else 0,
                                            output_tokens=Image_Output_token if Image_Output_token else 0
                                        )
            if return_generated_payload:
                api_error = build_api_error(e, serviceProvider)
                raise api_error
            
    async def handle_user_input_for_file(
        self,
        user_id,
        license_id,
        project_id,
        branch_id,
        env,
        session_id,
        session_name,
        prompt_id,
        unique_id,
        dateTime,
        template,
        original_template,
        template_id,
        input_type,
        user_input,
        user_input_tokens,
        file_name,
        file_content,
        chatContext,
        prompt_type,
        script_type,
        count,
        is_modified,
        apiKey,
        serviceProvider,
        model,
        sa_info,
        resourceId,
        resource,
        request_time_for_storing_1_tc_in_MD,
        return_generated_payload=False,
        File_Input_token=0,
        File_Output_token=0,
    ):
        if env:
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else:
            mongoDb_license_id = f"optimize_{license_id}"

        try:
            logger.info(f"Processing file MTC generation request (count={count}) using pre-processed document summary.")
            raw_summary = file_content if isinstance(file_content, str) else (file_content.get("file_content") if isinstance(file_content, dict) else "")
            formatted_file_content = {
                "file_content": raw_summary,
                "input_token": File_Input_token,
                "output_token": File_Output_token,
            }

            agent_operstion = AgentOperation(
                user_id=user_id,
                license_id=license_id,
                project_id=project_id,
                branch_id=branch_id,
                env=env,
                session_id=session_id,
                session_name=session_name,
                prompt_id=prompt_id,
                unique_id=unique_id,
                dateTime=dateTime,
                json_template=template,
                original_template=original_template,
                template_id=template_id,
                input_type=input_type,
                user_input=user_input,
                user_input_tokens=user_input_tokens,
                file_name=file_name,
                file_content=formatted_file_content,
                context_summary=raw_summary,
                chatContext=chatContext,
                prompt_type=prompt_type,
                script_type=script_type,
                count=count,
                is_modified=is_modified,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                sa_info=sa_info,
                resourceId=resourceId,
                resource=resource,
                bearer_token=None,
                memory=True,
                is_file=True,
                is_jira=False,
                is_image=False,
                is_video=False,
                is_figma=False,
            )  
            result = await agent_operstion.async_lang_graph_builder(
                apiKey,
                serviceProvider,
                model,
                sa_info,
                request_time_for_storing_1_tc_in_MD,
                return_generated_payload=return_generated_payload
            )
            
            # If no test cases were generated at all, raise an exception to record the failure in MongoDB
            if agent_operstion._total_testcase_count == 0:
                raise ValueError("Unable to generate manual test cases. Please try again.")
            
            return result
        except (GenerationCancelled, asyncio.CancelledError) as e:
            logger.info(f"Generation cancelled in handle_user_input_for_file | unique_id={unique_id}")
            if not ('agent_operstion' in locals() and getattr(agent_operstion, "_cancel_finalized", False)):
                accumulated_input_tokens = 0
                accumulated_output_tokens = 0
                test_case_count = 0
                follow_up = None
                if 'agent_operstion' in locals():
                    accumulated_input_tokens += getattr(agent_operstion, "_total_input_tokens", 0)
                    accumulated_output_tokens += getattr(agent_operstion, "_total_output_tokens", 0)
                    test_case_count = getattr(agent_operstion, "_total_testcase_count", 0)
                    follow_up = getattr(agent_operstion, "_follow_up", None)
                self.mark_generation_cancelled(
                    unique_id=unique_id,
                    license_id=mongoDb_license_id,
                    input_tokens=accumulated_input_tokens,
                    output_tokens=accumulated_output_tokens,
                    test_case_count=test_case_count,
                    follow_up=follow_up,
                )
            if isinstance(e, asyncio.CancelledError):
                raise
            return None
        except Exception as e:
            if return_generated_payload:
                raise e
            else:
                logger.error(f"Error in handle_user_input_for_file: {e}", exc_info=True)
                accumulated_input_tokens = 0
                accumulated_output_tokens = 0
                if 'agent_operstion' in locals():
                    accumulated_input_tokens += getattr(agent_operstion, "_total_input_tokens", 0)
                    accumulated_output_tokens += getattr(agent_operstion, "_total_output_tokens", 0)
                self.save_generation_error(
                    unique_id=unique_id,
                    error=e,
                    license_id=mongoDb_license_id,
                    service_provider=serviceProvider,
                    input_tokens=accumulated_input_tokens,
                    output_tokens=accumulated_output_tokens
                )

    async def handle_user_input(
        self,
        user_input: str,
        session_id: str,
        session_name,
        count,
        license_id,
        project_id,
        prompt_id,
        user_id,
        input_type,
        script_type,
        file_name,
        file_content, 
        is_modified,
        user_input_tokens, 
        images_path, 
        image_content,
        template_id, 
        unique_id,
        dateTime,
        original_template,
        template,
        bearer_token=None,
        apiKey=None,
        serviceProvider=None,
        model=None,
        prompt_type=None,
        sa_info=None,
        resourceId=None,
        resource=None,
        env=None,
        video_name=None,
        video_content=None,
        request_time_for_storing_1_tc_in_MD=None,
        return_generated_payload=False,
        branch_id=None,
        Input_Token_Video=None,
        Output_Token_Video=None,
        chatContext=None,
    ):
        if env:
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else:
            mongoDb_license_id = f"optimize_{license_id}"

        try:
            if env :
                COLLECTION_NAME = f"ff_cloud_{env}_{license_id}_{project_id}"
            else :
                COLLECTION_NAME = f"ff_cloud_{license_id}_{project_id}"
            agent_operstion = AgentOperation(
                json_template=template, 
                user_input=user_input,
                collection_name=COLLECTION_NAME,
                embeddings=self.embeddings,
                qdrant_client=qdrantAsyncClient,
                # qdrant_client=qdrant_client,
                session_id=session_id, 
                session_name=session_name,
                prompt_id=prompt_id,
                user_id=user_id,
                input_type=input_type,
                script_type=script_type,
                file_name=file_name,
                file_content=file_content,
                is_modified=is_modified,
                user_input_tokens=user_input_tokens,
                images_path=images_path,
                image_content=image_content,
                template_id=template_id,
                unique_id=unique_id,
                dateTime=dateTime,
                original_template=original_template,
                bearer_token=bearer_token,            
                count=count,
                memory=True, 
                is_jira=False,
                is_image =False,
                is_file =False,
                is_video=False,
                is_figma=False,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                sa_info=sa_info,
                resourceId=resourceId,
                resource=resource,
                env=env,
                video_name=video_name,
                video_content=video_content,
                license_id=license_id,
                project_id=project_id,
                branch_id=branch_id,
                return_generated_payload=return_generated_payload,
                Input_Token_Video=Input_Token_Video,
                Output_Token_Video=Output_Token_Video,    
                chatContext=chatContext,
            )
            result = await agent_operstion.async_lang_graph_builder(
                apiKey,
                serviceProvider,
                model,
                sa_info,
                request_time_for_storing_1_tc_in_MD,
                return_generated_payload=return_generated_payload
            )
            
            # If no test cases were generated at all, raise an exception to record the failure in MongoDB
            if agent_operstion._total_testcase_count == 0:
                raise ValueError("Unable to generate manual test cases. Please try again.")
            
            return result

        except (GenerationCancelled, asyncio.CancelledError) as e:
            logger.info(f"Generation cancelled in handle_user_input | unique_id={unique_id}")
            if not ('agent_operstion' in locals() and getattr(agent_operstion, "_cancel_finalized", False)):
                input_tokens = 0
                output_tokens = 0
                test_case_count = 0
                follow_up = None
                if 'agent_operstion' in locals():
                    input_tokens = getattr(agent_operstion, "_total_input_tokens", 0)
                    output_tokens = getattr(agent_operstion, "_total_output_tokens", 0)
                    test_case_count = getattr(agent_operstion, "_total_testcase_count", 0)
                    follow_up = getattr(agent_operstion, "_follow_up", None)
                self.mark_generation_cancelled(
                    unique_id=unique_id,
                    license_id=mongoDb_license_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    test_case_count=test_case_count,
                    follow_up=follow_up,
                )
            if isinstance(e, asyncio.CancelledError):
                raise
            return None
            
        except Exception as e:
            if return_generated_payload:
                raise e
            else:
                logger.error(f"Error in handle_user_input: {e}", exc_info=True)
                input_tokens = 0
                output_tokens = 0
                if 'agent_operstion' in locals():
                    input_tokens = getattr(agent_operstion, "_total_input_tokens", 0)
                    output_tokens = getattr(agent_operstion, "_total_output_tokens", 0)
                self.save_generation_error(
                    unique_id=unique_id,
                    error=e,
                    license_id=mongoDb_license_id,
                    service_provider=serviceProvider,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )


    async def handle_user_input_for_figma(
        self,
        user_input: str,
        session_id: str,
        session_name,
        count,
        license_id,
        project_id,
        bearer_token,
        prompt_id,
        user_id,
        input_type,
        script_type,
        is_modified,
        user_input_tokens,
        template_id,
        unique_id,
        dateTime,
        original_template,
        template,
        apiKey=None,
        serviceProvider=None,
        model=None,
        prompt_type=None,
        sa_info=None,
        resourceId=None,
        resource=None,
        env=None,
        page_name=None,
        instance_name=None,
        request_time_for_storing_1_tc_in_MD=None,
        return_generated_payload=False,
        branch_id=None,
        chatContext=None,
    ):
        if env:
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else:
            mongoDb_license_id = f"optimize_{license_id}"

        try:
            if env :
                COLLECTION_NAME = f"ff_cloud_{env}_figma_{license_id}_{project_id}"
            else :
                COLLECTION_NAME = f"ff_cloud_figma_{license_id}_{project_id}"
            agent_operstion = AgentOperation(
                json_template=template, 
                user_input=user_input,
                collection_name=COLLECTION_NAME,
                embeddings=self.embeddings,
                qdrant_client=qdrantAsyncClient,
                # qdrant_client=qdrant_client,
                session_id=session_id, 
                session_name=session_name,
                prompt_id=prompt_id,
                user_id=user_id,
                input_type=input_type,
                script_type=script_type,
                is_modified=is_modified,
                user_input_tokens=user_input_tokens,
                template_id=template_id,
                unique_id=unique_id,
                dateTime=dateTime,
                original_template=original_template,
                bearer_token=bearer_token,
                branch_id=branch_id,            
                count=count,
                memory=True, 
                is_jira=False,
                is_image =False,
                is_file =False,
                is_video=False,
                is_figma=True,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                sa_info=sa_info,
                resourceId=resourceId,
                resource=resource,
                env=env,
                page_name=page_name,
                instance_name=instance_name,
                license_id=license_id,
                project_id=project_id,
                return_generated_payload=return_generated_payload,
                chatContext=chatContext
            )
            result = await agent_operstion.async_lang_graph_builder(
                apiKey,
                serviceProvider,
                model,
                sa_info,
                request_time_for_storing_1_tc_in_MD,
                return_generated_payload=return_generated_payload
            )
            
            # If no test cases were generated at all, raise an exception to record the failure in MongoDB
            if agent_operstion._total_testcase_count == 0:
                raise ValueError("Unable to generate manual test cases. Please try again.")
            
            return result
            
        except (GenerationCancelled, asyncio.CancelledError) as e:
            logger.info(f"Generation cancelled in handle_user_input_for_figma | unique_id={unique_id}")
            if not ('agent_operstion' in locals() and getattr(agent_operstion, "_cancel_finalized", False)):
                input_tokens = 0
                output_tokens = 0
                test_case_count = 0
                follow_up = None
                if 'agent_operstion' in locals():
                    input_tokens = getattr(agent_operstion, "_total_input_tokens", 0)
                    output_tokens = getattr(agent_operstion, "_total_output_tokens", 0)
                    test_case_count = getattr(agent_operstion, "_total_testcase_count", 0)
                    follow_up = getattr(agent_operstion, "_follow_up", None)
                self.mark_generation_cancelled(
                    unique_id=unique_id,
                    license_id=mongoDb_license_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    test_case_count=test_case_count,
                    follow_up=follow_up,
                )
            if isinstance(e, asyncio.CancelledError):
                raise
            return None
        except Exception as e:
            logger.error(f"Error in handle_user_input: {e}", exc_info=True)
            if return_generated_payload:
                raise
            else:
                self.save_generation_error(
                    unique_id=unique_id,
                    error=e,
                    license_id=mongoDb_license_id,
                    service_provider=serviceProvider
                )

    async def handle_user_input_for_jira(
        self,
        jira_ids,
        user_name,
        api_token,
        domain,
        apiKey,
        serviceProvider,
        model,
        sa_info,
        resourceId,
        resource,
        session_id,
        session_name,
        user_input,
        prompt_type,
        json_structure,
        template,
        template_id,
        template_keys,
        file_content,
        temp_header,
        start_time_total,
        license_id,
        project_id,
        bearer_token,
        prompt_id,
        user_id,
        unique_id,
        dateTime,
        env,
        branch_id,
        chatContext,
        count=1,
        input_type="text",
        script_type="manual",
        is_modified=False,
        request_time_for_storing_1_tc_in_MD=None,
        return_generated_payload=False,
        process_jira=False,
        isAutomationScript: bool = False,
        
    ):
        # Compute mongoDb_license_id once at the top (DRY)
        if env:
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else:
            mongoDb_license_id = f"optimize_{license_id}"

        try:
            batch_summary = None
            parent_ip = 0
            parent_op = 0

            if process_jira:
                temp_dir = tempfile.mkdtemp(prefix="jira_upload_")
                jira_generator = JiraDocGenerator(email=user_name, api_token=api_token, domain=domain)            
                parent_contexts = {}
                target_keys = []
                
                # 1. Quickly fetch parent fields to discover child keys BEFORE doing heavy image/text AI processing
                async def fetch_parent_fields(j_id):
                    fields = await jira_generator.fetch_issue_clean(j_id)
                    c_keys = []
                    for subtask in fields.get("Subtasks", []):
                        s_key = subtask.get("key")
                        if s_key and s_key not in c_keys:
                            c_keys.append(s_key)
                    for child in fields.get("Child Issues", []):
                        c_key = child.get("key")
                        if c_key and c_key not in c_keys:
                            c_keys.append(c_key)
                    return j_id, fields, c_keys

                logger.info("[JIRA Pipeline] Quickly fetching parent fields to discover child tickets...")
                parent_fields_results = await asyncio.gather(*(fetch_parent_fields(j_id) for j_id in jira_ids))

                # Setup parent mappings and dynamically allocate child limits
                parent_fields_map = {}
                all_available_children = {}
                
                for j_id, p_fields, c_keys in parent_fields_results:
                    parent_fields_map[j_id] = p_fields
                    all_available_children[j_id] = c_keys
                    
                num_parents = len(jira_ids)
                if num_parents == 1:
                    max_total_children = 10
                elif num_parents == 2:
                    max_total_children = 10
                elif num_parents >= 3:
                    max_total_children = 9
                else:
                    max_total_children = 10
                    
                parent_to_children_map = {j_id: [] for j_id in jira_ids}
                remaining_pool = max_total_children
                
                # Keep allocating as long as we have pool capacity and at least one parent has available children left to pick
                active_allocation = True
                while remaining_pool > 0 and active_allocation:
                    active_allocation = False
                    for j_id in jira_ids:
                        if remaining_pool == 0:
                            break
                        allocated = parent_to_children_map[j_id]
                        available = all_available_children[j_id]
                        if len(allocated) < len(available):
                            allocated.append(available[len(allocated)])
                            remaining_pool -= 1
                            active_allocation = True
                
                target_keys = []
                for j_id in jira_ids:
                    c_keys = parent_to_children_map[j_id]
                    if c_keys:
                        target_keys.extend(c_keys)
                    else:
                        target_keys.append(j_id)
                
                target_keys = list(dict.fromkeys(target_keys))
                
                # 2. Now started processing (parents and children) in one giant parallel batch
                child_count = len([k for k in target_keys if k not in jira_ids])
                logger.info(f"[JIRA Pipeline] Started processing for {len(jira_ids)} parents and {child_count} children CONCURRENTLY...")
                
                async def process_ticket(t_key):
                    nonlocal parent_ip, parent_op
                    is_parent = t_key in jira_ids
                    fields_to_pass = parent_fields_map.get(t_key) if is_parent else None
                    t_context, t_ip, t_op, t_fields = await jira_generator.build_ticket_context(
                        ticket_key=t_key,
                        apiKey=apiKey,
                        serviceProvider=serviceProvider,
                        model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink","Groq"] else model,
                        sa_info=sa_info,
                        resource=resource,
                        resourceId=resourceId,
                        temp_dir=temp_dir,
                        pre_fetched_fields=fields_to_pass
                    )
                    parent_ip += t_ip
                    parent_op += t_op
                    return t_key, t_context, t_ip, t_op, is_parent

                # We process everything together
                all_ticket_keys = list(set(jira_ids + target_keys))
                all_results = await asyncio.gather(*(process_ticket(k) for k in all_ticket_keys))
                
                child_context_map = {}
                for t_key, t_context, t_ip, t_op, is_parent in all_results:
                    if is_parent:
                        parent_contexts[t_key] = t_context
                    else:
                        child_context_map[t_key] = t_context
                        
                # 3. Construct the hierarchical contexts for output
                all_contexts = {}
                hierarchical_contexts = {}
                
                for j_id in jira_ids:
                    p_context = parent_contexts[j_id]
                    c_keys = parent_to_children_map[j_id]
                    child_contexts_list = []
                    
                    # Assign to legacy all_contexts mapping
                    if not c_keys:
                        all_contexts[j_id] = {
                            "Parent Ticket": p_context
                        }
                    else:
                        for ck in c_keys:
                            if ck in child_context_map:
                                child_contexts_list.append(child_context_map[ck])
                                all_contexts[ck] = {
                                    "Parent Ticket": p_context,
                                    "Child Tickets": [child_context_map[ck]]
                                }
                                
                    hierarchical_contexts[j_id] = {
                        "Parent Ticket Context": p_context
                    }
                    if child_contexts_list:
                        hierarchical_contexts[j_id]["Child Tickets Contexts"] = child_contexts_list
                
                # os.makedirs("Jira_Output_Reference", exist_ok=True)
                # with open("Jira_Output_Reference/Context.json", "w", encoding="utf-8") as f:
                #     json.dump(hierarchical_contexts, f, indent=4)
                    
                time_taken = time.time() - start_time_total
                logger.info(f"Time taken to fetch and build context: {time_taken:.2f} seconds")
                
                # Serialize the entire hierarchical context for the LLM
                batch_summary = json.dumps(hierarchical_contexts, indent=2)
                context_summary = batch_summary
                
                # Persist the preprocessed document summary into MongoDB user_mtc_to_atc collection
                try:
                    self.initialize_db_and_collections_mtc_to_atc(
                        license_id=mongoDb_license_id,
                        unique_id=prompt_id,
                        content=context_summary
                    )
                    logger.info(f"Successfully stored preprocessed jira summary for prompt_id: {prompt_id} in user_mtc_to_atc")
                except Exception as db_store_err:
                    logger.error(f"Failed to store preprocessed jira summary in user_mtc_to_atc: {db_store_err}")

            else:
                batch_summary = file_content
                context_summary = ""
            
            # --- BATCH TESTCASE GENERATION ---
            logger.info("[JIRA Pipeline] Starting Batch MTC Generation for all retrieved contexts.")
            
            # We use a single generic file name for the batch request
            batch_file_name = "Batch_Jira_Tickets.txt"
            if jira_ids and len(jira_ids) == 1:
                batch_file_name = f"{jira_ids[0]}_JiraCard.txt"
            elif jira_ids:
                batch_file_name = f"{'_'.join(jira_ids)}_JiraCards.txt"
            if return_generated_payload and not isAutomationScript :
                # Deduct preprocessing tokens when returning summary only (Stage 1).
                # When is_automation_steps=True, the generate.py finally block handles deduction.
                preprocessing_tokens = parent_ip + parent_op
                if preprocessing_tokens > 0 and serviceProvider == "DefaultFireFlink":
                    try:
                        await update_ai_service_instance_token_usage(
                            mongo_url=None,
                            license_id=license_id,
                            service_provider=serviceProvider,
                            tokens=preprocessing_tokens
                        )
                        logger.info(f"Stage 1 token deduction | Endpoint: /jira-to-mtc | tokens={preprocessing_tokens} | serviceProvider={serviceProvider}")
                    except Exception as deduction_err:
                        logger.error(f"Failed to deduct preprocessing tokens in /jira-to-mtc Stage 1: {deduction_err}")
                return {
                    "context_summary": batch_summary,
                    "ref_id": prompt_id
                }

            COLLECTION_NAME = None    
            agent_operstion = AgentOperation(
                json_template=json_structure, 
                user_input=user_input,
                collection_name=COLLECTION_NAME,
                embeddings=None,
                qdrant_client=None,
                session_id=session_id, 
                session_name=session_name,
                prompt_id=prompt_id,
                user_id=user_id,
                input_type=input_type,
                script_type=script_type,
                file_name=batch_file_name,
                file_content=batch_summary,
                context_summary=context_summary,
                is_modified=is_modified,
                user_input_tokens=0, 
                images_path=None, 
                image_content=None,
                template_id=template_id, 
                unique_id=unique_id, 
                dateTime=dateTime,
                original_template=template,
                bearer_token=bearer_token,
                count=count,
                memory="",
                is_jira=True,
                is_image=False,
                is_file=False,
                is_video=False,
                is_figma = False,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                sa_info=sa_info,
                env=env,
                branch_id=branch_id,
                chatContext=chatContext,
                license_id=license_id,
                project_id=project_id,
                resourceId=resourceId,
                resource=resource,
                video_name=None,
                video_content=None,
                Jira_Input_token=parent_ip,
                Jira_Output_token=parent_op,
                return_generated_payload=return_generated_payload
            )
            
            try:
                res = await agent_operstion.async_lang_graph_builder(
                    apiKey, serviceProvider, model, sa_info,
                    request_time_for_storing_1_tc_in_MD,
                    return_generated_payload=return_generated_payload
                )
                if return_generated_payload:
                    return res
            except Exception as e:
                logger.error(f"Error in batch generation pipeline: {e}")
                raise
                
            total_test_case_count = agent_operstion._total_testcase_count
            
            # If no test cases were generated at all, raise an exception to record the failure in MongoDB
            if total_test_case_count == 0:
                raise ValueError("Unable to generate manual test cases. Please try again.")

        except (GenerationCancelled, asyncio.CancelledError) as e:
            logger.info(f"Generation cancelled in handle_user_input_for_jira | unique_id={unique_id}")
            if not ('agent_operstion' in locals() and getattr(agent_operstion, "_cancel_finalized", False)):
                accumulated_input_tokens = 0
                accumulated_output_tokens = 0
                test_case_count = 0
                follow_up = None
                if 'agent_operstion' in locals():
                    accumulated_input_tokens += getattr(agent_operstion, "_total_input_tokens", 0)
                    accumulated_output_tokens += getattr(agent_operstion, "_total_output_tokens", 0)
                    test_case_count = getattr(agent_operstion, "_total_testcase_count", 0)
                    follow_up = getattr(agent_operstion, "_follow_up", None)
                self.mark_generation_cancelled(
                    unique_id=unique_id,
                    license_id=mongoDb_license_id,
                    input_tokens=accumulated_input_tokens,
                    output_tokens=accumulated_output_tokens,
                    test_case_count=test_case_count,
                    follow_up=follow_up,
                )
            if isinstance(e, asyncio.CancelledError):
                raise
            return None
        except Exception as e:
            if return_generated_payload:
                raise e
            else:
                logger.error(f"Error in handle_user_input_for_jira: {e}", exc_info=True)
                accumulated_input_tokens = 0
                accumulated_output_tokens = 0
                if 'parent_ip' in locals():
                    accumulated_input_tokens += locals().get('parent_ip', 0) or 0
                if 'parent_op' in locals():
                    accumulated_output_tokens += locals().get('parent_op', 0) or 0
                if 'agent_operstion' in locals():
                    accumulated_input_tokens += getattr(agent_operstion, "_total_input_tokens", 0)
                    accumulated_output_tokens += getattr(agent_operstion, "_total_output_tokens", 0)
                self.save_generation_error(
                    unique_id=unique_id,
                    error=e,
                    license_id=mongoDb_license_id,
                    service_provider=serviceProvider,
                    input_tokens=accumulated_input_tokens,
                    output_tokens=accumulated_output_tokens
                )
            


    async def handle_user_input_for_video_process(
        self,
        user_id,
        license_id,
        project_id,
        branch_id,
        env,
        session_id,
        session_name,
        prompt_id,
        unique_id,
        dateTime,
        template,
        original_template,
        template_id,
        input_type,
        user_input,
        user_input_tokens,
        video_name,
        chatContext,
        prompt_type,
        script_type,
        count,
        is_modified,
        apiKey,
        serviceProvider,
        model,
        sa_info,
        resourceId,
        resource,
        request_time_for_storing_1_tc_in_MD,
        return_generated_payload=False,
    ):
        if env:
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else:
            mongoDb_license_id = f"optimize_{license_id}"
        print("this is mongodb id:",mongoDb_license_id)
        try:
            if env :
                COLLECTION_NAME = f"ff_cloud_{env}_video_{license_id}_{project_id}"
            else :
                COLLECTION_NAME = f"ff_cloud_video_{license_id}_{project_id}"
            agent_operstion = AgentOperation(
                json_template=template, 
                user_input=user_input,
                collection_name=COLLECTION_NAME,
                embeddings=self.embeddings,
                qdrant_client=qdrantAsyncClient,
                # qdrant_client=qdrant_client,
                session_id=session_id, 
                session_name=session_name,
                prompt_id=prompt_id,
                user_id=user_id,
                input_type=input_type,
                script_type=script_type,
                is_modified=is_modified,
                user_input_tokens=user_input_tokens,
                template_id=template_id,
                unique_id=unique_id,
                dateTime=dateTime,
                original_template=original_template,
                branch_id=branch_id,            
                count=count,
                memory=True, 
                is_jira=False,
                is_image =False,
                is_file =False,
                is_figma=False,
                is_video=True,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                sa_info=sa_info,
                resourceId=resourceId,
                resource=resource,
                env=env,
                video_name=video_name,
                license_id=license_id,
                project_id=project_id,
                return_generated_payload=return_generated_payload,
                chatContext=chatContext
            )
            result = await agent_operstion.async_lang_graph_builder(
                apiKey,
                serviceProvider,
                model,
                sa_info,
                request_time_for_storing_1_tc_in_MD,
                return_generated_payload=return_generated_payload
            )
            
            # If no test cases were generated at all, raise an exception to record the failure in MongoDB
            if agent_operstion._total_testcase_count == 0:
                raise ValueError("Unable to generate manual test cases. Please try again.")
            
            return result
            
        except Exception as e:
            self.save_generation_error(
                unique_id=unique_id,
                error=e,
                license_id=mongoDb_license_id,
                service_provider=serviceProvider
            )