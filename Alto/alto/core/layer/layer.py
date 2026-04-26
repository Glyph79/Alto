# web/layer/layer.py
import asyncio
import os
import time
import glob
import statistics
from datetime import datetime
from collections import deque
import psutil

from alto.core.dispatcher import Dispatcher
from alto.session import get_session, save_session, validate_session_state, _lock, _RELOAD_MARKER_PATH, clear_benchmark_result, get_benchmark_result, _hot, SESSIONS_DIR
from alto.config import config, CONFIG_PATH, load_config, save_config
from alto.core.benchmark import BenchmarkRunner
from alto.core.model_info import get_model_info, list_models
from alto.core.plugins import PluginManager

STREAM_BY_CHAR = config.getboolean('stream', 'by_char')
STREAM_DELAY = config.getfloat('stream', 'delay')
ADMIN_PASSWORD = config.get('admin', 'password', fallback='7134')

# Request tracking
REQUEST_LATENCIES = deque(maxlen=60)  # last 60 request durations in seconds
SERVER_START_TIME = time.time()

class AltoLayer:
    def __init__(self):
        self.dispatcher = None
        self.plugin_manager = PluginManager()

    def _get_dispatcher(self):
        if self.dispatcher is None:
            model_name = config.get('DEFAULT', 'default_model')
            self.dispatcher = Dispatcher(model_name)
        return self.dispatcher

    def _is_admin_authenticated(self, state: dict) -> bool:
        return state.get("admin_authenticated", False)

    def _set_admin_authenticated(self, state: dict):
        state["admin_authenticated"] = True
        return state

    async def _handle_command(self, cmd: str, session_id: str, user_id: int, state: dict) -> str:
        parts = cmd.strip().split()
        if not parts:
            return "Unknown command."

        command = parts[0].lower()
        
        if command == '/help':
            return self._get_help_text()
        
        # Special case: /auth <password> to authenticate
        if command == '/auth':
            if len(parts) != 2:
                return "Usage: /auth <password>"
            password = parts[1]
            if password != ADMIN_PASSWORD:
                return "Incorrect admin password."
            state = self._set_admin_authenticated(state)
            save_session(session_id, state)
            return "Authentication successful. You can now use admin commands without password."
        
        # For all other admin commands, require authentication first
        if not self._is_admin_authenticated(state):
            return "Admin access required. Use /auth <password> first."
        
        return await self._execute_admin_command(command, parts[1:], state)

    async def _execute_admin_command(self, command: str, args: list, state: dict) -> str:
        if command == '/reload':
            if args and args[0].lower() == 'config':
                return await self._reload_config()
            else:
                return await self._reload_model()
        
        elif command == '/load' and len(args) >= 1 and args[0].lower() == 'model':
            if len(args) < 2:
                return "Usage: /load model <model_name>"
            model_name = args[1]
            return await self._load_model(model_name)
        
        elif command == '/accuracy':
            return await self._get_accuracy()
        
        elif command == '/average':
            return await self._get_average()
        
        elif command == '/status':
            return await self._get_status()
        
        elif command == '/sessions':
            return await self._get_sessions()
        
        elif command == '/plugins':
            return self._list_plugins()
        
        elif command == '/plugin' and len(args) >= 1 and args[0].lower() == 'reload':
            self.plugin_manager.reload_all()
            return "All plugins reloaded."
        
        elif command == '/rebake':
            target = args[0].lower() if args else 'all'
            if target not in ('typo', 'exact', 'all'):
                return "Usage: /rebake [typo|exact|all]"
            dispatcher = self._get_dispatcher()
            result = dispatcher.rebake_jit(target)
            return result
        
        elif command == '/list':
            if len(args) < 1:
                return "Usage: /list <subcommand> [args]\nSubcommands: info, all"
            subcommand = args[0].lower()
            if subcommand == 'info':
                model_name = args[1] if len(args) > 1 else self._get_dispatcher().model_name
                return await self._list_info(model_name)
            elif subcommand == 'all':
                return await self._list_all()
            else:
                return "Unknown list subcommand. Use: info, all"
        
        elif command == '/clear' and len(args) >= 1 and args[0].lower() == 'results':
            if len(args) < 2:
                return "Usage: /clear results <model_name>"
            model_name = args[1]
            return await self._clear_results(model_name)
        
        else:
            return "Unknown command. Type /help for available commands."

    def _get_help_text(self) -> str:
        return (
            "📖 Available commands:\n\n"
            "/help - Show this help message\n"
            "/auth <password> - Authenticate for admin commands (required once per session)\n\n"
            "MODEL COMMANDS (require authentication):\n"
            "/reload - Reload current model and repair all sessions\n"
            "/reload config - Reload configuration from disk (reloads model if ram_only_mode changed)\n"
            "/load model <model_name> - Switch to a different model\n\n"
            "PLUGIN COMMANDS (require authentication):\n"
            "/plugins - List available plugins\n"
            "/plugin reload - Force rebuild plugin index and clear cache\n\n"
            "BENCHMARK COMMANDS (require authentication):\n"
            "/benchmark - Run comprehensive benchmark on current model (streaming)\n"
            "/accuracy - Show latest benchmark results\n"
            "/average - Show only the average confidence from latest benchmark\n"
            "/clear results <model_name> - Clear benchmark results for a model\n\n"
            "SYSTEM COMMANDS (require authentication):\n"
            "/status - Show server uptime, memory, sessions, cache, request stats\n"
            "/sessions - List active hot sessions and count cold sessions\n"
            "/rebake [typo|exact|all] - Validate and repair JIT cache entries against current model\n\n"
            "INFO COMMANDS (require authentication):\n"
            "/list info [model_name] - Show model information (groups, nodes, size, mode)\n"
            "/list all - List all available models"
        )

    def _list_plugins(self) -> str:
        plugins = self.plugin_manager.list_plugins()
        if not plugins:
            return "No plugins found in resources/plugins/"
        return "Available plugins:\n" + "\n".join(f"  - {p}" for p in plugins)

    async def _reload_config(self) -> str:
        """Reload configuration from disk and reload the model if ram_only_mode changed."""
        global config
        old_ram_mode = config.getboolean('ai', 'ram_only_mode', fallback=False)
        config = load_config()
        new_ram_mode = config.getboolean('ai', 'ram_only_mode', fallback=False)
        if old_ram_mode != new_ram_mode:
            await self._reload_model()
            return "Configuration reloaded and model reloaded to apply ram_only_mode change."
        else:
            return "Configuration reloaded (no model reload needed)."

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
        save_config(config)
        return await self._reload_model()

    async def _get_accuracy(self) -> str:
        dispatcher = self._get_dispatcher()
        results = get_benchmark_result(dispatcher.model_name)
        if not results:
            return "No benchmark results found. Run /benchmark first."
        avg_conf = results.get('average_confidence', 0)
        total = results.get('total_tests', 0)
        high = results.get('high_confidence', 0)
        low = results.get('low_confidence', 0)
        model = results['model_name']
        timestamp = results['datetime']
        return (
            f"📊 Latest benchmark results ({timestamp})\n"
            f"Model: {model}\n"
            f"Total tests: {total}\n"
            f"Average confidence: {avg_conf:.1f}%\n"
            f"Confidence range: {low:.1f}% – {high:.1f}%\n"
            f"Run /benchmark to update."
        )

    async def _get_average(self) -> str:
        dispatcher = self._get_dispatcher()
        results = get_benchmark_result(dispatcher.model_name)
        if not results:
            return "No benchmark results found. Run /benchmark first."
        avg = results.get('average_confidence', 0)
        return f"Average confidence: {avg:.1f}%"

    async def _get_status(self) -> str:
        uptime = time.time() - SERVER_START_TIME
        uptime_str = f"{int(uptime//3600)}h {int((uptime%3600)//60)}m {int(uptime%60)}s"
        mem = psutil.virtual_memory()
        proc = psutil.Process(os.getpid())
        proc_mem = proc.memory_info().rss // (1024**2)  # MB
        # Active sessions
        hot_count = len(_hot)
        # Cold sessions: count JSON files in users/ and tests/ (excluding benchmark sessions)
        cold_count = 0
        for dir_name in ['users', 'tests']:
            dir_path = os.path.join(SESSIONS_DIR, dir_name)
            if os.path.exists(dir_path):
                for fname in os.listdir(dir_path):
                    if fname.endswith('.json'):
                        cold_count += 1
        # Cache stats
        cache = self._get_dispatcher().matcher.cache
        with cache._lock:
            groups_cached = len(cache._groups)
            nodes_cached = len(cache._nodes)
            fallbacks_cached = len(cache._fallbacks)
        # Request stats
        if REQUEST_LATENCIES:
            avg_latency = statistics.mean(REQUEST_LATENCIES) * 1000  # ms
            max_latency = max(REQUEST_LATENCIES) * 1000
            min_latency = min(REQUEST_LATENCIES) * 1000
            req_stats = f"Avg: {avg_latency:.1f}ms, High: {max_latency:.1f}ms, Low: {min_latency:.1f}ms"
        else:
            req_stats = "No requests yet"
        return (
            f"🖥️ System Status\n"
            f"Uptime: {uptime_str}\n"
            f"System memory: {mem.percent}% used ({mem.used//(1024**2)} MB / {mem.total//(1024**2)} MB)\n"
            f"Process memory: {proc_mem} MB\n"
            f"Sessions: {hot_count} hot, {cold_count} cold\n"
            f"Cache: {groups_cached} groups, {nodes_cached} nodes, {fallbacks_cached} fallbacks\n"
            f"Requests (last 60): {req_stats}\n"
            f"Current model: {self._get_dispatcher().model_name}\n"
            f"Threshold: {self._get_dispatcher().threshold}%"
        )

    async def _get_sessions(self) -> str:
        hot_count = len(_hot)
        lines = [f"🔥 Hot sessions ({hot_count}):"]
        for sid, (state, last_used) in _hot.items():
            last_used_str = datetime.fromtimestamp(last_used).strftime("%H:%M:%S")
            user_id = state.get("user_id", "none")
            prefix = "🔬" if sid.startswith('__benchmark__') else "👤"
            lines.append(f"  {prefix} {sid[:30]}... - last: {last_used_str} - user: {user_id}")
        # Count cold sessions
        cold_count = 0
        for dir_name in ['users', 'tests']:
            dir_path = os.path.join(SESSIONS_DIR, dir_name)
            if os.path.exists(dir_path):
                for fname in os.listdir(dir_path):
                    if fname.endswith('.json'):
                        cold_count += 1
        lines.append(f"\n❄️ Cold sessions on disk: {cold_count}")
        return "\n".join(lines)

    async def _list_info(self, model_name: str) -> str:
        info = get_model_info(model_name)
        if not info:
            return f"Model '{model_name}' not found or inaccessible."
        results = get_benchmark_result(model_name)
        latest_str = ""
        if results:
            avg = results.get('average_confidence', 0)
            dt = results['datetime'][:19].replace('T', ' ')
            latest_str = f"\nLatest benchmark: {dt} - Avg confidence {avg:.1f}%"
        # Determine mode
        ram_mode = config.getboolean('ai', 'ram_only_mode', fallback=False)
        mode_str = "RAM" if ram_mode else "Disk"
        return (
            f"📊 Model Info: {info['name']}\n"
            f"  Mode: {mode_str}\n"
            f"  Groups: {info['groups']}\n"
            f"  Follow-up nodes: {info['followup_nodes']}\n"
            f"  Average tree size: {info['avg_tree_size']}\n"
            f"  Topics: {info['topics']}\n"
            f"  File size: {info['file_size_mb']} MB ({info['file_size_bytes']} bytes){latest_str}"
        )

    async def _list_all(self) -> str:
        models = list_models()
        if not models:
            return "No models found in resources/models/"
        lines = ["📁 Available models:"]
        for m in models:
            info = get_model_info(m)
            if info:
                lines.append(f"  {m} - {info['groups']} groups, {info['followup_nodes']} nodes, {info['file_size_mb']} MB")
            else:
                lines.append(f"  {m} - (unable to read details)")
        return "\n".join(lines)

    async def _clear_results(self, model_name: str) -> str:
        if clear_benchmark_result(model_name):
            return f"Benchmark results for model '{model_name}' cleared."
        else:
            return f"No benchmark session found for model '{model_name}'. Nothing to clear."

    async def process_message(self, user_message: str, session_id: str = "default", user_id: int = None):
        start_time = time.time()
        try:
            # Benchmark command (streaming)
            if user_message.startswith('/benchmark'):
                state = get_session(session_id, user_id)
                if not self._is_admin_authenticated(state):
                    response = "Admin access required. Use /auth <password> first."
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
                state = get_session(session_id, user_id)
                response = await self._handle_command(user_message, session_id, user_id, state)
                if self._is_admin_authenticated(state):
                    save_session(session_id, state)
                async for chunk in self._stream_string(response):
                    yield chunk
                return

            # Normal message processing
            state = get_session(session_id, user_id)
            # First try plugins
            response, new_state = self.plugin_manager.handle(user_message, state)
            if response is not None:
                save_session(session_id, new_state)
                async for chunk in self._stream_string(response):
                    yield chunk
                return

            # Fallback to AI model
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
        finally:
            # Track request latency
            duration = time.time() - start_time
            REQUEST_LATENCIES.append(duration)

    async def _stream_string(self, text: str):
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