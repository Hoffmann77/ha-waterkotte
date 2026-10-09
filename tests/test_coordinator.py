"""Tests for the regular updates of the coordinator."""
import asyncio
from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump import coordinator as coordinator_module
from custom_components.waterkotte_heatpump.const import CONF_SERIAL, CONF_SYSTEMTYPE, DOMAIN
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .conftest import HOST, SERIAL

OUTSIDE = {WKHPTag.TEMPERATURE_OUTSIDE: {"value": 7.5, "status": "S_OK"}}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_temperature_outside".lower())
    return hass.states.get(entity_id).state


async def test_lost_value_read_again(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that a value, that is missing in an update, is read again - and only then is unavailable."""
    mock_bridge.async_get_data.return_value = OUTSIDE
    entry = await _setup(hass)
    assert _state(hass) == "7.5"

    # the value is missing in the update (e.g. a failed request) - but can be read again
    mock_bridge.async_get_data.return_value = {}
    mock_bridge.async_read_values.reset_mock()
    mock_bridge.async_read_values.return_value = OUTSIDE
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass) == "7.5"
    mock_bridge.async_read_values.assert_awaited_once()
    assert mock_bridge.async_read_values.await_args.args[0] == [WKHPTag.TEMPERATURE_OUTSIDE]

    # the value can't be read again either: unavailable
    mock_bridge.async_read_values.return_value = {
        WKHPTag.TEMPERATURE_OUTSIDE: {"value": None, "status": "E_NOTFOUND"}}
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass) == "unavailable"

    # a value, that wasn't available before, is not read again in every update
    mock_bridge.async_read_values.reset_mock()
    await entry.runtime_data.async_refresh()
    mock_bridge.async_read_values.assert_not_awaited()


async def test_requests_one_at_a_time(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that a read (e.g. of a service action) waits, while an update is running."""
    mock_bridge.async_get_data.return_value = OUTSIDE
    entry = await _setup(hass)
    coordinator = entry.runtime_data

    release = asyncio.Event()

    async def slow_update():
        await release.wait()
        return OUTSIDE

    mock_bridge.async_get_data.side_effect = slow_update
    mock_bridge.async_read_values.reset_mock()
    update = hass.async_create_task(coordinator.async_refresh())
    await asyncio.sleep(0)
    read = hass.async_create_task(coordinator.async_read_values([WKHPTag.TEMPERATURE_OUTSIDE]))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # the read waits for the update
    mock_bridge.async_read_values.assert_not_awaited()

    release.set()
    await update
    await read
    mock_bridge.async_read_values.assert_awaited_once()


async def test_own_web_session(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the bridge has an own session (the login cookies must not end up in the shared session of HA)."""
    entry = await _setup(hass)
    session = coordinator_module.WaterkotteClient.call_args.kwargs["web_session"]
    assert session is not async_get_clientsession(hass)
    assert not session.closed

    # the session is detached, when the config entry is unloaded (after the logout)
    assert await hass.config_entries.async_unload(entry.entry_id)
    mock_bridge.logout.assert_awaited_once()
    assert session.closed
