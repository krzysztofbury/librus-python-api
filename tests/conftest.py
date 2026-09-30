from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--mcp-checkout",
        type=Path,
        help="Consumer adapter checkout for opt-in offline integration tests",
    )


@pytest.fixture
def mcp_checkout(pytestconfig: pytest.Config) -> Path:
    checkout: Path | None = pytestconfig.getoption("mcp_checkout")
    if checkout is None:
        raise pytest.UsageError("Integration tests require --mcp-checkout=PATH")
    checkout = checkout.resolve()
    if not (checkout / "src/native_identity.py").is_file():
        raise pytest.UsageError("The checkout must contain the native identity adapter")
    return checkout
