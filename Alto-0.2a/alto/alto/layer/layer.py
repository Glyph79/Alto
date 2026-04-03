import asyncio
from alto.core.handler import process_message as pipeline_process
from alto.session.session import get_session, save_session
from alto.config import config

STREAM_BY_CHAR = config.getboolean('stream', 'by_char')
STREAM_DELAY = config.getfloat('stream', 'delay')

class AltoLayer:
    async def process_message(self, user_message: str, session_id: str = "default", user_id: int = None):
        state = get_session(session_id, user_id)
        loop = asyncio.get_event_loop()
        final_response, new_state = await loop.run_in_executor(
            None, pipeline_process, user_message, state
        )
        save_session(session_id, new_state)

        if STREAM_BY_CHAR:
            for char in final_response:
                yield char
                await asyncio.sleep(STREAM_DELAY)
                await asyncio.sleep(0)          # force event loop to flush socket
        else:
            words = final_response.split()
            for i, word in enumerate(words):
                if i > 0:
                    yield ' ' + word
                else:
                    yield word
                await asyncio.sleep(STREAM_DELAY)
                await asyncio.sleep(0)

alto_layer = AltoLayer()
process_message = alto_layer.process_message