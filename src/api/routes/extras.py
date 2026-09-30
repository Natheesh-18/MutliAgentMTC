from fastapi import APIRouter
from src.api.runtime import *  # noqa: F401,F403
import os
router = APIRouter()

@router.post("/code-generation")
async def code_request(payload : CodeGenerationRequest):
    try:
        manualSteps = payload.manualSteps
        language = payload.language
        framework = payload.framework
        # license_id = build_license_id(payload.license_id)
        
        if not manualSteps:
            return {
                "responseCode": 400,
                "status": "FAILURE",
                "message": "No steps found"
            },200
        if language:
            generated_code = manualTestCase.get_generated_code(
                manualSteps, language
            )
        else:
            generated_code = manualTestCase.get_framework_generated_code(
                manualSteps, framework
            )

        return {
            "responseCode": 200,
            "responseObject": generated_code,
            "status": "SUCCESS"
        }
    except Exception as e:
        logger.error(f"Error processing code request: {e}")
        return {
            "status": "error",
            "message": str(e)
        }, 500

@router.post("/manual_testcase_download")
async def testcase_download(payload : DownloadTestCasesRequest):
    try:
        logger.info(f"Received body: {payload}")

        response_list = payload.response

        test_cases = []
        serial_number = 1

        for item in response_list:
            # manual_test_case = item.get("manualTestCase", {})
            test_case_details = {
                "TC_SL_NO": serial_number,
                **{
                    str(detail.get("label", "")): (
                        ", ".join(map(str, detail.get("value", [])))
                        if isinstance(detail.get("value", []), list)
                        else str(detail.get("value", ""))
                    )
                    for detail in item.get("testCaseDetails", [])
                },
            }

            test_steps_data = item.get("testSteps", {}).get("data", [])
            if (
                test_steps_data
                and isinstance(test_steps_data, list)
                and len(test_steps_data) > 1
            ):
                headers = [cell.get("value", "") for cell in test_steps_data[0]]
                required_fields = {"Test Steps", "Input", "Expected Result"}
                field_indices = {
                    header: i
                    for i, header in enumerate(headers)
                    if header in required_fields
                }

                for step_row in test_steps_data[1:]:
                    step_dict = {
                        field: step_row[field_indices[field]].get("value", "")
                        for field in field_indices
                        if field_indices[field] < len(step_row)
                        and isinstance(step_row[field_indices[field]], dict)
                    }
                    combined_data = {**test_case_details, **step_dict}
                    test_cases.append(combined_data)
            else:
                test_cases.append(test_case_details)

            serial_number += 1

        test_cases_df = pd.DataFrame(test_cases)
        current_time = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        filename = f"Manual_Test_Case_{current_time}.xlsx"
        file_path = os.path.join(os.getcwd(), filename)

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            test_cases_df.to_excel(writer, sheet_name="Test cases", index=False)

        wb = openpyxl.load_workbook(file_path)
        ws = wb["Test cases"]
        header_fill = PatternFill(
            start_color="4472C4", end_color="4472C4", fill_type="solid"
        )
        header_font = Font(color="000000", bold=True)
        header_alignment = Alignment(horizontal="left", vertical="center")

        for col_idx, cell in enumerate(ws[1], start=1):
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
            ws.column_dimensions[get_column_letter(col_idx)].width = 20

        tc_col_letter = "B"
        for col_idx, cell in enumerate(ws[1], start=1):
            if cell.value == "TC_SL_NO":
                tc_col_letter = get_column_letter(col_idx)
                break

        test_case_columns = list(test_case_details.keys())
        column_indices = [
            ws[1].index(cell) + 1 for cell in ws[1] if cell.value in test_case_columns
        ]

        prev_row = 2
        for row in range(3, ws.max_row + 2):
            if ws[f"{tc_col_letter}{row}"].value != ws[f"{tc_col_letter}{row-1}"].value:
                for col_idx in column_indices:
                    ws.merge_cells(
                        start_row=prev_row,
                        start_column=col_idx,
                        end_row=row - 1,
                        end_column=col_idx,
                    )
                    ws[f"{get_column_letter(col_idx)}{prev_row}"].alignment = Alignment(
                        horizontal="left", vertical="center"
                    )
                prev_row = row

        wb.save(file_path)

        if os.path.exists(file_path):
            return FileResponse(
                path=file_path,
                filename=filename,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "responseCode": 400,
                    "responseObject": None,
                    "status": "FAILURE",
                    "message": "Unable to download the testcase",
                }
            )

    except Exception as e:
        logger.exception("Error occurred")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )



@router.get("/get-follow-up-queries/{license_id}/{prompt_id}")
async def get_follow_up_queries(
    
    license_id: str,
    prompt_id: str
):
    try:
        # Validate request parameters
        if not license_id or not prompt_id:
            raise HTTPException(
                status_code=400,
                detail="license_id and prompt_id are required."
            )

        # Construct database name
        profile = os.getenv("PROFILE")

        if profile:
            mongo_db_name = f"optimize_{profile}_{license_id}"
        else:
            mongo_db_name = f"optimize_{license_id}"

        logger.info(f"Database Name: {mongo_db_name}")
        logger.info(f"Prompt ID: {prompt_id}")

        # Load collection
        collection_prompt = manualTestCase.load_collection_for_user_prompt(
            license_id=mongo_db_name
        )

        if collection_prompt is None:
            logger.error("Unable to load user_prompt_collection.")
            raise HTTPException(
                status_code=500,
                detail="Unable to load user_prompt_collection."
            )

        # Fetch document
        prompt_doc = collection_prompt.find_one(
            {"prompt_id": prompt_id}
        )

        if not prompt_doc:
            logger.warning(
                f"No document found for prompt_id: {prompt_id}"
            )
            return JSONResponse(
                status_code=404,
                content={
                    "responseCode": 404,
                    "status": "failure",
                    "message": f"No document found for prompt_id: {prompt_id}"
                }
            )

        logger.info(f"Document Found: {prompt_doc}")

        follow_up = prompt_doc.get("follow_up", "")

        return JSONResponse(
            status_code=200,
            content=jsonable_encoder(
                {
                    "responseCode": 200,
                    "status": "success",
                    "message": "SUCCESS",
                    "responseObject": {
                        "prompt_id": prompt_id,
                        "follow_up": follow_up,
                        "no_of_testcase_generated": prompt_doc.get("test_case_count", 0),
                        
                    }
                }
            )
        )

    except HTTPException as he:
        raise he

    except Exception as e:
        logger.error(
            f"Error fetching follow-up queries for prompt_id {prompt_id}: {str(e)}",
            exc_info=True
        )

        return JSONResponse(
            status_code=500,
            content={
                "responseCode": 500,
                "status": "failure",
                "message": "Failed to fetch follow-up queries.",
                "error": str(e)
            }
        )
