"""Prompt and test-case CRUD / read APIs."""
from src.persistence._shared import *  # noqa: F401,F403


class PromptCrudMixin:
    def update_user_prompt_details_by_id(self, document_id, license_id, update_data):
        try:
            collection_user_prompt_details = (
                self.load_collection_for_user_prompt_details(license_id=license_id)
            )
            filter_query = {"_id": document_id}
            update_query = {"$set": update_data}

            result = collection_user_prompt_details.update_one(
                filter_query, update_query
            )

            if result.matched_count > 0:
                if result.modified_count > 0:
                    updated_document = collection_user_prompt_details.find_one(
                        filter_query
                    )
                    return {
                        "status": "SUCCESS",
                        "updated_document": updated_document,
                        "prompt_id": updated_document.get("prompt_id", "Not found"),
                        "message": "TestCase updated successfully",
                    }
                else:
                    return {
                        "responseCode": 200,
                        "status": "SUCCESS",
                        "message": "No changes made to the document",
                    }
            else:
                return {
                    "responseCode": 400,
                    "status": "FAILURE",
                    "message": "Document not found",
                }

        except Exception as e:
            logger.error(f"Error updating document: {e}")
            return {"status": "failure", "error": f"An error occurred: {str(e)}"}

    def delete_id(self, document_id, license_id, prompt_id, count, prompt_unique_id):
        try:
            user_prompt_details_collection = (
                self.load_collection_for_user_prompt_details(license_id=license_id)
            )
            user_prompt_collection = self.load_collection_for_user_prompt(
                license_id=license_id
            )
            if document_id:
                if not isinstance(document_id, list):
                    document_id = [document_id]

                filter_query = {"_id": {"$in": document_id}}
                result = user_prompt_details_collection.delete_many(filter_query)

                print(f"Deleted {result.deleted_count} documents.")
            else:
                print("No document_id provided.")

            if result.deleted_count > 0:
                template_for_prompt_exists = {"prompt_id": prompt_id, "count": count}
                exists = (
                    user_prompt_details_collection.find_one(template_for_prompt_exists)
                    is not None
                )
                if not exists:
                    user_prompt_collection.delete_one({"_id": prompt_unique_id})
                    user_prompt_details_collection.update_many(
                        {"count": {"$gt": count}}, {"$inc": {"count": -1}}
                    )
                    user_prompt_collection.update_many(
                        {"count": {"$gt": count}}, {"$inc": {"count": -1}}
                    )
                else:
                    user_prompt_collection.update_one(
                        {"_id": prompt_unique_id},
                        {"$inc": {"test_case_count": -result.deleted_count}},
                    )
                return {
                    "responseCode": 200,
                    "status": "SUCCESS",
                    "message": "Document deleted successfully",
                }
            else:
                return {
                    "responseCode": 404,
                    "status": "FAILURE",
                    "message": "Document not found",
                }

        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return {"status": "failure", "error": f"An error occurred: {str(e)}"}

    def delete_prompt(self, prompt_id, license_id):
        try:
            collection_prompt = self.load_collection_for_user_prompt(
                license_id=license_id
            )
            collection_user_prompt_details = (
                self.load_collection_for_user_prompt_details(license_id=license_id)
            )

            filter_query = {"prompt_id": prompt_id}

            result_prompt = collection_prompt.delete_many(filter_query)
            result_user_prompt_details = collection_user_prompt_details.delete_many(
                filter_query
            )

            deleted_count_prompt = result_prompt.deleted_count
            deleted_count_user_prompt_details = result_user_prompt_details.deleted_count

            if deleted_count_prompt > 0 or deleted_count_user_prompt_details > 0:
                return {
                    "status": "SUCCESS",
                    "responseCode": 200,
                    "message": f"Deleted {deleted_count_prompt} document(s) from 'collection_prompt' and "
                    f"{deleted_count_user_prompt_details} document(s) from 'collection_user_prompt_details'.",
                }
            else:
                return {
                    "status": "FAILURE",
                    "responseCode": 400,
                    "message": "No documents found with the provided prompt_id in both collections.",
                }

        except Exception as e:
            logger.error(f"Error deleting documents by prompt_id: {e}")
            return {"status": "failure", "error": f"An error occurred: {str(e)}"}

    def delete_all(self, license_id, session_id):
        try:
            delete_prompt_details_collection = (
                self.load_collection_for_user_prompt_details(license_id=license_id)
            )
            user_prompt_collection = self.load_collection_for_user_prompt(
                license_id=license_id
            )

            if isinstance(session_id, list):
                filter_query = {"session_id": {"$in": session_id}}
                result1 = delete_prompt_details_collection.delete_many(filter_query)
                result2 = user_prompt_collection.delete_many(
                    {"session_id": {"$in": session_id}}
                )
            else:
                filter_query = {"session_id": session_id}
                result1 = delete_prompt_details_collection.delete_one(filter_query)
                result2 = user_prompt_collection.delete_one({"session_id": session_id})

            if result1.deleted_count > 0 or result2.deleted_count > 0:
                return {
                    "responseCode": 200,
                    "status": "SUCCESS",
                    "message": "Document(s) deleted successfully",
                }
            else:
                return {
                    "responseCode": 400,
                    "status": "FAILURE",
                    "message": "Document not found",
                }

        except Exception as e:
            return {"status": "failure", "error": f"An error occurred: {str(e)}"}

    def delete_session_id(self, session_id, license_id):
        try:
            collection_prompt = self.load_collection_for_user_prompt(
                license_id=license_id
            )
            collection_user_prompt_details = (
                self.load_collection_for_user_prompt_details(license_id=license_id)
            )

            filter_query = {"session_id": session_id}

            result_prompt = collection_prompt.delete_many(filter_query)
            result_user_prompt_details = collection_user_prompt_details.delete_many(
                filter_query
            )

            deleted_count_prompt = result_prompt.deleted_count
            deleted_count_user_prompt_details = result_user_prompt_details.deleted_count

            if deleted_count_prompt > 0 or deleted_count_user_prompt_details > 0:
                return {
                    "status": "SUCCESS",
                    "responseCode": 200,
                    "message": f"Deleted {deleted_count_prompt} document(s) from 'collection_prompt' and "
                    f"{deleted_count_user_prompt_details} document(s) from 'collection_user_prompt_details'.",
                }
            else:
                return {
                    "status": "FAILURE",
                    "responseCode": 400,
                    "message": "No documents found with the provided prompt_id in both collections.",
                }

        except Exception as e:
            logger.error(f"Error deleting documents by prompt_id: {e}")
            return {"status": "failure", "error": f"An error occurred: {str(e)}"}

    def get_by_prompt_id(self, prompt_id, license_id, count):
        collection_prompt = self.load_collection_for_user_prompt(license_id=license_id)
        collection_prompt_details = self.load_collection_for_user_prompt_details(
            license_id=license_id
        )

        filter_query = {"prompt_id": prompt_id, "count": count}

        prompt_document = collection_prompt.find_one(filter_query)

        user_prompt_details_documents = collection_prompt_details.find(filter_query)

        if prompt_document:
            response = {
                "prompt_document": prompt_document,
                "test_cases_details": converting_values_to_list_of_string(
                    list(user_prompt_details_documents)
                ),
            }
            return {"responseCode": 200, "status": "SUCCESS", "data": response}
        else:
            return {
                "responseCode": 400,
                "status": "FAILURE",
                "message": "No documents found with the provided prompt_id.",
            }


    def get_all_user_prompts_and_last_user_prompt_details(self, license_id, project_id):
        try:
            collection_user_prompt = self.load_collection_for_user_prompt(
                license_id=license_id
            )
            collection_user_prompt_details = (
                self.load_collection_for_user_prompt_details(license_id=license_id)
            )

            all_user_prompts_cursor = collection_user_prompt.aggregate(
                [
                    {"$match": {"project_id": project_id}},
                    {
                        "$addFields": {
                            "_id": {"$toString": "$_id"},
                            "session_id": {"$toString": "$session_id"},
                        }
                    },
                    {"$sort": {"created_at": 1}},
                    #{"$limit": 30},
                ]
            )
            all_user_prompts_list = list(all_user_prompts_cursor)[-100:]

            if not all_user_prompts_list:
                return {
                    "status": "failure",
                    "message": "No documents found in user_prompt_collection",
                }

            seen_sessions = set()
            session_list = []
            for prompt in all_user_prompts_list:
                sid = prompt.get("session_id")
                sname = prompt.get("session_name", "Unnamed Session")
                if sid and sid not in seen_sessions:
                    seen_sessions.add(sid)
                    session_list.append({"session_id": sid, "session_name": sname})
                    if len(session_list) > 30: 
                        removed = session_list.pop(0)
                        seen_sessions.remove(removed["session_id"])

            last_session_id = all_user_prompts_list[-1].get("session_id")

            last_session_prompts = [
                p
                for p in all_user_prompts_list
                if p.get("session_id") == last_session_id
            ]

            last_prompt = last_session_prompts[-1] if last_session_prompts else None
            last_prompt_id = last_prompt.get("prompt_id") if last_prompt else None
            
            if last_prompt:
                latest_count = last_prompt.get("count", None)


            if last_prompt_id:
                test_case_cursor = collection_user_prompt_details.aggregate(
                    [
                        {"$match": {"prompt_id": last_prompt_id, "count": latest_count}},
                        {
                            "$addFields": {
                                "_id": {"$toString": "$_id"},
                                "prompt_id": {"$toString": "$prompt_id"},
                            }
                        },
                        {"$sort": {"created_at": 1}},
                    ]
                )
                last_prompt_test_cases = list(test_case_cursor)
            else:
                last_prompt_test_cases = []

            return {
                "status": "SUCCESS",
                "responseCode": 200,
                "data": {
                    "sessions": session_list,
                    "user_prompts": last_session_prompts,
                    "test_cases_details": converting_values_to_list_of_string(
                        last_prompt_test_cases
                    ),
                },
            }

        except Exception as e:
            return {"status": "failure", "error": str(e)}

    def get_session_id(self, license_id, session_id):
        try:
            collection_user_prompt = self.load_collection_for_user_prompt(
                license_id=license_id
            )
            collection_user_prompt_details = (
                self.load_collection_for_user_prompt_details(license_id=license_id)
            )

            all_user_prompts = collection_user_prompt.aggregate(
                [
                    {"$match": {"session_id": session_id}},
                    {"$addFields": {"_id": {"$toString": "$_id"}}},
                    {"$sort": {"created_at": 1}},
                    #{"$limit": 100},
                ]
            )
            all_user_prompts_list = list(all_user_prompts)[-100:]

            if not all_user_prompts_list:
                return {
                    "status": "failure",
                    "message": "No documents found in user_prompt_collection",
                }

            last_prompt_id = all_user_prompts_list[-1]["prompt_id"]

            if last_prompt_id:
                latest_count_result = collection_user_prompt_details.aggregate([
                    {"$match": {"prompt_id": last_prompt_id}},
                    {"$group": {"_id": "$prompt_id", "latest_count": {"$max": "$count"}}}
                ])
                latest_count_data = list(latest_count_result)

                if latest_count_data:
                    latest_count = latest_count_data[0]["latest_count"]

                    user_prompt_details_with_testcases = collection_user_prompt_details.aggregate(
                        [
                            {"$match": {"prompt_id": last_prompt_id, "count": latest_count}},
                            {
                                "$addFields": {
                                    "_id": {"$toString": "$_id"},
                                    "prompt_id": {"$toString": "$prompt_id"},
                                }
                            },
                            {"$sort": {"created_at": 1}},
                        ]
                    )
                    user_prompt_details_list = list(user_prompt_details_with_testcases)
                else:
                    latest_count = None
                    user_prompt_details_list = []
            else:
                latest_count = None
                user_prompt_details_list = []

            return {
                "status": "SUCCESS",
                "responseCode": 200,
                "data": {
                    "user_prompts": all_user_prompts_list,
                    "test_cases_details": converting_values_to_list_of_string(
                        user_prompt_details_list
                    )
                },
            }

        except Exception as e:
            return {"status": "failure", "error": str(e)}
