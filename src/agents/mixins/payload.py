"""Generated-MTC payload shaping and LLM error detection."""
from src.agents._shared import *  # noqa: F401,F403


class PayloadMixin:
    def build_generated_mtc_payload(self, state):
        test_cases_payload = None
        if isinstance(state, dict):
            test_cases_payload = state
        elif hasattr(state, "corrected_testcases") and state.corrected_testcases:
            test_cases_payload = state.corrected_testcases
        elif hasattr(state, "raw_testcases") and state.raw_testcases:
            test_cases_payload = state.raw_testcases
        elif hasattr(state, "validated_testcases") and state.validated_testcases:
            test_cases_payload = (
                state.validated_testcases.model_dump()
                if hasattr(state.validated_testcases, "model_dump")
                else state.validated_testcases
            )

        context_summary = ""
        if hasattr(state, "context_summary"):
            context_summary = state.context_summary or ""
        elif isinstance(state, dict):
            context_summary = state.get("context_summary") or state.get("summary") or ""
        
        if not context_summary and isinstance(test_cases_payload, dict):
            context_summary = (
                test_cases_payload.get("context_summary")
                or test_cases_payload.get("summary")
                or ""
            )

        if isinstance(test_cases_payload, dict) and ("testcases" in test_cases_payload or "manual_testcase" in test_cases_payload):
            raw_manual_testcase = test_cases_payload.get("testcases") or test_cases_payload.get("manual_testcase") or []
            formatted_testcases = []
            for item in raw_manual_testcase:
                if isinstance(item, list):
                    t_step = str(item[0]) if len(item) > 0 else ""
                    s_input = str(item[1]) if len(item) > 1 else ""
                    formatted_testcases.append([t_step, s_input])
                elif isinstance(item, dict):
                    t_step = item.get("test_step") or item.get("Test Steps") or ""
                    s_input = item.get("step_input") or item.get("Step Input") or ""
                    formatted_testcases.append([t_step, s_input])
                else:
                    formatted_testcases.append([str(item), ""])
            return {
                "summary": context_summary,
                "testcases": formatted_testcases,
            }

        first_testcase = {}
        if isinstance(test_cases_payload, dict):
            test_cases = test_cases_payload.get("Test Cases", []) or []
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
        manual_test_steps = []
        for step in steps:
            if isinstance(step, list):
                t_step = str(step[0]) if len(step) > 0 else ""
                s_input = str(step[1]) if len(step) > 1 else ""
                manual_test_steps.append([t_step, s_input])
                continue
            elif not isinstance(step, dict):
                manual_test_steps.append([str(step), ""])
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
            manual_test_steps.append([t_step, s_input])

        if isinstance(test_cases_payload, dict) and "Test Cases" in test_cases_payload:
            try:
                threading.Thread(target=SummaryCreation().generate_summary, args=(test_cases_payload, self.prompt_id)).start()
            except Exception as thread_err:
                logger.error(f"Failed to start SummaryCreation thread in build_generated_mtc_payload: {thread_err}")

        return {
            "summary": context_summary,
            "testcases": manual_test_steps,
        }

    def set_return_payload_state(self, state, response):
        if isinstance(response, str):
            response = json.loads(response)
        state.raw_testcases = response
        state.corrected_testcases = self.key_corrector.correct_keys(response) or response
        state.context_summary = self.context_summary or ""
        if not state.context_summary and isinstance(response, dict):
            response_context_summary = response.get("context_summary") or response.get("summary") or ""
            if response_context_summary:
                state.context_summary = response_context_summary
        return state

