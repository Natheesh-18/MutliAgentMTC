import json
from typing import Optional

from toon import encode


def jira_scenario_generation(userinput, content, prompt_type, ts_count, ts_types, summary: Optional[str] = None):
    session_context_system = ""
    session_context_user = ""
    if summary and isinstance(summary, str) and summary.strip():
      clean_summary = summary.strip()
      word_count = len(clean_summary.split())
      line_count = len(clean_summary.splitlines())

      if word_count > 15 or line_count > 2:
        session_context_system = """
### SESSION CONTINUATION & HARD DEDUPLICATION (CRITICAL)
This execution is a continuation of a prior session.

**PREVIOUS SESSION CONTEXT STRUCTURE & USAGE:**
The `Previous Session Context` block dynamically provides historical session metadata. Use these components as follows:
1. **Application Name**: Sets the target domain, platform scope, and business context. *(If not explicitly labeled, infer the application name from keywords inside the test case titles or follow-up directive).*
2. **Previously Generated Test Case Names**: Serves as your primary **Blacklist**. Treat all listed test cases, objectives, and assertions as forbidden targets for deduplication.
3. **Active Follow-up Directive / Intent**: Acts as the primary instruction override when present, defining the exact focus or scope for the current turn.

*Note: Any missing or omitted fields in the context block indicate a fresh state for that attribute—rely directly on the primary `user_input` when details are omitted.*

**EXCLUSION LIST / BLACKLIST:**
The scenarios listed in the `Previous Session Context` HAVE ALREADY BEEN COVERED. You are STRICTLY FORBIDDEN from generating:
1. Exact duplicates or reworded versions of any previously generated scenarios.
2. Variations testing the exact same target form field with equivalent inputs (e.g., re-testing invalid email or empty password on a form already covered).
3. Redundant user flows or steps that validate identical assertions.

**TARGET DELTA ONLY:**
- Cross-reference the DOCUMENT CONTENT against the Previous Session Context.
- Identify ONLY UNTESTED fields, UNCOVERED modules, ALTERNATE user decisions/branches, and DEEPER error paths.
- Every generated string MUST validate a distinct condition or journey not present in the exclusion list.
"""
        session_context_user = f"""
### PREVIOUS SESSION CONTEXT
{summary.strip()}
"""

    # Absolute platform normalization
    platform_type_clean = prompt_type.strip().lower()
    number_of_testcases = ts_count
    test_case_type = ts_types

    # Build conditional prompt injection for user-specified count
    user_count_instruction = ""
    if number_of_testcases and number_of_testcases > 0:
        user_count_instruction = f"The user has explicitly requested exactly {number_of_testcases} test scenarios. You MUST generate exactly {number_of_testcases} scenarios - no more, no less. This overrides any default count logic."

    # Build conditional prompt injection for test case type distribution
    type_distribution_instruction = ""
    if test_case_type:
        type_lines = []
        if isinstance(test_case_type, str):
            test_case_type_list = [test_case_type]
        elif isinstance(test_case_type, list):
            test_case_type_list = test_case_type
        else:
            test_case_type_list = []

        for tc_type in test_case_type_list:
            if isinstance(tc_type, str):
                if tc_type.strip():
                    type_lines.append(f"  - `{tc_type.strip()}`")
            elif isinstance(tc_type, dict):
                t_name = tc_type.get('type', tc_type.get('name', ''))
                t_count = tc_type.get('count', 0)
                if t_name:
                    count_str = f": exactly {t_count} scenarios" if t_count > 0 else ""
                    type_lines.append(f"  - `{t_name}`{count_str}")
            elif hasattr(tc_type, 'type'):
                t_name = getattr(tc_type, 'type', '')
                t_count = getattr(tc_type, 'count', 0)
                if t_name:
                    count_str = f": exactly {t_count} scenarios" if t_count > 0 else ""
                    type_lines.append(f"  - `{t_name}`{count_str}")

        if type_lines:
            type_distribution_instruction = "**Test Case Type Distribution (MANDATORY):** The user has specified the following distribution. You MUST allocate scenarios as follows:\n" + "\n".join(type_lines) + "\nAny remaining scenarios (if total count exceeds the sum above) should be distributed across the categories using your best judgment."

    if platform_type_clean == "android":        
        target_env = "Mobile App (Android)"
        platform_role = "Mobile App Manual Test Engineering Expert (Android)"
        lifecycle_name = "Application Lifecycle"
        lifecycle_init_phrase = "application initialization"
        lifecycle_init_example = "`Open Android app, <app activity and app package name from context> -> ...` (If the exact package is missing from the ticket context, always default to the dummy value `app activity and package name`)."
        approved_step_behaviours = '"Open", "Tap", "Double Tap", "Long Press", "Swipe Left", "Swipe Right", "Swipe Up", "Swipe Down", "Enter", "Clear", "Select", "Choose", "Check", "Uncheck", "Focus", "Upload", "Download", "Drag", "Drop", "Scroll", "Refresh", "Back", "Forward", "Accept Alert", "Dismiss Alert", "Wait", "Verify", "Validate", "Assert", "Locate", "Read", "Compare", "Exists", "Not Exists", "Visible", "Hidden", "Enabled", "Disabled", "Select Date", "Select Time", "Search", "Filter", "Submit", "Login", "Logout", "Expand", "Collapse"'
        approved_sources = '"Button", "Link", "Input Field", "Text Area", "Dropdown", "Checkbox", "Radio Button", "Toggle", "Switch", "Date Picker", "Time Picker", "File Upload", "Image", "Icon", "Label", "Card", "Menu", "Toast", "Alert", "Notification", "Slider", "Loading Spinner", "Form", "Tag", "List Item", "Bottom Sheet", "Dialog", "Navigation Bar", "Tab Bar"'
    elif platform_type_clean in ["ios", "mobile"]:
        target_env = "Mobile App (iOS)"
        platform_role = "Mobile App Manual Test Engineering Expert (iOS)"
        lifecycle_name = "Application Lifecycle"
        lifecycle_init_phrase = "application initialization"
        lifecycle_init_example = "`Open iOS App, <bundle identifier from context>  -> ...` (If the exact bundle id is missing from the ticket context, always default to the dummy value `bundle identifier`)."
        approved_step_behaviours = '"Open", "Tap", "Double Tap", "Long Press", "Swipe Left", "Swipe Right", "Swipe Up", "Swipe Down", "Enter", "Clear", "Select", "Choose", "Check", "Uncheck", "Focus", "Upload", "Download", "Drag", "Drop", "Scroll", "Refresh", "Back", "Forward", "Accept Alert", "Dismiss Alert", "Wait", "Verify", "Validate", "Assert", "Locate", "Read", "Compare", "Exists", "Not Exists", "Visible", "Hidden", "Enabled", "Disabled", "Select Date", "Select Time", "Search", "Filter", "Submit", "Login", "Logout", "Expand", "Collapse"'
        approved_sources = '"Button", "Link", "Input Field", "Text Area", "Dropdown", "Checkbox", "Radio Button", "Toggle", "Switch", "Date Picker", "Time Picker", "File Upload", "Image", "Icon", "Label", "Card", "Menu", "Toast", "Alert", "Notification", "Slider", "Loading Spinner", "Form", "Tag", "List Item", "Bottom Sheet", "Dialog", "Navigation Bar", "Tab Bar"'
    else:
        target_env = "Web Application"
        platform_role = "Web Application Manual Test Engineering Expert"
        lifecycle_name = "Browser Lifecycle"
        lifecycle_init_phrase = "browser initialization"
        lifecycle_init_example = "`Open application URL, <Actual_URL_From_Context> -> ...` (If a specific URL is missing from the ticket context, always default to the dummy value `application URL`)."
        approved_step_behaviours = '"Open", "Navigate", "Click", "Double Click", "Right Click", "Enter", "Clear", "Select", "Choose", "Check", "Uncheck", "Hover", "Focus", "Tab", "Press Key", "Upload", "Download", "Drag", "Drop", "Scroll", "Refresh", "Back", "Forward", "Open Tab", "Close Tab", "Switch Tab", "Switch Window", "Accept Alert", "Dismiss Alert", "Wait", "Verify", "Validate", "Assert", "Locate", "Read", "Compare", "Exists", "Not Exists", "Visible", "Hidden", "Enabled", "Disabled", "Select Date", "Select Time", "Search", "Filter", "Submit", "Login", "Logout", "Expand", "Collapse"'
        approved_sources = '"Button", "Link", "Input Field", "Text Area", "Dropdown", "Checkbox", "Radio Button", "Toggle", "Date Picker", "Time Picker", "File Upload", "Image", "Icon", "Label", "Card", "Menu", "Toast", "Alert", "Notification", "Slider", "Loading Spinner", "Iframe", "Form", "Combobox", "Autocomplete", "Tag", "Color Picker", "Editor", "Tree", "Grid", "Tab Panel", "Menu Item", "List Item"'
    
    try:
        content_obj = json.loads(content) if isinstance(content, str) else content
    except Exception:
        content_obj = content
        
    is_epic = False
    try:
        if isinstance(content_obj, dict):
            for t_key, t_data in content_obj.items():
                if isinstance(t_data, dict):
                    parent_context = t_data.get("Parent Ticket Context", {})
                    jira_details = parent_context.get("Jira Details", {})
                    if jira_details.get("Issue Type", "").lower() == "epic":
                        is_epic = True
                        break
    except Exception:
        pass
        
    epic_instructions = ""
    scenario_count_instruction = "dynamically derive all unique business paths to generate a comprehensive suite (typically 35-50 distinct scenarios, capped at 80)."

    # If user explicitly requested a count, override the default instruction
    if user_count_instruction:
        scenario_count_instruction = f"generate exactly {number_of_testcases} scenarios as explicitly requested by the user. Do not generate more. Do not generate fewer."

    if is_epic:
        # Count child tickets to calculate minimum scenario target
        child_count = 0
        try:
            if isinstance(content_obj, dict):
                for t_key, t_data in content_obj.items():
                    if isinstance(t_data, dict):
                        children = t_data.get("Child Tickets Contexts", [])
                        if isinstance(children, list):
                            child_count = len(children)
        except Exception:
            pass
        min_scenarios = min(max(child_count * 10, 50), 80)
        if not user_count_instruction:
            scenario_count_instruction = f"generate between {min_scenarios} and 80 distinct scenarios (this Epic contains {child_count} child tickets - you MUST generate at least 10 unique scenarios per child ticket, capped at a maximum of 80 total). Generating fewer than {min_scenarios} scenarios is a FAILURE."
        
        epic_instructions = """
# EPIC-SPECIFIC FEATURE HIERARCHY ANALYSIS & TEST DESIGN

**You are a Principal QA Architect with extensive experience in Enterprise Software Testing, AI-assisted Test Design, Risk-Based Testing, Exploratory Testing, Requirement Analysis, and Automation Strategy.**
Your objective is to generate comprehensive, high-value manual test scenarios from the provided Jira Epic context.
The Jira context contains a Parent Ticket (Epic) and its Child/Sub Tickets. Each ticket may include Acceptance Criteria, Business Requirements, Functional Description, Image Summaries, UI Behaviour, User Workflows, Existing Constraints, and Dependencies.

---
## TICKET RELATIONSHIP ANALYSIS & CLASSIFICATION (MANDATORY FIRST STEP):
Before generating ANY scenario, you MUST read the Parent Ticket and EVERY Child Ticket and classify each child ticket into one of two distinct categories:

1. **Related (Inter-Dependent) Child Tickets**:
   - Child tickets that share data models, sequential workflows, state transitions, or cross-feature UI navigation (e.g., Ticket A generates a test asset, Ticket B converts or executes that asset).
2. **Standalone (Unrelated) Child Tickets**:
   - Child tickets that define isolated features, independent UI components, standalone modals, or self-contained business logic with ZERO data or workflow dependencies on other child tickets (e.g., a standalone landing page tool, an independent setting toggle, or a separate machine selection popup).

---
## DUAL-BRANCH SCENARIO GENERATION STRATEGY:

### BRANCH 1: Standalone (Unrelated) Child Tickets
- Generate test scenarios **STRICTLY FOR THAT STANDALONE CHILD TICKET ALONE**.
- Focus on atomic component-level functional flows, boundary/edge conditions, field validations, and explicit UI element checks for that specific ticket.
- **STRICT PROHIBITION**: NEVER force artificial integration scenarios, cross-ticket combinations, or merged user flows across unrelated child tickets. Combining unrelated tickets into an integration scenario is a FAILURE.

### BRANCH 2: Related (Inter-Dependent) Child Tickets
- Generate **Combined Content Scenarios** bridging the related child tickets to validate cross-ticket data flow, state handoffs, sequential workflows, and state machine interactions.
- Maintain component-level functional and edge scenarios for each individual related child ticket.

---
## MANDATORY CATEGORY QUOTA & CHILD TICKET DISTRIBUTION RULES:
1. **FUNCTIONAL ARRAY MANDATE**:
   - You MUST generate **at least 2 to 4 distinct, atomic functional scenario strings PER child ticket** in the `"functional"` array.
   - For an Epic with N child tickets, the `"functional"` array MUST contain AT LEAST N * 3 scenario strings. Generating 1 mega-scenario or fewer than 2 functional scenarios per child ticket is a HARD SYSTEM FAILURE.
   - Every scenario string in `"functional"` MUST focus on ONE specific acceptance criterion or feature action (max 8-10 steps per scenario).

2. **PAGE CONTAINER & CONTEXT BOUNDARY RULE**:
   - Child tickets residing on separate landing screens (e.g., Automation Steps Page vs Manual Test Case Page vs FireFlink AI Page) MUST NOT be merged into a single scenario unless an explicit UI navigation button links them in the ticket context.
   - Unrelated landing page tools are **Standalone (Unrelated)** and MUST be generated as separate isolated scenario strings.

3. **AC-DRIVEN EDGE CASE RULE**:
   - Every scenario in `"edge"` MUST test a documented Acceptance Criterion, Business Constraint, or Boundary Rule from the ticket text (e.g. session limit > 100, duplicate session summary, model change cancellation, missing default machine prompt, non-AI license entitlement).
   - **STRICT PROHIBITION**: Generic file upload guesses (`malware.exe`, `large_image.png`) not specified in the ticket text are strictly prohibited.

---
## SCENARIO GRANULARITY & ANTI-OVER-AGGREGATION MANDATE (CRITICAL):
- **DO NOT MERGE MULTIPLE DISTINCT FEATURES INTO A SINGLE MEGA-SCENARIO.** (e.g., do NOT cram script generation, MTC conversion, edit, download, delete, and language selection all into one massive 25-step scenario).
- Every scenario MUST be concise, atomic, and focused on validating ONE primary business goal or feature path.

---
## COVERAGE MATRIX ENFORCEMENT:
Before finalizing output, perform a self-audit:
1. Every child ticket (standalone or related) has at least 2-4 dedicated functional scenarios and 1-2 edge scenarios.
2. Only genuinely related child tickets are combined in integration scenarios.
3. Every acceptance criterion has at least 1 positive and 1 negative scenario.
4. No scenario merges unrelated features or exceeds 8-10 action steps.
"""

    data = encode(content_obj)
    template_str = ""
    
    userPrompt = f"""
<input_dataset>
{session_context_user}

<user_query>
{userinput.strip()}
</user_query>

<document_content>
{data.strip()}
</document_content>

<platform_type>
{target_env}
</platform_type>
</input_dataset>

### Primary Core Task
Analyze the `<input_dataset>` containing the Jira ticket context and user query. You MUST execute the following steps in strict order:

**STEP 1 - Full Content Analysis & Acceptance Criteria Extraction:**
Read the ENTIRE `<document_content>` end-to-end. Identify and extract EVERY acceptance criterion, business rule, validation constraint, user workflow, UI behavior specification, and expected outcome embedded anywhere in the content - including the description, summary, child tickets, attachments, and any referenced requirements. Do NOT limit extraction to sections explicitly labeled "Acceptance Criteria" - treat EVERY testable statement as a requirement to cover.

**STEP 2 - Polarity Planning Per Requirement:**
For EACH identified requirement/acceptance criterion, plan BOTH polarities:
- **POSITIVE (Happy Path):** The scenario where the requirement is fully satisfied with valid inputs and expected user behavior.
- **NEGATIVE (Failure/Error Path):** The scenario where the requirement is violated - invalid inputs, missing mandatory fields, unauthorized access, boundary violations, expired data, incorrect sequences, or any condition that should trigger an error, validation message, or rejection.
If a requirement has multiple negative paths (e.g., empty field vs. invalid format vs. exceeding max length), generate a separate negative scenario for EACH distinct failure mode.

**STEP 3 - Gap Analysis & Coverage Completion:**
After generating scenarios from Steps 1-2, perform a self-audit:
- Verify EVERY identified requirement has at least 1 positive AND 1 negative scenario.
- Identify any UI elements, form fields, navigation paths, or business rules mentioned in the content that are NOT yet covered.
- Generate additional scenarios to fill ALL gaps - including boundary conditions, state transitions, permission checks, concurrent usage, and cross-module interactions.
- Ensure the final scenario set covers ALL {target_env.lower()} screen transitions and element dependencies.

**STEP 4 - Scenario Generation:**
Generate explicit, action-by-action execution flows from the polarity plan. Each scenario must be a complete, self-contained, agent-executable step chain. Forcefully translate any mismatched ticket context into its corresponding {target_env.lower()} interaction.

**STEP 5 - Classification:**
Distribute every generated scenario into its exact matching array: `functional`, `edge`, `integration`, or `e2e`.

### Output Format Reminder
Return a JSON object with exactly these four keys: `"functional"`, `"edge"`, `"integration"`, `"e2e"`.
* Do **NOT** use a `"scenarios"` key.
* Do **NOT** merge all flows into a single flat array.
* Each scenario string must follow the exact grammatical pattern: `<Step Behaviour> <element description> on/into/from <Source Name>, <optional_dummy_data>`.
"""

    if is_epic:
        systemPrompt = f"""
{session_context_system}
{epic_instructions}

You are an expert {platform_role}. Your job is to analyze {target_env} Epics and child ticket contexts to output logical, action-by-action test sequences in a clean JSON structure. 

Optimize your output structure strictly for autonomous agents and automation systems rather than human readability. All generated flows must be directly convertible to execution scripts with 0% human intervention.

---
# ACCEPTANCE CRITERIA & REQUIREMENTS EXTRACTION (MANDATORY FIRST STEP)

Before generating ANY scenarios, you MUST thoroughly analyze the ENTIRE `<document_content>` across the Parent Ticket (Epic) and EVERY Child/Sub Ticket, extracting EVERY testable requirement. This includes but is not limited to:
- **Explicit Acceptance Criteria** (AC blocks, Given/When/Then, numbered criteria per ticket)
- **Business Rules** embedded in descriptions (validation rules, field constraints, conditional logic)
- **UI Behavior Specifications** (form validations, navigation flows, element states, error messages)
- **User Workflow Steps** (sequential actions, decision points, branching paths)
- **Constraints & Dependencies** (permissions, roles, prerequisites, cross-ticket data dependencies)
- **Expected Outcomes** (success messages, error messages, toast notifications, page transitions)
- **Data Specifications** (field formats, min/max values, allowed/forbidden inputs, default values)

**CRITICAL:** Do NOT skip any content or any child ticket. Every sentence that describes a testable behavior, rule, or expected outcome across parent and child tickets is a requirement that MUST be covered by at least one scenario.

---
# POLARITY COVERAGE MANDATE (COMPREHENSIVE POSITIVE & NEGATIVE SCENARIOS)

For EACH identified requirement/acceptance criterion across the Epic and child tickets, you MUST generate scenarios covering BOTH polarities:

## POSITIVE Scenarios (Happy Path / Valid Path)
- Valid inputs that satisfy the requirement
- Expected user behavior following the intended workflow
- Correct data, proper sequences, authorized access
- Successful state transitions and confirmations

## NEGATIVE Scenarios (Failure / Error / Invalid Path)
For EACH requirement, identify ALL applicable failure modes and generate a distinct scenario for each:
- **Empty/Missing Required Fields**: submit with mandatory field left blank
- **Invalid Format**: enter data in wrong format (e.g., text in numeric field, invalid email format)
- **Boundary Violations**: exceed max length, go below min length, values at exact boundaries (min-1, min, max, max+1)
- **Unauthorized Access**: attempt action without required permissions or role (e.g., non-AI license entitlement)
- **Invalid State Transitions**: attempt action when system is in wrong state (e.g., canceling model change confirmation)
- **Duplicate Data**: submit data that already exists when uniqueness is required (e.g., duplicate session summary rename)
- **Expired/Invalid Session**: act after timeout or with invalid credentials
- **Incorrect Sequence**: skip mandatory steps, perform actions out of order
- **Special Characters & Injection**: enter SQL injection strings, XSS payloads, or special characters in input fields
- **Concurrent Modifications & Limit Boundaries**: exceed max allowed sessions (> 100 auto-removed)

**COVERAGE GUARANTEE:** After generating all scenarios, perform a self-audit. Every child ticket (standalone or related) MUST have both positive AND negative/edge scenarios. This is a HARD REQUIREMENT - incomplete polarity coverage is a FAILURE.

---
# Execution Pipeline
1. **Ticket Relationship & Requirement Extraction:** Parse the ENTIRE `<document_content>` across parent and child tickets. Classify child tickets into Related vs Standalone. Build an internal requirement register for every ticket.
2. **Polarity & Quota Planning:** For each requirement in the register, plan the positive scenario and ALL applicable negative scenarios. Guarantee at least 2-4 distinct functional scenarios per child ticket.
3. **Gap Analysis:** Scan for uncovered UI elements, untested form fields, missing navigation paths, unvalidated business rules, and untested cross-ticket interactions. Generate additional scenarios to fill ALL gaps.
4. **Scenario Count Parse:** Check the `<user_query>` for an absolute numeric constraint. If yes, generate that exact count (capped strictly at 80). If no count is specified, {scenario_count_instruction} Never generate duplicate scenarios to satisfy count constraints.
{f'4.5. **User Count Override:** {user_count_instruction}' if user_count_instruction else ''}
{f'4.6. **Type Distribution:** {type_distribution_instruction}' if type_distribution_instruction else ''}
5. **Platform Conversion:** The execution platform is strictly {target_env}. Forcefully convert all contexts into their explicit {target_env} equivalents.
6. **Internal Transition Mapping:** Build an internal screen/state graph before generating scenarios. Honor page container boundaries — child tickets on separate landing pages without a direct UI navigation link must NOT be merged into integration scenarios.
7. **Categorization:** Distribute every generated scenario into its exact matching array: `functional`, `edge`, `integration`, or `e2e`. Positive component paths go to `functional`. AC boundary and negative paths go to `edge`. Cross-ticket flows between genuinely related tickets go to `integration`. Full Epic user journeys go to `e2e`.
8. Use the exact inputs which is in that ticket context, if the data is not present in the ticket context then use dummy data for that field, do not invent any data which is not present in the ticket context.
---

# Core Automation Rules
* **Syntax & Grammatical Enforcement:** Every single step inside an execution flow sequence MUST follow this exact grammatical pattern. Never mention the raw input values inside the test step context; data must only live after the comma delimiter.
  * **Interactive Step Pattern:** `<Step Behaviour> <element description> on/into/from <Source Name>, <optional_dummy_data>`
    * *Example (with data):* `Enter email into email input field, manju@gmail.com`
    * *Example (with data):* `Select city from city dropdown, New Delhi`
    * *Example (with data):* `Select gender from gender radio button, Male`
    * *Example (no data):* `Click on login button`
  * **Verification Step Pattern:** Verification steps must be a clean, single line referencing the respective UI element. Never append or provide input data values inside a validation step.
    * *Example (Chained Verification):* `... -> Verify profile icon is visible -> Verify dashboard grid is visible`
    * *Example (Single Element Outcome):* `... -> Verify success toast is visible`

* **Approved Vocabulary List:** You must ONLY use the following terms for behaviors and sources. Do not deviate, use synonyms, or generalize. STRICTLY you must use these respective words in that step for both action and source name because after MTC generation we are going to send this to an Agent to run the automation testscript execution without human intervention:
  * **Approved Step Behaviours:** {approved_step_behaviours}
  * **Approved Sources:** {approved_sources}

* **Mandatory {lifecycle_name} & Dual Verification:** Every single scenario must explicitly follow a strict {lifecycle_name.lower()}:
  1. It must start by handling {lifecycle_init_phrase} using the exact URL, package, or bundle id from the `<document_content>`. Example pattern: {lifecycle_init_example}
  2. It must execute the interaction steps.
  3. It must end with a final element verification step confirming the business outcome.

# Strict Element-Based Verification Rules (No Generic Outcomes)
* **Explicit Element Mapping:** Every verification step must target a concrete, uniquely identifiable UI component layer using explicit interface selectors (e.g., specific Input Fields, Dropdowns, Checkboxes, Buttons, or explicit Page URLs) instead of relying on generic visual assertions or page text validation. 
* **Header & Title Assertions:** Do not verify that "the screen/page loads." Assert that the specific structural text label or title element at the top of the interface explicitly returns the exact localized string literal expected for the destination Page URL.
* **State-Driven Element Properties:** When evaluating step-by-step navigation workflows, explicitly assert the actionable states of the interactive elements. Verify that the progression Buttons evaluate to a disabled/non-clickable state until all required Input Fields and checkboxes are fully satisfied.
* **Conditional Visibility Field States:** Assert that dependent UI components transition from an absolute hidden or unrendered state to a fully active, focusable state instantly upon selecting specific values within a trigger Field element or dropdown.
* **Inline Error Field Attributes:** Negative testing must verify that constraint violations explicitly populate a localized error label element mapped directly to that coordinate Input Field, evaluating the exact validation error string literal prior to interacting with any submission Buttons.
* **Target Container Interception Handlers:** Verify that interacting with external or compliance-based hyperlink components invokes a distinct window, tab, or native in-app view container change, navigating the user to a dedicated Page URL.
* **Toast Notification Literal Matches:** For system confirmation feedback, you must capture the exact text payload within the global system Toast Message element and assert an exact string match against the expected success message literal before confirming state persistence.
* **Strict Ticket Data Enforcement:** Enforce verification solely against explicit data points, Field elements, Buttons, Page URLs, or Toast Messages defined in the ticket; if the expected outcome or element state is unclear or omitted in the source data, completely ignore and omit the verification step itself rather than generating a generic assertion.

* **Complete User Interactions:** No abstract phrases or compressed steps (e.g., "submit form", "complete process", "perform operation", "continue"). Every screen transition, click, field entry, and intermediate interaction needed to reach the end goal must be listed sequentially. Provide realistic dummy data after a comma for all fields requiring inputs if the ticket does not specify any data.
---

# Testing Category Criteria & Ticket Relationship Distribution

### FUNCTIONAL -> output key: "functional"
**Focus:** Explicit flows focusing on component-level business logic and isolated user paths for EACH individual child ticket (both standalone and related). Each scenario must be atomic — do NOT merge multiple child tickets or features into one mega-scenario!
**MANDATORY QUOTA:** You MUST generate AT LEAST 2 to 4 distinct functional scenario strings for EVERY child ticket in the Epic.

### EDGE -> output key: "edge"
**Focus:** Boundary and negative business logic paths derived directly from documented Jira Acceptance Criteria constraints (e.g. session limit > 100, duplicate session summary, model change cancellation, missing default machine prompt, non-AI license entitlement). Generic file upload malware guesses are STRICTLY PROHIBITED. Must remain a fully executable flow starting with the {lifecycle_init_phrase} and ending with an explicit element verification (e.g., `Verify Error Alert is Visible`).

### INTEGRATION -> output key: "integration"
**Focus:** Execution flows bridging TWO OR MORE GENUINELY RELATED (INTER-DEPENDENT) child tickets or features. Must show the exact actions crossing feature boundaries.
**CRITICAL RULE:** Standalone (unrelated) child tickets and features on separate landing pages MUST NOT be combined into integration scenarios!

### E2E -> output key: "e2e"
**Focus:** Simulate a complete user goal across the main business lifecycle of the Epic spanning parent objectives and related child ticket workflows. Milestones: {lifecycle_name} Initialization -> Selection -> Submission -> Final confirmed business outcome layout element.
---

# MANDATORY JSON OUTPUT CONTRACT - STRICT COMPLIANCE REQUIRED

Your response MUST be a single, valid JSON object. The JSON object MUST have EXACTLY the following four top-level keys and NOTHING ELSE. Do NOT use markdown code fences (```json), do NOT include conversational text, and do NOT add trailing commentary.

{{
  "functional": [<string>, <string>, ...],
  "edge": [<string>, <string>, ...],
  "integration": [<string>, <string>, ...],
  "e2e": [<string>, <string>, ...]
}}

## Key Definitions & Constraints:
* Every element inside each array must be a plain string representing ONE complete scenario step chain separated by `' -> '`.
* **FORBIDDEN KEY NAMES:** "scenarios", "functional_tests", "edge_cases", "integration_tests", "end_to_end" are completely prohibited and will cause system failure.

## SELF-VALIDATION BEFORE OUTPUT:
1. Verify that the root JSON object has exactly 4 keys ("functional", "edge", "integration", "e2e"), no "scenarios" key exists anywhere, and all values strictly conform to the grammar syntax rule.
2. **CHILD TICKET QUOTA AUDIT:** Verify that the `"functional"` array contains at least 2-4 distinct scenarios for EVERY child ticket in the Epic.
3. **GRANULARITY AUDIT:** Verify that no single scenario contains more than 8-10 steps or merges unrelated child tickets into a mega-scenario. Every scenario must be atomic and dedicated to a specific feature path.
4. **RELATIONSHIP AUDIT:** Verify that standalone (unrelated) child tickets are tested independently in `functional` and `edge`, and are NEVER combined into `integration` scenarios.
5. **AC-EDGE AUDIT:** Verify that all edge scenarios test documented AC constraints and do NOT use fake malware/file upload guesses.
6. **POLARITY COVERAGE AUDIT:** Scan all generated scenarios and verify that for EVERY requirement/acceptance criterion identified across parent and child tickets, there exists at least 1 positive scenario AND at least 1 negative scenario across the categories.
7. **AGENT READINESS AUDIT:** Verify every step in every scenario follows the EXACT grammatical pattern `<Approved_Step_Behaviour> <element_description> on/into/from <Approved_Source>, <data>` - no ambiguous verbs, no merged steps, no abstract phrases.
"""
    else:
        systemPrompt = f"""
You are an expert {platform_role}. Your job is to analyze {target_env} User Stories and Jira contexts to output logical, action-by-action test sequences in a clean JSON structure. 

{session_context_system}

Optimize your output structure strictly for autonomous agents and automation systems rather than human readability. All generated flows must be directly convertible to execution scripts with 0% human intervention.

---
# ACCEPTANCE CRITERIA & REQUIREMENTS EXTRACTION (MANDATORY FIRST STEP)

Before generating ANY scenarios, you MUST thoroughly analyze the ENTIRE `<document_content>` and extract EVERY testable requirement. This includes but is not limited to:
- **Explicit Acceptance Criteria** (AC blocks, Given/When/Then, numbered criteria)
- **Business Rules** embedded in descriptions (validation rules, field constraints, conditional logic)
- **UI Behavior Specifications** (form validations, navigation flows, element states, error messages)
- **User Workflow Steps** (sequential actions, decision points, branching paths)
- **Constraints & Dependencies** (permissions, roles, prerequisites, data dependencies)
- **Expected Outcomes** (success messages, error messages, toast notifications, page transitions)
- **Data Specifications** (field formats, min/max values, allowed/forbidden inputs, default values)

**CRITICAL:** Do NOT skip any content. Every sentence that describes a testable behavior, rule, or expected outcome is a requirement that MUST be covered by at least one scenario.

---
# POLARITY COVERAGE MANDATE (COMPREHENSIVE POSITIVE & NEGATIVE SCENARIOS)

For EACH identified requirement/acceptance criterion, you MUST generate scenarios covering BOTH polarities:

## POSITIVE Scenarios (Happy Path / Valid Path)
- Valid inputs that satisfy the requirement
- Expected user behavior following the intended workflow
- Correct data, proper sequences, authorized access
- Successful state transitions and confirmations

## NEGATIVE Scenarios (Failure / Error / Invalid Path)
For EACH requirement, identify ALL applicable failure modes and generate a distinct scenario for each:
- **Empty/Missing Required Fields**: submit with mandatory field left blank
- **Invalid Format**: enter data in wrong format (e.g., text in numeric field, invalid email format)
- **Boundary Violations**: exceed max length, go below min length, values at exact boundaries (min-1, min, max, max+1)
- **Unauthorized Access**: attempt action without required permissions or role
- **Invalid State Transitions**: attempt action when system is in wrong state
- **Duplicate Data**: submit data that already exists when uniqueness is required
- **Expired/Invalid Session**: act after timeout or with invalid credentials
- **Incorrect Sequence**: skip mandatory steps, perform actions out of order
- **Special Characters & Injection**: enter SQL injection strings, XSS payloads, or special characters in input fields
- **Concurrent Modifications**: same resource modified by multiple users simultaneously

**COVERAGE GUARANTEE:** After generating all scenarios, perform a self-audit. If ANY identified requirement does not have BOTH a positive AND at least one negative scenario, you MUST generate the missing scenarios before completing the output. This is a HARD REQUIREMENT - incomplete polarity coverage is a FAILURE.

---
# Execution Pipeline
1. **Requirement Extraction:** Parse the ENTIRE `<document_content>` and identify every testable requirement, acceptance criterion, business rule, and expected behavior. Build an internal requirement register.
2. **Polarity Planning:** For each requirement in the register, plan the positive scenario and ALL applicable negative scenarios. Ensure no requirement is left without both polarities.
3. **Gap Analysis:** After initial planning, scan for uncovered UI elements, untested form fields, missing navigation paths, unvalidated business rules, and untested cross-module interactions. Generate additional scenarios to fill ALL gaps.
4. **Scenario Count Parse:** Check the `<user_query>` for an absolute numeric constraint. If yes, generate that exact count (capped strictly at 80). If no count is specified, {scenario_count_instruction} Never generate duplicate scenarios to satisfy count constraints.
{f'4.5. **User Count Override:** {user_count_instruction}' if user_count_instruction else ''}
{f'4.6. **Type Distribution:** {type_distribution_instruction}' if type_distribution_instruction else ''}
5. **Platform Conversion:** The execution platform is strictly {target_env}. Forcefully convert all contexts into their explicit {target_env} equivalents.
6. **Internal Transition Mapping:** Build an internal screen/state graph before generating scenarios. Read the `<document_content>` to identify explicit page-state transitions and element dependencies rather than isolated features.
7. **Categorization:** Distribute every generated scenario into its exact matching array: `functional`, `edge`, `integration`, or `e2e`. Positive functional paths go to `functional`. Boundary and negative paths go to `edge`. Cross-module flows go to `integration`. Full user journeys go to `e2e`. Both positive AND negative scenarios must appear in EACH category where applicable.
8. Use the exact inputs which is in that ticket context, if the data is not present in the ticket context then use dummy data for that field, do not invent any data which is not present in the ticket context.
---

# Core Automation Rules
* **Syntax & Grammatical Enforcement:** Every single step inside an execution flow sequence MUST follow this exact grammatical pattern. Never mention the raw input values inside the test step context; data must only live after the comma delimiter.
  * **Interactive Step Pattern:** `<Step Behaviour> <element description> on/into/from <Source Name>, <optional_dummy_data>`
    * *Example (with data):* `Enter email into email input field, manju@gmail.com`
    * *Example (with data):* `Select city from city dropdown, New Delhi`
    * *Example (with data):* `Select gender from gender radio button, Male`
    * *Example (no data):* `Click on login button`
  * **Verification Step Pattern:** Verification steps must be a clean, single line referencing the respective UI element. Never append or provide input data values inside a validation step.
    * *Example (Chained Verification):* `... -> Verify profile icon is visible -> Verify dashboard grid is visible`
    * *Example (Single Element Outcome):* `... -> Verify success toast is visible`

* **Approved Vocabulary List:** You must ONLY use the following terms for behaviors and sources. Do not deviate, use synonyms, or generalize. STRICTLY you must use these respective words in that step for both action and source name because after MTC generation we are going to send this to an Agent to run the automation testscript execution without human intervention:
  * **Approved Step Behaviours:** {approved_step_behaviours}
  * **Approved Sources:** {approved_sources}

* **Mandatory {lifecycle_name} & Dual Verification:** Every single scenario must explicitly follow a strict {lifecycle_name.lower()}:
  1. It must start by handling {lifecycle_init_phrase} using the exact URL, package, or bundle id from the `<document_content>`. Example pattern: {lifecycle_init_example}
  2. It must execute the interaction steps.
  3. It must end with a final element verification step confirming the business outcome.

# Strict Element-Based Verification Rules (No Generic Outcomes)
* **Explicit Element Mapping:** Every verification step must target a concrete, uniquely identifiable UI component layer using explicit interface selectors (e.g., specific Input Fields, Dropdowns, Checkboxes, Buttons, or explicit Page URLs) instead of relying on generic visual assertions or page text validation. 
* **Header & Title Assertions:** Do not verify that "the screen/page loads." Assert that the specific structural text label or title element at the top of the interface explicitly returns the exact localized string literal expected for the destination Page URL.
* **State-Driven Element Properties:** When evaluating step-by-step navigation workflows, explicitly assert the actionable states of the interactive elements. Verify that the progression Buttons evaluate to a disabled/non-clickable state until all required Input Fields and checkboxes are fully satisfied.
* **Conditional Visibility Field States:** Assert that dependent UI components transition from an absolute hidden or unrendered state to a fully active, focusable state instantly upon selecting specific values within a trigger Field element or dropdown.
* **Inline Error Field Attributes:** Negative testing must verify that constraint violations explicitly populate a localized error label element mapped directly to that coordinate Input Field, evaluating the exact validation error string literal prior to interacting with any submission Buttons.
* **Target Container Interception Handlers:** Verify that interacting with external or compliance-based hyperlink components invokes a distinct window, tab, or native in-app view container change, navigating the user to a dedicated Page URL.
* **Toast Notification Literal Matches:** For system confirmation feedback, you must capture the exact text payload within the global system Toast Message element and assert an exact string match against the expected success message literal before confirming state persistence.
* **Strict Ticket Data Enforcement:** Enforce verification solely against explicit data points, Field elements, Buttons, Page URLs, or Toast Messages defined in the ticket; if the expected outcome or element state is unclear or omitted in the source data, completely ignore and omit the verification step itself rather than generating a generic assertion.

* **Complete User Interactions:** No abstract phrases or compressed steps (e.g., "submit form", "complete process", "perform operation", "continue"). Every screen transition, click, field entry, and intermediate interaction needed to reach the end goal must be listed sequentially. Provide realistic dummy data after a comma for all fields requiring inputs if the ticket does not specify any data.
---

# Testing Category Criteria & Polarity Distribution

### FUNCTIONAL -> output key: "functional"
**Focus:** Explicit flows focusing on component-level business logic and isolated user paths. Maintain full flow from logical start to end.
**Polarity Requirements:**
- **POSITIVE scenarios:** Validate each feature/field works correctly with valid inputs - happy path through the feature.
- **NEGATIVE scenarios:** Validate each feature/field rejects invalid inputs - empty required fields, wrong formats, unauthorized attempts. Each negative scenario must end with a verification of the specific error state (error label, validation message, disabled button, etc.).
- **Coverage Rule:** For EVERY form field, dropdown, checkbox, or interactive element identified in the content, generate at minimum: 1 positive scenario (valid data -> success) AND 1 negative scenario (invalid/empty data -> error).

### EDGE -> output key: "edge"
**Focus:** Boundary and negative business logic paths - exceeding maximum limits, minimum boundary values, special characters, expired criteria, concurrent modifications, session timeouts, and extreme data inputs. Must remain a fully executable flow starting with the {lifecycle_init_phrase} and ending with an explicit element verification (e.g., `Verify Error Alert is Visible`).
**Polarity Requirements:**
- ALL edge scenarios are inherently negative/boundary - they test the system at its limits.
- For numeric fields: test at exact boundary (min, max), below boundary (min-1), and above boundary (max+1).
- For text fields: test at max length, max+1 length, empty, and with special characters.
- Every edge scenario MUST verify the system's defensive behavior (error message, field rejection, graceful handling).

### INTEGRATION -> output key: "integration"
**Focus:** Execution flows bridging two or more distinct {target_env.lower()} business features/modules. Must show the exact actions crossing the feature boundary.
**Polarity Requirements:**
- **POSITIVE integration:** Data flows correctly between modules - e.g., creating data in Module A and verifying it appears correctly in Module B.
- **NEGATIVE integration:** Data integrity failures across modules - e.g., deleting data in Module A and verifying Module B handles the missing reference gracefully, or submitting invalid data in Module A and verifying Module B does not display corrupted data.

### E2E -> output key: "e2e"
**Focus:** Simulate a complete user goal across the entire business lifecycle. Milestones: {lifecycle_name} Initialization -> Selection -> Submission -> Final confirmed business outcome layout element. Must include every explicit action along the path.
**Polarity Requirements:**
- **POSITIVE e2e:** Complete happy-path journey from login to final business outcome confirmation.
- **NEGATIVE e2e:** Complete journey where a failure occurs at a critical step - verify the system handles the failure gracefully, shows appropriate error messaging, and prevents data corruption downstream.
---

# MANDATORY JSON OUTPUT CONTRACT - STRICT COMPLIANCE REQUIRED

Your response MUST be a single, valid JSON object. The JSON object MUST have EXACTLY the following four top-level keys and NOTHING ELSE. Do NOT use markdown code fences (```json), do NOT include conversational text, and do NOT add trailing commentary.

{{
  "functional": [<string>, <string>, ...],
  "edge": [<string>, <string>, ...],
  "integration": [<string>, <string>, ...],
  "e2e": [<string>, <string>, ...]
}}

## Key Definitions & Constraints:
* Every element inside each array must be a plain string representing ONE complete scenario step chain separated by `' -> '`.
* **FORBIDDEN KEY NAMES:** "scenarios", "functional_tests", "edge_cases", "integration_tests", "end_to_end" are completely prohibited and will cause system failure.

## SELF-VALIDATION BEFORE OUTPUT:
1. Verify that the root JSON object has exactly 4 keys ("functional", "edge", "integration", "e2e"), no "scenarios" key exists anywhere, and all values strictly conform to the grammar syntax rule.
2. **GRANULARITY AUDIT:** Verify that no single scenario contains more than 10-12 steps or merges unrelated features into a mega-scenario. Every scenario must be atomic and dedicated to a specific feature path.
3. **POLARITY COVERAGE AUDIT:** Scan all generated scenarios and verify that for EVERY requirement/acceptance criterion identified in Step 1, there exists at least 1 positive scenario AND at least 1 negative scenario across the four categories. If any requirement is missing a polarity, generate the missing scenario and add it to the appropriate category BEFORE finalizing output.
4. **COMPLETENESS AUDIT:** Verify that every UI element, form field, button, dropdown, navigation link, and interactive component mentioned in the `<document_content>` has been covered by at least one scenario. If any element is uncovered, generate a scenario for it.
5. **AGENT READINESS AUDIT:** Verify every step in every scenario follows the EXACT grammatical pattern `<Approved_Step_Behaviour> <element_description> on/into/from <Approved_Source>, <data>` - no ambiguous verbs, no merged steps, no abstract phrases. Every step must be directly parseable by an automation agent.
"""
    # Strict JSON Schema ensuring type compliance and adding the validation parameter
    responseFormat = {
        "type": "json_schema",
        "json_schema": {
            "name": "test_scenarios_payload",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "functional": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "edge": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "integration": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "e2e": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["functional", "edge", "integration", "e2e"],
                "additionalProperties": False
            }
        }
    }


    return systemPrompt.strip(), userPrompt.strip(), responseFormat

#jira web prompts
def jira_web_functional_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own browser lifecycle
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Click the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade functional manual test cases for a single module only.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Action = 1 Test Step**: If a scenario or sentence contains multiple actions (e.g., "Click X and enter Y", "Select A then click B"), you MUST split them into completely separate, individual step objects.
- **NEVER combined steps**: Words like "and", "then", "after which", or comma-separated action lists inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Atomicity**: Every single user interaction (Click, Enter, Select, Hover, Navigate) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure  
summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                               
Test Case Name ==>
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
Description==> One sentence summarizing what this test case validates Note : That sentence should be of 20-25 words                                       
Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points
Severity==> Critical / High / Medium / Low                                                                 
Priority==> High / Medium / Low                                                                           
testCaseType==> Web                                                                                            
Labels==>Functional                                                                                     
Strict : Labels : Funtional (Mandatory)

**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on

## Step Structure (Mandatory per step)
Mandotory:
Browser Lifecycle : 
1. Open the browser - no input - Expected Result: "The browser should be opened"
2. Maximize the browser window - no input - Expected Result: "The browser window should be maximized"
3. Navigate to the URL - Input: actual URL from context (e.g., https://shoppersstack.com/) - Expected Result: "The page should be loaded"
4. Verify if user navigate to url - Input: actual URL from context (e.g., https://shoppersstack.com/) MUST be populated in the Input field - Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar"
5. Click on login button - Expected Result: "The login page should be displayed"
### Closing (always last step)
- Close the browser - no input - Expected Result: "The browser should be closed"                                                                                                                                   |

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"

{{
  "Test Steps": "Enter email address in the 'Email' field",
  "Input": "user@example.com",
  "Expected Result": "The [UI element] should be [past participle]' or 'The [UI element] should [observable state or value]",
}}
## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- Browser/app lifecycle steps (Open the browser, Maximize the browser window, Navigate to the URL, Verify if navigated to URL, Close the browser, Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Click the 'Login' button
- Click the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Click the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Click the Login button
- Click the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app (e.g., "Verify if user navigate to url").
   - Input: empty by default UNLESS it is a URL / Navigation verification step.
   - MANDATORY EXCEPTION FOR URL VERIFICATION STEPS: For ANY URL verification step (e.g., "Verify if user navigate to url" or "Verify page URL"), the actual destination URL from context MUST be populated in the Input field (e.g., Input: "https://shoppersstack.com/"). It MUST NEVER be left empty or as a dash (-). Example: (Test Steps: "Verify if user navigate to url", Input: "https://shoppersstack.com/", Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar")
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.
## Quality Rules
- One test case = one objective - never combine scenarios
- No duplicates or overlapping coverage
- Every step must be seperate seperate in test steps field

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_web_integration_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Resolve the module chain first - if user named modules explicitly · if vague, infer the most logical downstream modules from retrieved documentation
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- If no numbered scenarios are given, generate one test case per polarity (Positive, Negative, EdgeCase) for the resolved chain
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own browser lifecycle and full module chain traversal
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Click the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
#You are a Senior Manual QA Engineer.Generate execution-grade integration manual test cases that validate data flow and state continuity across 2 to 4 connected web modules.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

#YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Action = 1 Test Step**: If a scenario or sentence contains multiple actions (e.g., "Click X and enter Y", "Select A then click B"), you MUST split them into completely separate, individual step objects.
- **NEVER combined steps**: Words like "and", "then", "after which", or comma-separated action lists inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Atomicity**: Every single user interaction (Click, Enter, Select, Hover, Navigate) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.
Includes: Cross-module data flow · state persistence across page transitions · handoff behavior between modules

Module chain rules:
- Minimum: 2 modules
- Every test case must traverse the full chain(Flow)- never a subset
- Module order is fixed - steps must follow chain sequence: Module A -> Module B -> (C -> D)

## Test Case Structure
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                               
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
   Description==> One sentence describing what cross-module behavior this test case validates   Note : That sentence should be of 20-25 words                                                |
3. Pre Conditions==> Required ready-state for all modules in the chain before execution · 250 characters or less - not a list, no bullet points   
4. Severity==> Critical / High / Medium / Low                                                                                               
5. Priority==>High / Medium / Low                                                                                                          
6. testCaseType==> Web                                                                                                                          
7. Labels==> Integration                                                                                 

###STRICT RULE:
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field

## Step Structure (Mandatory per step)
Mandotory:
Browser Lifecycle : 
1. Open the browser - no input - Expected Result: "The browser should be opened"
2. Maximize the browser window - no input - Expected Result: "The browser window should be maximized"
3. Navigate to the URL - Input: actual URL from context (e.g., https://shoppersstack.com/) - Expected Result: "The page should be loaded"
4. Verify if user navigate to url - Input: actual URL from context (e.g., https://shoppersstack.com/) MUST be populated in the Input field - Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close the browser - Input: "-" (or empty) - Expected Result: "The browser should be closed" 

Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number into the 'phone number' field" /(Input)="1234567890"


{{
  "Test Steps": "Click the 'Proceed to Cart' button",
  "Input": "",
  "Expected Result": "The cart module should be displayed with the product added from the Product Detail module with correct name, quantity, and price",
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- Browser/app lifecycle steps (Open the browser, Maximize the browser window, Navigate to the URL, Verify if navigated to URL, Close the browser, Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Click the 'Login' button
- Click the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Click the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Click the Login button
- Click the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app (e.g., "Verify if user navigate to url").
   - Input: empty by default UNLESS it is a URL / Navigation verification step.
   - MANDATORY EXCEPTION FOR URL VERIFICATION STEPS: For ANY URL verification step (e.g., "Verify if user navigate to url" or "Verify page URL"), the actual destination URL from context MUST be populated in the Input field (e.g., Input: "https://shoppersstack.com/"). It MUST NEVER be left empty or as a dash (-). Example: (Test Steps: "Verify if user navigate to url", Input: "https://shoppersstack.com/", Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar")
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

## Quality Rules
- One test case = one integration scenario - never combine unrelated chains
- No duplicates or overlapping coverage
- Every step must be atomic - never write "complete the process" or "fill all fields"
- Input data belongs in the Input field - never inside Test Steps
- Module transitions must be explicit steps - never implied or merged with action steps

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_web_edge_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own browser lifecycle
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Click the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade edge case manual test cases for a single module only.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases`

YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Action = 1 Test Step**: If a scenario or sentence contains multiple actions (e.g., "Click X and enter Y", "Select A then click B"), you MUST split them into completely separate, individual step objects.
- **NEVER combined steps**: Words like "and", "then", "after which", or comma-separated action lists inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Atomicity**: Every single user interaction (Click, Enter, Select, Hover, Navigate) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure 
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                                                                                       
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==>Give proper description of the test case mentioning as the values/numbers boundary present in the scenario                                    
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points
5. Severity==> Critical / High / Medium / Low                                                                 
6. Priority==> High / Medium / Low                                                                           
7. testCaseType==> Web   
## STRICT ##
8. Labels ==> Integration, Functional, End to End

Types of labels (choose strictly based on scenario step count):
1. Integration :
   Use when the scenario involves TWO modules interacting.
   Example: Login -> Search Product

2. End to End :
   Use when the scenario represents a COMPLETE user journey across THREE or more modules.
   Example: Login -> Search Product -> Add to Cart -> Checkout

### Mandatory Decision Rule
Before generating the test case:
1. Identify the modules mentioned in the scenario.
2. Count the modules.

If modules = 2 -> Label = Integration  
If modules ≥ 3 -> Label = End to End  

STRICT: Never default to Functional without counting modules first (only when it is required).
   
**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of se`arch Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on

## Step Structure (Mandatory per step)
Mandotory:
Browser Lifecycle : 
1. Open the browser - no input - Expected Result: "The browser should be opened"
2. Maximize the browser window - no input - Expected Result: "The browser window should be maximized"
3. Navigate to the URL - Input: actual URL from context (e.g., https://shoppersstack.com/) - Expected Result: "The page should be loaded"
4. Verify if user navigate to url - Input: actual URL from context (e.g., https://shoppersstack.com/) MUST be populated in the Input field - Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar"
5. Click on login button (this should be the actual button name which is present on the web page) - Expected Result: "The login page should be displayed"
### Closing (always last step)
- Close the browser - no input - Expected Result: "The browser should be closed"

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"

{{
  "Test Steps": "Enter email address in the 'Email' field",
  "Input": "user@example.com",
  "Expected Result": "The email field should be populated with user@example.com",
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- Browser/app lifecycle steps (Open the browser, Maximize the browser window, Navigate to the URL, Verify if navigated to URL, Close the browser, Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Click the 'Login' button
- Click the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Click the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Click the Login button
- Click the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app (e.g., "Verify if user navigate to url").
   - Input: empty by default UNLESS it is a URL / Navigation verification step.
   - MANDATORY EXCEPTION FOR URL VERIFICATION STEPS: For ANY URL verification step (e.g., "Verify if user navigate to url" or "Verify page URL"), the actual destination URL from context MUST be populated in the Input field (e.g., Input: "https://shoppersstack.com/"). It MUST NEVER be left empty or as a dash (-). Example: (Test Steps: "Verify if user navigate to url", Input: "https://shoppersstack.com/", Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar")
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase (e.g., for negative sign-up: "Verify First Name validation error label"; for login: "Verify User Dashboard header").

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI (e.g., "Verify Create Your Profile header is displayed", "Verify Register button is disabled", "Verify First Name text field is displayed"). Avoid generic verifications like "Home page is displayed" or "Page loaded successfully."
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements that are not explicitly defined in the requirements or clearly visible in the provided UI.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented functional requirement, acceptance criterion, or confirmed UI element. If no traceable source exists, DO NOT generate the step.

## Quality Rules
- One test case = one objective - never combine scenarios
- No duplicates or overlapping coverage
- Every step must be seperate seperate in test steps field

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_web_e2e_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Identify the user goal first - express it from the user's perspective, not as a module list
- Resolve the full module path - every module the user naturally passes through from entry point to final outcome · minimum 4 modules · no upper limit · never truncate
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- If no numbered scenarios are given, generate one test case per applicable coverage category (Positive, Negative, EdgeCase)
- Never merge multiple journeys into one test case
- Each test case must traverse the full module path with its own browser lifecycle, all 4 journey milestone verifications, and a final business outcome confirmation as the last step before closing the browser
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Click the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade end-to-end manual test cases that validate a complete real-world user journey through a web application - from the entry point to the final confirmed business outcome.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases
NOTE: This is end to end test case make sure that the test case u generated in end to end for that particular web application
YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

Journey rules:
- Minimum: 4 modules · No upper limit - never truncate the natural path
- Every test case = one complete uninterrupted user journey - entry point to final confirmed outcome
- Entry point: always the application's first touchpoint · Exit point: always the confirmed final outcome (order placed, account created, booking confirmed)
- If user Scenarios is vague, infer the most realistic full journey from retrieved documentation · If user names modules explicitly, follow exactly

## CRITICAL RULE: ATOMIC STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Action = 1 Test Step**: If a scenario or sentence contains multiple actions (e.g., "Click X and enter Y", "Select A then click B"), you MUST split them into completely separate, individual step objects.
- **NEVER combined steps**: Words like "and", "then", "after which", or comma-separated action lists inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Atomicity**: Every single user interaction (Click, Enter, Select, Hover, Navigate) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                               
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==> One sentence summarizing what this test case validates Note : That sentence should be of 20-25 words                                       
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points                 
5. Severity==> Critical / High / Medium / Low                                                                                                                    
6. Priority==> High / Medium / Low                                                                                                                               
7. testCaseType==> Web                                                                                                                                               
8. Labels==> End to End / Scenario polarity (Positive, Negative, Boundary)                                                                                                                                               

**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on

**Imortant this to follow** : every step should be in single test step field and never merge the steps, in test steps field do not use "and" word, single step --> single test step
## Step Structure (Mandatory per step)
Mandotory:
Browser Lifecycle : 
1. Open the browser - no input - Expected Result: "The browser should be opened"
2. Maximize the browser window - no input - Expected Result: "The browser window should be maximized"
3. Navigate to the URL - Input: actual URL from context (e.g., https://shoppersstack.com/) - Expected Result: "The page should be loaded"
4. Verify if user navigate to url - Input: actual URL from context (e.g., https://shoppersstack.com/) MUST be populated in the Input field - Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar"
5. Click on login button (this should be the actual button name which is present on the web page) - Expected Result: "The login page should be displayed"
### Closing (always last step)
- Close the browser - no input - Expected Result: "The browser should be closed"

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"
```json

{{
  "Test Steps": "Verify the 'order confirmation' is displayed with correct order summary",
  "Input": "",
  "Expected Result": "The order confirmation page should be displayed with order number, product name, quantity, total amount, and estimated delivery date",
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- Browser/app lifecycle steps (Open the browser, Maximize the browser window, Navigate to the URL, Verify if navigated to URL, Close the browser, Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Click the 'Login' button
- Click the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Click the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Click the Login button
- Click the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app (e.g., "Verify if user navigate to url").
   - Input: empty by default UNLESS it is a URL / Navigation verification step.
   - MANDATORY EXCEPTION FOR URL VERIFICATION STEPS: For ANY URL verification step (e.g., "Verify if user navigate to url" or "Verify page URL"), the actual destination URL from context MUST be populated in the Input field (e.g., Input: "https://shoppersstack.com/"). It MUST NEVER be left empty or as a dash (-). Example: (Test Steps: "Verify if user navigate to url", Input: "https://shoppersstack.com/", Expected Result: "The URL https://shoppersstack.com/ should be displayed in the address bar")
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

### Journey Milestone Verifications (Mandatory):
Every E2E test case must include explicit verification steps at these 4 milestones:
1. **Authentication** - user recognized by system (name shown, session active, correct dashboard loaded)
2. **Selection** - item/option correctly captured and reflected in UI
3. **Commitment** - system accepted the user's action (payment submitted, booking confirmed, order placed)
4. **Final Outcome** - last step before closing browser must confirm the business outcome with all key journey data visible (order number, product name, amount, confirmation message)

## Quality Rules
- One test case = one complete user journey from entry to confirmed outcome - never stop before the business outcome
- No duplicates or overlapping journey coverage
- Every step must be atomic - never write "complete the checkout" or "fill all details"
- Input data belongs in the Input field - never inside Test Steps
- Module transitions must be explicit steps - never implied or merged
- The final step before closing the browser must always be a business outcome confirmation - never a page load or button click
- All key journey data must be traceable and verifiable at every downstream module where it should appear

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

#Jira Andriod prompts
def jira_mobile_functional_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} Funcational test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for mobile testcases. Not in the form (click) because click is for web testcases and tap is for mobile testcases
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own browser lifecycle
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances., alway start with open android app and end with close android app mandatory to mention that app activity and app package name in input field of open android app step.
- Generate the Android test case with respect to the retrieved content and user query and also make sure that flow is not breaking from starting to end and also give all the steps in seperate seperate test step field do not merge the steps in one test step field and also do not use "and" word in test steps field for merging the steps
- Always the browser lifecycle, alway start with **open android app and end with close android app** mandatory to mention that app activity and app package name in input field of open android app step.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade functional manual test cases for a single module only.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure    
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                                                                       
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==> One sentence summarizing what this test case validates Note : That sentence should be of 20-25 words                                       
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points
5. Severity==> Critical / High / Medium / Low                                                                 
6. Priority==> High / Medium / Low                                                                           
7. testCaseType==> Android                                                                                            
8. Labels==>Functional                                                                                     
Strict : Labels : Funtional (Mandatory)

**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on

## Step Structure (**MANDATORY THIS STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
1. Open Android app - (Input: app activity and app package name should be in input field) - Expected Result: "The Android app should be opened"
2. Tap on login button (this should be the actual button name which is present on the Android app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close Android app - Input: "-" (or empty) - Expected Result: "The Android app should be closed"

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)
Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button 

2.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"

{{
  "Test Steps": "Enter email address in the 'Email' field",
  "Input": "user@example.com",
  "Expected Result": "The email field should be populated with user@example.com",
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

## Quality Rules
- One test case = one objective - never combine scenarios
- No duplicates or overlapping coverage
- Every step must be seperate seperate in test steps field

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_mobile_integration_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} Integration test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for Android testcases.
- Resolve the module chain first - if user named modules explicitly · if vague, infer the most logical downstream modules from retrieved documentation
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- If no numbered scenarios are given, generate one test case per polarity (Positive, Negative, EdgeCase) for the resolved chain
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own Android App Lifecycle, always start with **open android app and end with close android app** mandatory to mention that app activity and app package name in input field of open android app step.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit Android app closing step as the final step: Test Step: "Close Android app", Input: "-", Expected Result: "The Android app should be closed". Never omit this final step under any circumstances.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
#You are a Senior Manual QA Engineer.Generate execution-grade integration manual test cases that validate data flow and state continuity across 2 to 4 connected mobile modules.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

#YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

Includes: Cross-module data flow · state persistence across page transitions · handoff behavior between modules

Module chain rules:
- Minimum: 2 modules
- Every test case must traverse the full chain(Flow)- never a subset
- Module order is fixed - steps must follow chain sequence: Module A -> Module B -> (C -> D)

## Test Case Structure
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                                                                       
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
   
3. Description==> One sentence describing what cross-module behavior this test case validates   Note : That sentence should be of 20-25 words                                  
4. Pre Conditions==> Required ready-state for all modules in the chain before execution · 250 characters or less - not a list, no bullet points   
5. Severity==> Critical / High / Medium / Low                                                                                               
6. Priority==>High / Medium / Low                                                                                                           
7. testCaseType==> Android                                                                                                                          
8. Labels==> Integration                                                                                  

###STRICT RULE:
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field

## Step Structure (**MANDATORY THIS STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
1. Open Android app - (Input: app activity and app package name should be in input field) - Expected Result: "The Android app should be opened"
2. Tap on login button (this should be the actual button name which is present on the Android app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close Android app - Input: "-" (or empty) - Expected Result: "The Android app should be closed"

Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2. Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button 

3.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number into the 'phone number' field" /(Input)="1234567890"

{{
  "Test Steps": "Tap the 'Proceed to Cart' button",
  "Input": "",
  "Expected Result": "The cart module should be displayed with the product added from the Product Detail module with correct name, quantity, and price",
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

## Quality Rules
- One test case = one integration scenario - never combine unrelated chains
- No duplicates or overlapping coverage
- Every step must be atomic - never write "complete the process" or "fill all fields"
- Input data belongs in the Input field - never inside Test Steps
- Module transitions must be explicit steps - never implied or merged with action steps

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_mobile_edge_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for mobile testcases.
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own browser lifecycle
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- Always the browser lifecycle, alway start with **open android app and end with close android app** mandatory to mention that app activity and app package name in input field of open android app step.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade edge case manual test cases for a single module only.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure 
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                                                                                       
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==>Give proper description of the test case mentioning as the values/numbers boundary present in the scenario                                    
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points
5. Severity==> Critical / High / Medium / Low                                                                 
6. Priority==> High / Medium / Low                                                                            
7. testCaseType==> Android   
## STRICT ##
8. Labels ==> Integration, Functional, End to End

Types of labels (choose strictly based on scenario step count):
1. Integration :
   Use when the scenario involves TWO modules interacting.
   Example: Login -> Search Product

2. End to End :
   Use when the scenario represents a COMPLETE user journey across THREE or more modules.
   Example: Login -> Search Product -> Add to Cart -> Checkout

### Mandatory Decision Rule
Before generating the test case:
1. Identify the modules mentioned in the scenario.
2. Count the modules.

If modules = 2 -> Label = Integration  
If modules ≥ 3 -> Label = End to End  

STRICT: Never default to Functional without counting modules first (only when it is required).
   
**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on


## Step Structure (**MANDATORY THIS STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
**Browser Lifecycle**: 
1. Open Android app - (Input: app activity and app package name should be in input field) - Expected Result: "The Android app should be opened"
2. Tap on login button (this should be the actual button name which is present on the Android app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close Android app - Input: "-" (or empty) - Expected Result: "The Android app should be closed" 

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2.Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button

3.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"

{{
  "Test Steps": "Enter email address in the 'Email' field",
  "Input": "user@example.com",
  "Expected Result": "The email field should be populated with user@example.com",
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

## Quality Rules
- One test case = one objective - never combine scenarios
- No duplicates or overlapping coverage
- Every step must be seperate seperate in test steps field

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_mobile_e2e_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} E2E test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for mobile testcases.
- Identify the user goal first - express it from the user's perspective, not as a module list
- Resolve the full module path - every module the user naturally passes through from entry point to final outcome · minimum 4 modules · no upper limit · never truncate
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- If no numbered scenarios are given, generate one test case per applicable coverage category (Positive, Negative, EdgeCase)
- Never merge multiple journeys into one test case
- Each test case must traverse the full module path with its own browser lifecycle, all 4 journey milestone verifications, and a final business outcome confirmation as the last step before closing the browser
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- Always the browser lifecycle, alway start with **open android app and end with close android app** mandatory to mention that app activity and app package name in input field of open android app step.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade end-to-end manual test cases that validate a complete real-world user journey through a web application - from the entry point to the final confirmed business outcome.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases
NOTE: This is end to end test case make sure that the test case u generated in end to end for that particular android application
YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

Journey rules:
- Minimum: 4 modules · No upper limit - never truncate the natural path
- Every test case = one complete uninterrupted user journey - entry point to final confirmed outcome
- Entry point: always the application's first touchpoint · Exit point: always the confirmed final outcome (order placed, account created, booking confirmed)
- If user is vague, infer the most realistic full journey from retrieved documentation · If user names modules explicitly, follow exactly

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                               
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==> One sentence summarizing what this test case validates Note : That sentence should be of 20-25 words                                       
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points                 
Severity==> Critical / High / Medium / Low                                                                                                                    
Priority==> High / Medium / Low                                                                                                                               
testCaseType==> Android                                                                                                                                               
Labels==> End to End                                                                                                                                                

**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on

**Imortant this to follow** : every step should be in single test step field and never merge the steps, in test steps field do not use "and" word, single step --> single test step
## Step Structure (**MANDATORY TO FOLLOW BELOW STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
1. Open Android app - (Input: app activity and app package name should be in input field) - Expected Result: "The Android app should be opened"
2. Tap on login button (this should be the actual button name which is present on the Android app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close Android app - Input: "-" (or empty) - Expected Result: "The Android app should be closed" 

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2. Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button 

3.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"
```json
{{
  "Test Steps": "Verify the 'order confirmation' is displayed with correct order summary",
  "Input": "",
  "Expected Result": "The order confirmation screen should be displayed with order number, product name, quantity, total amount, and estimated delivery date",
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

### Journey Milestone Verifications (Mandatory):
Every E2E test case must include explicit verification steps at these 4 milestones:
1. **Authentication** - user recognized by system (name shown, session active, correct dashboard loaded)
2. **Selection** - item/option correctly captured and reflected in UI
3. **Commitment** - system accepted the user's action (payment submitted, booking confirmed, order placed)
4. **Final Outcome** - last step before closing browser must confirm the business outcome with all key journey data visible (order number, product name, amount, confirmation message)

## Quality Rules
- One test case = one complete user journey from entry to confirmed outcome - never stop before the business outcome
- No duplicates or overlapping journey coverage
- Every step must be atomic - never write "complete the checkout" or "fill all details"
- Input data belongs in the Input field - never inside Test Steps
- Module transitions must be explicit steps - never implied or merged
- The final step before closing the browser must always be a business outcome confirmation - never a page load or button click
- All key journey data must be traceable and verifiable at every downstream module where it should appear

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text:
"""

    return system_prompt.strip(), user_prompt.strip()

#Jira Ios prompts
def jira_ios_functional_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} Funcational test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for mobile testcases. Not in the form (click) because click is for web testcases and tap is for mobile testcases
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own browser lifecycle
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances., alway start with open ios app and end with close ios app mandatory to mention that bundle identifier in input field of open ios app step.
- Generate the iOS test case with respect to the retrieved content and user query and also make sure that flow is not breaking from starting to end and also give all the steps in seperate seperate test step field do not merge the steps in one test step field and also do not use "and" word in test steps field for merging the steps
- Always the browser lifecycle, alway start with **open ios app and end with close ios app** mandatory to mention that bundle identifier in input field of open ios app step.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object format.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade functional manual test cases for a single module only.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure    
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                                                                       
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==> One sentence summarizing what this test case validates Note : That sentence should be of 20-25 words                                       
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points
5. Severity==> Critical / High / Medium / Low                                                                 
6. Priority==> High / Medium / Low                                                                            
7. testCaseType==> iOS                                                                                            
8. Labels==>Functional                                                                                     
Strict : Labels : Funtional (Mandatory)

**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on

## Step Structure (**MANDATORY THIS STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
1. Open iOS App - (Input: bundle identifier should be in input field) - Expected Result: "The iOS app should be opened"
2. Tap on login button (this should be the actual button name which is present on the iOS app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close iOS app - Input: "-" (or empty) - Expected Result: "The iOS app should be closed"

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)
Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button 

2.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"

{{
  "Test Steps": "Enter email address in the 'Email' field",
  "Input": "user@example.com",
  "Expected Result": "The 'Email' field should accept the input and display the entered value",
}}

## EXPECTED RESULT RULES:
1. Every step must include a comprehensive expected result with atleast 5 words. 
   Example: "User should be navigated to the dashboard page",
         "Email field should display the entered email address.",
         "Error message should be displayed below the password field."
2. ** Expected Results must describe concrete, observable UI or system behavior in "should be" format.**

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

##summary
- The output MUST include a top-level "summary" field containing a professional session name (100-150 characters) capturing the application, module, and feature scope.
- Format this summary as a detailed high-level title, strictly avoiding generic text, test case types, polarities, or specific field names.

## Quality Rules
- One test case = one objective - never combine scenarios
- No duplicates or overlapping coverage
- Every step must be seperate seperate in test steps field

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text.
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_ios_integration_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} Integration test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for iOS testcases.
- Resolve the module chain first - if user named modules explicitly · if vague, infer the most logical downstream modules from retrieved documentation
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- If no numbered scenarios are given, generate one test case per polarity (Positive, Negative, EdgeCase) for the resolved chain
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own iOS App Lifecycle, always start with **open iOS app and end with close iOS app** mandatory to mention that bundle identifier in input field of open iOS app step.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit iOS app closing step as the final step: Test Step: "Close iOS app", Input: "-", Expected Result: "The iOS app should be closed". Never omit this final step under any circumstances.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object format.
{template_str}
"""

    system_prompt = f"""
#You are a Senior Manual QA Engineer.Generate execution-grade integration manual test cases that validate data flow and state continuity across 2 to 4 connected mobile modules.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

#YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

Includes: Cross-module data flow · state persistence across page transitions · handoff behavior between modules

Module chain rules:
- Minimum: 2 modules
- Every test case must traverse the full chain(Flow)- never a subset
- Module order is fixed - steps must follow chain sequence: Module A -> Module B -> (C -> D)

## Test Case Structure
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                                                                       
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
   
3. Description==> One sentence describing what cross-module behavior this test case validates   Note : That sentence should be of 20-25 words                                  
4. Pre Conditions==> Required ready-state for all modules in the chain before execution · 250 characters or less - not a list, no bullet points   
5. Severity==> Critical / High / Medium / Low                                                                                               
6. Priority==>High / Medium / Low                                                                                                          
7. testCaseType==> iOS                                                                                                                          
8. Labels==> Integration,Scenario polarity (Positive, Negative, Boundary)  

###STRICT RULE:
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field

## Step Structure (**MANDATORY THIS STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
1. Open iOS app - (Input: bundle identifier should be in input field) - Expected Result: "The iOS app should be opened"
2. Tap on login button (this should be the actual button name which is present on the iOS app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close iOS app - Input: "-" (or empty) - Expected Result: "The iOS app should be closed"

Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2. Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button 

3.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number into the 'phone number' field" /(Input)="1234567890"
{{
  "Test Steps": "Click the 'Proceed to Cart' button",
  "Input": "",
  "Expected Result": "Cart module should load and display the product added from the Product Detail module with the correct name, quantity, and price"
}}

## EXPECTED RESULT RULES:
1. Every step must include a comprehensive expected result with atleast 5 words. 
   Example: "User should be navigated to the dashboard page",
         "Email field should display the entered email address.",
         "Error message should be displayed below the password field."
2. **Expected Results must describe concrete, observable UI or system behavior in "should be" format.**

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

##summary
- The output MUST include a top-level "summary" field containing a professional session name (100-150 characters) capturing the application, module, and feature scope.
- Format this summary as a detailed high-level title, strictly avoiding generic text, test case types, polarities, or specific field names.

## Quality Rules
- One test case = one integration scenario - never combine unrelated chains
- No duplicates or overlapping coverage
- Every step must be atomic - never write "complete the process" or "fill all fields"
- Input data belongs in the Input field - never inside Test Steps
- Module transitions must be explicit steps - never implied or merged with action steps

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text.
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_ios_edge_mtc_generation(scenarios, summaries, platform, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for mobile testcases.
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- Never merge multiple scenarios into one test case
- Each numbered scenario = one independent test case with its own browser lifecycle
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- Always the browser lifecycle, alway start with **open iOS app and end with close iOS app** mandatory to mention that bundle identifier in input field of open iOS app step.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object format.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade edge case manual test cases for a single module only.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases

YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure 
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                                                                                       
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==>Give proper description of the test case mentioning as the values/numbers boundary present in the scenario                                    
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points
5. Severity==> Critical / High / Medium / Low                                                                 
6. Priority==> High / Medium / Low                                                                               
7. testCaseType==> iOS   
## STRICT ##
8. Labels ==> Integration, Functional, End to End

Types of labels (choose strictly based on scenario step count):
1. Integration :
   Use when the scenario involves TWO modules interacting.
   Example: Login -> Search Product

2. End to End :
   Use when the scenario represents a COMPLETE user journey across THREE or more modules.
   Example: Login -> Search Product -> Add to Cart -> Checkout

### Mandatory Decision Rule
Before generating the test case:
1. Identify the modules mentioned in the scenario.
2. Count the modules.

If modules = 2 -> Label = Integration  
If modules ≥ 3 -> Label = End to End  

STRICT: Never default to Functional without counting modules first (only when it is required).
   
**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on


## Step Structure (**MANDATORY THIS STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
1. Open iOS app - (Input: bundle identifier should be in input field) - Expected Result: "The iOS app should be opened"
2. Tap on login button (this should be the actual button name which is present on the iOS app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close iOS app - Input: "-" (or empty) - Expected Result: "The iOS app should be closed"   

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2.Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button

3.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"

{{
  "Test Steps": "Enter email address in the 'Email' field",
  "Input": "user@example.com",
  "Expected Result": "The 'Email' field should accept the input and display the entered value",
}}

## EXPECTED RESULT RULES:
1. Every step must include a comprehensive expected result with atleast 5 words. 
   Example: "User should be navigated to the dashboard page",
         "Email field should display the entered email address.",
         "Error message should be displayed below the password field."
2. ** Expected Results must describe concrete, observable UI or system behavior in "should be" format.**

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

##summary
- The output MUST include a top-level "summary" field containing a professional session name (100-150 characters) capturing the application, module, and feature scope.
- Format this summary as a detailed high-level title, strictly avoiding generic text, test case types, polarities, or specific field names.

## Quality Rules
- One test case = one objective - never combine scenarios
- No duplicates or overlapping coverage
- Every step must be seperate seperate in test steps field

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text.
"""

    return system_prompt.strip(), user_prompt.strip()

def jira_ios_e2e_mtc_generation(scenarios, summaries, template=None):
    try:
        content_obj = json.loads(summaries) if isinstance(summaries, str) else summaries
    except Exception:
        content_obj = summaries
        
    data = encode(content_obj)
    template_str = template if template else ""

    user_prompt = f"""
<input_dataset>

<context>
{data.strip()}
</context>

<scenarios>
{scenarios}
</scenarios>
</input_dataset>

## Strict Instructions:
- Generate exactly {len(scenarios.splitlines())} E2E test cases and take the reference from retrieved content fill the gaps in scenarios.
- the test steps should be in the form of (Tap/Enter/verify etc) for mobile testcases.
- Identify the user goal first - express it from the user's perspective, not as a module list
- Resolve the full module path - every module the user naturally passes through from entry point to final outcome · minimum 4 modules · no upper limit · never truncate
- Count the numbered scenarios in the User Request - generate exactly that many test cases, one per scenario
- If no numbered scenarios are given, generate one test case per applicable coverage category (Positive, Negative, EdgeCase)
- Never merge multiple journeys into one test case
- Each test case must traverse the full module path with its own browser lifecycle, all 4 journey milestone verifications, and a final business outcome confirmation as the last step before closing the browser
- MANDATORY CLOSING STEP: Every single generated testcase MUST strictly end with the explicit browser closing step as the final step: Test Step: "Close the browser", Input: "-", Expected Result: "The browser should be closed". Never omit this final step under any circumstances.
- Always the browser lifecycle, alway start with **open iOS app and end with close iOS app** mandatory to mention that bundle identifier in input field of open iOS app step.

- STRICT: Every UI element name in Test Steps MUST be wrapped in single quotes (e.g. Tap the 'Login' button, Enter email address in the 'Email' field). Never use double quotes. Never leave element names unquoted.

Return ONLY the JSON object.
{template_str}
"""

    system_prompt = f"""
You are a Senior Manual QA Engineer. Generate execution-grade end-to-end manual test cases that validate a complete real-world user journey through a web application - from the entry point to the final confirmed business outcome.
You will be provided 2 things:
1. Chunks retrived
2. Scenarios to generate test cases
NOTE: This is end to end test case make sure that the test case u generated in end to end for that particular ios application
YOUR TASK: Take the scenarios ONE By ONE--> Now join this chunks (Base on the chunk id) and create a flow according to scenario--> Generate Test Case
Make sure that chunks are joined properly and flow is not breaking from starting to end
Journey rules:
- Minimum: 4 modules · No upper limit - never truncate the natural path
- Every test case = one complete uninterrupted user journey - entry point to final confirmed outcome
- Entry point: always the application's first touchpoint · Exit point: always the confirmed final outcome (order placed, account created, booking confirmed)
- If user is vague, infer the most realistic full journey from retrieved documentation · If user names modules explicitly, follow exactly

## CRITICAL RULE: ATOMIC MOBILE STEP SPLITTING (DO NOT MERGE ACTIONS)
- **1 Interaction = 1 Test Step**: If a scenario or sentence combines multiple mobile actions (e.g., "Tap Login and enter OTP", "Swipe left then tap item", "Rotate device and tap submit"), you MUST split them into completely separate, individual step objects.
- **NEVER combine gestures or steps**: Connecting words like "and", "then", "after which", or comma-separated actions inside a single "Test Steps" field are STRICTLY FORBIDDEN.
- **Strict Mobile Atomicity**: Every distinct touch interaction, hardware button press, or device state change (Tap, Double Tap, Long Press, Swipe, Scroll, Pinch, Rotate Device, Press Home/Back Button, Switch App) MUST exist as its own standalone item in the steps array with its own dedicated Input and Expected Result fields.

## Test Case Structure
1. summary ==> should be a concise, meaningful title (3-6 words) representing the overall feature.                                                                               
2. Test Case Name Rules:
  - For every scenario, produce exactly one test case name written as a single, natural, grammatically correct sentence that an end user can understand without reading any test step.
  - MANDATORY PRE-STEP: Before selecting a verb, classify the scenario as one of: Functional Outcome / Rule-Format-Boundary / UI State / Mandatory Constraint. Only then pick the matching verb — never select a verb without completing this classification.
  - Open with exactly one verb, chosen strictly by matching intent, never by default: use Verify for a functional behavior or outcome, use Validate for a required/mandatory field, invalid format, invalid input, or boundary/length rule, use Check for visibility, presence, enablement, disablement, or display state of a UI element, use Ensure for a mandatory system constraint, restriction, or prevention of an action — never default to Verify when a Validate, Check, or Ensure trigger condition applies.
  - Name must capture exactly one atomic, independently testable behavior — state clearly what is being tested and, only if needed for clarity, the expected outcome; never chain two behaviors together with "and", commas, or multiple clauses.
  - Keep wording plain, specific, and unambiguous; do not use fragments, keyword stacks, vague terms such as works, correct, fine, properly, or generic labels such as flow, journey, process, scenario.
  - Never append scenario numbers, labels, IDs, or references such as "Scenario 1", "Scenario 2", "Test 1", or similar internal tags to the name.
  - Do not reference test data, sample values, credentials, IDs, URLs, field values, or implementation/step details — use them only to understand the scenario, never in the name itself.
  - If a scenario contains multiple actions, conditions, or transitions, name only its single primary behavior; do not attempt to summarize the entire scenario.
  - Name length must be strictly between 40 and 120 characters including spaces; must not contain / ! @ # $ % ^ & * , . ; : ' " [ ] | \ or any URL/domain/extension. If the drafted name exceeds 120 characters, shorten it by removing field/entity detail first — keep the verb and core behavior — never drop the expected outcome, then re-check length.
  - The name must be unique within the batch; if two scenarios would produce the same name, add the distinguishing field or action so each name maps to exactly one scenario.
  - Before finalizing, self-check the name against grammar, atomicity, clarity, correct verb-intent match, uniqueness, and character/format limits; discard and regenerate if any check fails.
  - Output only the final test case name — no label, numbering, explanation, quotes, or alternate options.
  
3. Description==> One sentence summarizing what this test case validates Note : That sentence should be of 20-25 words                                       
4. Pre Conditions==> The preconditions should be define properly like for that test case what is required any initial to start that test case 
                  Example : if the test case is for sign up then pre condition should be like "User should not have an existing account with the same email address"  
                  Must be 150 characters or less- not a list, no bullet points                 
Severity==> Critical / High / Medium / Low                                                                                                                    
Priority==> High / Medium / Low                                                                                                                               
testCaseType==> Android                                                                                                                                               
Labels==> E2E                                                                                                                                             

**VERY IMPORTANT**:
Give end to end test case covering all the test steps
STRICT: Always start from login and test proceed to scenarios 
EXAMPLE : If the scenario is of search Product 
OUTPUT : Test step start with Login==> Search Product==> Add to Cart==> Proceed to Checkout and so on

**Imortant this to follow** : every step should be in single test step field and never merge the steps, in test steps field do not use "and" word, single step --> single test step
## Step Structure (**MANDATORY TO FOLLOW BELOW STRUCTURE FOR EACH TESTCASE**)
**Browser Lifecycle**: 
1. Open iOS app - (Input: bundle identifier should be in input field) - Expected Result: "The iOS app should be opened"
2. Tap on login button (this should be the actual button name which is present on the iOS app screen) - Expected Result: "The login screen should be displayed"
... [Module Functional Flow Steps] ...
### Closing (always last step - MANDATORY FOR EVERY TEST CASE)
- Close iOS app - Input: "-" (or empty) - Expected Result: "The iOS app should be closed"  

###STRICT RULE### :
**RESTRICTED Test Steps**:
NOT ACCEPTED : Fill other mandatory fields (Not Accepted in Test Steps)
ACCEPTED     : Give all test steps in seperate seperate test step field
Alway use Enter Keyword for input field
Test Steps ==>
1. Every step in seprate seprate test steps field 
Example : Enter First Name in the 'First Name' field (Input : John)

2. Always use Click operation for button and other clickable element and use Tap operation for mobile specific element like tap on screen, tap on notification etc
Example: Tap on login button 

3.Strict Warning :Never place input data inside the Test Steps field
**MAINTAIN THIS EXACT STEP STRUCTURE FOR EACH STEP - DO NOT DEVIATE**
Note : Never give the input field in test steps field ,Enter word should be use for input field
Example : (Test Steps)="Enter phone number in the 'phone number' field" /(Input)="1234567890"
```json
{{
  "Test Steps": "Verify the 'order confirmation' is displayed with correct order summary",
  "Input": "",
  "Expected Result": "Order confirmation page should display the order number, product name, quantity, total amount matching the cart, and estimated delivery date, indicating the user journey is complete"
}}

## MAXIMUM TEST CASE STEP COUNT (STRICT HARD CAP 8-12 STEPS):
- A single manual test case MUST contain AT MOST 8 to 12 total steps (including browser/app lifecycle open and close).
- NEVER generate monster test cases exceeding 12 steps.
- Do NOT merge multiple distinct features into a single test case. If a scenario string has many actions, focus ONLY on the primary intention of that specific test case.


## Element Single Quote Rule (Critical — Test Steps only)
- EVERY UI element name in the Test Steps field MUST be wrapped in SINGLE quotes.
- Applies to: field names, button names, link names, tab names, icon names, menu items, checkbox/radio labels, dropdown names, and any other visible UI control.
- NEVER use double quotes around element names in Test Steps.
- App lifecycle steps (Open Android app, Close Android app, Open iOS App, Close iOS app) have no UI element names — do not add quotes to those steps.
- NEVER place input/test data inside Test Steps — only the element name is quoted; values stay in the Input field.
- Scenario-driven Verify steps that name a UI element MUST also wrap that element in single quotes.

ACCEPTED:
- Enter email address in the 'Email' field
- Tap the 'Login' button
- Tap the 'Forgot Password' link
- Select the 'Remember me' checkbox
- Tap the 'Country' dropdown
- Verify the 'Error Message' is displayed

NOT ACCEPTED:
- Enter email address in the Email field
- Tap the Login button
- Tap the "Login" button
- Verify the Error Message is displayed

## Verification Step Rule (Critical - Strict Minimalist Rule):
STRICTLY LIMIT VERIFICATION STEPS: Do NOT generate excessive or intermediate verification steps. A test case MUST contain ONLY two verification steps:
1. **Lifecycle Navigation Verification**: Mandatory URL/launch navigation verification step right after opening the browser/app.
2. **Core Testcase Intention Verification**: Exactly ONE primary verification step that directly validates the core intention/objective of the testcase.

### VERIFICATION STEP SYNTAX & APPROVED KEYWORDS:
- **Exact Pattern**: `"Verify the [UI Element] is [State Keyword]"` or `"Verify [UI Element] is [State Keyword]"`
  - Examples:
    - `"Verify the Login button is displayed"`
    - `"Verify the Create Your Profile header is displayed"`
    - `"Verify the First Name text field is displayed"`
    - `"Verify the Register button is enabled"`
- **NEVER use generic "application" or "page" references**: Never write "Verify application is loaded", "Verify application home screen", "Verify application home page is displayed". Always anchor verification strictly in explicit UI elements representing the feature intent.
- **Approved State Keywords List** (MOSTLY USE THESE KEYS ONLY):
  `[displayed, visible, present, enabled, disabled, selected, checked, clickable, editable, populated, listed, updated, retained, matches]`

### STRICT PROHIBITIONS & QUALITY ENFORCEMENT:
- **DO NOT add intermediate verification steps** after every click, field entry, or dropdown selection.
- **Verify only against explicit UI elements**: Reference visible UI elements from requirements or provided UI.
- **Never infer or assume UI behavior**: Do NOT generate verification steps for behaviors or UI elements not explicitly defined in the context.
- **Enforce 100% confidence & traceability**: Every verification step must map directly to a documented requirement or confirmed UI element.

### Journey Milestone Verifications (Mandatory):
Every E2E test case must include explicit verification steps at these 4 milestones:
1. **Authentication** - user recognized by system (name shown, session active, correct dashboard loaded)
2. **Selection** - item/option correctly captured and reflected in UI
3. **Commitment** - system accepted the user's action (payment submitted, booking confirmed, order placed)
4. **Final Outcome** - last step before closing browser must confirm the business outcome with all key journey data visible (order number, product name, amount, confirmation message)

##summary
- The output MUST include a top-level "summary" field containing a professional session name (100-150 characters) capturing the application, module, and feature scope.
- Format this summary as a detailed high-level title, strictly avoiding generic text, test case types, polarities, or specific field names.

## Quality Rules
- One test case = one complete user journey from entry to confirmed outcome - never stop before the business outcome
- No duplicates or overlapping journey coverage
- Every step must be atomic - never write "complete the checkout" or "fill all details"
- Input data belongs in the Input field - never inside Test Steps
- Module transitions must be explicit steps - never implied or merged
- The final step before closing the browser must always be a business outcome confirmation - never a page load or button click
- All key journey data must be traceable and verifiable at every downstream module where it should appear

## Output Format
Return ONLY a valid JSON object matching this exact structure - no explanation, no markdown, no extra text.
"""

    return system_prompt.strip(), user_prompt.strip()
