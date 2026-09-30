import re
import ast
from flask import jsonify
from fastapi.responses import JSONResponse
import json

class APIError(Exception):
    def __init__(self, responseCode: int, message: str):
        self.responseCode = responseCode
        self.message = message
        self.status = "failure"

        self.error = {
            "responseCode": responseCode,
            "status": "failure",
            "error_message": message,
        }
        super().__init__(message)


def build_error_response(e, model: str = None, serviceProvider: str = None):
    # --- Custom APIError handling ---
    if isinstance(e, APIError):
        return {
            "responseCode": e.responseCode,
            "status": "failure",
            "error_message": e.message,
        }

    # --- Default handling ---
    error_message = str(e)
    status_code = 500
    clean_message = error_message

    # --- Extract status code ---
    match = re.search(r"Error code:\s*(\d+)", error_message)
    if match:
        status_code = int(match.group(1))

        if "- {" in error_message:
            try:
                error_dict_str = error_message.split(" - ", 1)[1]
                error_dict = ast.literal_eval(error_dict_str)
                clean_message = error_dict.get("error", {}).get("message", error_message)
            except Exception:
                clean_message = error_message

        elif "- [" in error_message:
            try:
                error_list_str = error_message.split(" - ", 1)[1]
                error_list = ast.literal_eval(error_list_str)
                clean_message = error_list[0]["error"]["message"]
            except Exception:
                clean_message = error_message

    elif error_message.strip().startswith(("401", "403", "429")):
        status_code = int(error_message.split(" ", 1)[0])
        clean_message = error_message.split("[", 1)[0].strip()

    # --- Extract structured error message ---
    try:
        if "- {" in error_message:
            error_dict = ast.literal_eval(error_message.split(" - ", 1)[1])
            clean_message = error_dict.get("error", {}).get("message", error_message)

        elif "- [" in error_message:
            error_list = ast.literal_eval(error_message.split(" - ", 1)[1])
            clean_message = error_list[0]["error"]["message"]

    except Exception:
        clean_message = error_message

    # --- Override common HTTP messages ---
    if status_code == 401:
        clean_message = "Authentication failed. Invalid credentials."
    elif status_code == 403:
        clean_message = "Access forbidden. Required API or permission is missing."
    elif status_code == 429:
        clean_message = "Rate Limit Exceeded. Please try again later."

    # --- Final response ---
    return {
        "responseCode": status_code,
        "status": "failure",
        "error_message": clean_message,
    }

def build_api_error(e, service_provider=None):
    error_str = str(e).lower()
    error_message = str(e)
    provider = (service_provider or "").lower()

    # Clean and beautify Jira and validation errors for UI presentation
    if (
        "unauthorized" in error_str
        or "client must be authenticated" in error_str
        or "invalid jira api token" in error_str
    ):
        return APIError(
            responseCode=401,
            message="Jira authentication failed. Please verify your Jira API token and email in FireFlink configurations."
        )
    elif "jira project not configured" in error_str:
        return APIError(
            responseCode=400,
            message="Jira project not configured in the current FireFlink project."
        )
    elif "failed to connect to jira" in error_str:
        return APIError(
            responseCode=400,
            message="Unable to connect to Jira. Please verify the domain name or network status."
        )
    elif "zero test cases" in error_str:
        return APIError(
            responseCode=400,
            message="Generation completed, but no test cases were generated. Please refine your inputs or prompt."
        )

    if isinstance(e, APIError):
        return e

    # Parse serialized APIError dict string if present
    if error_message.strip().startswith("{") and "responseCode" in error_message:
        try:
            err_dict = ast.literal_eval(error_message.strip())
            if isinstance(err_dict, dict) and "message" in err_dict:
                return APIError(
                    responseCode=err_dict.get("responseCode", 400),
                    message=err_dict.get("message")
                )
        except Exception:
            pass

    if "429" in error_str or "rate limit" in error_str:
        return APIError(
            responseCode=429,
            message="Rate limit exceeded. Please try again later.",
        )

    elif (
        "401" in error_str
        or "authentication" in error_str
        or "invalid api key" in error_str
    ):
        return APIError(
            responseCode=401,
            message="Authentication failed. Please check your API key.",
        )

    elif "413" in error_str or "request too large" in error_str:
        return APIError(
            responseCode=413,
            message="Request too large for model to handle.",
        )

    elif isinstance(e, json.JSONDecodeError):
        return APIError(
            responseCode=400,
            message="Unable to generate all requested test cases. Please retry to generate the remaining test cases again.",
        )

    else:
        responseCode = 400
        clean_message = error_message

        if provider in ["defaultfireflink","groq","openai","anthropic","azure_ai",]:
            match = re.search(r"Error code:\s*(\d+)", error_message)
            if match:
                responseCode = int(match.group(1))

            if " - {" in error_message:
                try:
                    error_dict_str = error_message.split(" - ", 1)[1]
                    error_dict = ast.literal_eval(error_dict_str)

                    clean_message = (
                        error_dict.get("error", {})
                        .get("message", error_message)
                    )

                except Exception:
                    clean_message = error_message

        elif provider == "gemini":

            match = re.match(r"(\d+)", error_message.strip())

            if match:
                responseCode = int(match.group(1))

            gemini_match = re.search(
                r'message:\s*"([^"]+)"',
                error_message
            )

            if gemini_match:
                clean_message = gemini_match.group(1)

            elif "[" in error_message:
                clean_message = error_message.split("[", 1)[0].strip()

        return APIError(
            responseCode=responseCode,
            message=clean_message,
        )
    