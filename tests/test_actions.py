"""Tests for the error handling of the entity actions and the service actions."""
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump.const import (
    CONF_SERIAL,
    CONF_SYSTEMTYPE,
    DOMAIN,
    SERVICE_GET_ENERGY_BALANCE,
    SERVICE_SET_HOLIDAY,
)
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import TooManyUsersException
from .conftest import HOST, SERIAL

HOLIDAY = {"start": "2026-12-20 08:00:00", "end": "2027-01-06 18:00:00"}


@pytest.fixture
async def entry(hass: HomeAssistant, mock_bridge: MagicMock) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=2, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}".lower())


async def test_write_failed(hass: HomeAssistant, mock_bridge: MagicMock, entry: MockConfigEntry) -> None:
    """Test that a failed write is raised (and not swallowed)."""
    mock_bridge.async_write_value.side_effect = TooManyUsersException("TOO_MANY_USERS")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("switch", "turn_on", {"entity_id": _entity_id(hass, "switch", "HOLIDAY_ENABLED")},
                                       blocking=True)
    assert err.value.translation_key == "write_failed"


async def test_write_not_confirmed(hass: HomeAssistant, mock_bridge: MagicMock, entry: MockConfigEntry) -> None:
    """Test that a write, that the heat pump did not confirm, is raised."""
    mock_bridge.async_write_value.side_effect = None
    mock_bridge.async_write_value.return_value = {}
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("switch", "turn_off", {"entity_id": _entity_id(hass, "switch", "HOLIDAY_ENABLED")},
                                       blocking=True)
    assert err.value.translation_key == "write_not_confirmed"


async def test_invalid_adjust_value(hass: HomeAssistant, mock_bridge: MagicMock, entry: MockConfigEntry) -> None:
    """Test that a value of an adjust number, that the heat pump does not support, is rejected."""
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": _entity_id(hass, "number", "TEMPERATURE_HEATING_ADJUST"), "value": 0.25}, blocking=True
        )
    assert err.value.translation_key == "invalid_value"
    mock_bridge.async_write_value.assert_not_awaited()


async def test_service_read_failed(hass: HomeAssistant, mock_bridge: MagicMock, entry: MockConfigEntry) -> None:
    """Test that a failed read of a response-only service is raised (and does not return a string)."""
    mock_bridge.async_read_values.side_effect = TooManyUsersException("TOO_MANY_USERS")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(DOMAIN, SERVICE_GET_ENERGY_BALANCE, {}, blocking=True, return_response=True)
    assert err.value.translation_key == "read_failed"


async def test_service_write_failed(hass: HomeAssistant, mock_bridge: MagicMock, entry: MockConfigEntry) -> None:
    """Test that a failed write of a service is returned as error response - or raised without a response."""
    mock_bridge.async_write_value.side_effect = TooManyUsersException("TOO_MANY_USERS")

    response = await hass.services.async_call(DOMAIN, SERVICE_SET_HOLIDAY, HOLIDAY, blocking=True,
                                              return_response=True)
    assert "error" in response

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, SERVICE_SET_HOLIDAY, HOLIDAY, blocking=True)
