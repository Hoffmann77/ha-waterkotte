import logging
import re
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Sequence

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as config_val, device_registry as dev_reg, entity_registry as entity_reg
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.waterkotte_heatpump.pywaterkotte_ha import WaterkotteClient
from custom_components.waterkotte_heatpump.pywaterkotte_ha.const import ECOTOUCH, EASYCON
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import (
    InvalidPasswordException,
    InvalidValueException,
    StatusException,
    TooManyUsersException,
)
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .service import async_setup_services
from .const import (
    CONF_POLLING_INTERVAL,
    MIN_POLLING_INTERVAL,
    CONF_TAGS_PER_REQUEST,
    CONF_BIOS,
    CONF_FW,
    CONF_SERIAL,
    CONF_SERIES,
    CONF_SYSTEMTYPE,
    CONF_ADD_SCHEDULE_ENTITIES,
    CONF_ADD_SERIAL_AS_ID,
    CONF_USE_VENT,
    CONF_USE_HEATING_CURVE,
    CONF_USE_DISINFECTION,
    CONF_USE_POOL,
    TITLE,
    MANUFACTURER,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
    FEATURE_VENT,
    FEATURE_HEATING_CURVE,
    FEATURE_DISINFECTION,
    FEATURE_POOL,
    OPTIONS_KEYS,
    CONFIG_VERSION, CONFIG_MINOR_VERSION
)
from .naming import device_name, entry_title, known_or_none

_LOGGER: logging.Logger = logging.getLogger(__package__)
CONFIG_SCHEMA = config_val.removed(DOMAIN, raise_if_present=False)

# the setup flags of the config entry -> the feature, whose entities are enabled by default
_FEATURE_FLAGS = {
    CONF_USE_VENT: FEATURE_VENT,
    CONF_USE_HEATING_CURVE: FEATURE_HEATING_CURVE,
    CONF_USE_DISINFECTION: FEATURE_DISINFECTION,
    CONF_USE_POOL: FEATURE_POOL,
}

# the coordinator of a loaded config entry is stored as its runtime_data
type WaterkotteConfigEntry = ConfigEntry[WKHPDataUpdateCoordinator]


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
            if new_unique_id is None and _is_real_serial(serial):
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
        if not _is_real_serial(old_serial):
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


def _is_real_serial(serial: str | None) -> bool:
    """Check if the serial was read from the heat pump - older versions stored a random UUID, when the
    heat pump did not provide a serial number"""
    return serial is not None and serial not in ("", "None") and re.fullmatch(r"[0-9a-f]{32}", serial) is None


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

    config_entry.async_on_unload(config_entry.add_update_listener(entry_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry) -> bool:
    _LOGGER.debug("async_unload_entry() called for entry: %s", config_entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if unload_ok:
        await config_entry.runtime_data.bridge.logout()

    return unload_ok


async def entry_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    _LOGGER.debug("entry_update_listener() called for entry: %s", config_entry.entry_id)
    await hass.config_entries.async_reload(config_entry.entry_id)


class WKHPDataUpdateCoordinator(DataUpdateCoordinator[dict[WKHPTag, dict]]):
    """The values of the tags (of all enabled entities) - polled from the heat pump"""

    config_entry: WaterkotteConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: WaterkotteConfigEntry):
        # the serial number of the heat pump (or the config entry id, when the heat pump does not provide a
        # serial number) is used for the device identifier and as prefix of the unique_id's of the entities
        serial = config_entry.data.get(CONF_SERIAL)
        if not _is_real_serial(serial):
            serial = None
        self.serial = serial
        self.unique_id_base = serial if serial is not None else config_entry.entry_id

        self.available_features = [feature for flag, feature in _FEATURE_FLAGS.items() if config_entry.data.get(flag)]
        _LOGGER.debug("available_features: %s", self.available_features)

        def setting(key, default):
            # settings that have not been changed via the options yet, are taken from the initial configuration
            return config_entry.options.get(key, config_entry.data.get(key, default))

        # the connection data is only stored in the config entry data (not in the options)
        _system_type = config_entry.data.get(CONF_SYSTEMTYPE, ECOTOUCH)
        _host = config_entry.data.get(CONF_HOST)
        # by default, EASYCON does not have a password option... BUT if the user specified login credentials,
        # then we must use them!
        _default_credential = None if _system_type == EASYCON else "waterkotte"
        _user = setting(CONF_USERNAME, _default_credential)
        _pwd = setting(CONF_PASSWORD, _default_credential)
        if _system_type == EASYCON and (_user is None or _pwd is None):
            _user = None
            _pwd = None

        self.bridge = WaterkotteClient(host=_host, username=_user, pwd=_pwd, system_type=_system_type,
                                       web_session=async_get_clientsession(hass), tags=[],
                                       tags_per_request=setting(CONF_TAGS_PER_REQUEST, 10),
                                       lang=hass.config.language.lower())

        fw = config_entry.data.get(CONF_FW)
        bios = config_entry.data.get(CONF_BIOS)
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id_base)},
            manufacturer=MANUFACTURER,
            name=device_name(hass, config_entry, serial),
            model=known_or_none(config_entry.data.get(CONF_SERIES)),
            model_id=known_or_none(config_entry.data.get(CONF_ID)),
            serial_number=serial,
            sw_version=f"{fw} BIOS: {bios}" if fw is not None else None,
            configuration_url=f"http://{_host}",
        )

        # update_interval can be adjusted in the options
        super().__init__(hass, _LOGGER, config_entry=config_entry, name=DOMAIN,
                         update_interval=timedelta(seconds=max(MIN_POLLING_INTERVAL, setting(CONF_POLLING_INTERVAL, 60))))

    async def _async_setup(self) -> None:
        """Connect to the heat pump (once, during the first refresh)."""
        async with self._map_errors():
            # the EasyCon interface has no login - so we also read a tag to check the connection
            await self.bridge.async_check_login()
            if not await self.bridge.async_read_values([WKHPTag.VERSION_BIOS]):
                raise UpdateFailed(f"no data could be read from the heat pump at {self.config_entry.data.get(CONF_HOST)}")

        await self._async_complete_device_information()

        # we check if the operation hours will be returned as TOTAL's (and if this is
        # not the case, we enable it!
        try:
            res = await self.bridge.async_read_value(WKHPTag.OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634)
            if res.get('status', None) == "S_OK" and not res.get('value', True):
                _LOGGER.info("enable 'total OPERATING_HOURS' counters via OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634")
                await self.bridge.async_write_value(WKHPTag.OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634, True)
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.warning("could not enable OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634: %s %s", type(e).__name__, e)

    async def _async_complete_device_information(self) -> None:
        """Older versions could not decode the series and the system id of the heat pump - so they are missing in
        the existing config entries. They are read once and stored in the config entry (the model of the device)."""
        data = self.config_entry.data
        if known_or_none(data.get(CONF_SERIES)) is not None and known_or_none(data.get(CONF_ID)) is not None:
            return
        try:
            values = await self.bridge.async_read_values([WKHPTag.INFO_SERIES, WKHPTag.INFO_ID])
        except Exception as err:  # pylint: disable=broad-except
            # not required for the setup - the next setup tries again
            _LOGGER.debug("could not read the series and the system id: %s %s", type(err).__name__, err)
            return

        new_data = dict(data)
        for key, tag in ((CONF_SERIES, WKHPTag.INFO_SERIES), (CONF_ID, WKHPTag.INFO_ID)):
            value = known_or_none((values.get(tag) or {}).get("value"))
            if value is not None and known_or_none(data.get(key)) is None:
                new_data[key] = value
        if new_data == data:
            return

        # only a generated title is updated (a title, that the user has changed, is kept)
        title = self.config_entry.title
        if title == entry_title(data.get(CONF_SERIES), self.serial):
            title = entry_title(new_data.get(CONF_SERIES), self.serial)
        _LOGGER.info("completed the device information: series %s, system id %s",
                     new_data.get(CONF_SERIES), new_data.get(CONF_ID))
        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data, title=title)
        # the entities (and so the device) are added after the setup of the coordinator
        self.device_info["model"] = known_or_none(new_data.get(CONF_SERIES))
        self.device_info["model_id"] = known_or_none(new_data.get(CONF_ID))

    async def _async_update_data(self) -> dict[WKHPTag, dict]:
        """Update data via library."""
        # each entity registers its tag as coordinator context - so we only
        # request the tags of the entities that are currently enabled
        self.bridge.tags = list(set(self.async_contexts()))
        _LOGGER.debug("number of entities to query: %s (1 entity can consist of n-tags)", len(self.bridge.tags))
        async with self._map_errors():
            result = await self.bridge.async_get_data()
        _LOGGER.debug("number of entity values read: %s", len(result))

        # only the values that have been read in this update - the entities of the other tags are unavailable
        # (and don't show an outdated value)
        return {tag: value for tag, value in result.items() if value is not None and value["status"] == "S_OK"}

    @asynccontextmanager
    async def _map_errors(self):
        """Map the errors of the heat pump to the errors of the coordinator."""
        try:
            yield
        except InvalidPasswordException as err:
            # starts the reauth flow
            raise ConfigEntryAuthFailed(f"invalid credentials for the heat pump at {self.config_entry.data.get(CONF_HOST)}") from err
        except TooManyUsersException as err:
            raise UpdateFailed("too many users are logged in to the heat pump", retry_after=30) from err
        except (UpdateFailed, ConfigEntryAuthFailed):
            raise
        except Exception as err:
            raise UpdateFailed(f"error communicating with the heat pump: {type(err).__name__} {err}") from err

    async def async_read_values(self, tags: Sequence[WKHPTag]) -> dict:
        """Read the values of the tags (outside the regular updates) - the errors are raised as HomeAssistantError"""
        try:
            return await self.bridge.async_read_values(tags)
        except (StatusException, aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="read_failed",
                                     translation_placeholders={"error": f"{type(err).__name__} {err}"}) from err

    async def async_write_tag(self, tag: WKHPTag, value):
        """Write the value of a tag to the heat pump - the errors are raised as HomeAssistantError"""
        placeholders = {"tag": tag.name, "value": str(value)}
        try:
            result = await self.bridge.async_write_value(tag, value)
        except (ValueError, InvalidValueException) as err:
            # the value can't be encoded for the tag (or the tag is read only)
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_value",
                                         translation_placeholders=placeholders) from err
        except (StatusException, aiohttp.ClientError, TimeoutError) as err:
            # e.g. too many users are logged in to the heat pump
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed",
                                     translation_placeholders={**placeholders,
                                                               "error": f"{type(err).__name__} {err}"}) from err
        _LOGGER.debug("write result: %s", result)

        if tag in result:
            self.async_set_updated_data({**self.data, tag: result[tag]})
        # writing a value can change other values of the heat pump as well (and after a failed write, the
        # current value is shown again)
        await self.async_request_refresh()
        if tag not in result:
            # the heat pump did not confirm the written value
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_not_confirmed",
                                     translation_placeholders=placeholders)
