from app.services.mock_bank import mock_bank_service


def pytest_runtest_setup() -> None:
    mock_bank_service.reset()
