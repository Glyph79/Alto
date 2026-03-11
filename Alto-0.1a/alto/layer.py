import asyncio
from handler import process_message as pipeline_process
from session import get_session, save_session

# ========== STREAMING CONFIGURATION ==========
STREAM_BY_CHAR = True          # True = character‑by‑character, False = word‑by‑word
STREAM_DELAY = 0.00025           # Delay in seconds between chunks
# =============================================

class AltoLayer:
    async def process_message(self, user_message: str, session_id: str = "default"):
        """
        Async generator that yields chunks of the response.
        Manages session state automatically.
        """
        # 1. Retrieve current state for this session
        state = get_session(session_id)

        # 2. Run the handler to get response and updated state
        #    (handler remains synchronous – run in executor to avoid blocking)
        loop = asyncio.get_event_loop()
        final_response, new_state = await loop.run_in_executor(
            None, pipeline_process, user_message, state
        )

        # 3. Save updated state
        save_session(session_id, new_state)

        # 4. Stream the response character by character
        if STREAM_BY_CHAR:
            for char in final_response:
                yield char
                await asyncio.sleep(STREAM_DELAY)
        else:
            words = final_response.split()
            for i, word in enumerate(words):
                if i > 0:
                    yield ' ' + word
                else:
                    yield word
                await asyncio.sleep(STREAM_DELAY)

# Singleton
alto_layer = AltoLayer()
process_message = alto_layer.process_message