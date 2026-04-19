import argparse
import json
import sys
from backend.cmd_router import COMMANDS   # changed from train to backend
from backend.model import close_all_models   # changed from train to backend

def interactive_loop():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line or line == "exit":
            break
        try:
            req = json.loads(line)
            cmd = req.get("command")
            kwargs = req.get("args", {})
            if cmd not in COMMANDS:
                result = {"error": f"Unknown command: {cmd}"}
            else:
                result = COMMANDS[cmd](**kwargs)
        except FileNotFoundError as e:
            result = {"error": str(e)}
        except Exception as e:
            result = {"error": str(e)}
        print(json.dumps(result), flush=True)
    close_all_models()

def main():
    if "--interactive" in sys.argv:
        interactive_loop()
        return

    parser = argparse.ArgumentParser(description="Alto Trainer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Model commands
    p = subparsers.add_parser("list-models")
    p.set_defaults(func=COMMANDS["list-models"])

    p = subparsers.add_parser("create-model")
    p.add_argument("name")
    p.add_argument("--description", default="")
    p.add_argument("--author", default="")
    p.add_argument("--version", default="1.0.0")
    p.set_defaults(func=COMMANDS["create-model"])

    p = subparsers.add_parser("get-model")
    p.add_argument("name")
    p.set_defaults(func=COMMANDS["get-model"])

    p = subparsers.add_parser("update-model")
    p.add_argument("name")
    p.add_argument("--description")
    p.add_argument("--author")
    p.add_argument("--version")
    p.set_defaults(func=COMMANDS["update-model"])

    p = subparsers.add_parser("delete-model")
    p.add_argument("name")
    p.set_defaults(func=COMMANDS["delete-model"])

    p = subparsers.add_parser("rename-model")
    p.add_argument("name")
    p.add_argument("new_name")
    p.set_defaults(func=COMMANDS["rename-model"])

    # Group commands
    p = subparsers.add_parser("add-group")
    p.add_argument("name")
    p.add_argument("--data", required=True)
    p.set_defaults(func=COMMANDS["add-group"])

    p = subparsers.add_parser("update-group")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--data", required=True)
    p.set_defaults(func=COMMANDS["update-group"])

    p = subparsers.add_parser("delete-group")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.set_defaults(func=COMMANDS["delete-group"])

    # Follow‑up tree commands
    p = subparsers.add_parser("get-followups")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.set_defaults(func=COMMANDS["get-followups"])

    p = subparsers.add_parser("save-followups")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--data", required=True)
    p.set_defaults(func=COMMANDS["save-followups"])

    p = subparsers.add_parser("get-node-details")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("node_id", type=int)
    p.set_defaults(func=COMMANDS["get-node-details"])

    # Section commands removed

    # Topic commands
    p = subparsers.add_parser("get-topics")
    p.add_argument("name")
    p.set_defaults(func=COMMANDS["get-topics"])

    p = subparsers.add_parser("add-topic")
    p.add_argument("name")
    p.add_argument("--topic", required=True)
    p.set_defaults(func=COMMANDS["add-topic"])

    p = subparsers.add_parser("rename-topic")
    p.add_argument("name")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.set_defaults(func=COMMANDS["rename-topic"])

    p = subparsers.add_parser("delete-topic")
    p.add_argument("name")
    p.add_argument("--topic", required=True)
    p.add_argument("--action", choices=["reassign", "delete_groups"], default="reassign")
    p.add_argument("--target")
    p.set_defaults(func=COMMANDS["delete-topic"])

    # Utility commands
    p = subparsers.add_parser("get-model-db-path")
    p.add_argument("name")
    p.set_defaults(func=COMMANDS["get-model-db-path"])

    p = subparsers.add_parser("import-db")
    p.add_argument("name", nargs="?")
    p.add_argument("--file", required=True)
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=COMMANDS["import-db"])

    # Lightweight group commands
    p = subparsers.add_parser("get-group-summaries")
    p.add_argument("name")
    p.set_defaults(func=COMMANDS["get-group-summaries"])

    p = subparsers.add_parser("get-group-full")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.set_defaults(func=COMMANDS["get-group-full"])

    args = parser.parse_args()
    kwargs = {k: v for k, v in vars(args).items() if k not in ('func', 'command') and v is not None}
    result = args.func(**kwargs)
    print(json.dumps(result))

if __name__ == "__main__":
    main()