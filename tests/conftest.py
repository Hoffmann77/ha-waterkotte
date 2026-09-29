"""Fixtures for the Waterkotte Heatpump tests."""
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag

SERIAL = "WE15123456"
HOST = "192.168.1.50"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in all tests."""
    yield


def device_info_values(serial: str | None = SERIAL) -> dict:
    """Values of the device information tags - as returned by WaterkotteClient.async_read_values()"""
    values = {
        WKHPTag.VERSION_BIOS: "0405",
        WKHPTag.VERSION_CONTROLLER: "0110",
        WKHPTag.INFO_ID: "Ai1+ 5007.3",
        WKHPTag.INFO_SERIES: "Ai1+",
        WKHPTag.INFO_SERIAL: serial,
    }
    return {tag: {"value": value, "status": "S_OK"} for tag, value in values.items()}


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Mock the WaterkotteClient that is used by the config flow."""
    with patch(
        "custom_components.waterkotte_heatpump.config_flow.WaterkotteClient", autospec=True
    ) as client_class:
        client = client_class.return_value
        client.login = AsyncMock()
        client.async_read_values = AsyncMock(return_value=device_info_values())
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent the setup of created config entries (no heat pump available in the tests)."""
    with (
        patch("custom_components.waterkotte_heatpump.async_setup_entry", return_value=True) as setup_entry,
        patch("custom_components.waterkotte_heatpump.async_unload_entry", return_value=True),
    ):
        yield setup_entry
