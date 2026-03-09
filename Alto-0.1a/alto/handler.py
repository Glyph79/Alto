# handler.py
"""
Orchestration pipeline. Each step receives the current text and a state dict,
and returns (updated_text, updated_state). The final text is sent to the user.
"""

# ----------------------------------------------------------------------
# Define individual processing steps below.
# Each step must be a callable with signature (text: str, state: dict)
# -> (new_text: str, new_state: dict)
# ----------------------------------------------------------------------

def preprocess_step(text: str, state: dict) -> (str, dict):
    """Example: trim whitespace and convert to lowercase."""
    text = text.strip().lower()
    return text, state

def route_step(text: str, state: dict) -> (str, dict):
    """Core routing: get response from router."""
    from router import router
    response = router.handle(text)
    return response, state

def postprocess_step(text: str, state: dict) -> (str, dict):
    """Example: capitalise first letter (optional post-formatting)."""
    if text:
        text = text[0].upper() + text[1:]
    return text, state

# ----------------------------------------------------------------------
# Pipeline configuration – list steps in desired order.
# ----------------------------------------------------------------------
PIPELINE_STEPS = [
    preprocess_step,
    route_step,
    postprocess_step,
]

def process_message(user_message: str) -> str:
    """
    Run the user message through all pipeline steps and return the final response.
    """
    state = {}
    current = user_message
    for step in PIPELINE_STEPS:
        current, state = step(current, state)
    return current