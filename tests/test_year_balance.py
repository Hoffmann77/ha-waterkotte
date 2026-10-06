"""Tests for the values of the energy balance of a year (the year can be changed in the web interface)."""
from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump.const import CONF_SERIAL, CONF_SYSTEMTYPE, DOMAIN
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .conftest import HOST, SERIAL


def _data(balance_year: int | None) -> dict:
    values = {
        WKHPTag.DATE_YEAR: 26,
        WKHPTag.ENERGY_CONSUMPTION_TOTAL_YEAR: 3026.7,
        WKHPTag.TEMPERATURE_OUTSIDE: 7.5,
    }
    if balance_year is not None:
        values[WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO] = balance_year
    return {tag: {"value": value, "status": "S_OK"} for tag, value in values.items()}


def _state(hass: HomeAssistant, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_{key}".lower())
    return hass.states.get(entity_id).state


async def test_other_year_selected(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the yearly values are unavailable, while the balance of an older year is selected in the web
    interface - and that the other values are not affected."""
    mock_bridge.async_get_data.return_value = _data(2026)
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # the selected year is read together with the yearly values
    assert WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO in mock_bridge.tags
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == "3026.7"

    # someone looks at the balance of 2024 in the web interface
    mock_bridge.async_get_data.return_value = _data(2024)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == STATE_UNAVAILABLE
    assert _state(hass, "TEMPERATURE_OUTSIDE") == "7.5"

    # the year can't be read: the values are shown (like before)
    mock_bridge.async_get_data.return_value = _data(None)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == "3026.7"
