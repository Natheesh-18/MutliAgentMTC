from typing import List, Dict
from src.agents.memory import AgentMemoryOperation

class SummaryCreation:

    def generate_summary(self, test_cases: List[Dict], prompt_id) -> str:
        if not test_cases:
            return "No test cases generated"
        names = [tc.get("Test Case Name", "Unnamed") for tc in test_cases['Test Cases']]
        summary_lines = [
            f"- Key test scenarios: {names}...",
        ]
        AgentMemoryOperation().append_to_session_history(prompt_id=prompt_id, new_entry="\n".join(summary_lines))