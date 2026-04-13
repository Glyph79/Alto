# web/layer/layer.py
import asyncio
import os
import time
from alto.core.dispatcher import Dispatcher
from alto.session import get_session, save_session, validate_session_state, _lock, _RELOAD_MARKER_PATH
from alto.config import config
from alto.core.benchmark import BenchmarkRunner

STREAM_BY_CHAR = config.getboolean('stream', 'by_char')
STREAM_DELAY = config.getfloat('stream', 'delay')
ADMIN_PASSWORD = config.get('admin', 'password', fallback='7134')

class AltoLayer:
    def __init__(self):
        self.dispatcher = None

    def _get_dispatcher(self):
        if self.dispatcher is None:
            model_name = config.get('DEFAULT', 'default_model')
            self.dispatcher = Dispatcher(model_name)
        return self.dispatcher

    async def _handle_command(self, cmd: str, session_id: str, user_id: int) -> str:
        """Handle non-streaming commands."""
        parts = cmd.strip().split()
        if not parts:
            return "Unknown command."

        command = parts[0].lower()
        
        if command == '/reload':
            if len(parts) != 2:
                return "Usage: /reload <password>"
            password = parts[1]
            if password != ADMIN_PASSWORD:
                return "Incorrect admin password."
            return await self._reload_model()
        
        elif command == '/load' and len(parts) >= 3 and parts[1].lower() == 'model':
            if len(parts) < 4:
                return "Usage: /load model <model_name> <password>"
            model_name = parts[2]
            password = parts[3]
            if password != ADMIN_PASSWORD:
                return "Incorrect admin password."
            return await self._load_model(model_name)
        
        elif command == '/accuracy':
            if len(parts) != 2:
                return "Usage: /accuracy <password>"
            password = parts[1]
            if password != ADMIN_PASSWORD:
                return "Incorrect admin password."
            return await self._get_accuracy()
        
        else:
            return "Unknown command. Available: /reload <password>, /load model <name> <password>, /benchmark <password>, /accuracy <password>"

    async def _reload_model(self) -> str:
        self.dispatcher = None
        new_dispatcher = self._get_dispatcher()
        with open(_RELOAD_MARKER_PATH, 'w') as f:
            f.write(str(time.time()))
        from alto.session import _hot
        with _lock:
            for sid, (state, last_used) in list(_hot.items()):
                if not state.get("_validated_after_reload"):
                    try:
                        validated = validate_session_state(state, new_dispatcher.matcher)
                        _hot[sid] = (validated, last_used)
                    except Exception as e:
                        print(f"Error validating session {sid}: {e}")
        return "Model reloaded successfully. All sessions have been retained and validated."

    async def _load_model(self, model_name: str) -> str:
        try:
            from alto.core.adapters import get_adapter
            get_adapter(model_name)
        except Exception as e:
            return f"Model '{model_name}' not found: {e}"
        config.set('DEFAULT', 'default_model', model_name)
        from alto.config import save_config
        save_config(config)
        return await self._reload_model()

    async def _get_accuracy(self) -> str:
        dispatcher = self._get_dispatcher()
        runner = BenchmarkRunner(dispatcher)
        results = runner.get_latest_results()
        if not results:
            return "No benchmark results found. Run /benchmark first."
        accuracy = results['accuracy']
        total = results['total_tests']
        correct = results['correct']
        high = results.get('high_score', 0)
        low = results.get('low_score', 0)
        avg = results.get('average_score', 0)
        model = results['model_name']
        timestamp = results['datetime']
        return (
            f"📊 Latest benchmark results ({timestamp})\n"
            f"Model: {model}\n"
            f"Accuracy (≥70%): {accuracy:.1f}% ({correct}/{total})\n"
            f"Score distribution: High {high:.1f}% | Low {low:.1f}% | Avg {avg:.1f}%\n"
            f"Run /benchmark to update."
        )

    async def process_message(self, user_message: str, session_id: str = "default", user_id: int = None):
        # Check for benchmark command (streaming)
        if user_message.startswith('/benchmark'):
            parts = user_message.strip().split()
            if len(parts) != 2:
                response = "Usage: /benchmark <password>"
                async for chunk in self._stream_string(response):
                    yield chunk
                return
            password = parts[1]
            if password != ADMIN_PASSWORD:
                response = "Incorrect admin password."
                async for chunk in self._stream_string(response):
                    yield chunk
                return
            
            dispatcher = self._get_dispatcher()
            runner = BenchmarkRunner(dispatcher)
            try:
                for chunk in runner.run_benchmark_streaming():
                    if STREAM_BY_CHAR:
                        for char in chunk:
                            yield char
                            await asyncio.sleep(STREAM_DELAY)
                    else:
                        yield chunk
                        await asyncio.sleep(STREAM_DELAY)
            except Exception as e:
                error_msg = f"Benchmark failed: {str(e)}"
                async for chunk in self._stream_string(error_msg):
                    yield chunk
            return

        # Other commands (non-streaming)
        if user_message.startswith('/'):
            response = await self._handle_command(user_message, session_id, user_id)
            async for chunk in self._stream_string(response):
                yield chunk
            return

        # Normal message processing
        state = get_session(session_id, user_id)
        loop = asyncio.get_event_loop()
        final_response, new_state = await loop.run_in_executor(
            None, self._get_dispatcher().process, user_message, state
        )
        save_session(session_id, new_state)

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

    async def _stream_string(self, text: str):
        """Helper to stream a string character by character or word by word."""
        if STREAM_BY_CHAR:
            for char in text:
                yield char
                await asyncio.sleep(STREAM_DELAY)
        else:
            words = text.split()
            for i, word in enumerate(words):
                if i > 0:
                    yield ' ' + word
                else:
                    yield word
                await asyncio.sleep(STREAM_DELAY)

alto_layer = AltoLayer()
process_message = alto_layer.process_message