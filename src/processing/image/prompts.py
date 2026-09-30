from typing import Tuple, Dict, Any

def irrelevant_image_detection_prompt(user_input: str) -> Tuple[str, Dict[str, Any]]:
    """Returns the system prompt and JSON schema for irrelevant image detection."""
    user_input = str(user_input)
    if user_input == "":
        user_input = "Analyze and Validate the provided images."

    json_structure_image_schema = {
        "type": "object",
        "properties": {
            "content": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "imageName": {"type": "string"}
                    },
                    "required": ["imageName"],
                    "additionalProperties": False
                }
            },
            "invalidImages": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["content", "invalidImages"],
        "additionalProperties": False
    }

    prompt = """
You are an expert image analyzer working from a software testing and QA perspective.

You will be given one or more images, each labeled with a generated screen name (e.g., img_1, img_2).

==================================================
CLASSIFICATION RULES
==================================================

DEFAULT RULE: When in doubt → mark as VALID.
Only mark INVALID if you are 100% certain the image has absolutely NO relation 
to any software, web, or mobile application.

VALID image = ANY image that contains even a single software UI element, including:
  - UI screenshots of web, mobile, or desktop apps (ANY domain, ANY language)
  - Alert boxes, modals, popups, overlays, dialogs appearing over an app screen
  - Screens with non-English text or any regional/foreign language scripts
  - Blurred or partially visible app backgrounds behind a modal/popup
  - Flow diagrams, wireframes, navigation maps, user journey diagrams
  - App store listings, mockups, prototypes, error screens, loading screens
  - Dashboards, admin panels, settings screens, splash screens
  - ANY screen showing buttons, forms, input fields, menus, or navigation elements
  - Low quality, blurry, or partial screenshots that show any app UI element
  - Any image showing a browser, browser URL bar, or browser chrome
  - CAPTCHA challenges (image grids, object selection, puzzle sliders) embedded within an app screen
  - Real-world photos or objects appearing INSIDE a software UI (e.g. product images, avatars, CAPTCHA grids)

INVALID image = ONLY images that satisfy ALL of the following conditions:
  - Contains zero software UI elements (no buttons, no forms, no browser, no screen)
  - Contains zero diagrams, wireframes, or flow charts
  - Is purely a real-world photograph, abstract art, or blank/corrupted image
  - Cannot in any way be used by a QA engineer to write a test case

==================================================
HOW TO DECIDE — ASK YOURSELF THESE QUESTIONS:
==================================================
Q1. Can I see a browser, app screen, or any digital interface? → VALID
Q2. Can I see any buttons, input fields, menus, or navigation elements? → VALID
Q3. Can I see any modal, popup, alert, overlay, or CAPTCHA challenge? → VALID
Q4. Can I see any diagram, wireframe, or flow chart? → VALID
Q5. Does the image contain ANY real-world photos or objects embedded
    WITHIN a software UI (e.g. product images, avatars, CAPTCHA grids)? → VALID
Q6. Is the ONLY content a real-world photo/image with zero UI elements? → INVALID

==================================================
FOR EACH VALID IMAGE, EXTRACT:
==================================================
1. "imageName" → A short descriptive name based on what the screen shows
                 Examples: "Login Page", "Dashboard Screen", "Checkout Flow", 
                 "Language Selection Modal", "Train Search Page"

==================================================
OUTPUT FORMAT (STRICT JSON ONLY)
==================================================
{
  "content": {
    "<ScreenName>": {
      "imageName": "<descriptive name based on the screen>"
    }
  },
  "invalidImages": ["<ScreenName>", "<ScreenName>"]
}

==================================================
RULES :
==================================================
- Output ONLY valid JSON. No explanations, no markdown, no extra text.
- Every image must appear either in "content" or in "invalidImages". Never skip an image.
- Only VALID images go into "content". Only INVALID images go into "invalidImages".
- If no invalid images → "invalidImages": []
- If no valid images → "content": {}
"""
    return prompt, json_structure_image_schema

imageSummarySchema = {
    "type": "object",
    "properties": {
        "screens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "screenName": {
                        "type": "string"
                    },
                    "description": {
                        "type": "string"
                    },
                    "journeyPosition": {
                        "type": "string"
                    },
                    "screenFlow": {
                        "type": "object",
                        "properties": {
                            "triggerAction":        {"type": "string"},
                            "landingAssertion":     {"type": "string"},
                            "landingAssertionType": {"type": "string"}
                        },
                        "required": [
                            "triggerAction",
                            "landingAssertion",
                            "landingAssertionType"
                        ],
                        "additionalProperties": False
                    },
                    "summary": {
                        "type": "string"
                    },
                    "assertions": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "messageText": {"type": "string"},
                                "messageType": {"type": "string"},
                                "trigger":     {"type": "string"}
                            },
                            "required": ["messageText", "messageType", "trigger"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": [
                    "screenName", "description", "journeyPosition",
                    "screenFlow", "summary", "assertions"
                ],
                "additionalProperties": False
            }
        },
        "overallSummary": {
            "type": "object",
            "properties": {
                "userIntention": {"type": "string"}
            },
            "required": ["userIntention"],
            "additionalProperties": False
        }
    },
    "required": ["screens", "overallSummary"],
    "additionalProperties": False
}

image_user_story_prompt = f"""PRIMARY TASK
    Given an image of a website or web page, generate  complete detail user stories that strictly follow the structure and depth of a professional QA user story.
    The generated user stories must be explicitly usable for deriving manual test cases without further clarification.
    MANDATORY OUTPUT STRUCTURE (DO NOT DEVIATE)
    For each user story, produce the following sections in this exact order and naming:
    USER STORY — <Concise Feature Name>
    Purpose
    As a <type of user>, I want to <primary action> so that <business or user value>.
    Pre-Conditions
    List only conditions that can be reasonably inferred from the UI image, such as:
    - Browser access
    - Page availability
    - User state (guest or logged-in), only if visually indicated
    UI Elements
    Note :ALL elements should be cover in that UI and it should tell whether clickable or not
    List all visible and relevant UI components, including:
    - Input fields
    - Buttons
    - Links
    - Checkboxes
    - Dropdowns
    - Labels
    - Error or helper text (if visible)
    Descriptions of navigated from:
    from where and how this image is navigated i.e as_destination (from_screen to destinationFrame) 


    Functional Flow
    Describe the step-by-step user interaction flow as observed from the UI image:
    the functional flow should be very detail i will give u am example of how should be the functional flow section 
    according to that you give for every image
    Example: The flow begins in the Sign In section of the Spencer’s Online page.
    The user enters their registered Email Address in the first input field. They then type their Password, ensuring it meets the required format (case-sensitive, 8 or more characters).
    The user may optionally select the Remember Me checkbox to stay signed in on future visits.
    The user clicks the Sign In button. The system validates the email and password combination. If the credentials are correct, the user is logged in and redirected to their account dashboard or the previous page they were viewing.
    If incorrect credentials are entered, the system displays an appropriate error message. The user may select the Forgot Password link if they need to recover or reset their password.
    in this way the flow should be for every image 
    note:cover all the fields properly and if they are having any  by default values in that field also highligh it properly in chunks because question for extracting the data can be asked base on the placeholder also 
    Note : when You are mentioning the about buttons ,links elements etc mention there name seperatly
    - Starting point (page or section)
    - User actions in sequence
    - System responses and validations
    - Navigation or state changes
    Write in clear, test-step-friendly language.
    Acceptance Criteria
    Write atomic, testable acceptance criteria using the format:
    AC1:
    AC2:
    AC3:
    Each acceptance criterion must:
    - Be verifiable via manual testing
    - Cover positive and negative scenarios where applicable
    - Reference visible UI elements and validations
    CONSTRAINTS AND QUALITY RULES
    - Do not include assumptions that are not visually supported.
    - Do not reference backend systems, APIs, or databases unless explicitly visible.
    - Do not merge unrelated features into a single user story.
    - Prefer clarity and testability over brevity.
    - Acceptance criteria must be sufficient to derive positive, negative, and edge test cases.
    OUTPUT RULES
    - Output plain text only.
    - No explanations, no commentary, no analysis.
    - Only the user story content.

"""
