from fastapi.responses import JSONResponse
from fastapi import APIRouter
from src.api.runtime import *  # noqa: F401,F403
import os , time , uuid , asyncio
router = APIRouter()
from qdrant_client.models import Filter, FieldCondition, MatchValue, NestedCondition
@router.get("/stream-generation")
async def stream_generation(
    request:    Request,        #use to check the client disconnection
    prompt_id:  str = Query(...),
    session_id: str = Query(...),
    license_id: str = Query(...),
    cursor:     int = Query(0, ge=0),
):
    """
    SSE Events:
        data: {full_mtc_document}   one MTC in ascending mtc_index order
        event: EOF                  generation complete
        event: CANCELLED            generation terminated by user
        event: ERROR                fatal error

    cursor = last received mtc_index
    """
    if not prompt_id.strip():  raise HTTPException(400, "prompt_id required")
    if not session_id.strip(): raise HTTPException(400, "session_id required")
    if not license_id.strip(): raise HTTPException(400, "license_id required")

    return StreamingResponse(
        event_generator(request, license_id, prompt_id, session_id, cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control"    : "no-cache",
            "Connection"       : "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/terminate-mtc-generation")
async def terminate_mtc_generation(data: TerminateMtcGenerationRequest):
    """
    Stop an in-progress manual testcase generation job by prompt_id.
    Already-persisted testcases are kept; pending LLM batches are cancelled.
    """
    prompt_id = (data.prompt_id or "").strip()
    license_id = (data.license_id or "").strip()

    if not prompt_id:
        raise HTTPException(400, "prompt_id required")
    if not license_id:
        raise HTTPException(400, "license_id required")

    env = os.getenv("PROFILE")
    mongoDb_license_id = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"

    try:
        collection_prompt = manualTestCase.load_collection_for_user_prompt(license_id=mongoDb_license_id)

        # Resolve latest job for this prompt_id only
        prompt_doc = collection_prompt.find_one(
            {"prompt_id": prompt_id},
            sort=[("created_at", -1)],
        )

        if prompt_doc is None:
            cancelled_ids = request_cancel_by_prompt(prompt_id)
            if not cancelled_ids:
                raise HTTPException(404, "No generation job found for the given prompt_id")
            return JSONResponse(
                status_code=200,
                content={
                    "message": "SUCCESS",
                    "responseCode": 200,
                    "responseObject": {
                        "prompt_id": prompt_id,
                        "unique_id": cancelled_ids[0],
                        "generation_status": "cancelled",
                        "detail": "Termination requested (job not found in DB; in-memory cancel applied).",
                    },
                },
            )

        unique_id = prompt_doc.get("_id")
        current_status = prompt_doc.get("generation_status")
        already_complete = bool(prompt_doc.get("is_complete"))

        if already_complete and current_status in ("completed", "failed", "cancelled"):
            return JSONResponse(
                status_code=200,
                content={
                    "message": "SUCCESS",
                    "responseCode": 200,
                    "responseObject": {
                        "prompt_id": prompt_id,
                        "unique_id": unique_id,
                        "generation_status": current_status or ("completed" if already_complete else "unknown"),
                        "detail": f"Generation already finished with status '{current_status}'.",
                    },
                },
            )

        known = manualTestCase.request_generation_cancel(
            unique_id=unique_id,
            license_id=mongoDb_license_id,
        )
        # Also cancel any other in-memory workers for the same prompt_id
        request_cancel_by_prompt(prompt_id)

        logger.info(
            f"Terminate MTC generation | prompt_id={prompt_id} "
            f"unique_id={unique_id} known_in_memory={known}"
        )

        return JSONResponse(
            status_code=200,
            content={
                "message": "SUCCESS",
                "responseCode": 200,
                "responseObject": {
                    "prompt_id": prompt_id,
                    "unique_id": unique_id,
                    "generation_status": "cancelled",
                    "detail": "Termination requested. Already generated testcases are retained.",
                },
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to terminate MTC generation: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to terminate generation: {e}")


@router.post("/generate-prompt")
async def savePrompt(data: GeneratePromptRequest):
    user_input = data.input + (data.file_name if data.file_name else "")
    logger.info(f"User input--------- {user_input}")
    user_id = data.user_id
    project_id = data.project_id
    session_id = data.session_id
    prompt_id = data.prompt_id
    license_id = data.license_id
    input_type = data.input_type
    env = os.getenv("PROFILE")
    count = data.count
    script_type = data.script_type
    bearer_token = data.bearer_token
    file_name = data.file_name
    file_content = data.file_content
    is_modified = data.is_modified
    user_input_tokens = count_tokens(data.input or "")
    session_name = data.session_name
    prompt_type = data.prompt_type
    summary = data.summary
    
    input_info = data.input_info
    branch_id = data.branch_id
    request_time_for_storing_1_tc_in_MD = {
        "start_time": time.time(),
        "stored_time": None
    }
    logger.info(f"Main MTC request initiated | Endpoint: /generate-prompt")
    logger.info(f"ContentSummary: {summary}")

    if not prompt_id:
        prompt_id = str(uuid.uuid4().hex)

    if not session_id:
        session_id = str(uuid.uuid4().hex)

    value = "SCR"
    unique_id = value + str(uuid.uuid4().hex)
    dateTime = datetime.now(timezone.utc)
    if env:
        mongoDb_license_id = f"optimize_{env}_{license_id}"
    else:
        mongoDb_license_id = f"optimize_{license_id}"

    apiKey = None
    serviceProvider = None
    model = None
    sa_info = None  

    try:
        if not all([user_id, project_id]):
            raise APIError(responseCode=400, message="Please send proper details")
        if count not in [1, 2, 3]:
            raise APIError(responseCode=400, message="Invalid count value. Allowed values: 1, 2, 3")

        try:
            sp_config = resolve_service_provider(license_id, project_id)
        except Exception as e:
            logger.warning(f"Failed While Fetching the serviceProviderInstance: {e}")
            raise APIError(
                responseCode=400,
                message=f"Failed to fetch service provider details: {e}"
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

        try:
            template = manualTestCase.fetch_test_case_template(license_id, project_id)
            logger.info("Template Fetched Successfully")
        except Exception as e:
            raise APIError(
                responseCode=400,
                message=f"Template Fetching Failed:{e}"
            )

        template_id = template['_id']
        logger.info(f"template_id: {template_id}")
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

        manualTestCase.initialize_db_and_collections(
            license_id=mongoDb_license_id,
            unique_id=unique_id,
            dateTime=dateTime,
            session_id=session_id,
            session_name=session_name,
            user_input=user_input,
            project_id=project_id,
            prompt_id=prompt_id,
            user_id=user_id,
            count=count,
            script_type=script_type,
            input_type=input_type,
            user_input_tokens=user_input_tokens,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            prompt_type=prompt_type,
            llm_error_response=None,
            branch_id=branch_id,
        )

        asyncio.create_task(manualTestCase.handle_user_input(
            user_input=user_input,
            session_id=session_id,
            session_name=session_name,
            count=count,
            license_id=license_id,
            project_id=project_id,
            bearer_token=bearer_token,
            prompt_id=prompt_id,
            user_id=user_id,
            input_type=input_type,
            script_type=script_type,
            file_name=file_name,
            file_content=file_content,
            is_modified=is_modified,
            user_input_tokens=user_input_tokens,
            images_path=None,
            image_content=None,
            template_id=template_id,
            unique_id=unique_id,
            dateTime=dateTime,
            original_template=template,
            template=json_structure,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            prompt_type=prompt_type,
            sa_info=sa_info,
            resourceId=resourceId,
            resource=resource,
            env=env,
            video_name=None,
            video_content=None,
            request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
            branch_id=branch_id,
            chatContext=summary,
        ))

    except Exception as e:
        logger.error(f"Error in generate-prompt pipeline: {str(e)}", exc_info=True)
        try:
            # Ensure the database document is initialized first
            manualTestCase.initialize_db_and_collections(
                license_id=mongoDb_license_id,
                unique_id=unique_id,
                dateTime=dateTime,
                session_id=session_id,
                session_name=session_name,
                user_input=user_input,
                project_id=project_id,
                prompt_id=prompt_id,
                user_id=user_id,
                count=count,
                script_type=script_type,
                input_type=input_type,
                user_input_tokens=user_input_tokens,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                llm_error_response=str(e),
                branch_id=branch_id,
            )
            # Record the error details in MongoDB
            manualTestCase.save_generation_error(
                unique_id=unique_id,
                error=e,
                license_id=mongoDb_license_id,
                service_provider=serviceProvider
            )
        except Exception as db_err:
            logger.error(f"Failed to record generate-prompt error in DB: {db_err}", exc_info=True)

    return JSONResponse(
        status_code=202,
        content=jsonable_encoder({
            "message": "SUCCESS",
            "responseCode": 200,
            "responseObject": {
                "data": {
                    "prompt_document": {
                        "_id": unique_id,
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
                        "prompt": user_input,
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
                        "branch_id": branch_id,
                    },
                    "test_cases_details": []
                }
            }
        })
    )

@router.post("/prompt-to-mtc")
async def temporary_mtc_via_prompt(data: GeneratePromptRequest):
    user_input = data.input + (data.file_name if data.file_name else "")
    logger.info(f"User input--------- {user_input}")
    user_id = data.user_id
    project_id = data.project_id
    session_id = data.session_id
    prompt_id = data.prompt_id
    license_id = data.license_id
    input_type = data.input_type
    env = os.getenv("PROFILE")
    count = data.count
    script_type = data.script_type
    file_name = ""
    file_input = ""
    is_modified = data.is_modified
    summary=data.summary
    user_input_tokens = count_tokens(data.input)
    session_name = data.session_name
    logger.info(f"Temp MTC request initiated | Endpoint: /prompt-to-mtc")
    logger.info(f"ContentSummary: {summary}")
    isAutomationScript=data.is_automation_steps

    if not prompt_id:
        prompt_id = str(uuid.uuid4().hex)

    if not session_id:
        session_id = str(uuid.uuid4().hex)

    if not all([user_id, project_id, license_id]):
        return JSONResponse(
            status_code=200,
            content={
                "status": "failure",
                "responseCode": 400, 
                "error_message": "user_id, project_id and license_id are required",
            }
        )
    
    if count not in [1, 2, 3]:
        return JSONResponse(
            status_code=200,
            content={
                "status": "failure",
                "responseCode": 400, 
                "error_message": "Invalid count value. Allowed values: 1, 2, 3",
            }
        )
    try:
        sp_config = resolve_service_provider(license_id, project_id)
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
                "status": "failure",
                "responseCode": 400, 
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
        errorResponse= build_api_error(e, serviceProvider)
        errorMessage=errorResponse.message
        return JSONResponse(status_code=200, content={"status": "failure", "responseCode": 400, "error_message": errorMessage})

    prompt_type = data.prompt_type
    branch_id = data.branch_id
    images_path = None
    image_content = None

    request_time_for_storing_1_tc_in_MD = {
    "start_time": time.time(),
    "stored_time": None
    }

    test_step_fields = ["Test Steps", "Step Input", "Expected Result"]
    json_structure = {
        "summary":"",
        "Test Cases": [
            {
                "Test Steps": [{field: "" for field in test_step_fields}],
            }
        ]
    }

    unique_id = "SCR" + str(uuid.uuid4().hex)
    dateTime=datetime.now(timezone.utc)
    if env:
        mongoDb_license_id = f"optimize_{env}_{license_id}"
    else:
        mongoDb_license_id = f"optimize_{license_id}"

    if env :
        COLLECTION_NAME = f"ff_cloud_{env}_{license_id}_{project_id}"
    else :
        COLLECTION_NAME = f"ff_cloud_{license_id}_{project_id}"


    if not isAutomationScript and data.file_name and data.file_name.strip():
        sum_file_name = data.file_name.strip()
        records, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="chunk_index",
                    match=MatchValue(value=-1)
                )
            ]
        ),
        limit=10,
        with_payload=True,
        with_vectors=False)

        full_description = None
        for record in records:
            files = record.payload.get("files", [])
            for file_info in files:
                if file_info.get("fileName", "").strip() == sum_file_name:
                    full_description = file_info.get("full_description")
                    break
            if full_description:
                break
        return JSONResponse(
                status_code=200,
                content={
                    "summary": full_description,
                    "ref_id": prompt_id
                }
            )
    
    try:
        response = await manualTestCase.handle_user_input(
            user_input=user_input,
            session_id=session_id,
            session_name=session_name,
            count=count,
            license_id=license_id,
            project_id=project_id,
            prompt_id=prompt_id,
            user_id=user_id,
            input_type=input_type,
            script_type=script_type,
            file_name=file_name,
            file_content=file_input,
            is_modified=is_modified,
            user_input_tokens=user_input_tokens,
            images_path=images_path,
            image_content=image_content,
            template_id=0,
            unique_id=unique_id,
            dateTime=dateTime,
            original_template=json_structure,
            template=json_structure,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            prompt_type=prompt_type,
            sa_info=sa_info,
            env=env,
            request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
            return_generated_payload=True,
            branch_id=branch_id,
            video_name=None,
            resourceId=resourceId,
            resource=resource,
            video_content=None,
            Input_Token_Video=None,
            Output_Token_Video=None,
            chatContext=summary
        )

        if isinstance(response, dict):
            if response.get("success") is False:
                error_info = response.get("error", {})
                return JSONResponse(
                    status_code=error_info.get("code", 500),
                    content={
                        "responseCode": error_info.get("code", 500),
                        "responseObject": None,
                        "status": "failure",
                        "error_message": error_info.get("message", "Temporary Prompt MTC Generation Failed")
                    }
                )
            if "testcases" in response or "manual_testcase" in response or "Test Cases" in response:
                summary_text = summary or response.get("summary", "") or response.get("context_summary", "") or ""
                payload = build_temporary_mtc_payload(summary_text, response)
                return JSONResponse(status_code=200, content=payload)

        return JSONResponse(
            status_code=200,
            content={
                "summary": "",
                "testcases": [],
                "ref_id": prompt_id
            }
        )

    except Exception as e:
        logger.error(f"Temporary Prompt MTC Generation Failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content=build_error_response(e, model, serviceProvider)
        )




