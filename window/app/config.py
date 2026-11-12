import os
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(name, default=""):
    """Window settings use a WINDOW_ prefix so they never collide with the host platform's env vars."""
    return os.environ.get("WINDOW_" + name, default)


DATA_DIR = _env("DATA_DIR", os.path.join(_HERE, "data"))
DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{DATA_DIR}/thewindow.db")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL_ANSWER = _env("MODEL_ANSWER", "gpt-5.5")
MODEL_PARSE = _env("MODEL_PARSE", "gpt-5.4-mini")
REASONING_EFFORT = _env("REASONING_EFFORT", "medium")
APP_PASSWORD = _env("APP_PASSWORD")               # only for standalone use; embedded mode relies on the host login
EMBEDDED = _env("EMBEDDED", "1") == "1"           # mounted inside crude-oil-analytics behind its password gate
ANALYST_USERS = [u.strip().lower() for u in _env("ANALYST_USERS").split(",") if u.strip()]
FRAME_ANCESTORS = _env("FRAME_ANCESTORS", "https://crude-oil-analytics.fly.dev")
MCP_TOKEN = _env("MCP_TOKEN")                     # empty = MCP connector disabled
SECRET_KEY = _env("SECRET_KEY") or os.urandom(32).hex()
BRIEF_PATH = _env("BRIEF_PATH", os.path.join(_HERE, "brief", "desk_brief.md"))
MAX_HISTORY_TURNS = int(_env("MAX_HISTORY_TURNS", "8"))
MAX_DAILY_NOTES = int(_env("MAX_DAILY_NOTES", "10"))
