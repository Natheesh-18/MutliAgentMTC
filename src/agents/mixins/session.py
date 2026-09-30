"""Session-name updates on the prompt document."""
from src.agents._shared import *  # noqa: F401,F403


class SessionMixin:
    def update_session_name(self,
        mongoCollectionName,
        unique_id,
        session_id,
        prompt_id,
        count,
        session_name
    ):
        mtc = get_manual_test_case()
        try:
            collection_prompt = mtc.load_collection_for_user_prompt(
                license_id=mongoCollectionName
            )

            result = collection_prompt.update_one(
                {"_id": unique_id,
                "session_id":session_id,
                "prompt_id":prompt_id,
                "count":count},
                {
                    "$set": {
                        "session_name": session_name
                    }
                }
            )
            if result.modified_count > 0:
                logger.info(f"Updated session_name for _id: {unique_id}")
                return {"status": "success"}

            elif result.matched_count > 0:
                logger.info(f"No changes needed for _id: {unique_id}")
                return {"status": "no_change"}

            else:
                logger.warning(f"No document found for _id: {unique_id}")
                return {"status": "not_found"}

        except Exception as e:
            logger.error(f"Error updating session_name: {e}")
            return {"status": "failure", "error": str(e)}
