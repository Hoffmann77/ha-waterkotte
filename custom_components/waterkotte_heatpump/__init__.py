"""The Waterkotte Heatpump integration."""
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as config_val, device_registry as dev_reg, entity_registry as entity_reg
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_SERIAL,
    CONF_SERIES,
    CONF_ADD_SCHEDULE_ENTITIES,
    CONF_ADD_SERIAL_AS_ID,
    TITLE,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
    OPTIONS_KEYS,
    CONFIG_VERSION, CONFIG_MINOR_VERSION
)
from .coordinator import WaterkotteConfigEntry, WKHPDataUpdateCoordinator
from .naming import entry_title, is_real_serial
from .service import async_setup_services

_LOGGER: logging.Logger = logging.getLogger(__package__)
CONFIG_SCHEMA = config_val.removed(DOMAIN, raise_if_present=False)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    if config_entry.version == 1:
        if config_entry.minor_version < 2:
            # update from 1.x to 1.2 [ensure that all unique_id's are lower case!]
            _LOGGER.info("async_migrate_entry(): Migration: from v%s.%s to v%s.%s", config_entry.version, config_entry.minor_version, CONFIG_VERSION, CONFIG_MINOR_VERSION)
            registry = entity_reg.async_get(hass)

            # 1'st run - ensure that all 'unique_id' are lower case...
            entities = entity_reg.async_entries_for_config_entry(registry, config_entry.entry_id)
            for entity in entities:
                if entity.unique_id != entity.unique_id.lower():
                    new_unique_id = entity.unique_id.lower()
                    _LOGGER.info("Entity ID: %s, Unique ID: %s updated!", entity.entity_id, entity.unique_id)
                    for already_existing_entity in entities:
                        if already_existing_entity.unique_id == new_unique_id:
                            _LOGGER.info("Entity ID: %s, Unique ID: %s already exists! - Will PURGE previous %s", entity.entity_id, new_unique_id, already_existing_entity.entity_id)
                            registry.async_remove(already_existing_entity.entity_id)

                    registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

            # 2'nd run - add the DOMAIN...
            entities = entity_reg.async_entries_for_config_entry(registry, config_entry.entry_id)
            prefix = f"{DOMAIN.lower()}.".lower()
            for entity in entities:
                if not entity.unique_id.startswith(prefix):
                    new_unique_id = f"{DOMAIN}.{entity.unique_id}".lower()
                    _LOGGER.debug("Entity ID: %s, Unique ID: %s will be updated!", entity.entity_id, entity.unique_id)
                    registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

            hass.config_entries.async_update_entry(config_entry, version=1, minor_version=2)
            _LOGGER.info("async_migrate_entry(): Migration to configuration version %s.%s successful", config_entry.version, config_entry.minor_version)

        if config_entry.minor_version < 3:
            # update from 1.2 to 1.3 [use the serial number as unique_id of the config entry]
            _LOGGER.info("async_migrate_entry(): Migration: from v%s.%s to v1.3", config_entry.version, config_entry.minor_version)
            new_unique_id = config_entry.unique_id
            serial = config_entry.data.get(CONF_SERIAL)
            if new_unique_id is None and is_real_serial(serial):
                # when the same heat pump have been configured twice, only the first entry gets the unique_id
                if not any(entry.unique_id == serial for entry in hass.config_entries.async_entries(DOMAIN)):
                    new_unique_id = serial

            # the options flow of older versions copied all data (incl. the host) into the options - now the
            # options contain only the settings of the options flow
            new_options = {key: value for key, value in config_entry.options.items() if key in OPTIONS_KEYS}

            hass.config_entries.async_update_entry(config_entry, unique_id=new_unique_id, options=new_options,
                                                   version=1, minor_version=3)
            _LOGGER.info("async_migrate_entry(): Migration to configuration version %s.%s successful", config_entry.version, config_entry.minor_version)

    if config_entry.version == 1:
        # update from 1.3 to 2.1 [the serial number (or the config entry id) is the base of the device identifier
        # and of the unique_id's of the entities - the 'add_serial_as_id' option is not required anymore]
        _LOGGER.info("async_migrate_entry(): Migration: from v%s.%s to v2.1", config_entry.version, config_entry.minor_version)
        new_data = dict(config_entry.data)
        old_serial = new_data.get(CONF_SERIAL)
        was_multi_instances = new_data.pop(CONF_ADD_SERIAL_AS_ID, False)
        if not is_real_serial(old_serial):
            # older versions stored a random UUID, when the heat pump did not provide a serial number
            new_data[CONF_SERIAL] = None
        unique_id_base = new_data[CONF_SERIAL] if new_data.get(CONF_SERIAL) is not None else config_entry.entry_id

        # all entries had the same title - but only update it, when the user did not rename the entry
        new_title = config_entry.title
        if new_title == TITLE:
            new_title = entry_title(new_data.get(CONF_SERIES), new_data.get(CONF_SERIAL))

        # old unique_id's: 'waterkotte_heatpump.<key>' or (multi instances) 'waterkotte_heatpump.<key>_<serial>'
        old_prefix = f"{DOMAIN}."
        old_suffix = f"_{old_serial or ''}".lower() if was_multi_instances else None
        registry = entity_reg.async_get(hass)
        for entity in entity_reg.async_entries_for_config_entry(registry, config_entry.entry_id):
            key = entity.unique_id
            if key.startswith(old_prefix):
                key = key[len(old_prefix):]
            if old_suffix is not None and key.endswith(old_suffix):
                key = key[:-len(old_suffix)]
            new_unique_id = f"{unique_id_base}_{key}".lower()
            if new_unique_id == entity.unique_id:
                continue

            # a leftover registry entry (e.g. from an older version) could already use the new unique_id - the
            # migration must not fail in this case (the entry could not be loaded anymore)
            existing_entity_id = registry.async_get_entity_id(entity.domain, DOMAIN, new_unique_id)
            if existing_entity_id is not None and existing_entity_id != entity.entity_id:
                _LOGGER.warning("async_migrate_entry(): Entity ID: %s, Unique ID: %s not migrated - the new Unique ID: %s is already used by %s. You can remove %s manually.", entity.entity_id, entity.unique_id, new_unique_id, existing_entity_id, entity.entity_id)
                continue

            registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

        # old device identifiers: ('DOMAIN', 'waterkotte_heatpump') and ('IP', <ip>)
        device_registry = dev_reg.async_get(hass)
        for device in dev_reg.async_entries_for_config_entry(device_registry, config_entry.entry_id):
            device_registry.async_update_device(device.id, new_identifiers={(DOMAIN, unique_id_base)})

        hass.config_entries.async_update_entry(config_entry, data=new_data, title=new_title, version=2, minor_version=1)
        _LOGGER.info("async_migrate_entry(): Migration to configuration version %s.%s successful", config_entry.version, config_entry.minor_version)

    if config_entry.version == 2 and config_entry.minor_version < 2:
        # update from 2.1 to 2.2 [the optional schedule entities have been removed - so we remove them (incl. the
        # disabled ones) from the entity registry, and the 'add_schedule_entities' option is not required anymore]
        _LOGGER.info("async_migrate_entry(): Migration: from v%s.%s to v2.2", config_entry.version, config_entry.minor_version)
        registry = entity_reg.async_get(hass)
        for entity in entity_reg.async_entries_for_config_entry(registry, config_entry.entry_id):
            if _SCHEDULE_ENTITY_UNIQUE_ID.search(entity.unique_id):
                registry.async_remove(entity.entity_id)

        new_data = {key: value for key, value in config_entry.data.items() if key != CONF_ADD_SCHEDULE_ENTITIES}
        new_options = {key: value for key, value in config_entry.options.items() if key != CONF_ADD_SCHEDULE_ENTITIES}
        hass.config_entries.async_update_entry(config_entry, data=new_data, options=new_options, version=2,
                                               minor_version=2)
        _LOGGER.info("async_migrate_entry(): Migration to configuration version %s.%s successful", config_entry.version, config_entry.minor_version)

    return True


# unique_id's of the removed schedule entities, e.g. '<serial>_schedule_heating_1mo_adjust1_value' (also in the old
# format 'waterkotte_heatpump.schedule_...') - the water disinfection entities ('schedule_water_disinfection_1mo')
# are not affected
_SCHEDULE_ENTITY_UNIQUE_ID = re.compile(
    r"(^|[._])schedule_(heating|cooling|water|pool|mix[123]|buffer_tank_circulation_pump|solar|pv)_"
    r"[1-7](mo|tu|we|th|fr|sa|su)_"
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration - the service actions are registered once (independent of the config entries)."""
    _LOGGER.info(STARTUP_MESSAGE)
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry) -> bool:
    coordinator = WKHPDataUpdateCoordinator(hass, config_entry)
    # connects to the heat pump (see WKHPDataUpdateCoordinator._async_setup) - raises ConfigEntryNotReady (or
    # ConfigEntryAuthFailed), when this is not possible
    await coordinator.async_config_entry_first_refresh()
    config_entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # the initial refresh ran before any entity was added (so no tags were requested) - now all
    # enabled entities have registered their tags as coordinator context, so we fetch the data
    await coordinator.async_refresh()

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry) -> bool:
    _LOGGER.debug("async_unload_entry() called for entry: %s", config_entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if unload_ok:
        await config_entry.runtime_data.bridge.logout()

    return unload_ok
