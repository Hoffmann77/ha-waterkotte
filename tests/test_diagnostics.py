"""Tests for the diagnostics of the Waterkotte Heatpump integration."""
from datetime import time
from unittest.mock import MagicMock

from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.waterkotte_heatpump.const import CONF_SERIAL, CONF_SYSTEMTYPE, DOMAIN
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .conftest import HOST, SERIAL


async def test_diagnostics(hass: HomeAssistant, hass_client: ClientSessionGenerator, mock_bridge: MagicMock) -> None:
    """Test that the diagnostics contain the values of the heat pump - but not the credentials."""
    mock_bridge.async_get_data.return_value = {
        WKHPTag.TEMPERATURE_OUTSIDE: {"value": 12.5, "status": "S_OK"},
        WKHPTag.SCHEDULE_WATER_DISINFECTION_START_TIME: {"value": time(3, 30), "status": "S_OK"},
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=2, unique_id=SERIAL, title=f"Waterkotte ({SERIAL})",
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH", CONF_USERNAME: "waterkotte",
              CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "diagnostics", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diagnostics["entry"]["data"][CONF_PASSWORD] == REDACTED
    assert diagnostics["entry"]["data"][CONF_HOST] == REDACTED
    assert diagnostics["entry"]["data"][CONF_SERIAL] == REDACTED
    assert diagnostics["entry"]["unique_id"] == REDACTED
    assert SERIAL not in str(diagnostics) and HOST not in str(diagnostics)
    assert diagnostics["data"]["TEMPERATURE_OUTSIDE"] == {"value": 12.5, "status": "S_OK"}
    assert diagnostics["data"]["SCHEDULE_WATER_DISINFECTION_START_TIME"]["value"] == "03:30:00"
    assert diagnostics["last_update_success"] is True
