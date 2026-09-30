"""Image and video analysis used before MTC generation."""
from src.persistence._shared import *  # noqa: F401,F403


class MediaAnalysisMixin:
     


    async def VideoAudioAnalyse(self,session_id,license_id,project_id,bearer_token,
                    template,apiKey,serviceProvider,model,prompt_type,
                    sa_info,user_input,session_name,count,
                    prompt_id,user_id,input_type,script_type,file_name,
                    file_content,is_modified,user_input_tokens,
                    image_content,template_id,unique_id,dateTime,original_template,
                    env,video_bytes,video_filename,video_name,resourceId,resource,Input_Token_Video,Output_Token_Video,request_time_for_storing_1_tc_in_MD):
        videoContent = {}
        temp_dir = None
        audio_path = None
        video_path = None
        audio_output = None
        combined_summary = None
        audio_result = {"has_audio": False}
        
        try:
            if count == 1:
                
                temp_dir = tempfile.mkdtemp(prefix="video_")
                try:
                    ext = os.path.splitext(video_filename)[1].lower() if video_filename else ""
                    video_path = os.path.join(temp_dir, f"{unique_id}{ext}")
                    with open(video_path, "wb") as buffer:
                        buffer.write(video_bytes)

                    # Frame extraction
                    logger.info(f"Video path: {video_path}")
                    logger.info(f"Video exists: {os.path.exists(video_path)}")
                    logger.info(f"Video size: {os.path.getsize(video_path)} bytes")
                    cap = cv2.VideoCapture(video_path)
                    logger.info(f"cap.isOpened(): {cap.isOpened()}")
                    if not cap.isOpened():
                        raise APIError(responseCode=400, message="Invalid video file, could not be opened.")

                    fps = cap.get(cv2.CAP_PROP_FPS)
                    logger.info(f"Detected video FPS: {fps}")
                    fps = fps if fps and fps > 0 else 1
                    if fps == 1:
                        logger.warning("FPS fallback used (invalid or missing FPS metadata)")
                    n = max(1, int(fps))  # 1 frame per second sampling

                    logger.info(f"Sampling interval (frames per second): {n}")

                    base64Frames = []
                    frame_count = 0

                    while cap.isOpened():
                        success, frame = cap.read()
                        if not success:
                            break

                        if frame_count % n == 0:
                            # -------- Resize for LLM token optimization --------
                            MAX_SIDE = 1280
                            orig_h, orig_w = frame.shape[:2]
                            orig_pixels = orig_w * orig_h

                            if max(orig_w, orig_h) > MAX_SIDE:
                                scale = MAX_SIDE / max(orig_w, orig_h)
                                new_width = int(orig_w * scale)
                                new_height = int(orig_h * scale)
                                frame = cv2.resize(
                                    frame,
                                    (new_width, new_height),
                                    interpolation=cv2.INTER_AREA
                                )

                            h, w = frame.shape[:2]
                            final_pixels = w * h
                            
                            _, buffer = cv2.imencode(
                                ".jpg",
                                frame,
                                [cv2.IMWRITE_JPEG_QUALITY, 90]
                            )
                            base64Frames.append(
                                base64.b64encode(buffer).decode("utf-8")
                            )
                        frame_count += 1
                    cap.release()
                    logger.info(f"{len(base64Frames)} frames extracted from video.")

                    if not base64Frames:
                        raise APIError(responseCode=400, message="No frames could be extracted from the video.")

                    try:
                        stds = frame_variance_stats(base64Frames)
                        if all(s < 3.0 for s in stds):
                            raise APIError(responseCode=400, message="Please upload a valid software application recording")
                        
                        logger.info("Summarization initiated")
                        start_time = time.time()
                        videoContent,inputToken,outputToken=await videoSummary(base64Frames,False, serviceProvider=serviceProvider, apiKey=apiKey, model=model, sa_info=sa_info, resource=resource, resourceId=resourceId)
                        
                        Input_Token_Video+=inputToken
                        Output_Token_Video+=outputToken
                        end_time = time.time()  
                        duration = end_time - start_time
                        logging.info(f"Summarization of attached VideoFile Timing | Duration: {duration:.3f}s")
                    except APIError:
                        raise
                    except Exception as e:
                        logger.exception(f"VideoSummarization failed: {str(e)}")
                        raise APIError(responseCode=400, message=str(e))
                    
                    if not videoContent.get("is_valid_software_video"):
                        raise APIError(responseCode=400, message="Please upload a valid software application recording")
                except Exception as e:
                    if isinstance(e, APIError):
                        raise e
                    raise APIError(responseCode=400, message=f"Video summary Fail: {e}")
                    
                # Audio extraction
                try:
                    logger.info("Audio extraction started")
                    start_time = time.time()
                    audio_result = extract_audio_from_video(video_path)
                    logger.info(f"Audio extraction result: {audio_result}")
                    end_time = time.time()
                    duration = end_time - start_time
                    logging.info(f"Extracting Audio Timing | Duration: {duration:.3f}s")
                except Exception as e:
                    logger.exception(f"Audio extraction failed: {str(e)}")
                    audio_result = {"has_audio": False, "audio_path": None}

                try:
                    logger.info(f"Audio passing to wisper llm")
                    start_time = time.time()
                    if audio_result and audio_result.get("has_audio") and audio_result.get("audio_path"):
                        logger.info("Audio detected. Sending to Whisper")
                        audio_path = audio_result["audio_path"]
                        audio_output = transcribe_audio(audio_path)
                        logger.info("Whisper transcription completed")
                    else:
                        logger.info("No audio found in video")
                    end_time = time.time()
                    duration = end_time - start_time
                    logging.info(f"Audio to text Timing | Duration: {duration:.3f}s") 
                except Exception as e:
                    logger.exception(f"WISPER LLM FAIL ERROR: {str(e)}")

                try:
                    logger.info(f"Combining the video and audio")
                    start_time = time.time()
                    if audio_output and audio_output.get('success')==True and audio_output.get("transcription"):
                        exact_video_txt=audio_output.get('transcription')
                        video_frame_summary=videoContent.get("summary")
                        systemPrompt,userPrompt,responseFormat=CheckingsummaryPrompt(exact_video_txt,video_frame_summary)
                        combined_summary,input_tokens_merge, output_tokens_merge=await LLMClient.generate_async(
                            serviceProvider=serviceProvider,
                            model="openai/gpt-oss-20b" if serviceProvider in ["DefaultFireFlink"] else model,
                            apiKey=apiKey,
                            system_prompt=systemPrompt, 
                            user_prompt=userPrompt,
                            sa_info=sa_info,
                            temperature=0.3,
                            response_format=responseFormat,
                            return_usage=True,
                            max_tokens=65000
                        )
                        Input_Token_Video+=input_tokens_merge
                        Output_Token_Video+=output_tokens_merge
                    end_time = time.time()
                    duration = end_time - start_time
                    logging.info(f"Combined summary Timing | Duration: {duration:.3f}s") 
                except Exception as e: 
                    logger.exception(f"Wisper Model failed: {str(e)}")
                    
                try:
                    logger.info(f"replacing the summary with merge summary")
                    start_time = time.time()
                    if combined_summary and combined_summary.get('audio_related_to_summary')=='yes':
                        parsed = json.loads(combined_summary) if isinstance(combined_summary, str) else combined_summary
                        merged_summary = parsed["merged_summary"]
                        merged_summary = merged_summary.replace("\n", "\n")
                        videoContent["summary"]=merged_summary
                    end_time = time.time()
                    duration = end_time - start_time
                    logging.info(f"Replacing summary Timing | Duration: {duration:.3f}s") 
                except Exception as e:
                    logger.exception(f"Failed to Replace summary: {str(e)}") 
        except APIError:
            raise
        except Exception as e:
            logger.exception(f"Video processing failed: {str(e)}")
            raise APIError(responseCode=400, message=str(e))
              
        finally:
            if audio_path is not None and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception as e:
                    pass
            if temp_dir is not None and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    pass

        videoContent.pop("is_valid_software_video", None)
        logger.info(f"Video content extracted successfully.")

        return videoContent, Input_Token_Video, Output_Token_Video


