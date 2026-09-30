"""Automation-code prompt templates and LLM code generation."""
from src.persistence._shared import *  # noqa: F401,F403


class CodeGenerationMixin:
    def framework_prompt_template(self) -> ChatPromptTemplate:
        system_prompt = """
    You are an expert test automation engineer.

    Convert the provided structured automation steps into a complete end-to-end
    JavaScript test script using the specified automation framework.

    Guidelines:
    1. The user specifies the JavaScript automation framework ({framework}).
    Use its syntax, methods, and best practices.

    2. Each step contains an "nlpName" such as:
    - "OpenBrowser", "NavigateToURL", "Click", "SendKeys", "CloseBrowser"
    - Optionally: "VerifyText", "VerifyElementPresent", etc.

    3. For each step:
    - Choose the best locator from elementsData.locators in this priority:
        id > name > xpath > className
    - Map actions correctly:
        - Navigation → open URL from stepInputs
        - Click → click target element
        - SendKeys → type provided value
        - VerifyText → assert text presence
        - VerifyElementPresent → assert element existence

    4. Framework structure:
    - Cypress → describe() / it()
    - Playwright / Puppeteer → async test with browser/context/page
    - WebDriver tools → setup/teardown or main()

    5. Include:
    - Required imports
    - Setup and teardown
    - Assertions using the framework’s assertion library
    - Appropriate waits (e.g., waitForSelector)

    Output requirements:
    - Generate ONLY executable JavaScript code
    - No explanations or markdown
    - Clean, readable formatting
    """

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}")
            ]
        )

    def prompt_template_for_code(self):
        system_prompt = """
            Convert the following structured automation steps into a complete '{language}' Selenium script.
            Guidelines:
            1. Each step includes an \"nlpName\" like:
            - \"OpenBrowser\", \"NavigateToURL\", \"Click\", \"SendKeys\", \"CloseBrowser\"
                - (Optionally) \"VerifyText\", \"VerifyElementPresent\", etc.

                2. For each step:
                - Use the best locator from \"elementsData.locators\", in this order of priority: \"id\" > \"name\" > \"xpath\" > \"className\".
                - If \"stepInputs\" exists, use its value appropriately (e.g., for \"SendKeys\", input the value).
                - For \"Click\", find the element and call \".click()\".
                - For \"NavigateToURL\", open the specified URL.
                - For \"Verify*\" steps:
                    - \"VerifyText\": Check if expected text is present on the page.
                    - \"VerifyElementPresent\": Check if the element exists using given locator.
                    - Include assertions using \"assert\" or conditionals with \"print()\" for pass/fail logging.

                3. Include:
                - Imports: \"selenium\", \"time\", \"unittest\" or \"assert\"
                - Setup using \"webdriver.Chrome()\" or similar
                - A \"main()\" function with all steps
                - Optional: wrap steps in \"try/except\" blocks for error handling

                4. Add \"time.sleep()\" where necessary between steps for stability.
                5. Print meaningful messages or raise assertion errors for verification steps.

                Here is the input data:
                {input}"""
        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}"),
            ]
        )

    def get_generated_code(self, manual_step, language):

        formatted_input = self.prompt_template_for_code().format(
            input=manual_step, language=language
        )
        response = self.llm.invoke(formatted_input)
        return response.content

    def get_framework_generated_code(self, manual_step, framework):
        if framework.lower() == "cypress":
            formatted_input = self.framework_prompt_template().format(
                input=manual_step, framework=framework
            )
        elif framework.lower() == "playwright":
            formatted_input = self.framework_prompt_template().format(
                input=manual_step, framework=framework
            )
        response = self.llm.invoke(formatted_input)
        return response.content
