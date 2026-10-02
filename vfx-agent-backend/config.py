import os
from pathlib import Path
from dotenv import load_dotenv

# Load the repository-level environment file.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def optional_env(name: str) -> str | None:
    """Return a configured value or None for an unset or empty variable."""
    return os.getenv(name) or None


def csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Read a comma-separated environment variable without empty entries."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


# OpenAI-compatible model configuration.
MAIN_AGENT_MODEL = os.getenv("OPENAI_MAIN_AGENT_MODEL", "gpt-5-mini")
CODE_AGENT_MODEL = os.getenv("OPENAI_CODE_AGENT_MODEL", "gpt-5-nano")
REFERENCE_ANALYZER_MODEL = os.getenv(
    "OPENAI_REFERENCE_ANALYZER_MODEL",
    CODE_AGENT_MODEL,
)
API_KEY = os.getenv("OPENAI_API_KEY")
API_ENDPOINT = optional_env("OPENAI_API_BASE")
MAX_REFERENCE_EVIDENCE_CHARS = int(os.getenv("MAX_REFERENCE_EVIDENCE_CHARS", "8000"))
REFERENCE_ANALYZER_CONCURRENCY = int(os.getenv("REFERENCE_ANALYZER_CONCURRENCY", "3"))

# Agent retry policy.
MAX_OUTER_RETRIES = 2

# LangGraph checkpoints and run events.
CHECKPOINT_DB = "checkpoints/langgraph.db"
RUN_DB = "checkpoints/runs.db"

# Runtime data directories.
POSE_DATA_DIR = str(Path(__file__).resolve().parent / "data")
CHAT_DATA_DIR = str(Path(__file__).resolve().parent / "chat_data")

# Local server defaults. Override CORS_ORIGINS with a comma-separated list.
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5800"))
CORS_ORIGINS = csv_env(
    "CORS_ORIGINS",
    ("http://localhost:5200", "http://127.0.0.1:5200"),
)

if __name__ == '__main__':
    print(f"MAIN_AGENT_MODEL={MAIN_AGENT_MODEL}")
    print(f"CODE_AGENT_MODEL={CODE_AGENT_MODEL}")
    print(f"API_ENDPOINT={API_ENDPOINT}")
