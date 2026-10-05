"""Tests for the read-only copies of the entities and for the read-only mode."""
from unittest.mock import MagicMock

import pytest
from homeassistant.const import ATTR_ICON, ATTR_UNIT_OF_MEASUREMENT, CONF_HOST, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump.const import (
    CONF_ADD_READONLY_COPIES,
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


async def test_readonly_copies(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the switches, numbers and selects have read-only copies (with the name and icon of the original)."""
    await _setup(hass, mock_bridge, {CONF_ADD_READONLY_COPIES: True})

    switch = hass.states.get(_entity_id(hass, "binary_sensor", "HOLIDAY_ENABLED_READONLY"))
    assert switch.entity_id.endswith("_holiday_read_only")
    assert switch.state == "off"
    assert switch.attributes[ATTR_ICON] == "mdi:calendar-blank"

    number = hass.states.get(_entity_id(hass, "sensor", "TEMPERATURE_HEATING_ADJUST_READONLY"))
    assert number.entity_id.endswith("_temperature_adjustment_heating_read_only")
    assert number.state == "1.5"
    assert number.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTemperature.KELVIN

    select = hass.states.get(_entity_id(hass, "sensor", "ENABLE_HEATING_READONLY"))
    # the translated name of the option
    assert select.state == "Auto"
    assert select.attributes[ATTR_ICON] == "mdi:radiator"

    # the copies use the tags of the original entities - and can't change them
    assert _entity_id(hass, "switch", "HOLIDAY_ENABLED_READONLY") is None


async def test_readonly_copies_removed(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the read-only copies are removed, when the option is disabled."""
    entry = await _setup(hass, mock_bridge, {CONF_ADD_READONLY_COPIES: True})
    assert _entity_id(hass, "sensor", "ENABLE_HEATING_READONLY") is not None

    hass.config_entries.async_update_entry(entry, options={CONF_ADD_READONLY_COPIES: False})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert _entity_id(hass, "sensor", "ENABLE_HEATING_READONLY") is None
    assert _entity_id(hass, "binary_sensor", "HOLIDAY_ENABLED_READONLY") is None
    assert _entity_id(hass, "select", "ENABLE_HEATING") is not None


async def test_no_readonly_copies_by_default(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    await _setup(hass, mock_bridge, {})
    assert _entity_id(hass, "sensor", "ENABLE_HEATING_READONLY") is None


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


async def test_readonly_copies_follow_original(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that a copy is enabled by default, when its original entity is enabled (and vice versa)."""
    entry = await _setup(hass, mock_bridge, {})
    registry = er.async_get(hass)
    # enable an entity, that is disabled by default - and disable one, that is enabled by default
    registry.async_update_entity(_entity_id(hass, "select", "ENABLE_MIXING2"), disabled_by=None)
    registry.async_update_entity(_entity_id(hass, "select", "ENABLE_HEATING"),
                                 disabled_by=er.RegistryEntryDisabler.USER)

    hass.config_entries.async_update_entry(entry, options={CONF_ADD_READONLY_COPIES: True})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert not registry.async_get(_entity_id(hass, "sensor", "ENABLE_MIXING2_READONLY")).disabled
    assert registry.async_get(_entity_id(hass, "sensor", "ENABLE_HEATING_READONLY")).disabled
    # not changed by the user: like the original
    assert not registry.async_get(_entity_id(hass, "sensor", "ENABLE_WARMWATER_READONLY")).disabled
    assert registry.async_get(_entity_id(hass, "sensor", "ENABLE_PV_READONLY")).disabled
