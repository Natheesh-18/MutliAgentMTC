"""JSON instruction, async runner, scenario batches, file selection."""
from src.agents._shared import *  # noqa: F401,F403


class SupportMixin:

    def create_type_batches(self,scenario_response, batch_size=5):
        batched_payloads = []

        for test_type, scenarios in scenario_response.items():
            if not scenarios:
                continue

            for i in range(0, len(scenarios), batch_size):
                batch = scenarios[i:i + batch_size]

                batched_payloads.append({
                    "test_type": test_type,
                    "batch_number": (i // batch_size) + 1,
                    "scenarios": batch
                })

        return batched_payloads
    
    def chosenFiles(self,filenames: list, data: dict) -> str:
        result = []

        for filename in filenames:
            file_data = next(
                (item for item in data["files"] if item["fileName"] == filename),
                None
            )

            if file_data:
                result.append(f"Filename: {file_data['fileName']}\n")

                modules = file_data["purpose"].split("\n\n")

                for module in modules:
                    result.append(module)

        return "\n\n".join(result)        
