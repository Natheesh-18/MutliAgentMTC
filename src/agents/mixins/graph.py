"""LangGraph entry points around generation."""
from src.agents._shared import *  # noqa: F401,F403


class GraphMixin:
    async def async_lang_graph_builder(self,apiKey,serviceProvider,model,sa_info,request_time_for_storing_1_tc_in_MD,return_generated_payload=False):

        initial_state = State()
        result = await self.async_generate_test_cases(
            apiKey,
            serviceProvider,
            model,
            sa_info,
            initial_state,
            request_time_for_storing_1_tc_in_MD,
            return_generated_payload=return_generated_payload
        )        
        return result
