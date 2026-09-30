from fastapi import APIRouter,Form,UploadFile,File
#this router becomes the container for related api endpoints in this file
router = APIRouter()
from src.api.runtime import *
from src.integrations.kafka import produce_video_job, video_max_retries
import os,json,tempfile,shutil,uuid,asyncio,time


@router.post("/video-upload-preprocess")
async def preprocess_video(
    payload: VideoUploadPreprocessPayload,
    request: Request,
    projectid: Optional[str] = Header(None, alias="Projectid"),
    projectname: Optional[str] = Header(None, alias="Projectname"),
    projecttype: Optional[str] = Header(None, alias="Projecttype"),
    licensetype: Optional[str] = Header(None, alias="Licensetype"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    license_id=payload.license_id
    video_id=payload.video_id
    video_name=payload.video_name
    replace=payload.replace
    user_id=payload.user_id
    storage_type = payload.storageType or "cloudS3"
    if isinstance(storage_type, list) and len(storage_type) > 0:
        storage_type = storage_type[0]
    project_id = projectid or request.headers.get("projectid")
    project_name = projectname or request.headers.get("projectname")
    project_type = projecttype or request.headers.get("projecttype")
    license_type = licensetype or request.headers.get("licensetype")
    bearer_token = authorization or request.headers.get("authorization")

    _lid=None
    try:
        try:
            env=None
            env=os.getenv("PROFILE")
            _lid= await mongodb_license_inti(license_id,env)
            print(_lid)
        except Exception as e:
            logger.info("Fail to initize the env")
            update_video_mongodb_status(_lid=_lid,video_id=video_id,status="Failed",message="Failed to Process the video")
            return JSONResponse(
                status_code=200,
                content={
                    "status":"FAILED",
                    "responseCode":500,
                    "message":"Failed to Process the video"
                }
            )
        
        if not license_id or not project_id or not user_id:
            logger.warning("Missing required parameters: license_id, project_id, or user_id")
            update_video_mongodb_status(_lid=_lid,video_id=video_id,status="Failed",message="Failed to Process the video")
            return JSONResponse(
                        status_code=200,
                        content={
                            "status": "FAILED",
                            "responseCode": 400,
                            "message": "Missing required parameters: license_id, project_id, or user_id."
                        }
                    )

        logger.info("checking the extension of video")
        if isinstance(video_name, list) and len(video_name) > 0:
            video_name=video_name[0]
        if not video_name or not video_name.lower().endswith(".mp4"):
            update_video_mongodb_status(_lid=_lid,video_id=video_id,status="Failed",message="Only allowed extension is mp4")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "Failed",
                    "responseCode": 400,
                    "message": "Only MP4 video files are supported."
                }
                )

        try:
            logger.info("Giving the collection name")
            if env:
                collection_name=f"ff_cloud_{env}_video_{license_id}_{project_id}"
            else:
                collection_name=f"ff_cloud_video_{license_id}_{project_id}"

        except Exception as e:
            logger.error("Fail to initilize the collection name")
            update_video_mongodb_status(_lid=_lid,video_id=video_id,status="Failed",message="Failed to Process the video")
            return JSONResponse(
                status_code=200,
                content={"status":"FAILED","responseCode":500,"error_message":f"Qdrant collection name fail:{e}"})
        print("this is the collection name")
        try:
            if replace==True:
                delete_points_of_videos(collection_name,qdrant_client,video_id,video_name)
                logger.info("successfully removed the data from the qdrant")
        except Exception as e:
            logger.error(str(e))
            raise

        s3_key = None
        s3_keys = []
        if storage_type == "cloudS3":
            s3_keys = build_video_s3_keys(
                license_id,
                project_id,
                video_name=video_name,
                user_id=user_id,
            )
            s3_key = s3_keys[0] if s3_keys else None

        job = {
            "license_id": license_id,
            "project_id": project_id,
            "_lid": _lid,
            "video_id": video_id,
            "video_name": video_name,
            "replace": replace,
            "collection_name": collection_name,
            "storage_type": storage_type,
            "s3_key": s3_key,
            "s3_keys": s3_keys if storage_type == "cloudS3" else [],
            "user_id": user_id,
            "retry_count": 0,
            "max_retries": video_max_retries(),
        }

        if storage_type != "cloudS3":
            job.update(
                {
                    "bearer_token": bearer_token,
                    "license_type": license_type,
                    "project_name": project_name,
                    "project_type": project_type,
                }
            )
        update_video_mongodb_status(
            _lid=_lid,
            video_id=video_id,
            status="Processing",
            message="Video processing started.",
        )
        try:
            produce_video_job(job, key=str(video_id))
        except Exception as e:
            logger.exception(f"Failed to publish video job: {e}")
            update_video_mongodb_status(
                _lid=_lid,
                video_id=video_id,
                status="Failed",
                message="Failed to Process the video",
            )
            return JSONResponse(
                status_code=500,
                content={
                    "status": "failure",
                    "responseCode": 500,
                    "error_message": "Failed to Process the video",
                },
            )

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "responseCode": 202,
                "responseObject": {
                    "video_name": video_name,
                    "project_id": project_id,
                    "license_id": license_id,
                    "status": "Processing"
                }
            }
        )
    
    except Exception as e:
        logger.exception( f"Video upload failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "failure",
                "responseCode": 500,
                "error_message": "Failed to Process the video"
            }
        )



@router.delete("/delete-video-collection")
async def delete_points_by_source(request: DeleteVideoCollectionRequest):
    license_id = request.license_id
    project_id = request.project_id
    video_id = request.video_id

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
        collection_name = f"ff_cloud_{env}_video_{license_id}_{project_id}"
    else:
        collection_name = f"ff_cloud_video_{license_id}_{project_id}"

    mongo_id = video_id.strip('"')
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
            should=[
                FieldCondition(
                    key="mongo_id",
                    match=MatchValue(value=mongo_id)
                ),
                FieldCondition(
                    key="mongo_id",
                    match=MatchValue(value=f'"{mongo_id}"')
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
                "deleted_source": video_id
            },
            "message": f"{video_id} instance deleted successfully."
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

# @router.post("/video_upload_preprocess")
# async def preprocess_video(
#     license_id: str = Form(...),
#     project_id: str = Form(...),
#     mongo_id: str = Form(...),
#     project_name: str = Form(...),
#     video_name: str = Form(...),
#     video: UploadFile = File(...),
# ):
# #here we are taking 4 text filed and 1 uploadfile from the postman request
# #form is used for text and file is used for attachement
#     temp_dir = None
#     audio_result = None
#     audio_output = None
#     video_path = None
#     try:
#         try:
#             logger.info("Initilizing the env and qdrant")
#             env=None
#             env=os.getenv("PROFILE")
#             _lid= await mongodb_license_inti(license_id,env)
#             print(_lid)
#             embeddings=manualTestCaseDoc.embeddings
#             # here the qdrant_client will come from embeddings which is defined globally
#             #rater then taking the data from env again n again it already qdrant cilent is defined use it immeadiateley
#             logger.info("env and Qrant initlizing completed")
#         except Exception as e:
#             logger.info("Fail to initize the env or qdrant")
#             update_video_mongodb_status(_lid=_lid,project_id=project_id,video_name=video_name,status="Failed")
#             return JSONResponse(
#                 status_code=200,
#                 content={
#                     "status":"failure",
#                     "responseCode":500,
#                     "error_message":f"Qdrant fail:{e}"
#                 }
#             )

#         try:
#             logger.info("Giving the collection name")
#             if env:
#                 collection_name=f"ff_cloud_{env}_video_{license_id}_{project_id}"
#             else:
#                 collection_name=f"ff_cloud_video_{license_id}_{project_id}"

#             try:
#                 logger.info("initilizing the collection in the qdrant")
#                 ensure_collection(collection_name,qdrant_client)

#             except Exception as e:
#                 logger.error("Fail to initilize the collection in qdrant")
#                 return JSONResponse(
#                     status_code=200,
#                     content={
#                         "status":"failure",
#                         "responseCode":500,
#                         "error_message":f"Qdrant collection fail:{e}"
#                     }
#                 )
#         except Exception as e:
#             logger.error("Fail to initilize the collection name")
#             return JSONResponse(
#                 status_code=200,
#                 content={
#                     "status":"failure",
#                     "responseCode":500,
#                     "error_message":f"Qdrant collection name fail:{e}"
#                 }
#             )

#         try:
#             logger.info("creating temp path for the video")
#             temp_dir = tempfile.mkdtemp(prefix="video_")
#             video_path = os.path.join(temp_dir, video.filename)
#             with open(video_path, "wb") as buffer:
#                 shutil.copyfileobj(video.file, buffer)
#         except Exception as e:
#             logger.info("Fail to create temp dir for the video")
#             return JSONResponse(
#                         status_code=200,
#                         content={
#                             "status":"failure",
#                             "responseCode":400,
#                             "error_message":f"Fail to create temp dir for the video with error:{e}"
#                         }
#                     )
#         try:
#             logger.info("Extracting the frame from the video")
#             frames = extract_frames(video_path)
#             print(f"\033[93mExtracted images: {len(frames)}\033[0m")
#             logger.info("Frame extraction completed")
#         except Exception as e:
#             return JSONResponse(
#                     status_code=200,
#                     content={
#                         "status": "failure",
#                         "responseCode": 400,
#                         "error_message": "For video frame extrcation failed"}
#                     )

#         try:
#             logger.info("Checking it blank or not")
#             stds = frame_variance_stats(frames)
#             if all(s < 3.0 for s in stds):
#                 logger.info("IT IS BLANK VIDEO")
#                 return JSONResponse(status_code=200,
#                                     content={
#                                     "status": "failure",
#                                     "responseCode": 400,
#                                     "error_message": "Please upload a valid software application recording"
#                                     })
#         except Exception as e:
#             return JSONResponse(status_code=500,
#                                 content={"status": "failure",
#                                         "responseCode": 400,
#                                         "error_message": "For blank video fail to check"
#                                         })

#         try:
#             logger.info("started analyzing the video")
#             response= analyze_video_frames(frames)    
#             # with open("all_llm_outputs.json", "w", encoding="utf-8") as f:
#             #     json.dump(all_llm_outputs, f, indent=4, ensure_ascii=False)
#             response = response.model_dump()
#         except VideoAPIError as e:
#             return JSONResponse(
#                 status_code=200,
#                 content={"status": e.status,"responseCode": e.responseCode,"error_message": e.message})

#         except LLMError as e:
#                 return JSONResponse(
#                     status_code=200,
#                     content={"status": "failure","responseCode": 500,"error_message": "LLM call failed","error": str(e)})

#         except ResponseParsingError as e:
#             return JSONResponse(
#                 status_code=200, 
#                 content={"status": "failure","responseCode": 500,"error_message": "Failed to parse LLM response","error": str(e)})

#         except Exception as e:
#             logger.exception("Unexpected error")
#             return JSONResponse(
#                 status_code=200,
#                 content={"status": "failure","responseCode": 500,"error_message": "Unexpected server error","error": str(e)})

#         try:
#             logger.info("Audio extraction started")
#             audio_result = extract_audio_from_video_large(video_path)
#             logger.info(f"Audio extraction result: {audio_result}")
#         except Exception as e:
#             logger.exception(f"Audio extraction failed: {str(e)}")
#             audio_result = {"has_audio": False, "audio_path": None}
#         try:
#             logger.info("Aduio passing to wisper model")
#             if audio_result and audio_result.get("has_audio") and audio_result.get("audio_path"):
#                 logger.info("Audio detected. Sending to Whisper")
#                 audio_path = audio_result["audio_path"]
#                 audio_output = transcribe_audio_large(audio_path)
#                 logger.info("Whisper transcription completed")
#             else:
#                 logger.info("No audio found in video")
#         except Exception as e:
#             logger.exception(f"WISPER LLM FAIL ERROR: {str(e)}")

#         print("this is audio txt:",audio_output)
#         video_name=video.filename
#         all_module_name=[]
#         all_module_name_flow=[]
#         for per_module in response["modules"]:
#             module_name=per_module["module_name"]
#             all_module_name.append(module_name)
#             entry_point=per_module["entry_point_url"]
#             credential=per_module["credentials"]
#             flow=per_module["flow"]

#             module_name_flow={
#                 "module_name":module_name,
#                 "flow":flow
#             }

#             all_module_name_flow.append(module_name_flow)

#             try:
#                 logger.info("storing data per flow in the qdrant")
#                 store_video_per_flow(collection_name,video_name,module_name,entry_point,credential,flow,embeddings,qdrant_client,mongo_id)
#                 logger.info("ended storing data per flow in the qdrant")
#             except Exception as e:
#                 return JSONResponse(
#                     status_code=200,
#                     content=
#                         {"status": "failure","responseCode": 500,"error_message": f"Qdrant error :{e}"}
#                         )
#         try:
#             logger.info("Storing the data selector chunk in the qdrant")
#             data_selector_chunk(collection_name,video_name,all_module_name,all_module_name_flow,embeddings,qdrant_client,mongo_id)    
#             logger.info("Ended Storing the data selector chunk in the qdrant")   
#         except Exception as e:
#             return JSONResponse(
#                     status_code=200,
#                     content={"status": "failure","responseCode": 500,"error_message": f"Qdrant error :{e}"})

#         try:
#             logger.info("creating content for e2e flow")
#             response.pop("is_valid_video",None)
#             for i, module in enumerate(response.get("modules", [])):
#                 if i != 0:
#                     module.pop("entry_point_url", None)
#         except Exception as e:
#             logger.warning(f"Not able to create data for e2e flow:{e}")

#         logger.info("Creating e2e scenarios")
#         system_prompt,user_prompt=e2e_system_user_prompt(response)

#         try:
#             logger.info("Starting LLM call for e2e scenario")
#             e2e_response=e2e_llm_call(system_prompt,user_prompt)
#             # parsed_response = json.loads(e2e_response)
#         except LLMError as e:
#             return JSONResponse(
#                     status_code=200,
#                     content={"status": "failure","responseCode": 500,"errorType": "LLM_ERROR","error_message": "LLM call failed","error": str(e)})

#         try:
#             if isinstance(e2e_response,list) and len(e2e_response)>0:
#                 e2e_response=e2e_response[0]
#             if isinstance(e2e_response,str):
#                 e2e_response=E2EFlowResponse.model_validate_json(e2e_response)
#             else:
#                 e2e_response=E2EFlowResponse.model_validate(e2e_response)
#         except Exception as e:
#             logger.exception("Invalid response schema from LLM for e2e")
#             return JSONResponse(
#                 status_code=200,
#                 content={"status": "failure","responseCode": 500,"error_message": f"LLM pydantic error with error: str(e)"}
#             )

#         e2e_response = e2e_response.model_dump()
#         e2e_entry_point=e2e_response["end_to_end_flow"]['entry_point']
#         e2e_flow=e2e_response["end_to_end_flow"]["steps"]

#         try:
#             logger.info("Storing e2e flow in the qdrant")
#             store_video_e2e(collection_name,video_name,e2e_entry_point,e2e_flow,embeddings,qdrant_client,mongo_id)
#         except Exception as e:
#             return JSONResponse(
#                 status_code=200,
#                 content={"status": "failure","responseCode": 500,"error_message": f"Qdrant error :{e}"})

#         try:
#             if audio_output!=None:
#                 logger.info("checking if the audio is related to the video or not")
#                 SYSTEM_PROMPT, USER_PROMPT, RESPONSE_FORMAT=audio_video_relation(e2e_response, audio_output)
#                 audio_response=audio_related_checking(SYSTEM_PROMPT, USER_PROMPT, RESPONSE_FORMAT)
#                 logger.info("audio related to video or not:",audio_response)

#                 if audio_response.related:
#                     logger.info("Storing auido in Qdrant")
#                     store_video_audio(collection_name,video_name,audio_output["transcription"],embeddings,qdrant_client,mongo_id)
#                     logger.info("Audio stored successfully")
#         except Exception as e:
#             logger.warning(f"Fail to check the audio related to video or not:{e}")

#         return JSONResponse(
#                 status_code=200,
#                 content={
#                 "responseCode": 200,
#                 "message": "Processed",
#                 "responseObject": {
#                     "collection_name": collection_name,
#                     "video_name": video_name
#                 }
#             })

#     except Exception as e:
#         return JSONResponse(
#             status_code=200,
#             content={"status": "failure","responseCode": 400,"message": f"Video processing fail:{e}"})

    # finally:
    #     # Cleanup audio
    #     if (
    #         audio_result is not None
    #         and audio_result.get("audio_path")
    #         and os.path.exists(audio_result["audio_path"])
    #     ):
    #         try:
    #             os.remove(audio_result["audio_path"])
    #         except Exception as e:
    #             logger.warning(
    #                 f"Failed to delete temp audio: {e}"
    #             )

    #     # Cleanup video temp directory
    #     if temp_dir is not None and os.path.exists(temp_dir):
    #         try:
    #             shutil.rmtree(temp_dir)
    #         except Exception as e:
    #             logger.warning(
    #                 f"Failed to delete temp directory: {e}"
    #             )


@router.post("/videoUpload-to-mtc")
async def video_mtc(data: TempVideoPromptRequest):
    user_input=data.input
    user_input+="\n\nNote: Please generate exactly 1 scenario and 1 test case only."
    user_id=data.user_id
    project_id=data.project_id
    license_id=data.license_id
    input_type=data.input_type
    count=data.count
    prompt_type=data.prompt_type
    summary=data.summary
    branch_id=data.branch_id
    ref_id=data.ref_id
    isAutomationScript=data.is_automation_steps
    video_name=data.file_name
    user_input_token=count_tokens(data.input)
    env=os.getenv("PROFILE")

    prompt_id = str(uuid.uuid4().hex)
    session_id = str(uuid.uuid4().hex)
    user_input_tokens = count_tokens(user_input)
    try:
        try:
            logger.info("Started fetching the service provider")
            result=fetch_service_provider_instance(license_id,project_id)
            logger.info("Successfully fetch service provider details")
        except Exception as e:
            logger.warning(f"Failed to fetch the service provider:{e}")
            return JSONResponse(
                status_code=200,
                content={
                    "status":"failure",
                    "error_message":f"Failed to fetch service provider details: {e}",
                    "response_code":500
                }
            )

        print("1️⃣"*10)
        print(result)
        print("1️⃣"*10)
        apiKey=result.get("api_key")
        serviceProvider=result.get("service_provider")
        model=result.get("model")
        sa_info=result.get("enterprise_config_file",None)
        resource=None
        if result.get("projectEndPoint"):
            resource="AzureFoundry"

        resourceId=result.get("resourceName") 
        if not resourceId:
            resourceId=(
                (urlparse(result.get("projectEndPoint", "")).netloc.split(".", 1)[0])
                if result.get("projectEndPoint")
                else result.get("resourceId", "").rstrip("/").split("/")[-1]
            )

        logger.info(f"ServiceProvider:{serviceProvider}")
        logger.info(f"model:{model}")

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

        request_time_for_storing_1_tc_in_MD = {
            "start_time": time.time(),
            "stored_time": None
        }
        test_step_fields = ["Test Steps", "Step Input"]
        json_structure = {
            "summary":"",
            "Test Cases": [
                {
                    "Test Steps": [{field: "" for field in test_step_fields}],
                }
            ]
        }

        if env:
            COLLECTION_NAME=f"ff_cloud_{env}_video_{license_id}_{project_id}"
            mongoDb_license_id=f"optimize_{env}_{license_id}"
        else:
            COLLECTION_NAME=f"ff_cloud_video_{license_id}_{project_id}"
            mongoDb_license_id=f"optimize_{license_id}"

        unique_id = "SCR" + str(uuid.uuid4().hex)
        dateTime = datetime.now(timezone.utc)
        video_summary=""

        if count==1 and not ref_id:
            end_to_end=await video_e2e_retrieval_temp(video_name,COLLECTION_NAME,qdrant_client)

            if end_to_end:
                video_summary = end_to_end[0].get("end_to_end_flow_of_video", "")
            else:
                video_summary = ""
            video_summary = f"FlowSummary: {video_summary}"
            try:
                manualTestCase.initialize_db_and_collections_mtc_to_atc(
                                    license_id=mongoDb_license_id,
                                    unique_id=prompt_id,
                                    content={"videoName":video_name}
                                )
                logger.info(f"Stored for future for prompt_id:{prompt_id}")
            except Exception as db_error:
                logger.error(f"Failed to store preprocessed file summary in user_mtc_to_atc: {db_error}")

        else:
            lookup_keys = []
            if ref_id:
                if isinstance(ref_id,str):
                    lookup_keys=[ref_id]
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
                atc_collection = manualTestCase.load_collection_for_mtc_to_atc(
                                    license_id=mongoDb_license_id
                                )  
                video_name_MDs = list(
                    atc_collection.find(
                        {"ref_id": {"$in": lookup_keys}},
                        {"ref_id": 1, "summary": 1}
                    )
                )

                if not video_name_MDs:
                    return JSONResponse(
                                status_code=200,
                                content={"status": "failure", "error_message": f"Failed to retrieve Video Details for ref_ids: {lookup_keys}","response_code":400}
                            )

                video_name_MD=video_name_MDs[0]
                video_sum=video_name_MD.get("summary",{})
                video_name=video_sum.get("videoName")
                if not video_name:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "failure",
                            "error_message": f"No stored video found for ref_ids: {lookup_keys}",
                            "response_code":400
                        })
            except Exception as db_err:
                logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids {lookup_keys}: {db_err}")
                return JSONResponse(
                    status_code=200,
                    content={"status": "failure", "error_message": f"No stored Video Details found in mtc_to_atc for ref_ids: {lookup_keys}."}
                )    
            
        if not isAutomationScript:  
            return JSONResponse(
                            status_code=200,
                            content={
                                "summary": video_summary,
                                "ref_id": prompt_id
                            }
                        )  

        response=await manualTestCase.handle_user_input_for_video_process(
            user_id=user_id,
            license_id=license_id,
            project_id=project_id,
            branch_id=data.branch_id,
            env=env,
            session_id = session_id,
            session_name = None,
            prompt_id=prompt_id,
            unique_id=unique_id,
            dateTime=dateTime,
            template=json_structure,
            original_template=json_structure,
            template_id=0,
            input_type=input_type,
            user_input=user_input,
            user_input_tokens=user_input_tokens,
            video_name=video_name,
            chatContext=summary,
            prompt_type=prompt_type,
            script_type='manual',
            count=count,
            is_modified=None,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            sa_info=sa_info,
            resourceId=resourceId,
            resource=resource,
            request_time_for_storing_1_tc_in_MD=request_time_for_storing_1_tc_in_MD,
            return_generated_payload=True,
        )

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
                payload = build_temporary_mtc_payload(video_summary, response)
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
            logger.error(f"Temporary video MTC Generation Failed: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=200,
                content=build_error_response(e, model, serviceProvider)
            )    


@router.post("/videoUpload-mtc-generation")
async def video_mtc(data: VideoPromptRequest):
    user_input=data.input
    user_id=data.user_id
    project_id=data.project_id
    session_id = data.session_id
    prompt_id = data.prompt_id
    license_id = data.license_id
    input_type = data.input_type
    count = data.count
    script_type = data.script_type
    session_name = data.session_name
    prompt_type=data.prompt_type
    summary = data.summary
    branch_id = data.branch_id
    ref_id=data.ref_id
    user_input_tokens = count_tokens(data.input)
    request_time_for_storing_1_tc_in_MD = {
        "start_time": time.time(),
        "stored_time": None
    } 

    logger.info(f"Main MTC request initiated | Endpoint: /videoUpload-mtc-generation")
    logger.info(f"Reference ID: {ref_id}")
    env=os.getenv("PROFILE")
    value="SCR"
    unique_id = value + str(uuid.uuid4().hex)
    dateTime=datetime.now(timezone.utc)
    if env:
        mongoDb_license_id=f"optimize_{env}_{license_id}"
    else:
        mongoDb_license_id=f"optimize_{license_id}"

    apiKey = None
    serviceProvider = None
    model = None
    sa_info = None
    resource = None
    resourceId = None
    video_name=None
    try:
    
        if not prompt_id:
            prompt_id = str(uuid.uuid4().hex)

        if not session_id:
            session_id = str(uuid.uuid4().hex)

        if not ref_id:
            raise APIError(responseCode=400, message="Unable to generate test cases. Please reattach the Figma instance and try again.")

        try:
            sp_config = resolve_service_provider(license_id, project_id)
        except Exception as e:
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
            template = manualTestCase.fetch_test_case_template(license_id, project_id)
            logger.info("Template Fetched Successfully")
        except Exception as e:
            logger.info("Failed to Fetch the template of MTC")
            raise APIError(responseCode=400,message=f"Template Fetching Failed:{e}")

        template_id=template['_id']
        logger.info(f"template_id: {template_id}")
        test_case_fields = [item["label"] for item in template.get("testCaseDetails", [])]
        test_step_fields = [cell["value"]for cell in template.get("testSteps", []).get("data", [[]])[0]]  

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
            print("this is document:",docs)
            
            if not docs:
                if not (video_name):
                    logger.error(f"Failed to retrieve Instance Details for ref_ids: {lookup_keys} and prompt_id: {prompt_id}.")
                    return JSONResponse(
                        status_code=400,
                        content={"status": "failure", "message": f"Unable to generate test cases. Please reattach the figma instance and try again."}
                    )
            else:
                doc=docs[0]
                summary_data = doc.get("summary", {})
                if isinstance(summary_data, dict):
                    video_name=summary_data.get("videoName") or video_name

            if not video_name:
                logger.error(f"No stored videoName found for ref_ids: {lookup_keys} and promp_id: {prompt_id}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "failure",
                        "message": "Unable to generate test cases. Please reattach the figma instance and try again"
                    })

        except Exception as db_err:
            logger.error(f"Failed to fetch stored summary from mtc_to_atc for ref_ids {lookup_keys}: {db_err}")
            if not (video_name):
                logger.error(f"No stored video Details found in mtc_to_atc for ref_ids: {lookup_keys} and prompt_id: {prompt_id}")
                return JSONResponse(
                    status_code=400,
                    content={"status": "failure", "message": "Unable to generate test cases. Please reattach the video and try again"}
                )
        logger.info(f"This is video name:{video_name}")

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

        asyncio.create_task(manualTestCase.handle_user_input_for_video_process(
                user_id=user_id,
                license_id=license_id,
                project_id=project_id,
                branch_id=branch_id,
                env=env,
                session_id = session_id,
                session_name = None,
                prompt_id=prompt_id,
                unique_id=unique_id,
                dateTime=dateTime,
                template=json_structure,
                original_template=template,
                template_id=template_id,
                input_type=input_type,
                user_input=user_input,
                user_input_tokens=user_input_tokens,
                video_name=video_name,
                chatContext=summary,
                prompt_type=prompt_type,
                script_type='manual',
                count=count,
                is_modified=None,
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
        logger.error(f"Error in generate-prompt pipeline: {str(e)}", exc_info=True)

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
                user_input_tokens=user_input_tokens,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                llm_error_response=str(e),
                branch_id=branch_id,
            )

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
                            "is_completed": False,
                            "video_name": video_name,
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


@router.get("/video-mongodb-status")
async def video_status(license_id: str = Query(...)):
    try:
        if not license_id:
            logger.warning("Missing required Parameter: license_id")
            return JSONResponse(status_code=200,content={"status":"FAILED","responseCode":500})
        try:
            env=None
            logger.info("Fetching env")
            env=os.getenv("PROFILE")
        except Exception as e:
            logger.info("Fail to Fetch env")
            return JSONResponse(status_code=200,content={"status":"FAILED","responseCode":500})

        try:
            _lid= await mongodb_license_inti(license_id,env)
        except Exception as e:
            return JSONResponse(status_code=200,content={"status":"FAILED","responseCode":500})

        try:
            logger.info("Mongodb connection and collection fetching")
            collection=get_the_collection(_lid)

            data=get_status_video(collection)
        except Exception as e:
            logger.error("mongodb collection fetching failed")
            return JSONResponse(status_code=200,content={"status":"FAILED","responseCode":500})

        video_data = list(data)

        for video in video_data:
            video["licenseId"] = license_id

        return JSONResponse(
            status_code=200,
            content={
                "status": "SUCCESS",
                "responseCode": 200,
                "responseObject": video_data
            }
        )

    except Exception as e:
        logger.error(
        f"mongodb collection fetching failed: {str(e)}",
        exc_info=True
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "FAILED",
            "responseCode": 500,
            "responseObject": []
        }
    )