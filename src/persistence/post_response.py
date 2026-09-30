import copy
import re
import time
import logging
from typing import List, Dict, Any, Optional
import asyncio
from pydantic import BaseModel, ValidationError
from typing import Optional
import json
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    force=True   
)
logger = logging.getLogger(__name__)

# Platform type casing expected by FE / ATC generation
_TEST_CASE_TYPE_CANONICAL = {
    "web": "Web",
    "android": "Android",
    "ios": "iOS",
    "desktop": "Desktop",
    "api": "API",
    "webmobileandroid": "WebMobileAndroid",
}


def normalize_test_case_type(value) -> str:
    """Normalize platform testCaseType to FE/ATC canonical casing (e.g. web → Web)."""
    if value is None:
        return ""
    if isinstance(value, list):
        # Prefer first non-empty entry
        for item in value:
            normalized = normalize_test_case_type(item)
            if normalized:
                return normalized
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return _TEST_CASE_TYPE_CANONICAL.get(text.lower(), text)


async def re_validate_test_cases_v2(data: dict, counter_ref: list, counter_lock, prompt_type: Optional[str] = None) -> dict:

    valid_test_cases = []

    for tc in data.get("Test Cases", []):
        if not isinstance(tc, dict):
            continue
        if not tc.get("Test Case Name") or not tc.get("testCaseType"):
            continue

        if "Test Case Name" in tc:
            tc["Test Case Name"] = re.sub(r'[^a-zA-Z0-9\s]', '', tc["Test Case Name"])
            tc["Test Case Name"] = re.sub(r'\s+', ' ', tc["Test Case Name"]).strip()

        # FE/ATC expect canonical casing (Web, not web)
        tc["testCaseType"] = normalize_test_case_type(tc.get("testCaseType"))

        async with counter_lock:
            tc["Requirement Id"] = f"REQ-{counter_ref[0]:03d}"
            counter_ref[0] += 1

        tc["Status"] = "Not Executed"
        if prompt_type:
            tc["testCaseType"] = prompt_type


        valid_test_cases.append(tc)

    return {
        "summary": data.get("summary", ""),
        "Test Cases": valid_test_cases
    }
import os
isOnprem = json.loads(os.getenv("isOnprem", "false").lower())


class State(BaseModel):
        messages: List[Dict] = []
        raw_testcases: Optional[Dict] = None
        corrected_testcases: Optional[Dict] = None
        validated_testcases: Optional[Any] = None
        correction_log: List[Dict] = []
        summary: Optional[str] = None
        error: Optional[Any] = None
        llm_warning: dict | None = None

state = State()

async def process_llm_response(
    response,
    unique_id,
    template,
    license_id,
    session_id,
    session_name=None,
    project_id=None,
    prompt_id=None,
    count=None,
    script_type=None,
    input_type=None,
    template_id=None,
    is_modified=None,
    mongoCollectionName=None,
    request_time_for_storing_1_tc_in_MD=None,
    branch_id=None
):
    from src.persistence.prompt import Prompt
    mtc= Prompt("openai/gpt-oss-20b")


    try:
        test_cases = response.get("Test Cases", [])
        if not test_cases:
            logger.warning("No test cases found in response")
            return

        test_case_count = len(test_cases)
        llm_token_usage = response.get("token_usage", {})

        temp_header = copy.deepcopy(template["testSteps"]["data"][0])
        template_keys = [key.get("value") for key in temp_header]
        
        ai_keys = test_cases[0].keys()
        manual_testcases = []

        for detail in test_cases:
            update_template = copy.deepcopy(template)

            for ai_key in ai_keys:
                for testcase_label in update_template["testCaseDetails"]:
                    ai_key_clean = re.sub(r"[^a-zA-Z0-9]", "", ai_key.lower().strip())
                    label_key_clean = re.sub(
                        r"[^a-zA-Z0-9]",
                        "",
                        testcase_label.get("label", "").lower().strip(),
                    )

                    if label_key_clean == ai_key_clean:
                        testcase_label["value"] = [detail.get(ai_key)]

            update_template["testCaseType"] = normalize_test_case_type(
                detail.get("TestCase Type")
                or detail.get("Test Case Type")
                or detail.get("testCaseType", "")
            )

            manual_testcases.append(update_template)

        def get_steps(steps):
            normalized_template_keys = [str(k).strip().lower() for k in template_keys]
            table_datas = []

            for step in steps:
                table_data_header = []
                lower_keys = {str(k).strip().lower(): v for k, v in dict(step).items()}

                for header in normalized_template_keys:
                    table_copy = copy.deepcopy(
                        temp_header[normalized_template_keys.index(header)]
                    )

                    if header in lower_keys:
                        table_copy["value"] = lower_keys.get(header)
                    elif header == "test steps":
                        table_copy["value"] = lower_keys.get("step description", "")
                    else:
                        table_copy["value"] = ""

                    table_data_header.append(table_copy)

                table_datas.append(table_data_header)

            return table_datas

        for index, testCase in enumerate(manual_testcases):
            ai_info = []
            test_case_data = test_cases[index]

            test_steps_key = next(
                (
                    key
                    for key in [
                        "steps", "Steps", "teststeps", "testSteps",
                        "test_steps", "Step", "test_Steps",
                        "Test Steps", "Teststeps", "Test_Steps",
                        "Test_steps", "TestSteps", "Test Case Steps",
                    ]
                    if key in test_case_data
                ),
                "testSteps",
            )

            for step in test_case_data.get(test_steps_key, []):
                ai_info.append(step)

            test_case_key = next(
                (
                    key
                    for key in [
                        "steps", "Steps", "teststeps", "testSteps",
                        "test_steps", "Step", "Test Case Steps", 
                        "test_Steps", "Test Steps", "Teststeps",
                        "Test_Steps", "Test_steps", "TestSteps",
                    ]
                    if key in testCase
                ),
                "testSteps",
            )

            if test_case_key in testCase:
                testCase[test_case_key]["data"].extend(get_steps(ai_info))

        await asyncio.to_thread(
            mtc.save_user_prompt_details,
            prompt_id,
            unique_id,
            session_id,
            session_name,
            template_id,
            manual_testcases,
            license_id,
            count,
            script_type,
            input_type,
            is_modified,
            project_id,
            mongoCollectionName,
            request_time_for_storing_1_tc_in_MD,
            branch_id=branch_id
        )
        logger.info(f"Processed and saved {test_case_count} test cases successfully")
        return

    except Exception as e:
        logging.error(f"Processing failed: {e}")
        

async def process_llm_results(llm_results, counter_ref,counter_lock,state,key_corrector,TopLevelModel, prompt_type=None):
    start_time = time.time()
    try:
        if not llm_results:
            logging.warning("Empty llm_results received")
            return state, 0, 0, None 

        total_input_tokens = sum(r.get("input_tokens", 0) for r in llm_results)
        total_output_tokens = sum(r.get("output_tokens", 0) for r in llm_results)
        
        valid_results = [r for r in llm_results if r.get("success")]

        logger.info(f"MTC generation completed for {len(valid_results)} successful batches")

       
        all_test_cases = []
        combined_summary = ""

        # Log failures
        for result in llm_results:
            if not result.get("success"):
                logging.error(
                    f"Batch {result.get('batch_number')} failed: {result.get('error')}"
                )

        # Process valid results
        for result in valid_results:
            batch_num = result.get("batch_number")
            logger.info(f"Processing batch {batch_num}")
            response = result.get("response")
           
            if isinstance(response, str):
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError as e:
                    logging.error(f"Batch {batch_num} JSON parse failed: {e}")
                    continue
            elif isinstance(response, dict):
                parsed = response
            else:
                logging.warning(f"Batch {batch_num} invalid response type")
                continue

            logging.info(f"Batch {batch_num} parsed keys: {list(parsed.keys())}")

            batch_test_cases = parsed.get("Test Cases", [])
            if not batch_test_cases:
                logging.warning(f"Batch {batch_num} has no test cases")
                continue

            batch_summary = parsed.get("summary", "")
            if batch_summary and not combined_summary:
                combined_summary = batch_summary

            all_test_cases.extend(batch_test_cases)

            logging.info(f"Batch {batch_num}: {len(batch_test_cases)} test cases")

        if not all_test_cases:
            logging.warning("No valid test cases found after aggregation")
            return state, 0, 0, None 

        total_tokens = total_input_tokens + total_output_tokens

        batch_result = {
            "Test Cases": all_test_cases,
            "summary": combined_summary,
            "token_usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
            },
        }

        logging.info(
            f"Before validation: {len(batch_result['Test Cases'])} test cases"
        )

        validate_data = await re_validate_test_cases_v2(batch_result, counter_ref, counter_lock, prompt_type)

        if not validate_data or not validate_data.get("Test Cases"):
            logging.warning("Validation returned empty test cases")
            return state, 0, 0, None  

        logging.info(
            f"After validation: {len(validate_data.get('Test Cases', []))} test cases"
        )
      
        state.raw_testcases = batch_result

        corrected_response = key_corrector.correct_keys(validate_data)
    
        if corrected_response is None:
            logging.warning("Key corrector returned None, using validated data")
            corrected_response = validate_data

        current_batch_corrected = copy.deepcopy(corrected_response)

        if state.corrected_testcases and "Test Cases" in state.corrected_testcases:
            state.corrected_testcases["Test Cases"].extend(corrected_response.get("Test Cases", []))
            if not state.corrected_testcases.get("summary") and corrected_response.get("summary"):
                state.corrected_testcases["summary"] = corrected_response.get("summary")
            corrected_response = state.corrected_testcases
        else:
            state.corrected_testcases = corrected_response

        state.correction_log = [
            {
                "original": orig,
                "corrected": corr,
                "similarity": float(score),
            }
            for orig, corr, score in key_corrector.correction_log
        ]
        
        state.validated_testcases = TopLevelModel(**corrected_response)
        
        duration = time.time() - start_time
        logging.info(f"MtcProcessing Timing | duration: {duration:.3f}s")

        return state,total_input_tokens,total_output_tokens,current_batch_corrected

    except Exception as e:
        logging.error(f"process_llm_results failed: {e}", exc_info=True)
        return state,0,0,None