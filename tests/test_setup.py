"""Tests for the setup (and the service actions) of the Waterkotte Heatpump integration."""
from datetime import datetime, time
from unittest.mock import MagicMock

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import ATTR_CONFIG_ENTRY_ID, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump import WKHPDataUpdateCoordinator
from custom_components.waterkotte_heatpump.const import (
    CONF_SERIAL,
    CONF_SYSTEMTYPE,
    DOMAIN,
    SERVICE_GET_ENERGY_BALANCE,
    SERVICE_SET_HOLIDAY,
)
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import (
    InvalidPasswordException,
    TooManyUsersException,
)
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .conftest import HOST, SERIAL


def _add_entry(hass: HomeAssistant, serial: str = SERIAL) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=2, unique_id=serial, title=f"Waterkotte ({serial})",
        data={CONF_HOST: HOST, CONF_SERIAL: serial, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    return entry


def _reauth_flows(hass: HomeAssistant) -> list:
    return [flow for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
            if flow["context"]["source"] == SOURCE_REAUTH]


async def test_setup_and_unload(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the coordinator is stored as runtime_data - and that the services stay registered."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, WKHPDataUpdateCoordinator)
    assert hass.services.has_service(DOMAIN, SERVICE_SET_HOLIDAY)
    # the entities registered their tags - so the data of the enabled entities is requested
    assert mock_bridge.async_get_data.await_count >= 1
    assert len(mock_bridge.tags) > 0

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    mock_bridge.logout.assert_awaited_once()
    assert hass.services.has_service(DOMAIN, SERVICE_SET_HOLIDAY)


async def test_entity_states(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test the states of entities, that need a conversion of the value of the heat pump."""
    mock_bridge.async_get_data.return_value = {
        WKHPTag.HOLIDAY_START_TIME: {"value": datetime(2026, 12, 20, 8, 0), "status": "S_OK"},
        WKHPTag.SCHEDULE_WATER_DISINFECTION_START_TIME: {"value": time(3, 30), "status": "S_OK"},
    }
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)

    def state(platform: str, key: str) -> str:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}".lower())
        return hass.states.get(entity_id).state

    # the heat pump provides the local time
    assert state("sensor", "HOLIDAY_START_TIME") == dt_util.as_utc(
        datetime(2026, 12, 20, 8, 0, tzinfo=dt_util.get_default_time_zone())).isoformat()
    assert state("number", "TEMPERATURE_HEATING_SETPOINT") == "unknown"

    # the disinfection start time is disabled by default
    registry.async_update_entity(
        registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_schedule_water_disinfection_start_time".lower()),
        disabled_by=None,
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert state("sensor", "SCHEDULE_WATER_DISINFECTION_START_TIME") == "03:30"


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientError("offline"), TooManyUsersException("TOO_MANY_USERS"), TimeoutError()],
)
async def test_setup_not_ready(hass: HomeAssistant, mock_bridge: MagicMock, side_effect: Exception) -> None:
    """Test that the setup is retried later, when the heat pump is not available."""
    mock_bridge.async_check_login.side_effect = side_effect
    entry = _add_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_no_data(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the setup is retried later, when no data could be read (e.g. the EasyCon interface is offline)."""
    mock_bridge.async_read_values.return_value = {}
    entry = _add_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_invalid_auth(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that invalid credentials start the reauth flow."""
    mock_bridge.async_check_login.side_effect = InvalidPasswordException("INVALID_PWD")
    entry = _add_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


async def test_update_invalid_auth(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that invalid credentials during a regular update start the reauth flow."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mock_bridge.async_get_data.side_effect = InvalidPasswordException("INVALID_PWD")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert len(_reauth_flows(hass)) == 1


async def test_service_single_heat_pump(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the config entry is optional, when only one heat pump is loaded."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mock_bridge.async_read_values.return_value = {
        WKHPTag.COP_HEATPUMP_YEAR: {"value": 4.2, "status": "S_OK"},
    }
    response = await hass.services.async_call(DOMAIN, SERVICE_GET_ENERGY_BALANCE, {}, blocking=True,
                                              return_response=True)
    assert response["cop"] == 4.2
    assert response["pool"] == "unknown"

    await hass.services.async_call(
        DOMAIN, SERVICE_SET_HOLIDAY, {"start": "2026-12-20 08:00:00", "end": "2027-01-06 18:00:00"}, blocking=True
    )
    mock_bridge.async_write_value.assert_any_await(WKHPTag.HOLIDAY_START_TIME, datetime(2026, 12, 20, 8, 0))
    mock_bridge.async_write_value.assert_any_await(WKHPTag.HOLIDAY_END_TIME, datetime(2027, 1, 6, 18, 0))


async def test_service_config_entry(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the config entry is required, when more (or less) than one heat pump is loaded."""
    first = _add_entry(hass)
    second = _add_entry(hass, serial="WE15999999")
    # setting up the integration loads all config entries
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.LOADED

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, SERVICE_GET_ENERGY_BALANCE, {}, blocking=True, return_response=True)
    assert err.value.translation_key == "config_entry_required"

    response = await hass.services.async_call(
        DOMAIN, SERVICE_GET_ENERGY_BALANCE, {ATTR_CONFIG_ENTRY_ID: second.entry_id}, blocking=True,
        return_response=True,
    )
    assert "cop" in response

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, SERVICE_GET_ENERGY_BALANCE, {ATTR_CONFIG_ENTRY_ID: "unknown"},
                                       blocking=True, return_response=True)
    assert err.value.translation_key == "config_entry_not_found"

    assert await hass.config_entries.async_unload(second.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, SERVICE_GET_ENERGY_BALANCE, {ATTR_CONFIG_ENTRY_ID: second.entry_id},
                                       blocking=True, return_response=True)
    assert err.value.translation_key == "config_entry_not_loaded"
