"""Tests for the setup (and the config entry migration) of the Waterkotte Heatpump integration."""
import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump import async_migrate_entry
from custom_components.waterkotte_heatpump.const import CONF_SERIAL, DOMAIN
from .conftest import HOST, SERIAL


async def test_migrate_1_2_sets_unique_id(hass: HomeAssistant) -> None:
    """Test that the migration uses the serial number as unique_id of the config entry."""
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, data={CONF_HOST: HOST, CONF_SERIAL: SERIAL})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.unique_id == SERIAL
    assert (entry.version, entry.minor_version) == (1, 3)


@pytest.mark.parametrize(
    "serial",
    [
        "0123456789abcdef0123456789abcdef",  # random UUID of older versions (no serial provided by the heat pump)
        "None",
        None,
    ],
)
async def test_migrate_1_2_without_serial(hass: HomeAssistant, serial: str | None) -> None:
    """Test that entries without a real serial number don't get a unique_id."""
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, data={CONF_HOST: HOST, CONF_SERIAL: serial})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.unique_id is None
    assert (entry.version, entry.minor_version) == (1, 3)


async def test_migrate_1_2_duplicate_serial(hass: HomeAssistant) -> None:
    """Test that a second entry of the same heat pump does not get the same unique_id."""
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_HOST: HOST, CONF_SERIAL: SERIAL}).add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, data={CONF_HOST: HOST, CONF_SERIAL: SERIAL})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.unique_id is None
