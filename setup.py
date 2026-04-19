#!/usr/bin/env python3
import os
import sys
import subprocess
import platform
import shutil

# Minimum Python version required
MIN_PYTHON = (3, 11)

def prompt_yes_no(prompt, default=False):
    """Ask a yes/no question; return True for yes, False for no."""
    if default:
        prompt_text = f"{prompt} [Y/n]: "
    else:
        prompt_text = f"{prompt} [y/N]: "
    while True:
        answer = input(prompt_text).strip().lower()
        if not answer:
            return default
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        print("Please answer yes or no.")

def check_python_version():
    """Check Python version; if insufficient, ask to continue."""
    if sys.version_info < MIN_PYTHON:
        print(f"❌ Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or higher is required.")
        print(f"   You are running Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        if not prompt_yes_no("Do you want to continue anyway? (This may cause errors)", default=False):
            sys.exit(1)
        print("⚠️  Continuing with unsupported Python version.")
    else:
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} found.")

def check_virtual_env():
    """Check for virtual environment; recommend and ask to continue."""
    in_venv = (hasattr(sys, 'real_prefix') or
               (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) or
               os.environ.get('VIRTUAL_ENV') is not None)
    if in_venv:
        print("✅ Running inside a virtual environment.")
    else:
        print("⚠️  It is recommended to use a Python virtual environment to avoid conflicts.")
        print("   You can create one with: python -m venv venv")
        print("   Then activate it with: venv\\Scripts\\activate (Windows) or source venv/bin/activate (Linux/macOS)")
        if not prompt_yes_no("Do you want to continue without a virtual environment?", default=False):
            sys.exit(1)

def check_pip():
    """Check for pip; if missing, ask to continue."""
    if not shutil.which("pip"):
        print("❌ pip not found.")
        print("   pip is required to install Python dependencies.")
        if not prompt_yes_no("Do you want to continue anyway? (Python dependencies will not be installed)", default=False):
            sys.exit(1)
        print("⚠️  Skipping Python dependency installation.")
        return False
    print("✅ pip found.")
    return True

def run_command(cmd, cwd=None):
    """Run a shell command and exit on failure."""
    print(f"Running: {cmd}")
    try:
        subprocess.check_call(cmd, shell=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed with exit code {e.returncode}")
        sys.exit(1)

def check_node_js():
    """Check if Node.js and npm are available; if missing, ask to continue."""
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    if node_path and npm_path:
        print("✅ Node.js and npm found.")
        return True
    else:
        print("❌ Node.js or npm not found.")
        print("   Node.js is required to set up the Electron client.")
        if not prompt_yes_no("Do you want to continue without setting up the client?", default=False):
            sys.exit(1)
        print("⚠️  Skipping client setup.")
        return False

def install_python_deps():
    """Install Python dependencies from requirements.txt."""
    if not os.path.exists("requirements.txt"):
        print("⚠️ requirements.txt not found. Skipping Python dependency installation.")
        return
    print("\nInstalling Python dependencies from requirements.txt...")
    run_command("pip install -r requirements.txt")

def setup_client():
    """Set up the Electron client by running npm install."""
    print("\nSetting up Electron client...")
    client_dir = "Client"
    if not os.path.isdir(client_dir):
        print(f"⚠️ Client directory '{client_dir}' not found. Skipping client setup.")
        return
    if not check_node_js():
        return
    print("Running npm install in Client folder...")
    run_command("npm install", cwd=client_dir)

def print_start_instructions():
    """Display how to run the application."""
    print("\n=== Setup complete ===")
    print("To run the application:")
    print("1. Start the Python backend:")
    print("   cd Alto && python app.py")
    print("2. Start the Electron client (in a separate terminal):")
    print("   cd Client && npm start")
    print("Note: The backend must be running before the client can connect.")

def main():
    print("Alto Setup Script\n")
    check_python_version()
    check_virtual_env()
    pip_available = check_pip()
    if pip_available:
        install_python_deps()
    setup_client()
    print_start_instructions()

if __name__ == "__main__":
    main()