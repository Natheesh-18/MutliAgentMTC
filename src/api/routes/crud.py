from fastapi import APIRouter
from src.api.runtime import *  # noqa: F401,F403
from flask import Flask, request, jsonify

router = APIRouter()

@router.put("/update-test-case")
async def update_prompt_details(payload : UpdateTestCaseRequest):
    license_id = build_license_id(payload.license_id)
    
    if not all([payload.id,license_id,payload.update_data]):
        return jsonify({"responseCode":400,"status":"FAILURE","message":"Please send proper details"})
    
    update_prompt=manualTestCase.update_user_prompt_details_by_id(payload.id,license_id,payload.update_data)
    if update_prompt['status']=='SUCCESS':
        return {
            'responseCode':200,
            'responseObject':update_prompt,
            'status':'SUCCESS',
            'message':'Testcase updated successfully'
        }
    return JSONResponse(
        status_code=400,
        content={
            "responseCode": 400,
            "responseObject": None,
            "status": "FAILURE",
            "message": "Please enter proper details",
        },
    )

@router.delete("/delete-id")
async def delete_based_on_id(payload : DeleteTestCaseByIdRequest):
    license_id = build_license_id(payload.license_id)

    if not all([payload.test_case_id, license_id, payload.prompt_id]):
        return {
                "responseCode": 400,
                "responseObject": None,
                "status": "FAILURE",
                "message": "Please send proper details",
            }

    delete_id = manualTestCase.delete_id(
        payload.test_case_id, license_id, payload.prompt_id, payload.count, payload.prompt_unique_id
    )
    if delete_id["status"] == "SUCCESS":
        return {
                "responseCode": 200,
                "status": "SUCCESS",
                "message": "Testcase deleted successfully",
            }
    else:
        return {
                "responseCode": 400,
                "status": "FAILURE",
                "message": "Failed to delete testcase",
            }


@router.delete("/clear-all")
async def delete_all(payload : ClearAllRequest):
    license_id = build_license_id(payload.license_id)
    if not all([license_id, payload.session_id]):
        return {
                "responseCode": 400,
                "responseObject": None,
                "status": "FAILURE",
                "message": "Please send proper details",
            }

    delete_id = manualTestCase.delete_all(license_id, payload.session_id)
    if delete_id["status"] == "SUCCESS":
        return {
                "responseCode": 200,
                "status": "SUCCESS",
                "message": "All sessions cleared successfully",
            }
    else:
        return {
                "responseCode": 400,
                "status": "FAILURE",
                "message": "Failed to clear session",
            }


@router.delete("/delete-session_id/{license_id}/{session_id}")
async def delete_by_session_id(license_id : str, session_id : str):
    license_id = build_license_id(license_id)
    if not all([session_id, license_id]):
        return {
                "responseCode": 400,
                "responseObject": None,
                "message": "FAILURE",
                "error": "please send proper prompt id",
            }
    delete_prompt_id = manualTestCase.delete_session_id(session_id, license_id)
    if delete_prompt_id["status"] == "SUCCESS":
        return {
                "responseCode": 200,
                "status": "SUCCESS",
                "message": "Session deleted successfully",
            }
    else:
        return {
                "responseCode": 400,
                "status": "FAILURE",
                "message": "Failed to delete session",
            }


@router.delete("/delete-prompt/{license_id}/{prompt_id}")
async def delete_by_prompt_id(license_id : str, prompt_id : str):
    license_id = build_license_id(license_id)
    if not all([prompt_id, license_id]):
        return {
                "responseCode": 400,
                "responseObject": None,
                "message": "FAILURE",
                "error": "please send proper prompt id",
            }
    delete_prompt_id = manualTestCase.delete_prompt(prompt_id, license_id)
    if delete_prompt_id["status"] == "SUCCESS":
        return {
                "responseCode": 200,
                "status": "SUCCESS",
                "message": "Prompt deleted successfully",
            }
    else:
        return {
                "responseCode": 400,
                "status": "FAILURE",
                "message": "Failed to delete prompt",
            }


@router.get("/user-prompt/{license_id}/{prompt_id}/{count}")
async def get_by_prompt_id(license_id : str, prompt_id : str, count : int):
    license_id = build_license_id(license_id)
    if not all([prompt_id, license_id]):
        return {
                "responseCode": 400,
                "responseObject": None,
                "message": "FAILURE",
                "error": "please send proper details",
            }
    get_by_prompt_id = manualTestCase.get_by_prompt_id(prompt_id, license_id, count)
    if get_by_prompt_id["status"] == "SUCCESS":
        return {
                "responseCode": 200,
                "responseObject": get_by_prompt_id,
                "message": "SUCCESS",
            }
    else:
        return {
                "responseCode": 400,
                "responseObject": None,
                "message": "FAILURE",
                "error": "No Prompt id found",
            }


@router.get("/user-prompts/{license_id}")
async def get_all_prompts(license_id: str,projectId : str = Header(default=None)):
    license_id = build_license_id(license_id)

    if not license_id:
        return {
                "responseCode": 400,
                "responseObject": None,
                "message": "FAILURE",
                "error": "please send proper license id",
            }
    get_all_user_prompts_and_last_user_prompt_details = (
        manualTestCase.get_all_user_prompts_and_last_user_prompt_details(
            license_id, projectId
        )
    )
    if get_all_user_prompts_and_last_user_prompt_details["status"] == "SUCCESS":
        return {
            "responseCode": 200,
            "responseObject": get_all_user_prompts_and_last_user_prompt_details,
            "status": "SUCCESS",
        }
    else:
        return {
            "responseCode": 400,
            "status": "FAILURE",
            "message": "No license id found"
        }


@router.get("/user-session_id/{license_id}/{session_id}")
async def get_session_id(license_id: str, session_id: str):
    license_id = build_license_id(license_id)
    if not license_id:
        return {
                "responseCode": 400,
                "responseObject": None,
                "message": "FAILURE",
                "error": "please send proper license id",
            }
        
    get_all_user_prompts_and_last_user_prompt_details = manualTestCase.get_session_id(
        license_id, session_id
    )
    if get_all_user_prompts_and_last_user_prompt_details["status"] == "SUCCESS":
        return {
            "responseCode": 200,
            "responseObject": get_all_user_prompts_and_last_user_prompt_details,
            "status": "SUCCESS",
        }
    else:
        return {
            "responseCode": 400,
            "status": "FAILURE",
            "message": "No license id found"
        }


