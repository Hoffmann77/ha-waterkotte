import asyncio
import logging
import re
from datetime import timedelta
from typing import Collection, Sequence, Any, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant, Event, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as config_val, device_registry as dev_reg, entity_registry as entity_reg
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.typing import UNDEFINED, UndefinedType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.waterkotte_heatpump.pywaterkotte_ha import WaterkotteClient
from custom_components.waterkotte_heatpump.pywaterkotte_ha.const import ECOTOUCH, EASYCON
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import TooManyUsersException, InvalidPasswordException
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from . import service as waterkotte_service
from .const import (
    CONF_POLLING_INTERVAL,
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
    TITLE,
    MANUFACTURER,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
    SERVICE_SET_HOLIDAY,
    SERVICE_SET_SCHEDULE_DATA,
    SERVICE_SET_DISINFECTION_START_TIME,
    SERVICE_GET_ENERGY_BALANCE,
    SERVICE_GET_ENERGY_BALANCE_MONTHLY,
    FEATURE_VENT,
    FEATURE_HEATING_CURVE,
    FEATURE_DISINFECTION,
    FEATURE_CODE_GEN,
    OPTIONS_KEYS,
    CONFIG_VERSION, CONFIG_MINOR_VERSION
)
from .entity import CustomFriendlyNameEntity
from .naming import device_name, entry_title

_LOGGER: logging.Logger = logging.getLogger(__package__)
SCAN_INTERVAL = timedelta(seconds=60)
CONFIG_SCHEMA = config_val.removed(DOMAIN, raise_if_present=False)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    if config_entry.version == 1:
        if config_entry.minor_version < 2:
            # update from 1.x to 1.2 [ensure that all unique_id's are lower case!]
            _LOGGER.info(f"async_migrate_entry(): Migration: from v{config_entry.version}.{config_entry.minor_version} to v{CONFIG_VERSION}.{CONFIG_MINOR_VERSION}")
            registry = entity_reg.async_get(hass)

            # 1'st run - ensure that all 'unique_id' are lower case...
            entities = entity_reg.async_entries_for_config_entry(registry, config_entry.entry_id)
            for entity in entities:
                if entity.unique_id != entity.unique_id.lower():
                    new_unique_id = entity.unique_id.lower()
                    _LOGGER.info(f"Entity ID: {entity.entity_id}, Unique ID: {entity.unique_id} updated!")
                    for already_existing_entity in entities:
                        if already_existing_entity.unique_id == new_unique_id:
                            _LOGGER.info(f"Entity ID: {entity.entity_id}, Unique ID: {new_unique_id} already exists! - Will PURGE previous {already_existing_entity.entity_id}")
                            registry.async_remove(already_existing_entity.entity_id)

                    registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

            # 2'nd run - add the DOMAIN...
            entities = entity_reg.async_entries_for_config_entry(registry, config_entry.entry_id)
            prefix = f"{DOMAIN.lower()}.".lower()
            for entity in entities:
                if not entity.unique_id.startswith(prefix):
                    new_unique_id = f"{DOMAIN}.{entity.unique_id}".lower()
                    _LOGGER.debug(f"Entity ID: {entity.entity_id}, Unique ID: {entity.unique_id} will be updated!")
                    registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

            hass.config_entries.async_update_entry(config_entry, version=1, minor_version=2)
            _LOGGER.info(f"async_migrate_entry(): Migration to configuration version {config_entry.version}.{config_entry.minor_version} successful")

        if config_entry.minor_version < 3:
            # update from 1.2 to 1.3 [use the serial number as unique_id of the config entry]
            _LOGGER.info(f"async_migrate_entry(): Migration: from v{config_entry.version}.{config_entry.minor_version} to v1.3")
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
            _LOGGER.info(f"async_migrate_entry(): Migration to configuration version {config_entry.version}.{config_entry.minor_version} successful")

    if config_entry.version == 1:
        # update from 1.3 to 2.1 [the serial number (or the config entry id) is the base of the device identifier
        # and of the unique_id's of the entities - the 'add_serial_as_id' option is not required anymore]
        _LOGGER.info(f"async_migrate_entry(): Migration: from v{config_entry.version}.{config_entry.minor_version} to v2.1")
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
            if new_unique_id != entity.unique_id:
                registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

        # old device identifiers: ('DOMAIN', 'waterkotte_heatpump') and ('IP', <ip>)
        device_registry = dev_reg.async_get(hass)
        for device in dev_reg.async_entries_for_config_entry(device_registry, config_entry.entry_id):
            device_registry.async_update_device(device.id, new_identifiers={(DOMAIN, unique_id_base)})

        hass.config_entries.async_update_entry(config_entry, data=new_data, title=new_title, version=2, minor_version=1)
        _LOGGER.info(f"async_migrate_entry(): Migration to configuration version {config_entry.version}.{config_entry.minor_version} successful")

    return True


def _is_real_serial(serial: str | None) -> bool:
    """Check if the serial was read from the heat pump - older versions stored a random UUID, when the
    heat pump did not provide a serial number"""
    return serial is not None and serial not in ("", "None") and re.fullmatch(r"[0-9a-f]{32}", serial) is None


def _str_or_none(value) -> str | None:
    """Device information as string - or None, if the heat pump did not provide the value"""
    if value is None or str(value) in ("", "None"):
        return None
    return str(value)


async def async_setup(hass: HomeAssistant, config: dict):  # pylint: disable=unused-argument
    """Set up this integration using YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    if DOMAIN not in hass.data:
        value = "UNKOWN"
        _LOGGER.info(STARTUP_MESSAGE)
        hass.data.setdefault(DOMAIN, {"manifest_version": value})

    coordinator = WKHPDataUpdateCoordinator(hass, config_entry)
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady
    else:
        # here we can do some init stuff (like read all data)...
        pass

    # we check if the operation hours will be returned as TOTAL's (and if this is
    # not the case, we enable it!
    try:
        res = await coordinator.bridge.async_read_value(WKHPTag.OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634)
        if res.get('status', None) == "S_OK":
            if not res.get('value', True):
                _LOGGER.info(f"async_setup_entry(): enable 'total OPERATING_HOURS' counters via OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634")
                await coordinator.bridge.async_write_value(WKHPTag.OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634, True)
    except BaseException as e:
        _LOGGER.warning(f"async_setup_entry(): could not enable OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634: {(type(e).__name__)} {e}")

    # ok now init the platforms...
    hass.data[DOMAIN][config_entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    service = waterkotte_service.WaterkotteHeatpumpService(hass, config_entry, coordinator)
    hass.services.async_register(DOMAIN, SERVICE_SET_HOLIDAY, service.set_holiday,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE_DATA, service.set_schedule_data,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_SET_DISINFECTION_START_TIME, service.set_disinfection_start_time,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_GET_ENERGY_BALANCE, service.get_energy_balance,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_GET_ENERGY_BALANCE_MONTHLY, service.get_energy_balance_monthly,
                                 supports_response=SupportsResponse.ONLY)

    # the initial refresh ran before any entity was added (so no tags were requested) - now all
    # enabled entities have registered their tags as coordinator context, so we fetch the data
    await coordinator.async_refresh()

    # ok we are done...
    config_entry.async_on_unload(config_entry.add_update_listener(entry_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.debug(f"async_unload_entry() called for entry: {config_entry.entry_id}")
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    if unload_ok:
        if DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]:
            # even if waterkotte does not support logout... I code it here...
            coordinator = hass.data[DOMAIN][config_entry.entry_id]
            await coordinator.bridge._internal_client.logout()

            hass.data[DOMAIN].pop(config_entry.entry_id)

        hass.services.async_remove(DOMAIN, SERVICE_SET_HOLIDAY)
        hass.services.async_remove(DOMAIN, SERVICE_SET_DISINFECTION_START_TIME)
        hass.services.async_remove(DOMAIN, SERVICE_GET_ENERGY_BALANCE)
        hass.services.async_remove(DOMAIN, SERVICE_GET_ENERGY_BALANCE_MONTHLY)

    return unload_ok


async def entry_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    _LOGGER.debug(f"entry_update_listener() called for entry: {config_entry.entry_id}")
    await hass.config_entries.async_reload(config_entry.entry_id)


class WKHPDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, config_entry):
        self.name = config_entry.title
        # the serial number of the heat pump (or the config entry id, when the heat pump does not provide a
        # serial number) is used for the device identifier and as prefix of the unique_id's of the entities
        serial = config_entry.data.get(CONF_SERIAL)
        if not _is_real_serial(serial):
            serial = None
        self.unique_id_base = serial if serial is not None else config_entry.entry_id

        self._config_entry = config_entry
        self.add_schedule_entities = config_entry.options.get(CONF_ADD_SCHEDULE_ENTITIES,
                                                              config_entry.data.get(CONF_ADD_SCHEDULE_ENTITIES, False))
        self.available_features = []
        if CONF_USE_VENT in config_entry.data and config_entry.data[CONF_USE_VENT]:
            self.available_features.append(FEATURE_VENT)
        if CONF_USE_HEATING_CURVE in config_entry.data and config_entry.data[CONF_USE_HEATING_CURVE]:
            self.available_features.append(FEATURE_HEATING_CURVE)
        if CONF_USE_DISINFECTION in config_entry.data and config_entry.data[CONF_USE_DISINFECTION]:
            self.available_features.append(FEATURE_DISINFECTION)
        _LOGGER.debug(f"available_features: {self.available_features}")

        # the connection data is only stored in the config entry data (not in the options)
        _system_type = config_entry.data.get(CONF_SYSTEMTYPE, ECOTOUCH)
        _host = config_entry.data.get(CONF_HOST)
        _user = config_entry.options.get(CONF_USERNAME, config_entry.data.get(CONF_USERNAME, "@@@µµµ@@@" if _system_type == EASYCON else "waterkotte"))
        _pwd = config_entry.options.get(CONF_PASSWORD, config_entry.data.get(CONF_PASSWORD, "@@@µµµ@@@" if _system_type == EASYCON else "waterkotte"))
        _tags_num = config_entry.options.get(CONF_TAGS_PER_REQUEST, config_entry.data.get(CONF_TAGS_PER_REQUEST, 10))

        if _system_type == EASYCON:
            # by default, EASYCON does not have a password option... BUT if the user specified login credentials,
            # then we must use them!
            if _user == "@@@µµµ@@@" or _pwd == "@@@µµµ@@@":
                _user = None
                _pwd = None

        self.bridge = WaterkotteClient(host=_host, username=_user, pwd=_pwd, system_type=_system_type,
                                       web_session=async_get_clientsession(hass), tags=[],
                                       tags_per_request=_tags_num, lang=hass.config.language.lower())

        global SCAN_INTERVAL
        # update_interval can be adjusted in the options (not for WebAPI)
        SCAN_INTERVAL = timedelta(seconds=config_entry.options.get(CONF_POLLING_INTERVAL,
                                                                   config_entry.data.get(CONF_POLLING_INTERVAL, 60)))

        fw = config_entry.data.get(CONF_FW)
        bios = config_entry.data.get(CONF_BIOS)
        self._device_info_dict = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id_base)},
            manufacturer=MANUFACTURER,
            name=device_name(hass, config_entry, serial),
            model=_str_or_none(config_entry.data.get(CONF_SERIES)),
            model_id=_str_or_none(config_entry.data.get(CONF_ID)),
            serial_number=serial,
            sw_version=f"{fw} BIOS: {bios}" if fw is not None else None,
            configuration_url=f"http://{_host}",
        )

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    # Callable[[Event], Any]
    def __call__(self, evt: Event) -> bool:
        _LOGGER.debug(f"Event arrived: {evt}")
        return True

    async def _async_update_data(self):
        """Update data via library."""
        try:
            # each entity registers its tag as coordinator context - so we only
            # request the tags of the entities that are currently enabled
            self.bridge.tags = list(set(self.async_contexts()))
            await self.bridge.login()
            _LOGGER.info(f"number of entities to query: {len(self.bridge.tags)} (1 entity can consist of n-tags)")
            result = await self.bridge.async_get_data()
            _LOGGER.info(f"number of entity values read: {len(result)}")

            if self.data is None:
                self.data = {}

            for a_tag_in_result in result:
                if result[a_tag_in_result]["status"] == "S_OK":
                    self.data[a_tag_in_result] = result[a_tag_in_result]

            return self.data

        except UpdateFailed as exception:
            raise UpdateFailed() from exception
        except InvalidPasswordException as invalid_pwd:
            _LOGGER.info(f"invalid password for waterkotte! {invalid_pwd}")
            raise UpdateFailed() from invalid_pwd
        except TooManyUsersException as too_many_users:
            _LOGGER.info(f"TooManyUsers response from waterkotte - waiting 30sec and then retry...")
            await asyncio.sleep(30)
            raise UpdateFailed() from too_many_users
        except Exception as other:
            _LOGGER.error(f"unexpected: {other}")
            raise UpdateFailed() from other

    async def async_read_values(self, tags: Sequence[WKHPTag]) -> dict:
        """Get data from the API."""
        ret = await self.bridge.async_read_values(tags)
        return ret

    async def async_write_tags(self, kv_pairs: Collection[Tuple[WKHPTag, Any]]) -> dict:
        """Get data from the API."""
        ret = await self.bridge.async_write_values(kv_pairs)
        return ret

    async def async_write_tag(self, tag: WKHPTag, value, entity: Entity = None):
        """Update single data"""
        result = await self.bridge.async_write_value(tag, value)
        _LOGGER.debug(f"write result: {result}")

        if tag in result:
            self.data[tag] = result[tag]
        else:
            _LOGGER.error(f"could not write value: '{value}' to: {tag} result was: {result}")

        # after we have written something to the Waterkotte we should force an update of the data...
        if entity is not None:
            entity.async_schedule_update_ha_state(force_refresh=True)


class WKHPBaseEntity(CustomFriendlyNameEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: WKHPDataUpdateCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator, context=description.tag)
        if description.feature is not None and FEATURE_CODE_GEN == description.feature:
            self.code_generated = True
        else:
            self.code_generated = False
        self._attr_translation_key = description.key.lower()
        self.coordinator = coordinator
        self.entity_description = description

        # check, if the feature should be enabled by default (if activated during setup)
        if not description.entity_registry_enabled_default and description.feature is not None:
            if description.feature in self.coordinator.available_features:
                self._attr_entity_registry_enabled_default = True

    def _name_internal(self, device_class_name: str | None,
                       platform_translations: dict[str, Any], ) -> str | UndefinedType | None:
        if self.code_generated:
            return self._name_internal_code_generated(self._attr_translation_key, platform_translations)
        else:
            return super()._name_internal(device_class_name, platform_translations)

    def _name_internal_code_generated(self, key, platform_translations: dict[str, Any]):
        temp = key.lower().replace('_', ' ')
        temp = temp.replace(' enable', '')
        temp = temp.replace(' value', '')
        a_list = ["schedule", "heating", "cooling", "water", "pool", "solar", "pv",
                  "mix1", "mix2", "mix3", "buffer tank circulation pump", "adjust",
                  "1mo", "2tu", "3we", "4th", "5fr", "6sa", "7su",
                  "start time", "end time"]
        for a_key in a_list:
            f_key = f"component.{self.platform.platform_name}.entity.code_gen.{a_key.replace(' ', '_')}.name"
            if f_key in platform_translations:
                temp = temp.replace(a_key, platform_translations.get(f_key))
            else:
                _LOGGER.warning(f"{a_key} -> {f_key} not found in platform_translations")

        return temp  # .title()

    @property
    def wkhp_tag(self):
        """Return a unique ID to use for this entity."""
        return self.entity_description.tag

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator._device_info_dict

    @property
    def available(self):
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.coordinator.unique_id_base}_{self.entity_description.key}".lower()

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name.

        If has_entity_name is False, this returns self.name
        If has_entity_name is True, this returns device.name + self.name
        """
        name = self.name
        if name is UNDEFINED:
            name = None

        if not self.has_entity_name or not (device_entry := self.device_entry):
            return name

        device_name = device_entry.name_by_user or device_entry.name
        if name is None and self.use_device_name:
            return f"[WKHP] {device_name}"

        # check if there is a user specified entity name (overwritten)
        if registry_entry := self.registry_entry:
            if registry_entry.has_entity_name and registry_entry.name is not None:
                name = registry_entry.name

        return f"[WKHP] {name}"