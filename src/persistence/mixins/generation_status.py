"""Generation error / cancel status writes."""
from src.persistence._shared import *  # noqa: F401,F403


class GenerationStatusMixin:
    def save_Error(self, unique_id, error, mongoCollectionName):
        try:
            collection_prompt = self.load_collection_for_user_prompt(
                license_id=mongoCollectionName
            )

            # Update matching document
            result = collection_prompt.update_one(
                {"_id": unique_id},   # filter
                {
                    "$set": {
                        "error_message": error
                    }
                }
            )

            if result.upserted_id is not None:               
                logger.error(f"Inserted ERROR document with _id: {unique_id}")
            elif result.modified_count > 0:
                logger.error(f"Updated existing ERROR document with _id: {unique_id}")
            elif result.matched_count > 0:
                logger.error(f"ERROR Document already exists, no changes for _id: {unique_id}")
        except Exception as e:
            logger.error(f"Save_Error Exception: {e}", exc_info=True)

    def save_generation_error(self, unique_id, error, license_id, service_provider, input_tokens=0, output_tokens=0):
        try:
            api_error = build_api_error(error, service_provider=service_provider)
            clean_error_msg = api_error.message

            collection_prompt = self.load_collection_for_user_prompt(license_id=license_id)
            filter_query = {"_id": unique_id}
            update_query = {"$set": {
                "is_complete": True,
                "generation_status": "failed",
                "error_message": clean_error_msg,
                "user_input_tokens": input_tokens,
                "total_output_tokens": output_tokens,
                "total_tokens_consumed": input_tokens + output_tokens
            }}
            db_res = collection_prompt.update_one(filter_query, update_query)
            logger.info(f"MongoDB error update | matched={db_res.matched_count} modified={db_res.modified_count} id={unique_id}")
        except Exception as db_err:
            logger.error(f"Failed to update failure status in MongoDB: {db_err}", exc_info=True)

    def mark_generation_cancelled(
        self,
        unique_id,
        license_id,
        input_tokens=0,
        output_tokens=0,
        test_case_count=None,
        follow_up=None,
    ):
        """Mark a generation job as cancelled so SSE can EOF with CANCELLED."""
        try:
            collection_prompt = self.load_collection_for_user_prompt(license_id=license_id)
            update_fields = {
                "is_complete": True,
                "generation_status": "cancelled",
                "error_message": None,
                "user_input_tokens": input_tokens,
                "total_output_tokens": output_tokens,
                "total_tokens_consumed": input_tokens + output_tokens,
            }
            if test_case_count is not None:
                update_fields["test_case_count"] = test_case_count
            if follow_up is not None:
                update_fields["follow_up"] = follow_up
            db_res = collection_prompt.update_one(
                {"_id": unique_id},
                {"$set": update_fields},
            )
            logger.info(
                f"MongoDB cancel update | matched={db_res.matched_count} "
                f"modified={db_res.modified_count} id={unique_id} "
                f"test_case_count={test_case_count} tokens={input_tokens + output_tokens}"
            )
        except Exception as db_err:
            logger.error(f"Failed to update cancelled status in MongoDB: {db_err}", exc_info=True)

    def request_generation_cancel(self, unique_id, license_id):
        """
        Signal cancel without marking complete yet.
        Worker will finish tokens / testcase count / follow-up, then set is_complete.
        """
        try:
            collection_prompt = self.load_collection_for_user_prompt(license_id=license_id)
            collection_prompt.update_one(
                {"_id": unique_id},
                {"$set": {
                    "generation_status": "cancelled",
                    "error_message": None,
                }},
            )
        except Exception as db_err:
            logger.error(f"Failed to persist cancel status: {db_err}", exc_info=True)
        return request_cancel(unique_id)
