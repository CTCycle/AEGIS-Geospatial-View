"""Reproduce the OpenCode Go gateway behaviour behind ISSUE-008.

Run from `app/` with `AEGIS_DATA_DIR=data server/.venv/Scripts/python.exe <this file>`.
The stored key is read in-process through the application's own repositories and
never printed. Each shape is sent to 8 fresh session ids (`x-opencode-session`
is the conversation id in the application); a shape that depends on the
upstream backend fails for the same sessions every time.
"""
import os
import sys
import uuid
os.environ.setdefault("AEGIS_DATA_DIR", "data")
sys.path.insert(0, os.getcwd())
from openai import OpenAI
from server.configurations import DatabaseSettings, ensure_environment_loaded
from server.configurations.database_configuration import load_database_configuration
from server.repositories.database.sqlite import SQLiteRepository  # first: avoids a circular import
from server.repositories.credential_material import CredentialEncryptionMaterialRepository
from server.repositories.credentials import CredentialRepository
from server.services.cryptography import CredentialEncryptionService

ensure_environment_loaded()
cfg = load_database_configuration()
db = SQLiteRepository(DatabaseSettings(database_path=cfg.database_path,
                                       sqlite_lock_timeout_seconds=cfg.sqlite_lock_timeout_seconds, backend=cfg.backend))
KEY = CredentialEncryptionService(material_repo=CredentialEncryptionMaterialRepository(db)).decrypt(
    CredentialRepository(db).get_active(provider="opencode-go", label="api_key").encrypted_value)
BASE, MODEL = "https://opencode.ai/zen/go/v1", "deepseek-v4.1-flash"
TOOL = {"type": "function", "function": {"name": "route_request", "description": "Route the request",
        "parameters": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}}}
MSGS = [{"role": "system", "content": "You are a router. Always call the route function."},
        {"role": "user", "content": "Show me a satellite view of Lisbon"}]
OFF = {"thinking": {"type": "disabled"}}
SHAPES = {
    "required + thinking disabled (loop before fix)": dict(tools=[TOOL], tool_choice="required", extra_body=OFF),
    "forced function object + thinking disabled": dict(tools=[TOOL], tool_choice={"type": "function", "function": {"name": "route_request"}}, extra_body=OFF),
    "required + thinking default": dict(tools=[TOOL], tool_choice="required"),
    "no tool_choice + thinking disabled (loop after fix)": dict(tools=[TOOL], extra_body=OFF),
    "auto + thinking disabled": dict(tools=[TOOL], tool_choice="auto", extra_body=OFF),
    "response_format json_object": dict(messages=[{"role": "user", "content": 'Reply with JSON {"a":1}'}], response_format={"type": "json_object"}),
}

def call(session, **kw):
    kw.setdefault("messages", MSGS)
    client = OpenAI(api_key=KEY, base_url=BASE, max_retries=0, timeout=40, default_headers={"x-opencode-session": session})
    try:
        client.chat.completions.create(model=MODEL, max_tokens=4000, **kw)
        return "."
    except Exception as exc:  # noqa: BLE001
        return "S" if "Timeout" in type(exc).__name__ else "X"

sessions = ["conv_" + uuid.uuid4().hex for _ in range(8)]
for name, kw in SHAPES.items():
    print(f"{name:55}", "".join(call(s, **kw) for s in sessions), "  (. ok, X rejected, S stalled)")
