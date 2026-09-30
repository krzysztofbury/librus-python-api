from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--mcp-checkout",
        type=Path,
        help="Consumer native-adapter checkout for opt-in offline integration tests",
    )


@pytest.fixture
def mcp_checkout(pytestconfig: pytest.Config) -> Path:
    checkout: Path | None = pytestconfig.getoption("mcp_checkout")
    if checkout is None:
        raise pytest.UsageError("Integration tests require --mcp-checkout=PATH")
    checkout = checkout.resolve()
    if not all(
        (checkout / f"src/{name}.py").is_file()
        for name in ("native_identity", "native_grades")
    ):
        raise pytest.UsageError(
            "The checkout must contain the native identity and final-grade adapters"
        )
    return checkout
