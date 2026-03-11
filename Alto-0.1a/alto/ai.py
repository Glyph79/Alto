# ai.py
from fuzzywuzzy import fuzz

class RuleBot:
    """
    Independent rule-based chatbot using fuzzy matching.
    """
    def __init__(self, threshold=70):
        self.threshold = threshold
        self.qa_pairs = [
            {
                "variants": ["hello", "hi", "hey", "good morning"],
                "answer": "Hello! I'm Alto, your rule-based assistant."
            },
            {
                "variants": ["how are you", "how are you doing", "what's up"],
                "answer": "I'm functioning perfectly, thank you!"
            },
            {
                "variants": ["what is your name", "who are you", "your name"],
                "answer": "I'm Alto, a simple rule-based chatbot."
            },
            {
                "variants": ["bye", "goodbye", "see you", "exit"],
                "answer": "Goodbye! Have a nice day."
            }
        ]
        self.fallback = "I'm sorry, I didn't understand that."

    def get_response(self, user_input):
        """
        Return (answer, confidence) for the given input.
        """
        best_score = 0
        best_answer = self.fallback
        for qa in self.qa_pairs:
            for variant in qa["variants"]:
                score = fuzz.ratio(user_input.lower(), variant.lower())
                if score > best_score:
                    best_score = score
                    best_answer = qa["answer"]
        if best_score >= self.threshold:
            return best_answer, best_score
        else:
            return self.fallback, 0

# Module‑compatible handle function (accepts state, returns response and new state)
def handle(text: str, state: dict) -> (str, dict):
    bot = RuleBot()
    response, _ = bot.get_response(text)
    return response, {}   # never claims the conversation