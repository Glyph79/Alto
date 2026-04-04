from ..router.router import router

def process_message(user_message: str, session_state: dict) -> (str, dict):
    """
    Central handler: optional pre‑processing, call router, optional post‑processing.
    Returns (response_text, updated_state).
    """
    text = user_message.strip().lower()
    response, new_state = router.handle(text, session_state)
    if response:
        response = response[0].upper() + response[1:]
    return response, new_state