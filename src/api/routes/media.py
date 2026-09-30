from fastapi import APIRouter
from src.api.runtime import *  # noqa: F401,F403
import os , time , uuid , asyncio , json , shutil

router = APIRouter()

@router.post("/image-mtc-generation")
async def image_preprocessing(request: ImagePreprocessingRequest, background_tasks: BackgroundTasks):

    user_id = request.user_id
    branch_id = request.branch_id
    project_id = request.project_id
    license_id = request.license_id
    bearer_token = request.bearer_token
    user_input = request.input
    session_id = request.session_id
    prompt_id = request.prompt_id
    input_type = request.input_type
    script_type = request.script_type
    is_modified = request.is_modified
    session_name = request.session_name
    image_content = request.image_content
    count = request.count
    prompt_type = request.prompt_type
    summary=request.summary
    ref_id = request.ref_id
    env = os.getenv("PROFILE")
    user_input_tokens = count_tokens(user_input)
    request_time_for_storing_1_tc_in_MD = {
        "start_time": time.time(),
        "stored_time": None
    }
    logger.info(f"Main MTC request initiated | Endpoint: /image-mtc-generation")
    logger.info(f"Content Summary: {summary}")
    logger.info(f"Reference ID: {ref_id}")

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

    model=None
    sa_info = None
    resource = None
    resourceId = None
    apiKey = None
    serviceProvider = None

    try:
        try:
            count = int(count)
        except:
            raise APIError(responseCode=400, message="Count must be an integer.")

        if count not in [1, 2, 3]:
            raise APIError(responseCode=400, message="Invalid count value. Allowed values: 1, 2, 3")
        
        if not ref_id:
            raise APIError(responseCode=400, message="Unable to generate testcases. Please re-upload the Image and try again")


        try:
            sp_config = resolve_service_provider(license_id, project_id)
        except Exception as e:
            raise APIError(responseCode=400, message=f"Failed to fetch service provider details: {e}")

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

        start_time = time.time()
        
        try:
            template = manualTestCase.fetch_test_case_template(license_id, project_id)
            logger.info("Template Fetched Successfully")
        except Exception as e:
            raise APIError(responseCode=400, message=f"Template Fetching Failed:{e}")

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
            "summary":"",
            "Test Cases": [
                {
                    **{field: "" for field in test_case_fields},
                    "Test Steps": [{field: "" for field in test_step_fields}],
                    "testCaseType":"",
                }
            ]
        }
        end_time = time.time()  # end timestamp
        duration = end_time - start_time
        logging.info(f"FetchingTemplate Timing | Duration: {duration:.3f}s")

        Image_Input_token = 0
        Image_Output_token = 0

        images_data = []
        lookup_keys = []
        if ref_id:
            if isinstance(ref_id, str):
                lookup_keys = [ref_id]
            elif isinstance(ref_id, list):
                lookup_keys = [str(k) for k in ref_id if k]
        if not lookup_keys and prompt_id:
            lookup_keys = [str(prompt_id)]

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
                image_content = "\n\n".join(summary_map.values())
            else:
                image_content = (image_content or "").strip()
                if not image_content:
                    logger.error(f"No stored summary found in mtc_to_atc for ref_ids: {lookup_keys} and prompt_id: {prompt_id}.")
                    raise APIError(
                        responseCode=400,
                        message=f"Unable to generate test cases. Please re-upload the Image and try again."
                    )
        except APIError:
            raise
        except Exception as db_err:
            logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids {lookup_keys} and prompt_id {prompt_id}: {db_err}")
            image_content = (image_content or "").strip()
            if not image_content:
                logger.error(f"Failed to retrieve stored summary for ref_ids: {lookup_keys} and prompt_id: {prompt_id}.")
                raise APIError(responseCode=400, message=f"Unable to generate test cases. Please re-upload the Image and try again.")

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
            images_path=[],  # Will be populated by the background task
            user_input_tokens=user_input_tokens,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            prompt_type=prompt_type,
            branch_id=branch_id
        )

        def run_image_task_in_background():
            asyncio.run(manualTestCase.handle_user_input_for_image(
                session_id=session_id,
                license_id=license_id,
                project_id=project_id,
                bearer_token=bearer_token,
                template=json_structure,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                resourceId=resourceId,
                resource=resource,
                prompt_type=prompt_type,
                sa_info=sa_info,
                user_input=user_input,
                session_name=session_name,
                count=count,
                prompt_id=prompt_id,
                user_id=user_id,
                input_type=input_type,
                script_type=script_type,
                is_modified=is_modified,
                user_input_tokens=user_input_tokens,
                images_data=images_data,
                image_content=image_content,
                template_id=template_id,
                unique_id=unique_id,
                dateTime=dateTime,
                original_template=template,
                env=env,
                Image_Input_token=Image_Input_token,
                Image_Output_token=Image_Output_token,
                request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
                branch_id=branch_id,
                chatContext=summary
            ))

        background_tasks.add_task(run_image_task_in_background)


    except Exception as e:
        logger.error(f"Image Generation Pipeline Error: {str(e)}", exc_info=True)
        try:
            accumulated_input_tokens = 0
            accumulated_output_tokens = 0
            if 'Image_Input_token' in locals():
                accumulated_input_tokens += locals().get('Image_Input_token', 0) or 0
            if 'Image_Output_token' in locals():
                accumulated_output_tokens += locals().get('Image_Output_token', 0) or 0
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
                images_path=[],
                user_input_tokens=user_input_tokens,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                branch_id=branch_id
            )
            # Record the error details in MongoDB
            manualTestCase.save_generation_error(
                unique_id=unique_id,
                error=e,
                license_id=mongoDb_license_id,
                service_provider=serviceProvider,
                input_tokens=accumulated_input_tokens,
                output_tokens=accumulated_output_tokens
            )
        except Exception as db_err:
            logger.error(f"Failed to record Image Generation error in DB: {db_err}", exc_info=True)

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
                        "branch_id":branch_id
                    },
                    "test_cases_details": []
                }
            }
        })
    )
    
@router.post("/image-to-mtc")
async def temporary_mtc_via_image(request: TempImagePreprocessingRequest):
    user_id = request.user_id
    project_id = request.project_id
    license_id = request.license_id
    bearer_token = request.bearer_token
    user_input = request.input or ""
    session_id = request.session_id
    prompt_id = request.prompt_id
    input_type = request.input_type
    script_type = request.script_type
    is_modified = request.is_modified
    session_name = request.session_name
    image_content = request.image_content
    count = request.count
    prompt_type = request.prompt_type
    service_accounts = getattr(request, 'service_accounts', None)
    summary = request.summary
    ref_id = request.ref_id
    isAutomationScript=request.is_automation_steps
    
    logger.info(f"Temp MTC request initiated | Endpoint: /image-to-mtc")
    logger.info(f"Content Summary: {summary}")
    logger.info(f"Reference ID: {ref_id}")

    raw_attachments = request.attachment_ids or []
    if isinstance(raw_attachments, str):
        attachment_ids = [raw_attachments]
    elif isinstance(raw_attachments, list):
        attachment_ids = []
        for item in raw_attachments:
            if isinstance(item, list):
                attachment_ids.extend(item)
            elif item:
                attachment_ids.append(str(item))
    else:
        attachment_ids = []

    env = os.getenv("PROFILE")
    user_input += "\n\nNote: Please generate exactly 1 scenario and 1 test case only."
    user_input_tokens = count_tokens(user_input)

    try:
        sp_config = resolve_service_provider(license_id, project_id)
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
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
        return JSONResponse(status_code=200, content={"status": "failure", "error_message": str(e)})

    request_time_for_storing_1_tc_in_MD = {
        "start_time": time.time(),
        "stored_time": None
    }
    logger.info("Stepping Into temporary mtc via image")
    if service_accounts:
        try:
            service_accounts = json.loads(service_accounts)
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=200,
                content={"status": "failure",
                         "error_message": "Invalid service_accounts JSON"}
                )


    if not prompt_id:
        prompt_id = str(uuid.uuid4().hex)
    dateTime = datetime.now(timezone.utc)

    if not all([user_id, project_id]):
        return JSONResponse(
            status_code=200,
            content={"status": "failure", "error_message": "Please send proper details"}
        )

    mongoDb_license_id = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"

    test_step_fields = ["Test Steps", "Step Input", "Expected Result"]
    json_structure = {
        "summary": "",
        "Test Cases": [
            {
                "Test Steps": [{field: "" for field in test_step_fields}],
            }
        ]
    }
    images_data = []
    Image_Input_token = 0
    Image_Output_token = 0


    try:
        # 1) Resolve image summary only (never generate MTC from raw images)
        if count == 1 and not ref_id:
            if isinstance(attachment_ids, str):
                attachment_ids = [attachment_ids]
            elif not attachment_ids:
                attachment_ids = []
            for file_content_id in attachment_ids:
                try:
                    image_bytes, ext, filename = fetch_image(file_content_id, license_id)
                except RuntimeError as e:
                    return JSONResponse(
                        status_code=200,
                        content={"status": "failure", "error_message": str(e)}
                    )
                
                if not validate_image_extension(ext):
                    return JSONResponse(
                        status_code=200,
                        content={
                            "responseCode": 400,
                            "responseObject": None,
                            "error_message": f"Invalid file type: {filename}. Only PNG/JPG/JPEG supported."
                        }
                    )
                images_data.append({"filename": filename, "bytes": image_bytes})

            if not images_data:
                return JSONResponse(
                    status_code=200,
                    content={"status": "failure", "error_message": "No image attachments provided. Please upload valid images."}
                )

            valid_images_data = []
            
            for img_info in images_data:
                file_bytes = img_info["bytes"]
                if not is_blank_image_bytes(file_bytes):
                    valid_images_data.append(img_info)

            if not valid_images_data:
                return JSONResponse(
                    status_code=200, 
                    content={"status": "failure", "error_message": "The uploaded images are Blank. Please upload valid images."}
                )

            try:
                # Detect irrelevant images and get openai formatted content
                image_content, valid_images, det_in_t, det_out_t = await detect_irrelevant_images(
                    valid_images_data, 
                    user_input, 
                    serviceProvider, 
                    apiKey, 
                    model, 
                    sa_info=sa_info, 
                    resource=resource, 
                    resourceId=resourceId
                )
                Image_Input_token += det_in_t
                Image_Output_token += det_out_t
                
                # Summarize images
                image_content, sum_in_t, sum_out_t = await summarize_images(
                    image_content, 
                    serviceProvider, 
                    apiKey, 
                    model, 
                    sa_info=sa_info, 
                    resource=resource, 
                    resourceId=resourceId
                )
                Image_Input_token += sum_in_t
                Image_Output_token += sum_out_t
                
            except Exception as e:
                logger.error(f"Error in image preprocessing pipeline: {e}")
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": error_info.get("code", 500),
                        "responseObject": None,
                        "error_message": error_info.get("message", "Image summary generation failed")
                    }
                )

            images_data = []
            try:
                manualTestCase.initialize_db_and_collections_mtc_to_atc(
                    license_id=mongoDb_license_id,
                    unique_id=prompt_id,
                    content=image_content
                )
                logger.info(
                    f"Successfully stored preprocessed image summary for prompt_id: {prompt_id} in user_mtc_to_atc"
                )
            except Exception as db_store_err:
                logger.error(f"Failed to store preprocessed image summary in user_mtc_to_atc: {db_store_err}")
        else:
            lookup_keys = []
            if ref_id:
                if isinstance(ref_id, str):
                    lookup_keys = [ref_id]
                elif isinstance(ref_id, list):
                    lookup_keys = [str(k) for k in ref_id if k]
            if not lookup_keys and prompt_id:
                lookup_keys = [str(prompt_id)]

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
                    image_content = "\n\n".join(summary_map.values())
                else:
                    image_content = (image_content or "").strip()
                    if not image_content:
                        return JSONResponse(
                            status_code=200,
                            content={"status": "failure", "error_message": f"No stored summary found in mtc_to_atc for ref_ids: {lookup_keys}."}
                        )
            except Exception as db_err:
                logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids {lookup_keys}: {db_err}")
                image_content = (image_content or "").strip()
                if not image_content:
                    return JSONResponse(
                        status_code=200,
                        content={"status": "failure", "error_message": f"Failed to retrieve stored summary for ref_ids: {lookup_keys}"}
                    )
        if not isAutomationScript:
            preprocessing_tokens = Image_Input_token + Image_Output_token
            if preprocessing_tokens > 0 and serviceProvider == "DefaultFireFlink":
                try:
                    await update_ai_service_instance_token_usage(
                        mongo_url=None,
                        license_id=license_id,
                        service_provider=serviceProvider,
                        tokens=preprocessing_tokens
                    )
                    logger.info(f"Stage 1 token deduction | Endpoint: /image-to-mtc | tokens={preprocessing_tokens} | serviceProvider={serviceProvider}")
                except Exception as deduction_err:
                    logger.error(f"Failed to deduct preprocessing tokens in /image-to-mtc Stage 1: {deduction_err}")
            return JSONResponse(
                status_code=200,
                content={
                    "summary": image_content,
                    "ref_id": prompt_id
                }
            )


        # 2) Generate MTC from summary + user_input (skip image reprocessing)
        response = await manualTestCase.handle_user_input_for_image(
            session_id=session_id,
            license_id=license_id,
            project_id=project_id,
            bearer_token=bearer_token,
            template=json_structure,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            resourceId=resourceId,
            resource=resource,
            prompt_type=prompt_type,
            sa_info=sa_info,
            user_input=user_input,
            session_name=session_name,
            count=count,
            prompt_id=prompt_id,
            user_id=user_id,
            input_type=input_type,
            script_type=script_type,
            is_modified=is_modified,
            user_input_tokens=user_input_tokens,
            images_data=[],
            image_content=image_content,
            template_id=0,
            unique_id=prompt_id,
            chatContext=summary,
            dateTime=dateTime,
            original_template=json_structure,
            env=env,
            branch_id=None,
            Image_Input_token=Image_Input_token,
            Image_Output_token=Image_Output_token,
            request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
            return_generated_payload=True,
            context_summary=image_content,
        )

        if isinstance(response, dict):
            if response.get("success") is False:
                error_info = response.get("error", {})
                return JSONResponse(
                    status_code=200,
                    # status_code=error_info.get("code", 500),
                    content={
                        "responseCode": error_info.get("code", 500),
                        "responseObject": None,
                        "error_message": error_info.get("message", "Temporary Image MTC Generation Failed")
                    }
                )
            if "testcases" in response or "manual_testcase" in response or "Test Cases" in response:
                # Prefer image UI summary for response + input-field detection
                summary_text = (
                    (image_content or "").strip()
                    or response.get("summary", "")
                    or response.get("context_summary", "")
                    or ""
                )
                payload = build_temporary_mtc_payload(
                    summary_text,
                    response,
                    input_check_text=f"{summary_text}\n{user_input or ''}",
                )
                # payload["ref_id"] = prompt_id
                return JSONResponse(status_code=200, content=payload)

        return JSONResponse(
            status_code=200,
            content={
                "summary": "",
                "testcases": [],
                "ref_id": prompt_id
            }
        )
    except APIError as e:

        logger.info(
            f"Temporary Image MTC Generation Failed : {e.message}",
            exc_info=True
        )

        return JSONResponse(
            status_code=200,
            content={
                "responseCode": 500,
                "status": "failure",
                "error_message": e.message
            }
        )
    except Exception as e:
        logger.error(f"Temporary Image MTC Generation Failed : {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content={
                "responseCode": 500,
                "responseObject": None,
                "error_message": str(e)
            }
        )

@router.post("/file-mtc-generation")
async def file_upload(request: FileUploadRequest):
    user_id = request.user_id
    license_id = request.license_id
    project_id = request.project_id
    branch_id = request.branch_id
    session_id = request.session_id
    session_name = request.session_name
    prompt_id = request.prompt_id
    ref_id = request.ref_id
    input_type = request.input_type
    user_input = request.input or ""
    prompt_type = request.prompt_type
    count = request.count
    file_name = request.file_name
    summary = request.summary
    script_type = request.script_type
    is_modified = request.is_modified
    file_content = ""


    logger.info(f"Main MTC request initiated | Endpoint: /file-mtc-generation")
    logger.info(f"Content Summary: {summary}")
    logger.info(f"Reference ID: {ref_id}")
    
    env = os.getenv("PROFILE")
    user_input_tokens = count_tokens(user_input)
    request_time_for_storing_1_tc_in_MD = {
        "start_time": time.time(),
        "stored_time": None
    }

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
    resourceId = None
    resource = None

    try:
        if not all([user_id, project_id]):
            raise APIError(responseCode=400, message="Please send proper details")
        if count not in [1, 2, 3]:
            raise APIError(responseCode=400, message="Invalid count value. Allowed values: 1, 2, 3")
        if not ref_id:
            raise APIError(responseCode=400, message="Unable to generate testcases. Please re-upload the File and try again")

        try:
            sp_config = resolve_service_provider(license_id, project_id)
        except Exception as e:
            logger.warning(f"Failed While Fetching the Instance: {e}")
            raise 

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

        start_time = time.time()
        try:
            logger.info("Fetching Template")
            template = manualTestCase.fetch_test_case_template(license_id, project_id)
        except Exception as e:
            logger.error(f"Template Fetching Failed: {e}", exc_info=True)
            raise 

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
        end_time = time.time()
        duration = end_time - start_time
        logging.info(f"FetchingTemplate Timing | Duration: {duration:.3f}s")

        lookup_keys = []
        if ref_id:
            if isinstance(ref_id, str):
                lookup_keys = [ref_id]
            elif isinstance(ref_id, list):
                lookup_keys = [str(k) for k in ref_id if k]
        if not lookup_keys and prompt_id:
            lookup_keys = [str(prompt_id)]

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
                    logger.error(f"No stored summary found in mtc_to_atc for ref_ids: {lookup_keys} and prompt_id: {prompt_id}")
                    raise APIError(
                        responseCode=400,
                        message="Unable to generate test cases. Please re-upload the File and try again."
                    )
        except APIError:
            raise
        except Exception as db_err:
            logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids: {lookup_keys} and prompt_id:{prompt_id} | Error: {db_err}")
            file_content = (file_content or "").strip()
            if not file_content:
                logger.error(f"Failed to retrieve stored summary for ref_ids: {lookup_keys} and prompt_id: {prompt_id}")
                raise APIError(responseCode=400, message="Unable to generate test cases. Please re-upload the File and try again")

        logger.info("InitializingDb/Collections")
        try:
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
                file_name=file_name,
                file_content=file_content, 
                user_input_tokens=user_input_tokens,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                branch_id=branch_id
            )
            logger.info("InitializingDb/Collections Successful")
        except Exception as e:
            logger.error(f"InitializingDb/Collections Failed: {e}", exc_info=True)
            raise 

        logger.info("Received request to generate MTC Trigger")
        try:
            asyncio.create_task(
                manualTestCase.handle_user_input_for_file(
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
                    template=json_structure,
                    original_template=template,
                    template_id=template_id,
                    input_type=input_type,
                    user_input=user_input,
                    user_input_tokens=user_input_tokens,
                    file_name=file_name,
                    file_content=file_content,
                    chatContext=summary,
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
                    request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
                )
            )
        except Exception as e:
            logger.exception(f"Failed to create background task for MTC generation: {str(e)}")
            raise

    except Exception as e:
        logger.error(f"Error in /file-mtc-generation pipeline: {str(e)}", exc_info=True)
        try:
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
                file_name=file_name,
                file_content="",
                user_input_tokens=user_input_tokens,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                branch_id=branch_id
            )
            manualTestCase.save_generation_error(
                unique_id=unique_id,
                error=e,
                license_id=mongoDb_license_id,
                service_provider=serviceProvider,
            )
        except Exception as db_err:
            logger.error(
                f"Failed to record /upload-file error in DB: {db_err}", exc_info=True
            )

    # ── Always return 202 — front-end polls MongoDB for the actual result ──────
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
                        "branch_id":branch_id
                    },
                    "test_cases_details": [],
                }
            },
        })
    )

@router.post("/file-to-mtc")
async def temporary_mtc_via_file(request: TempFileUploadRequest):
    user_id = request.user_id
    license_id = request.license_id
    project_id = request.project_id
    branch_id = request.branch_id
    session_id = request.session_id
    session_name = request.session_name
    prompt_id = request.prompt_id
    ref_id = request.ref_id
    input_type = request.input_type
    user_input = request.input or ""
    prompt_type = request.prompt_type
    count = request.count
    file_name = request.file_name
    raw_attachments = request.attachment_ids or []
    summary = request.summary
    isAutomationScript = request.is_automation_steps
    file_content = ""
    serviceProvider = None
    model = None
    logger.info(f"Temp MTC request initiated | Endpoint: /file-to-mtc")
    logger.info(f"Content Summary: {summary}")
    logger.info(f"Reference ID: {ref_id}")
    
    if isinstance(raw_attachments, str):
        attachment_ids = [raw_attachments]
    elif isinstance(raw_attachments, list):
        attachment_ids = []
        for item in raw_attachments:
            if isinstance(item, list):
                attachment_ids.extend(item)
            elif item:
                attachment_ids.append(str(item))
    else:
        attachment_ids = []

    user_input += "\n\nNote: Please generate exactly 1 scenario and 1 test case only."
    user_input_tokens = count_tokens(user_input)

    if not prompt_id:
        prompt_id = str(uuid.uuid4().hex)

    if not session_id:
        session_id = str(uuid.uuid4().hex)

    unique_id = str(uuid.uuid4().hex)
    dateTime = datetime.now(timezone.utc)
    env = os.getenv("PROFILE")
    mongoDb_license_id = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"

    if not all([user_id, project_id]):
        return JSONResponse(
            status_code=200,
            content={
                "responseCode": 400,
                "status": "failure",
                "error_message": "Please send proper details"
            }
        )

    try:
        sp_config = resolve_service_provider(license_id, project_id)
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
                "responseCode": 400,
                "status": "failure",
                "error_message": f"Failed to fetch service provider details: {e}"
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

    if count not in (1, 2, 3):
        return JSONResponse(
            status_code=200,
            content={
                "responseCode": 400,
                "status": "failure",
                "error_message": "Invalid count value. Allowed values: 1, 2, 3"
            }
        )

    if count == 1 and not ref_id and not attachment_ids:
        return JSONResponse(
            status_code=200,
            content={
                "responseCode": 400,
                "status": "failure",
                "error_message": "File attachment ID is required when count = 1 and ref_id is not provided"
            }
        )

    request_time_for_storing_1_tc_in_MD = {
        "start_time": time.time(),
        "stored_time": None
    }
    test_step_fields = ["Test Steps", "Step Input", "Expected Result"]
    json_structure = {
        "summary": "",
        "Test Cases": [
            {
                "Test Steps": [{field: "" for field in test_step_fields}],
            }
        ]
    }

    try:
        imgs_ip_tokens = imgs_op_tokens = file_ip_tokens = file_op_tokens = 0
        # 1) Resolve file summary only (never generate MTC from raw file)
        if count == 1 and not ref_id:
            file_content_id = attachment_ids[0]
            file_bytes, ext = fetch_file(
                file_content_id=file_content_id,
                license_id=license_id
            )
            start_time = datetime.now()
            logging.info(f"Started processing file attachment: {file_content_id} at {start_time}")
            start_perf = time.perf_counter()
            try:
                extracted_text, imgs_ip_tokens, imgs_op_tokens = await preprocess_file(
                    file_data=file_bytes,
                    file_extension=ext,
                    serviceProvider=serviceProvider,
                    apiKey=apiKey,
                    model=model,
                    sa_info=sa_info,
                    resourceId=resourceId,
                    resource=resource,
                )
                
            except APIError as e:
                logger.error(f"File preprocessing failed with APIError: {e.message}", exc_info=True)
                raise
            end_perf = time.perf_counter()
            logging.info(f"Finished processing file: {file_content_id} | Elapsed: {end_perf - start_perf:.2f}s")

            if not extracted_text.strip():
                raise ValueError("Unable to generate manual test cases as the uploaded file contains no readable content. Please upload a valid document.")

            logger.info("Document enrichment initiated")
            start_time_enrich = time.time()
            try:
                file_summary, file_ip_tokens, file_op_tokens = await enrich_document_content(
                    full_text=extracted_text,
                    apiKey=apiKey,
                    resourceId=resourceId,
                    resource=resource,
                    serviceProvider=serviceProvider,
                    model=model,
                    sa_info=sa_info,
                    max_concurrent=3,
                )
                logging.info(
                    f"Enrichment of attachedFile Timing | Duration: {time.time() - start_time_enrich:.3f}s"
                )
            except APIError as e:
                logger.error(f"Enrichment APIError: {e.message}", exc_info=True)
                raise
            except Exception as e:
                logger.exception(f"Enrichment failed: {str(e)}")
                raise

            file_content = file_summary
            try:
                manualTestCase.initialize_db_and_collections_mtc_to_atc(
                    license_id=mongoDb_license_id,
                    unique_id=prompt_id,
                    content=file_content
                )
                logger.info(f"Successfully stored preprocessed file summary for prompt_id: {prompt_id} in user_mtc_to_atc")
            except Exception as db_store_err:
                logger.error(f"Failed to store preprocessed file summary in user_mtc_to_atc: {db_store_err}")
        else:
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
        if not isAutomationScript:
            preprocessing_tokens = imgs_ip_tokens  + imgs_op_tokens + file_ip_tokens  + file_op_tokens or 0
            if preprocessing_tokens > 0 and serviceProvider == "DefaultFireFlink":
                try:
                    await update_ai_service_instance_token_usage(
                        mongo_url=None,
                        license_id=license_id,
                        service_provider=serviceProvider,
                        tokens=preprocessing_tokens
                    )
                    logger.info(f"Stage 1 token deduction | Endpoint: /file-to-mtc | tokens={preprocessing_tokens} | serviceProvider={serviceProvider}")
                except Exception as deduction_err:
                    logger.error(f"Failed to deduct preprocessing tokens in /file-to-mtc Stage 1: {deduction_err}")

            return JSONResponse(
                status_code=200,
                content={
                    "summary": file_content,
                    "ref_id": prompt_id
                }
            )
        File_Input_token = file_ip_tokens + imgs_ip_tokens
        File_Output_token = file_op_tokens + imgs_op_tokens
        # 2) Generate MTC from summary + user_input (skip file reprocessing)
        response = await manualTestCase.handle_user_input_for_file(
            user_id=user_id,
            license_id=license_id,
            project_id=project_id,
            branch_id=request.branch_id,
            env=env,
            session_id=session_id,
            session_name=session_name,
            prompt_id=prompt_id,
            unique_id=unique_id,
            dateTime=dateTime,
            template=json_structure,
            original_template=json_structure,
            template_id=0,
            input_type=input_type,
            user_input=user_input,
            user_input_tokens=user_input_tokens,
            file_name=file_name,
            file_content=file_content,
            chatContext=summary,
            prompt_type=prompt_type,
            script_type=request.script_type or 'manual',
            count=count,
            is_modified=request.is_modified,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            sa_info=sa_info,
            resourceId=resourceId,
            resource=resource,
            request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
            return_generated_payload=True,
            File_Input_token = File_Input_token,
            File_Output_token = File_Output_token
        )

        if isinstance(response, dict):
            if response.get("success") is False:
                error_info = response.get("error", {})
                return JSONResponse(
                    status_code=200,
                    content={
                        "responseCode": error_info.get("code", 500),
                        "status": "failure",
                        "error_message": error_info.get("message", "Temporary File MTC Generation Failed")
                    }
                )
            if "testcases" in response or "manual_testcase" in response or "Test Cases" in response:
                summary_text = (
                    (file_content or "").strip()
                    if isinstance(file_content, str)
                    else ""
                ) or response.get("summary", "") or response.get("context_summary", "") or ""
                payload = build_temporary_mtc_payload(
                    summary_text,
                    response,
                    input_check_text=f"{summary_text}\n{user_input or ''}",
                )
                # payload["ref_id"] = prompt_id
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
        logger.error(f"Temporary File MTC Generation Failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content=build_error_response(e, model, serviceProvider)
        )

