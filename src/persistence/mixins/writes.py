"""Prompt document writes, DB init, template and file fetch."""
from src.persistence._shared import *  # noqa: F401,F403


class PromptWritesMixin:
    def save_prompt_db(
        self,
        session_id,
        unique_id,
        dateTime,
        session_name,
        user_input,
        license_id,
        project_id,
        prompt_id,
        user_id,
        count,
        script_type,
        input_type,
        file_name,
        file_content,
        test_case_count,
        user_input_tokens,
        total_output_tokens,
        total_tokens_consumed,
        apiKey,
        serviceProvider,
        model,
        images_path,
        image_content,
        image_data,
        video_name,
        prompt_type,
        mongoCollectionName,
        branch_id=None,
        error_message=None,
        follow_up=None,
        generation_status=None,
    ):
        logger.info("Stepped into Saving prompt to DB...")
        try:
            if images_path is None:
                images_path=[]
            elif not isinstance(images_path,list):
                images_path=[images_path]
            collection_prompt = self.load_collection_for_user_prompt(
                license_id=mongoCollectionName
            )
            if generation_status is None:
                generation_status = "failed" if error_message else "completed"
            document = {
                "_id": unique_id,
                "prompt_id": prompt_id,
                "file_name": file_name,
                "file_content": file_content,
                "test_case_count": test_case_count,
                "user_input_tokens": user_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens_consumed": total_tokens_consumed,
                "image_content":image_content,
                "image_data":image_data,
                "video_name":video_name,
                "is_complete":True,
                "generation_status": generation_status,
                "error_message": error_message,
                "count": count,
                "session_id": session_id,
                "session_name": session_name,
                "created_at": dateTime,
                "project_id": project_id,
                "user_id": user_id,
                "prompt": user_input,
                "script_type": script_type,
                "input_type": input_type,
                "prompt_type": prompt_type,
                "follow_up":follow_up
            }
            result = collection_prompt.update_one(
                {"_id": unique_id},
                {"$set": document},
                upsert=True
            )
            if result.upserted_id is not None:
                logger.info(f"Inserted new document with _id: {unique_id}")
            elif result.modified_count > 0:
                logger.info(f"Updated existing document with _id: {unique_id}")
            elif result.matched_count > 0:
                logger.info(f"Document already exists, no changes for _id: {unique_id}")
            else:
                logger.error(f"Unexpected DB result for _id: {unique_id}")
                return {"status": "failure", "message": "DB operation failed"}
            return {"_id": unique_id, "prompt_id": prompt_id}
        except Exception as e:
            logger.error(f"Error saving prompt for session_id {session_id}: {e}")
            return {"error": f"Failed to save prompt: {str(e)}"}

    def save_user_prompt_details(
        self,
        prompt_id,
        parent_id,
        session_id,
        session_name,
        template_id,
        response,
        license_id,
        count,
        script_type,
        input_type,
        is_modified,
        project_id,
        mongoCollectionName,
        request_time_for_storing_1_tc_in_MD,
        branch_id=None
    ):
        try:
            if isinstance(response, dict):
                logger.error(f"Error in response: {response['error']}")
                return {"error": response["error"], "status_code": 500}

            logger.info("Save_user_prompt_details called")
            if not isinstance(response, list):
                response = [response]

            has_test_cases = any(item.get("testCaseDetails", []) for item in response)
            if not has_test_cases:
                logger.error("No test cases found in response.")
                return {"error": "No test cases found in response.", "status_code": 500}

            collection_user_prompt_details = (
                self.load_collection_for_user_prompt_details(license_id=mongoCollectionName)
            )
            response_documents = []
            from src.persistence.post_response import normalize_test_case_type
        
            for  item in response:
                test_cases = item.get("testCaseDetails", [])
                req_id = next(
                    d["value"][0]
                    for d in test_cases
                    if d.get("label") == "Requirement Id"
                )
                try:
                    i = int(req_id.split("-")[-1])
                except:
                    raise ValueError(f"Invalid Requirement Id: {req_id}")
                

                test_steps = item.get("testSteps", {})
                test_case_id = str(uuid.uuid4().hex)
                test_case_type = item.get("testCaseType") or item.get("Test Case Type") or ""
                # FE/ATC require canonical casing (Web, not web)
                test_case_type = normalize_test_case_type(test_case_type)

                final_test_steps = test_steps.get("data")
                for step in final_test_steps:
                    if step != final_test_steps[0]:
                        for value in step:
                            context_disable = value.get("contextDisable", {})
                            context_disable.pop("Add Row Top", None)
                            context_disable.pop("Delete Row", None)
                            style = value.get("styles", value.get("style", {}))
                            style["backgroundColor"] = ("#FFFFFF",)
                            style["underline"] = False
                            style["alignment"]["horizontal"] = "LEFT"
                            value["readOnly"] = False

                test_steps.update({"data": final_test_steps})

                test_case_document = {
                    "mtc_index": i,
                    "parent_id": parent_id,
                    "session_id": session_id,
                    "session_name": session_name,
                    "template_id": template_id,
                    "prompt_id": prompt_id,
                    "project_id": project_id,
                    "created_at": datetime.now(timezone.utc),
                    # "count": count,
                    "script_type": script_type,
                    "input_type": input_type,
                    "is_modified": is_modified,
                    # "manualTestCase": {
                    #     "testCaseDetails": test_cases,
                    #     "testSteps": test_steps,
                    #     "test_case_type": test_case_type,
                    # }
                    "testCaseDetails": test_cases,
                    "testSteps": test_steps,
                    "test_case_type": test_case_type,
                    "branch_id": branch_id,
                }

                try:
                    logger.debug(f"save_user_prompt_details upserting: prompt_id={prompt_id}, session_id={session_id}, parent_id={parent_id}, mtc_index={i}")
                    result = collection_user_prompt_details.update_one(
                        {
                            "parent_id": parent_id,
                            "mtc_index": i,
                            "count":count,
                        },
                        {
                            "$set": test_case_document,
                            "$setOnInsert": {
                                "_id": test_case_id
                            }
                        },
                        upsert=True
                    )

                    if result.upserted_id:
                        logger.info(f"Inserted test case {i}")

                        if request_time_for_storing_1_tc_in_MD is not None and request_time_for_storing_1_tc_in_MD.get("stored_time") is None:
                            request_time_for_storing_1_tc_in_MD["stored_time"] = time.time()
                            start_time = request_time_for_storing_1_tc_in_MD.get("start_time")
                            if start_time:
                                duration = request_time_for_storing_1_tc_in_MD["stored_time"] - start_time
                                logger.info(f"First TC stored in {duration:.3f} seconds")

                    elif result.modified_count > 0:
                        logger.info(f"Updated test case {i}")

                    elif result.matched_count > 0:
                        logger.info(f"No change for test case {i}")

                    response_documents.append(test_case_document)

                except Exception as db_error:
                    logger.error(f"Database error: {db_error}")
                    continue

            if request_time_for_storing_1_tc_in_MD is not None and request_time_for_storing_1_tc_in_MD.get("first_batch_stored_time") is None:
                request_time_for_storing_1_tc_in_MD["first_batch_stored_time"] = time.time()
                start_time = request_time_for_storing_1_tc_in_MD.get("start_time")
                if start_time:
                    duration = request_time_for_storing_1_tc_in_MD["first_batch_stored_time"] - start_time
                    logger.info(f"TIMING | First batch of test cases stored in MongoDB | Duration: {duration:.3f}s")

            return response_documents

        except Exception as e:
            logger.error(f"Exception in save_user_prompt_details: {str(e)}")
            return {"error": f"Failed to save test cases: {str(e)}", "status_code": 500}

        except Exception as e:
            logger.error(f"Exception in save_user_prompt_details: {str(e)}")
            return {"error": f"Failed to save test cases: {str(e)}", "status_code": 500}

    def initialize_db_and_collections(
        self,
        license_id,
        unique_id,
        dateTime,
        session_id,
        session_name,
        user_input,
        project_id,
        prompt_id,
        user_id,
        count,
        script_type,
        input_type,
        user_input_tokens,
        apiKey,
        serviceProvider,
        model,
        prompt_type,
        llm_error_response:Optional[str]=None,
        images_path:Optional[Any]=None,
        file_name:Optional[str]=None,
        file_content:Optional[Any] = None,
        video_name:Optional[str] = None,
        branch_id=None,
    ):
        import time
        t_start = time.time()
        try:
            # Get collection references
            collection_prompt = self.load_collection_for_user_prompt(license_id)
            logger.info(f"Collection for user prompt: {collection_prompt}")
            collection_details = self.load_collection_for_user_prompt_details(license_id)
            db = collection_prompt.database  

            existing_collections = db.list_collection_names()

            # -------------------------------
            # parentCollection : user_prompt_collection
            # -------------------------------
            try:
                if self.user_prompt_collection not in existing_collections:
                    logger.info(f"ParentCollection '{self.user_prompt_collection}' does not exist — creating it now")
                    db.create_collection(self.user_prompt_collection)
                    logger.info("ParentCollection is created MongoDB")
                logger.info(f"Upserting initial request document (unique_id={unique_id}) into ParentCollection (upsert=True)")

                db_result = collection_prompt.update_one(

                    {"_id": unique_id},
                    {
                        "$set": {
                            "prompt_id": prompt_id,
                            "project_id": project_id,
                            "session_id": session_id,
                            "session_name": session_name,
                            "created_at": dateTime,
                            "user_id": user_id,
                            "prompt": user_input,
                            "script_type": script_type,
                            "input_type": input_type,
                            "count": count,
                            "file_name": file_name,
                            "file_content": file_content,
                            "test_case_count": 0,
                            "user_input_tokens": user_input_tokens,
                            "total_output_tokens": 0,
                            "total_tokens_consumed": 0,
                            "is_complete": False,
                            "generation_status": "running",
                            "error_message": llm_error_response,
                            "apiKey": apiKey,
                            "serviceProvider": serviceProvider,
                            "model": model,
                            "images_path": images_path,
                            "video_name": video_name,
                            "prompt_type": prompt_type,
                            "branch_id": branch_id
                        },
                    },
                    upsert=True,
                )
                logger.info(f"Initial request document upserted successfully in ParentCollection (unique_id={unique_id})")
            except Exception as e:
                logger.error(f"Upserting initial request document into ParentCollection failed: {e}")

            # -------------------------------
            # childCollection : user_prompt_details_collection
            # -------------------------------
            try:
                logger.info(f"Ensuring child collection exists: '{self.user_prompt_details_collection}'")
                if self.user_prompt_details_collection not in existing_collections:
                    logger.info("childCollection is not exist")
                    db.create_collection(self.user_prompt_details_collection)
                    logger.info("childCollection Created in MongoDB")
                logger.info(f"Child collection '{self.user_prompt_details_collection}' is ready")
            except Exception as e:
                logger.error(f"Ensuring child collection '{self.user_prompt_details_collection}' failed: {e}")
        except Exception as e:
            logger.error(f"Error initializing DB/collections: {e}")
        finally:
            logger.info(f"TIMING | initialize_db_and_collections | Duration: {time.time() - t_start:.3f}s")

    def initialize_db_and_collections_mtc_to_atc(
        self,
        license_id,
        unique_id,
        content:Optional[Any] = None,
    ):
        import time
        t_start = time.time()
        try:
            collection_prompt = self.load_collection_for_mtc_to_atc(license_id)
            logger.info(f"Collection for mtc_to_atc: {collection_prompt}")
            db = collection_prompt.database  

            existing_collections = db.list_collection_names()

            try:
                if "mtc_to_atc" not in existing_collections:
                    logger.info(f"ParentCollection 'mtc_to_atc' does not exist — creating it now")
                    db.create_collection("mtc_to_atc")
                    logger.info("ParentCollection is created MongoDB")
                logger.info(f"Upserting initial request document (unique_id={unique_id}) into ParentCollection (upsert=True)")

                collection_prompt.update_one(

                    {"_id": unique_id},
                    {
                        "$set": {
                            "summary": content,
                            "ref_id": unique_id
                        }
                    },
                    upsert=True,
                )
                logger.info(f"Initial request document upserted successfully in ParentCollection (unique_id={unique_id})")
            except Exception as e:
                logger.error(f"Upserting initial request document into ParentCollection failed: {e}")

        except Exception as e:
            logger.error(f"Error initializing DB/collections for mtc_to_atc: {e}")
        finally:
            logger.info(f"TIMING | initialize_db_and_collections_mtc_to_atc | Duration: {time.time() - t_start:.3f}s")

    def fetch_test_case_template(self, license_id, project_id):
        import time
        t_start = time.time()
        java_api_url = f"{self.base_url}/optimize/v1/scriptTemplate/internal/get-testcase-template-for-project-id-by-ai/{license_id}/{project_id}"
        headers = {}
        try:
            response = requests.get(java_api_url, headers=headers)
            response.raise_for_status()
            res_obj = response.json().get("responseObject", {})
            logger.info(f"TIMING | fetch_test_case_template | Duration: {time.time() - t_start:.3f}s")
            return res_obj
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to fetch test case template for license_id={license_id}, project_id={project_id}: {e}"
            )
            logger.info(f"TIMING | fetch_test_case_template (FAILED) | Duration: {time.time() - t_start:.3f}s")
            return {}

    def fetch_file(
        self,
        file_id,
        bearer_token,
        license_type,
        project_id,
        project_name,
        project_type,
    ):
        url = f"{self.base_url}/optimize/v1/file/download/cloud/{file_id}"

        headers = {
            "Authorization": f"{bearer_token}",
            "licensetype": license_type,
            "projectid": project_id,
            "projectname": project_name,
            "projecttype": project_type,
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"File fetch failed: {e}")
            return None

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        if session_id not in self.session_info:
            self.session_info[session_id] = ChatMessageHistory()
        return self.session_info[session_id]
