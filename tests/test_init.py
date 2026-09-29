"""Tests for the setup (and the config entry migration) of the Waterkotte Heatpump integration."""
import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump import async_migrate_entry
from custom_components.waterkotte_heatpump.const import (
    CONF_ADD_SERIAL_AS_ID,
    CONF_POLLING_INTERVAL,
    CONF_SERIAL,
    CONF_SYSTEMTYPE,
    DOMAIN,
)
from .conftest import HOST, SERIAL

# random UUID, that older versions stored when the heat pump did not provide a serial number
UUID_SERIAL = "0123456789abcdef0123456789abcdef"


async def test_migrate_1_2(hass: HomeAssistant) -> None:
    """Test that the migration uses the serial number as unique_id of the config entry - and that the
    connection data (copied by the options flow of older versions) is removed from the options."""
    data = {CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH", CONF_USERNAME: "waterkotte"}
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        data=data,
        options={**data, CONF_PASSWORD: "new-password", CONF_POLLING_INTERVAL: 30},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.unique_id == SERIAL
    assert entry.options == {CONF_USERNAME: "waterkotte", CONF_PASSWORD: "new-password", CONF_POLLING_INTERVAL: 30}
    assert entry.data == data
    assert (entry.version, entry.minor_version) == (2, 1)


@pytest.mark.parametrize("serial", [UUID_SERIAL, "None", None])
async def test_migrate_1_2_without_serial(hass: HomeAssistant, serial: str | None) -> None:
    """Test that entries without a real serial number don't get a unique_id."""
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, data={CONF_HOST: HOST, CONF_SERIAL: serial})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.unique_id is None
    assert entry.data[CONF_SERIAL] is None
    assert (entry.version, entry.minor_version) == (2, 1)


async def test_migrate_1_2_duplicate_serial(hass: HomeAssistant) -> None:
    """Test that a second entry of the same heat pump does not get the same unique_id."""
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_HOST: HOST, CONF_SERIAL: SERIAL}).add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, data={CONF_HOST: HOST, CONF_SERIAL: SERIAL})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.unique_id is None


@pytest.mark.parametrize(
    ("data", "old_unique_id", "expected_base"),
    [
        # single instance
        ({CONF_SERIAL: SERIAL}, f"{DOMAIN}.temperature_outside", SERIAL),
        # multiple instances ('add_serial_as_id')
        ({CONF_SERIAL: SERIAL, CONF_ADD_SERIAL_AS_ID: True}, f"{DOMAIN}.temperature_outside_{SERIAL.lower()}", SERIAL),
        # multiple instances - heat pump without serial number (random UUID)
        ({CONF_SERIAL: UUID_SERIAL, CONF_ADD_SERIAL_AS_ID: True}, f"{DOMAIN}.temperature_outside_{UUID_SERIAL}", None),
        # very old entry without any serial number
        ({}, f"{DOMAIN}.temperature_outside", None),
    ],
)
async def test_migrate_1_3_unique_ids(
    hass: HomeAssistant, data: dict, old_unique_id: str, expected_base: str | None
) -> None:
    """Test that the unique_id's of the entities and the device identifier are based on the serial number
    (or the config entry id) - and that the entity_id's are not changed."""
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=3, data={CONF_HOST: HOST, **data})
    entry.add_to_hass(hass)
    if expected_base is None:
        expected_base = entry.entry_id

    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("DOMAIN", DOMAIN)})
    entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, old_unique_id, config_entry=entry, device_id=device.id
    )

    assert await async_migrate_entry(hass, entry)

    migrated_entity = er.async_get(hass).async_get(entity.entity_id)
    assert migrated_entity.unique_id == f"{expected_base}_temperature_outside".lower()
    assert dr.async_get(hass).async_get(device.id).identifiers == {(DOMAIN, expected_base)}
    assert CONF_ADD_SERIAL_AS_ID not in entry.data
    assert (entry.version, entry.minor_version) == (2, 1)
