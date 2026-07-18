from app.services.audit_log import audit_log_service
from app.services.checkpoint_store import checkpoint_store
from app.services.mock_bank import mock_bank_service


def pytest_runtest_setup() -> None:
    mock_bank_service.reset()
    audit_log_service.reset()
    checkpoint_store.reset()
