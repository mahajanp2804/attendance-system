"""The app must refuse to start outside DEBUG with a weak or placeholder SECRET_KEY."""

import os
import secrets
import subprocess
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_loads(tmp_path, secret_key, debug):
    """Import config in a fresh interpreter (it runs its checks at import time)."""
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DEBUG")}
    if secret_key is not None:
        env["SECRET_KEY"] = secret_key
    env["DEBUG"] = debug
    env["PYTHONPATH"] = BACKEND_DIR
    result = subprocess.run([sys.executable, "-c", "import config"],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    return result.returncode == 0


@pytest.mark.parametrize("key", [
    None,                                                     # built-in default
    "change-this-in-production-use-openssl-rand-hex-32",      # old docker-compose value
    "change-this-to-a-long-random-string-in-production",      # .env.example value
    "abc123",                                                 # too short
])
def test_refuses_weak_keys_in_production(tmp_path, key):
    assert not config_loads(tmp_path, key, "false")


def test_accepts_a_strong_key(tmp_path):
    assert config_loads(tmp_path, secrets.token_hex(32), "false")


def test_allows_the_default_key_in_debug(tmp_path):
    assert config_loads(tmp_path, None, "true")
