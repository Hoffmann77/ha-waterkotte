"""Tests for the read-only mode."""
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump.const import (
    CONF_READ_ONLY,
    CONF_SERIAL,
    CONF_SYSTEMTYPE,
    DOMAIN,
    SERVICE_SET_HOLIDAY,
)
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .conftest import HOST, SERIAL

VALUES = {
    WKHPTag.HOLIDAY_ENABLED: {"value": False, "status": "S_OK"},
    WKHPTag.TEMPERATURE_HEATING_ADJUST: {"value": 1.5, "status": "S_OK"},
    WKHPTag.ENABLE_HEATING: {"value": "auto", "status": "S_OK"},
}


async def _setup(hass: HomeAssistant, mock_bridge: MagicMock, options: dict) -> MockConfigEntry:
    mock_bridge.async_get_data.return_value = VALUES
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"}, options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}".lower())


async def test_read_only_mode(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that nothing is written to the heat pump in read-only mode."""
    # the total operating hours are not shown by the heat pump - but they are not enabled in read-only mode
    mock_bridge.async_read_value.return_value = {"value": False, "status": "S_OK"}
    await _setup(hass, mock_bridge, {CONF_READ_ONLY: True})

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call("switch", "turn_on",
                                       {"entity_id": _entity_id(hass, "switch", "HOLIDAY_ENABLED")}, blocking=True)
    assert err.value.translation_key == "read_only"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("select", "select_option",
                                       {"entity_id": _entity_id(hass, "select", "ENABLE_HEATING"), "option": "off"},
                                       blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, SERVICE_SET_HOLIDAY,
                                       {"start": "2026-12-20 08:00:00", "end": "2027-01-06 18:00:00"}, blocking=True)

    mock_bridge.async_write_value.assert_not_awaited()


async def test_operating_hours_totals_enabled(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the total operating hours are enabled during the setup (when not in read-only mode)."""
    mock_bridge.async_read_value.return_value = {"value": False, "status": "S_OK"}
    await _setup(hass, mock_bridge, {})
    mock_bridge.async_write_value.assert_awaited_with(WKHPTag.OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634, True)
