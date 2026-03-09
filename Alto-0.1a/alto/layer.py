import time
from handler import process_message as pipeline_process

# ========== HARDCODED STREAMING CONFIGURATION ==========
STREAM_BY_CHAR = True          # True = character-by-character, False = word-by-word
STREAM_DELAY = 0.001           # Delay in seconds between chunks
# ========================================================

class AltoLayer:
    """
    Orchestrates the conversation flow by calling the handler pipeline
    and streaming the final response.
    """
    def process_message(self, user_message):
        """
        Generator that yields chunks of the final response.
        """
        final_response = pipeline_process(user_message)

        if STREAM_BY_CHAR:
            for char in final_response:
                yield char
                time.sleep(STREAM_DELAY)
        else:
            words = final_response.split()
            for i, word in enumerate(words):
                if i > 0:
                    yield ' ' + word
                else:
                    yield word
                time.sleep(STREAM_DELAY)

# Create a singleton instance for easy import
alto_layer = AltoLayer()
process_message = alto_layer.process_message