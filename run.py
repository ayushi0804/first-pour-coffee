#!/usr/bin/env python3
"""
One command to run First Pour on your own machine:

    python run.py

What it does the first time:
  1. makes a virtual environment (.venv) and installs the requirements, if Flask isn't available
  2. creates .env with a fresh secret key and a random admin password
  3. starts the store at http://127.0.0.1:5000  (the database is created and filled on first start)

Options:
    --demo    add sample orders so the admin screens aren't empty
    --reset   delete the database and start from the sample catalog again

Set PORT (default 5000) or HOST (default 127.0.0.1) in the environment to change where it listens.
"""
import os
import re
import secrets
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def venv_python():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def has_flask():
    try:
        import flask  # noqa: F401
        return True
    except ImportError:
        return False


def bootstrap_env(env_path=None, example_path=None):
    """
    Creates .env from .env.example with a new secret key and admin password.
    Returns the new admin login to show once, or None if .env already existed.
    """
    env_path = Path(env_path or ROOT / ".env")
    example_path = Path(example_path or ROOT / ".env.example")
    if env_path.exists():
        return None
    text = example_path.read_text(encoding="utf-8")
    password = secrets.token_urlsafe(9)
    text = re.sub(r"(?m)^SECRET_KEY=.*$", "SECRET_KEY=" + secrets.token_hex(24), text)
    text = re.sub(r"(?m)^ADMIN_PASSWORD=.*$", "ADMIN_PASSWORD=" + password, text)
    env_path.write_text(text, encoding="utf-8")
    return {"user": "admin", "password": password}


def install_requirements():
    if not VENV.exists():
        print("Creating a virtual environment in .venv ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    print("Installing requirements (first run only) ...")
    subprocess.check_call([str(venv_python()), "-m", "pip", "install", "--quiet", "-r", str(ROOT / "requirements.txt")])


def main(argv):
    if not has_flask():
        if os.environ.get("FIRST_POUR_BOOTSTRAPPED"):
            sys.exit("Flask is still missing after installing the requirements. Run: pip install -r requirements.txt")
        try:
            install_requirements()
        except (subprocess.CalledProcessError, OSError) as exc:
            sys.exit(f"Could not install the requirements ({exc}).\n"
                     "Check your internet connection, or run: pip install -r requirements.txt")
        env = dict(os.environ, FIRST_POUR_BOOTSTRAPPED="1")
        sys.exit(subprocess.call([str(venv_python()), str(Path(__file__).resolve()), *argv], env=env))

    os.chdir(ROOT)
    created = bootstrap_env()

    if "--reset" in argv:
        (ROOT / "instance" / "store.db").unlink(missing_ok=True)
        print("Database reset.")

    # importing the app creates and fills the database if it is missing
    import app as store

    if "--demo" in argv:
        from tools import demo_data
        demo_data.run(store.app)

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    mode = "Razorpay TEST mode" if store.app.config["GATEWAY"].name == "razorpay" else "local payment simulator (no Razorpay keys set)"
    print()
    print("  First Pour Coffee Co.")
    print(f"  Store:    http://{host}:{port}/")
    print(f"  Admin:    http://{host}:{port}/admin")
    print(f"  Payments: {mode}")
    if created:
        print(f"  Admin login (created now, saved in .env):  {created['user']} / {created['password']}")
    print("  Press Ctrl+C to stop.\n")
    store.app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main(sys.argv[1:])
