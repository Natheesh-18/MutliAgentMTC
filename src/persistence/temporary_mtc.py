"""Helpers for temporary MTC payloads and token counting."""
import json
import re

import tiktoken


def converting_values_to_list_of_string(final_user_prompt_details):
    for doc in final_user_prompt_details:
        # manual_test_case = doc.get("manualTestCase")
        # if manual_test_case:
            test_case_details = doc.get("testCaseDetails", [])
            for test_case_detail in test_case_details:
                value = test_case_detail.get("value")
                if isinstance(value, list) and value:
                    inside_value = value[0]
                    if isinstance(inside_value, list):
                        test_case_detail["value"] = inside_value
                    elif isinstance(inside_value, dict):
                        test_case_detail["value"] = list(inside_value.values())
    return final_user_prompt_details

def count_tokens(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))

def build_temporary_mtc_payload(context_summary, generated_response, input_check_text=None):
    if isinstance(generated_response, dict) and ("testcases" in generated_response or "manual_testcase" in generated_response):
        testcases = generated_response.get("testcases") or generated_response.get("manual_testcase") or []
        summary = context_summary or generated_response.get("summary") or generated_response.get("context_summary") or ""
        testcases = remove_temporary_verification_steps(testcases)
        testcases = sanitize_temporary_mtc_step_inputs(testcases, input_check_text or summary)
        return {
            # "summary": summary,
            "testcases": testcases,
        }

    first_testcase = {}
    if isinstance(generated_response, dict):
        test_cases = generated_response.get("Test Cases", []) or []
        if test_cases:
            first_testcase = test_cases[0] or {}

    steps = (
        first_testcase.get("Test Steps")
        or first_testcase.get("testSteps")
        or first_testcase.get("TestSteps")
        or first_testcase.get("Steps")
        or first_testcase.get("steps")
        or []
    )

    manual_testcase = []
    for step in steps:
        if isinstance(step, list):
            t_step = str(step[0]) if len(step) > 0 else ""
            s_input = str(step[1]) if len(step) > 1 else ""
            manual_testcase.append([t_step, s_input])
            continue
        elif not isinstance(step, dict):
            manual_testcase.append([str(step), ""])
            continue

        t_step = (
            step.get("Test Steps")
            or step.get("Step Description")
            or step.get("Description")
            or step.get("Action")
            or step.get("test_step")
            or ""
        )
        s_input = (
            step.get("Step Input")
            or step.get("Input")
            or step.get("Test Data")
            or step.get("step_input")
            or ""
        )
        manual_testcase.append([t_step, s_input])

    summary = context_summary or ""
    manual_testcase = remove_temporary_verification_steps(manual_testcase)
    manual_testcase = sanitize_temporary_mtc_step_inputs(
        manual_testcase, input_check_text or summary
    )
    return {
        "summary": summary,
        "testcases": manual_testcase,
    }

def is_temporary_verification_step(step_text: str) -> bool:
    """Match verification steps (Verify...) for temporary APIs only."""
    if not step_text:
        return False
    normalized = re.sub(r"\s+", " ", str(step_text)).strip().lower()
    return normalized.startswith("verify")

def remove_temporary_verification_steps(testcases):
    """Drop all verification steps from temporary API payloads."""
    if not isinstance(testcases, list):
        return testcases
    filtered = []
    for step in testcases:
        if isinstance(step, list):
            step_text = str(step[0]) if step else ""
        elif isinstance(step, dict):
            step_text = (
                step.get("Test Steps")
                or step.get("Step Description")
                or step.get("Description")
                or step.get("Action")
                or step.get("test_step")
                or ""
            )
        else:
            step_text = str(step)
        if is_temporary_verification_step(step_text):
            continue
        filtered.append(step)
    return filtered

def summary_has_input_fields(summary_text: str) -> bool:
    """Detect whether content/UI summary mentions editable input fields."""
    if not summary_text or not str(summary_text).strip():
        return False
    cleaned = re.sub(r"(?i)\bno\s+input\b", " ", str(summary_text))
    patterns = [
        r"\binput\s*fields?\b",
        r"\btext\s*(?:box|field|area)s?\b",
        r"\btextbox(?:es)?\b",
        r"\btextarea\b",
        r"\bpassword\s*fields?\b",
        r"\bemail\s*fields?\b",
        r"\bsearch\s*(?:bar|box|field)\b",
        r"\bedit\s*texts?\b",
        r"\bform\s*fields?\b",
        r"\|\s*input\s*\|",
        r"\|\s*input\s*[,)]",
        r"element type[:\s|]+input\b",
        r"\btype[:\s]+input\b",
        r"\bplaceholder\b",
        r"\bpre-?filled\b",
    ]
    return any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in patterns)

def should_keep_step_input(step_input: str, has_input_fields: bool) -> bool:
    """
    Keep step inputs when the content has input fields.
    When it does not, drop dummy form values but keep lifecycle values (URL / app ids).
    """
    value = (step_input or "").strip()
    if not value or value.lower() in {"-", "n/a", "na", "none", "null"}:
        return False
    if has_input_fields:
        return True
    return bool(
        re.search(
            r"(?i)(https?://|www\.|appactivity|apppackage|bundleid|bundle\s*id)",
            value,
        )
    )

def extract_user_android_app_info(text: str):
    if not text or not isinstance(text, str):
        return None, None
    
    user_pkg = None
    user_act = None

    pkg_match = re.search(r"(?:appPackage|package)\s*[:=]?\s*([a-zA-Z0-9_\.]+)", text, re.IGNORECASE)
    act_match = re.search(r"(?:appActivity|activity)\s*[:=]?\s*([a-zA-Z0-9_\.\/]+)", text, re.IGNORECASE)

    if pkg_match:
        val = pkg_match.group(1).strip()
        if not val.lower().startswith(("this", "the", "and", "or", "app", "use")):
            user_pkg = val
    if act_match:
        val = act_match.group(1).strip()
        if not val.lower().startswith(("this", "the", "and", "or", "activity", "use")):
            user_act = val

    matches = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+\b", text)
    identifiers = [m for m in matches if not m.lower().endswith((".com", ".org", ".net", ".in", ".io", ".co")) or len(m.split(".")) > 2]

    for ident in identifiers:
        if not user_act and ("activity" in ident.lower() or "home" in ident.lower() or "main" in ident.lower()):
            user_act = ident
        elif not user_pkg and ident != user_act:
            user_pkg = ident

    if len(identifiers) >= 2:
        if not user_pkg and not user_act:
            user_pkg, user_act = identifiers[0], identifiers[1]
        elif user_pkg and not user_act and len(identifiers) > 1:
            remaining = [i for i in identifiers if i != user_pkg]
            if remaining:
                user_act = remaining[0]
        elif user_act and not user_pkg and len(identifiers) > 1:
            remaining = [i for i in identifiers if i != user_act]
            if remaining:
                user_pkg = remaining[0]

    return user_pkg, user_act

def extract_user_ios_bundle_id(text: str):
    if not text or not isinstance(text, str):
        return None
    match = re.search(r"(?:bundleId|bundle_id|bundle\s*identifier)\s*[:=]?\s*([a-zA-Z0-9_\.]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def override_lifecycle_inputs(testcases, summary_text: str):
    if not isinstance(testcases, list) or not summary_text:
        return testcases
    
    user_pkg, user_act = extract_user_android_app_info(summary_text)
    user_bundle = extract_user_ios_bundle_id(summary_text)

    for step in testcases:
        if isinstance(step, list) and len(step) > 0:
            step_name = str(step[0]).strip().lower()
            if "open android app" in step_name:
                if user_pkg or user_act:
                    current_input = str(step[1]) if len(step) > 1 else ""
                    cur_act_match = re.search(r"appActivity[:=]\s*([^\s,]+)", current_input, re.IGNORECASE)
                    cur_pkg_match = re.search(r"appPackage[:=]\s*([^\s,]+)", current_input, re.IGNORECASE)
                    
                    final_act = user_act or (cur_act_match.group(1) if cur_act_match else "")
                    final_pkg = user_pkg or (cur_pkg_match.group(1) if cur_pkg_match else "")
                    
                    new_input_parts = []
                    if final_act:
                        new_input_parts.append(f"appActivity:{final_act}")
                    if final_pkg:
                        new_input_parts.append(f"appPackage:{final_pkg}")
                    
                    if new_input_parts:
                        if len(step) > 1:
                            step[1] = ", ".join(new_input_parts)
                        else:
                            step.append(", ".join(new_input_parts))
            elif "open ios app" in step_name:
                if user_bundle:
                    if len(step) > 1:
                        step[1] = f"bundleId:{user_bundle}"
                    else:
                        step.append(f"bundleId:{user_bundle}")
    return testcases

def sanitize_temporary_mtc_step_inputs(testcases, summary_text: str):
    """Clear dummy Step Input values when the content summary has no input fields."""
    if not isinstance(testcases, list):
        return testcases
    has_fields = summary_has_input_fields(summary_text)
    for step in testcases:
        if isinstance(step, list) and len(step) > 1:
            if not should_keep_step_input(step[1], has_fields):
                step[1] = ""
    testcases = override_lifecycle_inputs(testcases, summary_text)
    return testcases
