from fastapi import APIRouter
from src.api.runtime import *  # noqa: F401,F403
from src.persistence.mongo_client import get_sync_client
import os , time , uuid , asyncio , json , re
router = APIRouter()

@router.post("/fetch-tickets")
async def fetch_tickets(request: FetchTicketsRequest):

    project_name = request.project_name
    company_domain = request.company_domain
    jira_mail_id = request.jira_mail_id
    jira_api_token = request.jira_api_token
    next_page_token = request.next_page_token

    # Initialize Jira authentication
    generator = JiraDocGenerator(
        email=jira_mail_id,
        api_token=jira_api_token,
        domain=company_domain,
    )

    # Fetch tickets
    result = await jira_issues_fetch_utility(
        generator=generator,
        domain=company_domain,
        project_name=project_name,
        next_page_token=next_page_token,
    )

    http_status_code = result.get("responseCode", 200)

    if http_status_code == 200:
        return result

    raise HTTPException(
        status_code=http_status_code,
        detail=result.get("message", "An error occurred"),
    )

@router.post("/jira-mtc-generation")
async def jira_mtc_generation(request: JiraPromptRequest):
    start_time_total = time.time()
    license_id = request.license_id
    user_id = request.user_id
    project_id = request.project_id
    script_type = request.script_type
    session_id = request.session_id
    prompt_id = request.prompt_id
    count = request.count
    input_type = request.input_type
    jira_ids = request.jira_ids
    is_modified = request.is_modified
    file_name = request.file_name
    user_prompt = request.input
    env = os.getenv("PROFILE")
    session_name = request.session_name
    prompt_type = request.prompt_type
    branch_id = request.branch_id
    summary = request.summary
    ref_id = request.ref_id
    
    images_path = None
    image_content = None
    logger.info(f"Main MTC request initiated | Endpoint: /jira-mtc-generation")
    logger.info(f"Content Summary: {summary}")
    logger.info(f"Reference ID: {ref_id}")

    request_time_for_storing_1_tc_in_MD = {
        "start_time": time.time(),
        "stored_time": None
    }
    
    
    # 2. Early generation of unique_id and mongoDb_license_id
    if not prompt_id:
        prompt_id = str(uuid.uuid4().hex)
    if not session_id:
        session_id = str(uuid.uuid4().hex)
        
    value = "SCR"
    unique_id = value + str(uuid.uuid4().hex)
    dateTime=datetime.now(timezone.utc)
    if env:
        mongoDb_license_id = f"optimize_{env}_{license_id}"
    else:
        mongoDb_license_id = f"optimize_{license_id}"

    # Fetch provider info early to pass to DB initialization (defined out of try block for local scope reference)
    apiKey = None
    serviceProvider = None
    model = None
    sa_info = None


    try:
        # 1. Early validation checks inside try-except wrapper
        if not all([user_id, project_id]):
            raise APIError(responseCode=400, message="Please send proper details (user_id and project_id are required)")
        if count not in [1, 2, 3]:
            raise APIError(responseCode=400, message="Invalid count value. Allowed values: 1, 2, 3")
        if not ref_id:
            raise APIError(responseCode=400, message="Unable to generate test cases. Please reattach the jira instance and try again.")

        # Fetch provider info and extract detailed error if it fails
        try:
            sp_config = resolve_service_provider(license_id, project_id)
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "failure",
                    "message": f"Failed to fetch service provider details: {e}",
                }
            )

        apiKey = sp_config.get("apiKey")
        serviceProvider = sp_config.get("serviceProvider")
        model = sp_config.get("model")
        sa_info = sp_config.get("sa_info")
        resource = sp_config.get("resource")
        resourceId = sp_config.get("resourceId")


        try:
            val_result, message = validateApiKey(
                serviceProvider=serviceProvider,
                model=model,
                apiKey=apiKey,
                sa_info=sa_info,
                resourceId=resourceId,
            )
            logger.info(f"......result: {val_result}, {message}")
        except Exception as e:
            raise e
        template = None
        retries = 0
        while retries <= 3:
            try:
                template = manualTestCase.fetch_test_case_template(license_id, project_id)
                if template:
                    break
            except Exception as e:
                logger.error(f"Error fetching template: {e}")
            retries += 1
            await asyncio.sleep(1)
            
        if not template:
            raise APIError(responseCode=400, message="Test case template not found for this project.")
            
        template_id = template['_id']
        test_case_fields = [
            item["label"] for item in template.get("testCaseDetails", [])
        ]
        test_step_fields = [
            cell["value"]
            for cell in template.get("testSteps", []).get("data", [[]])[0]
        ]
        json_structure = {
            "summary": "",
            "Test Cases": [
                {
                    **{field: "" for field in test_case_fields},
                    "Test Steps": [{field: "" for field in test_step_fields}],
                    "testCaseType": "",
                }
            ]
        }

        file_content = None

        lookup_keys = []
        if ref_id:
            if isinstance(ref_id, str):
                lookup_keys = [ref_id]
            elif isinstance(ref_id, list):
                lookup_keys = [str(k) for k in ref_id if k]
        if not lookup_keys and prompt_id:
            lookup_keys = [str(prompt_id)]

        if not lookup_keys:
            raise APIError(
                responseCode=400,
                message="ref_id or prompt_id is required"
            )

        mongoDb_license_id = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
        try:
            mtc_to_atc_col = manualTestCase.load_collection_for_mtc_to_atc(
                license_id=mongoDb_license_id
            )
            docs = list(
                mtc_to_atc_col.find(
                    {"ref_id": {"$in": lookup_keys}},
                    {"ref_id": 1, "summary": 1}
                )
            )

            summary_map = {}
            for doc in docs:
                summary_val = doc.get("summary")
                if isinstance(summary_val, str):
                    summary_val = summary_val.strip()
                if summary_val:
                    summary_map[doc["ref_id"]] = summary_val

            logger.info(
                f"Successfully retrieved {len(summary_map)} stored summaries for ref_ids: {lookup_keys}"
            )

            if summary_map:
                file_content = "\n\n".join(summary_map.values())
            else:
                file_content = (file_content or "").strip()
                if not file_content:
                    logger.error(f"No stored summary found in mtc_to_atc for ref_ids: {lookup_keys} and prompt_id: {prompt_id}.")
                    raise APIError(
                        responseCode=400,
                        message=f"Unable to generate test cases. Please reattach the Jira instance and try again."
                    )
        except APIError:
            raise
        except Exception as db_err:
            logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids: {lookup_keys} and prompt_id: {prompt_id} | Error: {db_err}")
            file_content = (file_content or "").strip()
            if not file_content:
                logger.error(f"Failed to retrieve stored summary for ref_ids: {lookup_keys} and prompt_id: {prompt_id}")
                raise APIError(responseCode=400, message="Unable to generate test cases. Please try again by reattaching the Jira instance.")
            
        manualTestCase.initialize_db_and_collections(
            license_id=mongoDb_license_id,
            unique_id=unique_id,
            dateTime=dateTime,
            session_id=session_id,
            session_name=session_name,
            user_input=user_prompt if user_prompt else "Generate test cases for this Jira ticket.",
            project_id=project_id,
            prompt_id=prompt_id,
            user_id=user_id,
            count=count,
            script_type=script_type,
            input_type=input_type,
            images_path=images_path,
            file_name=file_name,
            file_content="",
            user_input_tokens=0,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            prompt_type=prompt_type,
            video_name=None,
            branch_id=branch_id
        )
        
        asyncio.create_task(manualTestCase.handle_user_input_for_jira(
            jira_ids=None,
            user_name=None,
            api_token=None,
            domain=None,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            sa_info=sa_info,
            resourceId=resourceId,
            bearer_token="",
            resource=resource,
            session_id=session_id,
            session_name=session_name,
            user_input=user_prompt if user_prompt else "Generate test cases for this Jira ticket.",
            prompt_type=prompt_type,
            json_structure=json_structure,
            template=template,
            template_keys=[k.get("value") for k in template["testSteps"]["data"][0]],
            temp_header=template["testSteps"]["data"][0],
            template_id=template_id,
            file_content=file_content,
            start_time_total=start_time_total,
            license_id=license_id,
            project_id=project_id,
            prompt_id=prompt_id,
            user_id=user_id,
            unique_id=unique_id,
            dateTime=dateTime,
            env=env,
            branch_id=branch_id,
            chatContext=summary,
            count=count,
            input_type=input_type,
            script_type=script_type,
            is_modified=is_modified,
            request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
            process_jira=False
        ))

    except Exception as e:
        logger.error(f"Error in jira_mtc_generation pipeline: {str(e)}", exc_info=True)
        try:
            manualTestCase.initialize_db_and_collections(
                license_id=mongoDb_license_id,
                unique_id=unique_id,
                dateTime=dateTime,
                session_id=session_id,
                session_name=session_name,
                user_input=user_prompt if user_prompt else "Generate test cases for this Jira ticket.",
                project_id=project_id,
                prompt_id=prompt_id,
                user_id=user_id,
                count=count,
                script_type=script_type,
                input_type=input_type,
                images_path=images_path,
                file_name=file_name,
                file_content="",
                user_input_tokens=0,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                video_name=None,
                branch_id=branch_id
            )
            manualTestCase.save_generation_error(
                unique_id=unique_id,
                error=e,
                license_id=mongoDb_license_id,
                service_provider=serviceProvider
            )
        except Exception as db_err:
            logger.error(f"Failed to record Jira error in DB: {db_err}", exc_info=True)

    return JSONResponse(
        status_code=202,
        content=jsonable_encoder({
            "message": "SUCCESS",
            "responseCode": 200,
            "responseObject": {
                "data": {
                    "prompt_document": {
                        "_id": unique_id,
                        "apiKey": apiKey,
                        "count": count,
                        "created_at": dateTime,
                        "file_content": None,
                        "file_name": None,
                        "image_content": None,
                        "image_data": None,
                        "images_path": [],
                        "is_completed": False,
                        "input_type": input_type,
                        "model": model,
                        "project_id": project_id,
                        "prompt": user_prompt,
                        "prompt_id": prompt_id,
                        "prompt_type": prompt_type,
                        "script_type": "manual",
                        "serviceProvider": serviceProvider,
                        "session_id": session_id,
                        "session_name": session_name,
                        "test_case_count": 0,
                        "total_output_tokens": 0,
                        "total_tokens_consumed": 0,
                        "user_id": user_id,
                        "user_input_tokens": 0,
                        "branch_id":branch_id
                    },
                    "test_cases_details": []
                }
            }
        })
    )


@router.post("/process_jira_project")
async def process_jira_project(req: ProcessRequest, request: Request):
    print("Recieved jira project processing request")
    project_id = request.headers.get("projectid")
    instance_name = req.instance_name
    client = get_sync_client()
    profile = os.getenv("PROFILE")
    mongo_db_name = f"optimize_{profile}_{req.license_id}" if profile else f"optimize_{req.license_id}"
    mongo_collection = client[mongo_db_name]["data_source_instances"]
    print("Status set to Processing")
    # Perform the update to "Processing"
    await asyncio.to_thread(
        mongo_collection.update_one,
        {"instanceName": instance_name, "projectId": project_id},
        {"$set": {"status": "Processing"}},
        upsert=True
    )

    await asyncio.sleep(2)

    # Perform the update to "Processed"
    await asyncio.to_thread(
        mongo_collection.update_one,
        {"instanceName": instance_name, "projectId": project_id},
        {"$set": {"status": "Processed"}},
        upsert=True
    )
    print("Status set to Processed")

    return {
        "responseCode": 200,
        "status": "SUCCESS",
        "message": f"{instance_name} has been processed successfully"
    }


@router.post("/jira-to-mtc")
async def temporary_mtc_via_jira(data: TempJiraPromptRequest):
    """
    Generate a single Manual Test Case (MTC) from one or more Jira tickets.
    Returns: {context_summary: str, manual_testcase: array}
    """
    user_id = data.user_id
    project_id = data.project_id
    jira_ids = data.jira_ids
    user_input = data.input or data.user_prompt or ""
    user_input += "\n\nNote: Please generate exactly 1 scenario and 1 test case only."
    prompt_type = data.prompt_type or "Web"
    license_id = data.license_id
    env = os.getenv("PROFILE")
    count = data.count
    ref_id = data.ref_id
    prompt_id = data.prompt_id
    jira_instance_id = data.jira_instance_id
    session_id = data.session_id
    summary = data.summary
    isAutomationScript=data.is_automation_steps
    serviceProvider = None
    model = None
    logger.info(f"Temp MTC request initiated | Endpoint: /jira-to-mtc")
    logger.info(f"Content Summary: {summary}")
    logger.info(f"Reference ID: {ref_id}")

    if not all([user_id, project_id]):
        return JSONResponse(
            status_code=200,
            content={
                "responseCode": 400,
                "status": "failure",
                "error_message": "Please send proper details"
            }
        )
    
    if count not in (1, 2, 3):
            return JSONResponse(
                status_code=200,
                content={
                    "responseCode": 400,
                    "status": "failure",
                    "error_message": "Invalid count value. Allowed values: 1, 2, 3"
                }
            )


    if not prompt_id:
        prompt_id = str(uuid.uuid4().hex)
    if not session_id:
        session_id = str(uuid.uuid4().hex)

    try:
        try:
            sp_config = resolve_service_provider(license_id, project_id)
        except Exception as e:
            return JSONResponse(
                status_code=200,
                content={
                    "responseCode": 400,
                    "status": "failure",
                    "error_message": f"Failed to fetch service provider details: {e}",
                }
            )

        apiKey = sp_config.get("apiKey")
        serviceProvider = sp_config.get("serviceProvider")
        model = sp_config.get("model")
        sa_info = sp_config.get("sa_info")
        resource = sp_config.get("resource")
        resourceId = sp_config.get("resourceId")

        try:
            val_result, message = validateApiKey(
                serviceProvider=serviceProvider,
                model=model,
                apiKey=apiKey,
                sa_info=sa_info,
                resourceId=resourceId,
            )
            logger.info(f"......result: {val_result}, {message}")
        except Exception as e:
            return JSONResponse(
                status_code=200,
                content={
                    "responseCode": 400,
                    "status": "failure",
                    "error_message": str(e)
                }
            )


        test_step_fields = ["Test Steps", "Step Input", "Expected Result"]
        json_structure = {
            "summary": "",
            "Test Cases": [
                {
                    "Test Steps": [{field: "" for field in test_step_fields}],
                }
            ]
        }

        mongoDb_license_id = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
        unique_id = "SCR" + str(uuid.uuid4().hex)
        dateTime = datetime.now(timezone.utc)
        
        file_content = None
        parsed_jira_ids = []
        user_name = None
        api_token = None
        domain = None

        if count == 1 and not ref_id:
            process_jira = True
            
            # Parse Jira IDs
            jira_id_list = []
            if isinstance(jira_ids, str):
                if "[" in jira_ids:
                    try:
                        jira_id_list = json.loads(jira_ids)
                    except:
                        jira_id_list = [jira_ids]
                elif "," in jira_ids:
                    jira_id_list = [j.strip() for j in jira_ids.split(",")]
                else:
                    jira_id_list = [jira_ids]
            elif isinstance(jira_ids, list):
                jira_id_list = jira_ids
                
            if not jira_id_list:
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": 400,
                        "status": "failure",
                        "error_message": "Jira ID is required!"
                    }
                )
            if len(jira_id_list) > 3:
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": 400,
                        "status": "failure",
                        "error_message": "Maximum of 3 Jira tickets allowed!"
                    }
                )

            jira_url_pattern = r"^https:\/\/[A-Za-z0-9\-]+\.atlassian\.net\/browse\/([A-Z][A-Z0-9]+-\d+)$"
            jira_key_pattern = r"^[A-Z0-9]+-\d+$"
            
            for j_id in jira_id_list:
                url_match = re.match(jira_url_pattern, str(j_id))
                if url_match:
                    parsed_jira_ids.append(url_match.group(1))
                else:
                    if not re.match(jira_key_pattern, str(j_id)):
                        return JSONResponse(
                            status_code=200, 
                            content={
                                "responseCode": 400,
                                "status": "failure",
                                "error_message": f"The format of given Jira ID or URL is invalid: {j_id}"
                            }
                        )
                    parsed_jira_ids.append(str(j_id))

            # Fetch Jira Credentials from data_source_instances collection
            # Strategy: Primary lookup by jira_instance_id (_id), with fallbacks by projectId and jiraProjectKey
            try:
                mongo_client = get_sync_client()

                profile = os.getenv("PROFILE")
                mongo_db_name = f"optimize_{profile}_{license_id}" if profile else f"optimize_{license_id}"
                mongo_collection = mongo_client[mongo_db_name]["data_source_instances"]

                found_project_info = None

                # Primary: Lookup by _id if jira_instance_id is provided
                if jira_instance_id:
                    logger.info(f"Primary lookup: Fetching Jira credentials by _id: {jira_instance_id}")
                    found_project_info = await asyncio.to_thread(
                        mongo_collection.find_one,
                        {"_id": jira_instance_id}
                    )
                    if found_project_info:
                        logger.info(f"Found Jira instance by _id: {jira_instance_id}")

                # Fallback 1: Lookup by projectId and instanceType
                if not found_project_info:
                    logger.info(f"Fallback 1: Fetching Jira credentials by projectId: {project_id} and instanceType: jira")
                    found_project_info = await asyncio.to_thread(
                        mongo_collection.find_one,
                        {"projectId": project_id, "instanceType": "jira"}
                    )
                    if found_project_info:
                        logger.info(f"Found Jira instance by projectId: {project_id}")

                # Fallback 2: Extract jiraProjectKey from the Jira ticket prefix and match
                if not found_project_info and parsed_jira_ids:
                    jira_project_key = parsed_jira_ids[0].split("-")[0] if "-" in parsed_jira_ids[0] else None
                    if jira_project_key:
                        logger.info(f"Fallback 2: Fetching Jira credentials by jiraProjectKey: {jira_project_key}")
                        found_project_info = await asyncio.to_thread(
                            mongo_collection.find_one,
                            {"jiraProjectKey": jira_project_key, "instanceType": "jira"}
                        )
                        if found_project_info:
                            logger.info(f"Found Jira instance by jiraProjectKey: {jira_project_key}")

                # mongo_client.close()
            except Exception as e:
                logger.error(f"Failed to fetch Jira credentials from DB: {e}")
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": 400,
                        "status": "failure",
                        "error_message": f"Failed to fetch Jira credentials from database: {e}"
                    }
                )

            if not found_project_info:
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": 400,
                        "status": "failure",
                        "error_message": f"No Jira data source instance found. Tried jira_instance_id: {jira_instance_id}, projectId: {project_id}, jiraProjectKey from tickets: {parsed_jira_ids}"
                    }
                )

            domain = found_project_info.get("domain")
            api_token = found_project_info.get("apiToken")
            user_name = found_project_info.get("userName")

            jira_generator = JiraDocGenerator(email=user_name, api_token=api_token, domain=domain)
            await jira_generator.authenticate()
        else:
            process_jira = False
            lookup_keys = []
            if ref_id:
                if isinstance(ref_id, str):
                    lookup_keys = [ref_id]
                elif isinstance(ref_id, list):
                    lookup_keys = [str(k) for k in ref_id if k]
            if not lookup_keys and prompt_id:
                lookup_keys = [str(prompt_id)]

            if not lookup_keys:
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": 400,
                        "status": "failure",
                        "error_message": "ref_id or prompt_id is required"
                    }
                )

            try:
                mtc_to_atc_col = manualTestCase.load_collection_for_mtc_to_atc(
                    license_id=mongoDb_license_id
                )
                docs = list(
                    mtc_to_atc_col.find(
                        {"ref_id": {"$in": lookup_keys}},
                        {"ref_id": 1, "summary": 1}
                    )
                )

                summary_map = {}
                for doc in docs:
                    summary_val = doc.get("summary")
                    if isinstance(summary_val, str):
                        summary_val = summary_val.strip()
                    if summary_val:
                        summary_map[doc["ref_id"]] = summary_val

                logger.info(
                    f"Successfully retrieved {len(summary_map)} stored summaries for ref_ids: {lookup_keys}"
                )

                if summary_map:
                    file_content = "\n\n".join(summary_map.values())
                else:
                    file_content = (file_content or "").strip()
                    if not file_content:
                        return JSONResponse(
                            status_code=200,
                            content={
                                "responseCode": 400,
                                "status": "failure",
                                "error_message": f"No stored summary found in mtc_to_atc for ref_ids: {lookup_keys}."
                            }
                        )
            except Exception as db_err:
                logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids {lookup_keys}: {db_err}")
                file_content = (file_content or "").strip()
                if not file_content:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "responseCode": 400,
                            "status": "failure",
                            "error_message": f"Failed to retrieve stored summary for ref_ids: {lookup_keys}"
                        }
                    )

        response = await manualTestCase.handle_user_input_for_jira(
            jira_ids=parsed_jira_ids,
            user_name=user_name,
            api_token=api_token,
            domain=domain,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            sa_info=sa_info,
            resourceId=resourceId,
            resource=resource,
            session_id=session_id,
            session_name=data.session_name,
            user_input=user_input,
            prompt_type=prompt_type,
            json_structure=json_structure,
            template=json_structure,
            template_keys=[],
            template_id=0,
            temp_header=[],
            file_content=file_content,
            start_time_total=time.time(),
            license_id=license_id,
            project_id=project_id,
            bearer_token=None,
            prompt_id=prompt_id,
            user_id=user_id,
            unique_id=unique_id,
            dateTime=dateTime,
            env=os.getenv("PROFILE"),
            branch_id=None,
            chatContext=summary,
            count=count,
            input_type="text",
            script_type="manual",
            is_modified=False,
            request_time_for_storing_1_tc_in_MD={"start_time": time.time(), "stored_time": None},
            return_generated_payload=True,
            process_jira=process_jira,
            isAutomationScript=isAutomationScript
        )
        logger.info(f"handle_user_input_for_jira response: {response}")

        if isinstance(response, dict):
            if response.get("success") is False:
                error_info = response.get("error", {})
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": error_info.get("code", 500),
                        "status": "failure",
                        "error_message": error_info.get("message", "Temporary Jira MTC Generation Failed")
                    }
                )
            if not isAutomationScript and "context_summary" in response:
                return JSONResponse(
                    status_code=200,
                    content={
                        "summary": response["context_summary"],
                        "ref_id": response["ref_id"]
                    }
                )
            if "testcases" in response or "manual_testcase" in response or "Test Cases" in response:
                summary = file_content if file_content else (response.get("summary", "") or response.get("context_summary", ""))
                payload = build_temporary_mtc_payload(summary, response)
                # payload["ref_id"] = prompt_id
                return JSONResponse(
                    status_code=200,
                    content=payload
					)

        return JSONResponse(
            status_code=200,
            content={
                "summary": "",
                "testcases": [],
                "ref_id": prompt_id
            }
        )

    except Exception as e:
        logger.error(f"Temporary Jira MTC Generation Failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content=build_error_response(e, model, serviceProvider)
        )

