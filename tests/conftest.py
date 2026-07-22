import os
import tempfile
from pathlib import Path

import pytest


# Unit and integration tests must never consume a developer's real API credential from .env.
os.environ["LLM_GROUNDED_FAQ_ENABLED"] = "false"
os.environ["AGENTIC_PLANNER_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["DEMO_AUTH_REQUIRED"] = "false"
os.environ["AUDIT_STORE"] = "memory"
os.environ["CHECKPOINT_STORE_PATH"] = str(
    Path(tempfile.gettempdir()) / f"case-itau-pytest-checkpoints-{os.getpid()}.json"
)


@pytest.fixture(autouse=True)
def reset_stateful_test_doubles():
    from app.services.checkpoint_store import checkpoint_store
    from app.services.audit_log import audit_log_service
    from app.services.mock_bank import mock_bank_service
    from app.services.trace_store import trace_store

    checkpoint_store.reset()
    audit_log_service.reset()
    mock_bank_service.reset()
    trace_store.reset()
    yield
