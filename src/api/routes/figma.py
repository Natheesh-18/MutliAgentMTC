from fastapi import APIRouter
from src.api.runtime import *  # noqa: F401,F403
# from src.persistence.qdrant_client_provider import get_async_qdrant_client, get_sync_qdrant_client
import os , time , uuid , asyncio , shutil 
router = APIRouter()

@router.post("/figma_file_process")
async def figma_file_process(payload: FigmaPreprocessRequest):
    file_id = payload.file_id
    figma_access_token=payload.figma_access_token
    pages_id = payload.pages_name
    license_id = payload.license_id
    project_id = payload.project_id
    instance_name = payload.instance_name
    replace=payload.replace
    mongo_id=payload.mongo_id
    instance_name_change=payload.instance_name_change
    try:
        logger.info("initilizing the environment")
        env = os.getenv("PROFILE")
        embeddings=manualTestCaseDoc.embeddings
        # qdrant_client = get_sync_qdrant_client()
    except Exception as e:
        logger.exception(f"Error in env initilization:{e}")
        return JSONResponse(
            status_code=200,
            content={"status": "failure", "responseCode": 500,"message": f"Environment initialization failed: {str(e)}"})

    logger.info("initilizing the collection name")
    if env:
        collection_name = f"ff_cloud_{env}_figma_{license_id}_{project_id}"
    else:
        collection_name = f"ff_cloud_figma_{license_id}_{project_id}"

    if instance_name_change==True:
        try:
            logger.info(f"started Qdrant instance name")
            previous_instance_name=update_source_by_mongo_id(collection_name,qdrant_client,mongo_id,instance_name)
            return JSONResponse(
                    status_code=200,
                    content={
                    "responseCode": 200,
                    "message": f"Instance name changed from {previous_instance_name} to {instance_name} successfully",
                    "responseObject": {
                        "collection_name": collection_name,
                    }
                })
        except Exception as e:
            logger.error(f"failed to updated Qdrant instance name:{e}")
            return JSONResponse(
            status_code=200,
            content={"status": "failure","responseCode": 400,"message": "Fail to update the instnace name"}
        ) 

    else:
        try:
            if not license_id:
                logger.warning("Missing required parameters: license_id")
                return JSONResponse(
                status_code=200,
                content={"status": "failure","responseCode": 400,"message": "Missing required parameters: license_id"}
            ) 

            if not project_id:
                logger.warning("Missing required parameters: project_id")
                return JSONResponse(
                    status_code=200,
                    content={"status": "failure","responseCode": 400,"message": "Missing required parameters: project_id"}
            )

            if any(not v for v in (file_id, figma_access_token, pages_id,instance_name)):
                logger.warning("Missing required any of the parameters: file_id,figma_access_token,pages_id,instance_name")
                return JSONResponse(
                    status_code=200,
                    content={"status": "failure","responseCode": 400,"message": "Figma credentials are missing"}
            )

            OUTPUT_DIR = None
            
            try:
                logger.info(f"Fetching the data of figma with file_id:{file_id} of pages: {pages_id}")
                OUTPUT_DIR = fetch_figma_frames(file_id, figma_access_token, pages_id,instance_name)
            except FigmaAPIError as e:
                logger.exception(f"Error in fetching data")
                if replace==False:
                    try:
                        _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
                        DocumentProcessor(embeddings=manualTestCaseDoc.embeddings, qdrant_host=os.getenv("QDRANT_HOST"), qdrant_port=os.getenv("QDRANT_PORT")).update_figma_mongodb_status(license_id=_lid, project_id=project_id, mongo_id=mongo_id,instance_name=instance_name, status="Failed")
                    except Exception as _me:
                        logger.error(f"MongoDB status update error for {instance_name}: {_me}", exc_info=True)
                return JSONResponse(
                    status_code=200,
                    content={"status": "failure",
                            "responseCode": e.status_code,
                            "message": e.message
                            }
                )
            except Exception as e:
                logger.exception("Unexpected error while fetching figma frames")
                if replace==False:
                    try:
                        _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
                        DocumentProcessor(embeddings=manualTestCaseDoc.embeddings, qdrant_host=os.getenv("QDRANT_HOST"), qdrant_port=os.getenv("QDRANT_PORT")).update_figma_mongodb_status(license_id=_lid, project_id=project_id, mongo_id=mongo_id,instance_name=instance_name, status="Failed")
                    except Exception as _me:
                        logger.error(f"MongoDB status update error for {instance_name}: {_me}", exc_info=True)
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "failure",
                        "responseCode": 500,
                        "message": f"Unexpected error while fetching figma frames: {str(e)}"}
                )
            
            # OUTPUT_DIR=r"C:\Users\SakshiBagul\Desktop\ai_figma_streaming\mtc\src\figma_utils\FIGMA_ENTIER\b0ZMiXgbLiaznpVp57hd3H_DemoStay"

            try:
                if replace==True:
                    delete_points_by_source_replace(instance_name,collection_name,qdrant_client,mongo_id)
                    logger.info("successfully removed the data from the qdrant")
            except Exception as e:
                logger.error(str(e))
                raise

            try:
                logger.info(f"Started to extract Dropdown,ONhover,Destinationframe")
                cleaned_file_json(OUTPUT_DIR,file_id,pages_id)
                logger.info(f"Have given page wise json")
            except Exception as e: 
                logger.exception(f"Error in storing json of individual page: {e}")
                try:
                    _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
                    DocumentProcessor(embeddings=manualTestCaseDoc.embeddings, qdrant_host=os.getenv("QDRANT_HOST"), qdrant_port=os.getenv("QDRANT_PORT")).update_figma_mongodb_status(license_id=_lid, project_id=project_id, mongo_id=mongo_id,instance_name=instance_name, status="Failed")
                except Exception as _me:
                    logger.error(f"MongoDB status update error for {instance_name}: {_me}", exc_info=True)
                return JSONResponse(status_code=200, content={"status": "failure","responseCode": 500,"message": f"Flow extraction failed: {str(e)}"})
            
            try:
                logger.info(f"Starting for extrating the flow...")
                per_flow_tokens=flow_of_pages(OUTPUT_DIR,file_id,pages_id,collection_name,instance_name,embeddings,qdrant_client,mongo_id)
                print("extrcated per page json store in qdrant")
            except Exception as e:
                logger.exception(f"Error for doing the flow retrival {e}")
                #return JSONResponse(status_code=200, content={"status": "failure","responseCode": 500,"message": f"Flow extraction failed: {str(e)}"}) 
            try:
                print("started per image user story")
                result=Generate_User_Story(OUTPUT_DIR,collection_name,instance_name,embeddings,qdrant_client,mongo_id)
                processed_images=result["processed_images"]
                tokens = result["token_usage"]
                print("chunks store in qdrant")
            except Exception as e:
                logger.exception(f"Error for generating summary of image: {e}")
                try:
                    _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
                    DocumentProcessor(embeddings=manualTestCaseDoc.embeddings, qdrant_host=os.getenv("QDRANT_HOST"), qdrant_port=os.getenv("QDRANT_PORT")).update_figma_mongodb_status(license_id=_lid, project_id=project_id, mongo_id=mongo_id,instance_name=instance_name, status="Failed")
                except Exception as _me:
                    logger.error(f"MongoDB status update error for {instance_name}: {_me}", exc_info=True)
                return JSONResponse(status_code=200, content={"status": "failure","responseCode": 500,"message": f"User story generation failed: {str(e)}"})

            total_tokens = {
            "prompt_tokens": per_flow_tokens.get("prompt_tokens", 0) + tokens.get("prompt_tokens", 0),
            "completion_tokens": per_flow_tokens.get("completion_tokens", 0) + tokens.get("completion_tokens", 0),
            "total_tokens": per_flow_tokens.get("total_tokens", 0) + tokens.get("total_tokens", 0)}

            try:
                _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
                DocumentProcessor(embeddings=manualTestCaseDoc.embeddings, qdrant_host=os.getenv("QDRANT_HOST"), qdrant_port=os.getenv("QDRANT_PORT")).update_figma_mongodb_status(license_id=_lid, project_id=project_id, mongo_id=mongo_id,instance_name=instance_name, status="Processed")
                logger.info(f"Updated MongoDB status to Processed for {instance_name}")
            except Exception as _me:
                logger.error(
                    f"MongoDB status update error for {instance_name}: {_me}",
                    exc_info=True
                )
            
            if replace==True:
                return JSONResponse(
                            status_code=200,
                            content={
                            "responseCode": 200,
                            "message": f"{instance_name} instance updated successfully.",
                            "responseObject": {
                                "collection_name": collection_name,
                                "processed_images": len(processed_images),
                                "details": processed_images,
                                "llm_token_usage": total_tokens,
                            }
                        })
            else:
                return JSONResponse(
                    status_code=200,
                    content={
                    "responseCode": 200,
                    "message": "Processed",
                    "responseObject": {
                        "collection_name": collection_name,
                        "processed_images": len(processed_images),
                        "details": processed_images,
                        "llm_token_usage": total_tokens,
                    }
                })
        
        except Exception as e:
            try:
                _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
                DocumentProcessor(embeddings=manualTestCaseDoc.embeddings, qdrant_host=os.getenv("QDRANT_HOST"), qdrant_port=os.getenv("QDRANT_PORT")).update_figma_mongodb_status(license_id=_lid, project_id=project_id, mongo_id=mongo_id,instance_name=instance_name, status="Failed")
            except Exception as _me:
                logger.error(f"MongoDB status update error for {instance_name}: {_me}", exc_info=True)
            return JSONResponse(
                status_code=200,
                content={"status": "failure","responseCode": 400,"message": "Figma processing fail"}
        )
        finally:
            if OUTPUT_DIR and os.path.exists(OUTPUT_DIR):
                try:
                    shutil.rmtree(OUTPUT_DIR)
                    logger.info(f"Deleted OUTPUT_DIR: {OUTPUT_DIR}")
                except Exception as cleanup_error:
                    logger.error(
                        f"Failed to delete OUTPUT_DIR {OUTPUT_DIR}: {cleanup_error}",
                        exc_info=True
                    )


@router.post("/figma-mtc-generation")
async def figma_mtc(data: FigmaPromptRequest):
    user_input = data.input
    user_id = data.user_id
    project_id = data.project_id
    session_id = data.session_id
    prompt_id = data.prompt_id
    license_id = data.license_id
    input_type = data.input_type
    count = data.count
    script_type = data.script_type
    bearer_token = data.bearer_token
    is_modified = data.is_modified
    session_name = data.session_name
    prompt_type=data.prompt_type
    instance_name=data.instance_name
    page_name=data.page_name
    summary = data.summary
    input_info = data.input_info
    branch_id = data.branch_id
    ref_id=data.ref_id
    user_input_tokens = count_tokens(data.input)
    request_time_for_storing_1_tc_in_MD = {
    "start_time": time.time(),
    "stored_time": None
}   
    logger.info(f"Main MTC request initiated | Endpoint: /figma-mtc-generation")
    logger.info(f"ContentSummary: {summary}")
    logger.info(f"Reference ID: {ref_id}")
    env = os.getenv("PROFILE")
    value="SCR"
    unique_id = value + str(uuid.uuid4().hex)
    dateTime=datetime.now(timezone.utc)
    if env:
        mongoDb_license_id = f"optimize_{env}_{license_id}"
    else:
        mongoDb_license_id = f"optimize_{license_id}"
    
    apiKey = None
    serviceProvider = None
    model = None
    sa_info = None
    resource = None
    resourceId = None
    
    try:
        if not prompt_id:
            logger.info(f"intilizing the prompt_id")
            prompt_id = str(uuid.uuid4().hex)

        if not session_id:
            logger.info(f"intilizing the session_id")
            session_id = str(uuid.uuid4().hex)

        if not all([user_id, project_id,license_id]):
            logger.warning(f"Did not recieve required Parameters")
            raise APIError(responseCode=400, message="PLease Give all required fields")
        
        if count not in [1, 2, 3]:
            logger.warning(f"Count should always be in 1,2,3")
            raise APIError(responseCode=400, message="Invalid count value. Allowed values: 1, 2, 3")

        if not ref_id:
            raise APIError(responseCode=400, message="Unable to generate test cases. Please reattach the Figma instance and try again.")

        try:
            sp_config = resolve_service_provider(license_id, project_id)
        except Exception as e:
            logger.warning(f"Failed While Fetching the serviceProviderInstance: {e}")
            raise APIError(responseCode=400, message="Failed to fetch the ServiceProvider Detials")
        
        apiKey = sp_config.get("apiKey")
        serviceProvider = sp_config.get("serviceProvider")
        model = sp_config.get("model")
        sa_info = sp_config.get("sa_info")
        resource = sp_config.get("resource")
        resourceId = sp_config.get("resourceId") 
        start_time = time.time()

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
            logger.info("Fetching the template of MTC")       
            template = manualTestCase.fetch_test_case_template(
                license_id, project_id)
            logger.info("Template Fetched Successfully")
        except Exception as e:
            logger.info("Failed to Fetch the template of MTC")
            raise APIError(responseCode=400,message=f"Template Fetching Failed:{e}")
        
        template_id=template['_id']
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
        # if count == 1 and not ref_id:
        #     if not page_name or not instance_name:
        #         return JSONResponse(
        #             status_code=400,
        #             content={"status": "failure", "message": "Please select the instance and page_name."}
        #         )
        #     try:
        #         manualTestCase.initialize_db_and_collections_mtc_to_atc(
        #             license_id=mongoDb_license_id,
        #             unique_id=prompt_id,
        #             content={"pageName": page_name, "instanceName": instance_name}
        #         )
        #         logger.info(f"Successfully stored Figma credentials for prompt_id: {prompt_id} in user_mtc_to_atc")
        #     except Exception as db_store_err:
        #         logger.error(f"Failed to store Figma credentials in user_mtc_to_atc: {db_store_err}")
        # else:
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
            if not docs:
                if not (page_name and instance_name):
                    logger.error(f"Failed to retrieve Instance Details for ref_ids: {lookup_keys} and prompt_id: {prompt_id}.")
                    return JSONResponse(
                        status_code=400,
                        content={"status": "failure", "message": f"Unable to generate test cases. Please reattach the figma instance and try again."}
                    )
            else:
                doc = docs[0]
                summary_data = doc.get("summary", {})
                if isinstance(summary_data, dict):
                    page_name = summary_data.get("pageName") or page_name
                    instance_name = summary_data.get("instanceName") or instance_name
            
            if not page_name or not instance_name:
                logger.error(f"No stored pageName/instanceName found for ref_ids: {lookup_keys} and promp_id: {prompt_id}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "failure",
                        "message": "Unable to generate test cases. Please reattach the figma instance and try again"
                    })
        except Exception as db_err:
            logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids {lookup_keys}: {db_err}")
            if not (page_name and instance_name):
                logger.error(f"No stored Instance Details found in mtc_to_atc for ref_ids: {lookup_keys} and prompt_id: {prompt_id}")
                return JSONResponse(
                    status_code=400,
                    content={"status": "failure", "message": "Unable to generate test cases. Please reattach the figma instance and try again"}
                )
        logger.info(f"pageName:{page_name}") 
        logger.info(f"instanceName:{instance_name}") 
        logger.info("Initilizing the monogodb database Parent")\
        
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
        branch_id=branch_id)

        # try:
        #     _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
        #     instance_name=DocumentProcessor(embeddings=manualTestCaseDoc.embeddings, qdrant_host=os.getenv("QDRANT_HOST"), qdrant_port=os.getenv("QDRANT_PORT")).get_figma_instance_name(license_id=_lid, project_id=project_id, mongo_id=mongo_id)
        #     print("instance_name:",instance_name)
        # except Exception as e:
        #     logger.info("Fail to fetch the instance_name from mongo:{e}")
        #     raise e 

        asyncio.create_task(manualTestCase.handle_user_input_for_figma(
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
            is_modified=is_modified,
            user_input_tokens=user_input_tokens,
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
            page_name=page_name,
            instance_name=instance_name,
            request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
            branch_id=branch_id,
            chatContext=summary
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
                        "created_at":dateTime,
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
                        "prompt_type":prompt_type,
                        "script_type": "manual",
                        "serviceProvider": serviceProvider,
                        "session_id": session_id,
                        "session_name": session_name,
                        "test_case_count": 0,
                        "total_output_tokens": 0,
                        "total_tokens_consumed": 0,
                        "user_id": user_id,
                        "user_input_tokens": 0,
                        "branch_id": branch_id
                    },
                    "test_cases_details": []
                }
            }
        }
      )
    )


@router.delete("/delete_figma_collection")
async def delete_points_by_source(request: DeleteFigmaCollectionRequest):
    license_id = request.license_id
    project_id = request.project_id
    instance_name = request.instance_name

    try:
        logger.info("initilizing the environment")
        env = os.getenv("PROFILE")
        qdrant_client = qdrantAsyncClient
    except Exception as e:
        logger.exception(f"Error in env initilization:{e}")
        return JSONResponse(
            status_code=200,
            content={"status": "failure", "responseCode": 500,"message": f"Environment initialization failed: {str(e)}"})
    
    logger.info("initilizing the collection name")
    if env:
        collection_name = f"ff_cloud_{env}_figma_{license_id}_{project_id}"
    else:
        collection_name = f"ff_cloud_figma_{license_id}_{project_id}"

    try:
        # Check if collection exists
        collections_response = await qdrant_client.get_collections()
        collections = collections_response.collections
        existing_collection_names = [collection.name for collection in collections]
        
        if collection_name not in existing_collection_names:
            return {
                "responseCode": 404,
                "responseObject": None,
                "message": f"Collection '{collection_name}' does not exist"
            }

        # Delete points where payload["source"] == instance_name
        delete_filter = Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchValue(value=instance_name)
                )
            ]
        )

        await qdrant_client.delete(
            collection_name=collection_name,
            points_selector=delete_filter
        )

        return {
            "responseCode": 200,
            "responseObject": {
                "collection_name": collection_name,
                "deleted_source": instance_name
            },
            "message": f"{instance_name} instance deleted successfully."
        }

    except UnexpectedResponse as e:
        raise HTTPException(
            status_code=500,
            detail={
                "responseCode": 500,
                "responseObject": None,
                "message": f"Qdrant error: {str(e)}"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "responseCode": 500,
                "responseObject": None,
                "message": f"Unexpected failure: {str(e)}"
            }
        )


@router.post("/figma-to-mtc")
async def figma_mtc(data: TempFigmaPromptRequest):
    user_input = data.input
    user_input += "\n\nNote: Please generate exactly 1 scenario and 1 test case only."
    user_id = data.user_id
    project_id = data.project_id
    session_id = data.session_id
    prompt_id = data.prompt_id
    license_id = data.license_id
    input_type = data.input_type
    count = data.count
    script_type = data.script_type
    bearer_token = data.bearer_token
    is_modified = data.is_modified
    session_name = data.session_name
    prompt_type=data.prompt_type
    instance_name=data.instance_name
    page_name=data.page_name
    summary = data.summary
    input_info = data.input_info
    branch_id = data.branch_id
    ref_id=data.ref_id
    user_input_tokens = count_tokens(data.input)
    isAutomationScript=data.is_automation_steps
    env = os.getenv("PROFILE")
    logger.info(f"Temp MTC request initiated | Endpoint: /figma-to-mtc")
    logger.info(f"ContentSummary: {summary}")
    logger.info(f"Reference ID: {ref_id}")
    
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
                    "status": "failure",
                    "error_message": f"Failed to fetch service provider details: {e}",
                    "response_code": 400
                }
            )
        apiKey = sp_config.get("apiKey")
        serviceProvider = sp_config.get("serviceProvider")
        model = sp_config.get("model")
        sa_info = sp_config.get("sa_info")
        resource = sp_config.get("resource")
        resourceId = sp_config.get("resourceId")
        start_time = time.time()

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

        test_step_fields = ["Test Steps", "Step Input"]
        json_structure = {
            "summary":"",
            "Test Cases": [
                {
                    "Test Steps": [{field: "" for field in test_step_fields}],
                }
            ]
        }
        if env :
            COLLECTION_NAME = f"ff_cloud_{env}_figma_{license_id}_{project_id}"
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else :
            COLLECTION_NAME = f"ff_cloud_figma_{license_id}_{project_id}"
            mongoDb_license_id = f"optimize_{license_id}"

        unique_id = "SCR" + str(uuid.uuid4().hex)
        dateTime = datetime.now(timezone.utc)

        flow_summaries =[]
        flow_summary=''
        if count == 1 and not ref_id:
            # qdrant_client=get_async_qdrant_client()
            for page in page_name:
                flow_data = await get_page_flow(
                    page,
                    COLLECTION_NAME,
                    qdrantAsyncClient,
                    instance_name
                )
                flow_summaries.append(flow_data["FlowSummary"])

            flow_summary = "\n".join(flow_summaries)
            flow_summary = f"FlowSummary: {flow_summary}"
            try:
                manualTestCase.initialize_db_and_collections_mtc_to_atc(
                    license_id=mongoDb_license_id,
                    unique_id=prompt_id,
                    content={"pageName": page_name,
                                "instanceName":instance_name}
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
                    content={"status": "failure", "error_message": "ref_id or prompt_id is required","response_code":400}
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
                if not docs:
                        return JSONResponse(
                            status_code=200,
                            content={"status": "failure", "error_message": f"Failed to retrieve Instance Details for ref_ids: {lookup_keys}","response_code":400}
                        )
                doc = docs[0]
                summary_data = doc.get("summary", {})
                page_name = summary_data.get("pageName")
                instance_name = summary_data.get("instanceName")
                if not page_name or not instance_name:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "failure",
                            "error_message": f"No stored pageName/instanceName found for ref_ids: {lookup_keys}",
                            "response_code":400
                        })
            except Exception as db_err:
                logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids {lookup_keys}: {db_err}")
                return JSONResponse(
                    status_code=200,
                    content={"status": "failure", "error_message": f"No stored Instance Details found in mtc_to_atc for ref_ids: {lookup_keys}."}
                )
        if not isAutomationScript:
            return JSONResponse(
                status_code=200,
                content={
                    "summary": flow_summary,
                    "ref_id": prompt_id
                }
            )
        response = await manualTestCase.handle_user_input_for_figma(
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
            is_modified=is_modified,
            user_input_tokens=user_input_tokens,
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
            resourceId=resourceId,
            resource=resource,
            env=env,
            page_name=page_name,
            instance_name=instance_name,
            request_time_for_storing_1_tc_in_MD=None,
            return_generated_payload=True,
            branch_id=branch_id,
            chatContext=summary
            )
        
        # if isinstance(response, dict) and ("testcases" in response or "Test Cases" in response or "summary" in response):
        #     return build_temporary_mtc_payload(
        #         response.get("context_summary") or response.get("summary")  or "",
        #         response
        #     )

        # if response is not None and hasattr(response, "context_summary") or hasattr(response, "corrected_testcases") or hasattr(response, "raw_testcases"):
        #     state_payload = getattr(response, "corrected_testcases", None) or getattr(response, "raw_testcases", None) or {}
        #     payload=build_temporary_mtc_payload(
        #         getattr(flow_summary,
        #         state_payload,
        #     ))
        #     payload["ref_id"] = prompt_id
        #     return JSONResponse(status_code=200, content=payload)
        if isinstance(response, dict):
            if response.get("success") is False:
                error_info = response.get("error", {})
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "failure",
                        "responseCode": error_info.get("code", 500),
                        "error_message": error_info.get("message", "Temporary File MTC Generation Failed")
                    }
                )
            if "testcases" in response or "manual_testcase" in response or "Test Cases" in response:
                payload = build_temporary_mtc_payload(flow_summary, response)
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
        logger.error(f"Temporary Figma MTC Generation Failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content=build_error_response(e, model, serviceProvider)
        )

