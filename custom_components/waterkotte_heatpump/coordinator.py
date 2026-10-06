"""The coordinator of the Waterkotte Heatpump integration - it polls the values of the heat pump."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Sequence

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
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
from .const import (
    CONF_ADD_READONLY_COPIES,
    CONF_MONTHLY_STATISTICS,
    CONF_POLLING_INTERVAL,
    CONF_READ_ONLY,
    MIN_POLLING_INTERVAL,
    CONF_TAGS_PER_REQUEST,
    CONF_BIOS,
    CONF_FW,
    CONF_SERIAL,
    CONF_SERIES,
    CONF_SYSTEMTYPE,
    CONF_USE_VENT,
    CONF_USE_HEATING_CURVE,
    CONF_USE_DISINFECTION,
    CONF_USE_POOL,
    MANUFACTURER,
    DOMAIN,
    FEATURE_VENT,
    FEATURE_HEATING_CURVE,
    FEATURE_DISINFECTION,
    FEATURE_POOL
)
from .naming import device_name, entry_title, is_real_serial, known_or_none

_LOGGER: logging.Logger = logging.getLogger(__package__)

# the setup flags of the config entry -> the feature, whose entities are enabled by default
_FEATURE_FLAGS = {
    CONF_USE_VENT: FEATURE_VENT,
    CONF_USE_HEATING_CURVE: FEATURE_HEATING_CURVE,
    CONF_USE_DISINFECTION: FEATURE_DISINFECTION,
    CONF_USE_POOL: FEATURE_POOL,
}

# the values of the energy balance of a year: the heat pump provides them for the year, that is selected in its
# web interface (COP_HEATPUMP_ACTUAL_YEAR_INFO) - while someone looks at the balance of an older year, they don't
# belong to the current year
YEAR_BALANCE_TAGS: frozenset[WKHPTag] = frozenset({
    WKHPTag.COP_HEATPUMP_YEAR,
    WKHPTag.COP_TOTAL_SYSTEM_YEAR,
    WKHPTag.COP_HEATING_YEAR,
    WKHPTag.COP_HOT_WATER_YEAR,
    WKHPTag.ENERGY_CONSUMPTION_TOTAL_YEAR,
    WKHPTag.COMPRESSOR_ELECTRIC_CONSUMPTION_YEAR,
    WKHPTag.SOURCEPUMP_ELECTRIC_CONSUMPTION_YEAR,
    WKHPTag.ELECTRICAL_HEATER_ELECTRIC_CONSUMPTION_YEAR,
    WKHPTag.ENERGY_PRODUCTION_TOTAL_YEAR,
    WKHPTag.HEATING_ENERGY_PRODUCTION_YEAR,
    WKHPTag.HOT_WATER_ENERGY_PRODUCTION_YEAR,
    WKHPTag.POOL_ENERGY_PRODUCTION_YEAR,
    WKHPTag.COOLING_ENERGY_YEAR,
})
_YEAR_CHECK_TAGS = (WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO, WKHPTag.COP_HEATPUMP_TOTAL_SELECTED, WKHPTag.DATE_YEAR)


def _is_ok(value: dict | None) -> bool:
    """True, when the value has been read"""
    return value is not None and value["status"] == "S_OK"


# the yearly energy counters (kWh) - they only increase during a year
YEAR_ENERGY_TAGS: frozenset[WKHPTag] = YEAR_BALANCE_TAGS - {
    WKHPTag.COP_HEATPUMP_YEAR,
    WKHPTag.COP_TOTAL_SYSTEM_YEAR,
    WKHPTag.COP_HEATING_YEAR,
    WKHPTag.COP_HOT_WATER_YEAR,
}
# the maximum increase of a yearly energy counter: per hour since the last value and per update
_MAX_KWH_PER_HOUR = 50.0
_MAX_KWH_PER_UPDATE = 5.0
# after this number of updates with implausible values in a row, the values are accepted (e.g. after the counters of
# the heat pump have been reset)
_MAX_IMPLAUSIBLE_UPDATES = 3


def _number(values: dict, tag: WKHPTag) -> float | None:
    try:
        return float(values[tag]["value"])
    except (KeyError, TypeError, ValueError):
        return None


def is_total_selected(values: dict) -> bool:
    """True, when the total of all years ('Gesamt') is selected in the web interface"""
    return values.get(WKHPTag.COP_HEATPUMP_TOTAL_SELECTED, {}).get("value") in (True, 1, "1")


def is_other_year(values: dict) -> bool:
    """True, when the energy balance of another year than the current year of the heat pump (or the total of all
    years) is selected (when the year can't be read, the values are not discarded)"""
    if is_total_selected(values):
        return True
    try:
        balance_year = int(values[WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO]["value"])
        year = int(float(values[WKHPTag.DATE_YEAR]["value"]))
    except (KeyError, TypeError, ValueError):
        return False
    if year < 100:
        year += 2000
    return balance_year != year


class YearBalanceGuard:
    """Discards the values of the energy balance of a year, that don't belong to the current year.

    When the year is changed in the web interface, the heat pump doesn't switch the selected year (I1261) and the
    yearly values at the same moment - for one update the values of the other year (or 0) can be read together with
    the current year. So the yearly values are also discarded
    - in the first update after another year has been selected (until the values have settled) and
    - when an energy counter decreases or increases more than possible since its last value.
    """

    def __init__(self) -> None:
        self._settle = False
        self._implausible = 0
        self._year: int | None = None
        # the last accepted value of each energy counter: (time.monotonic(), value)
        self._reference: dict[WKHPTag, tuple[float, float]] = {}

    def filter(self, data: dict, now: float) -> dict:
        if is_other_year(data):
            # the values of another year would look like a reset of the yearly counters (in the statistics)
            _LOGGER.info("the energy balance of %s is selected in the web interface of the heat pump - the yearly "
                         "values are not updated",
                         "all years" if is_total_selected(data) else data[WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO]["value"])
            self._settle = True
            return self._discard(data)
        if self._settle:
            self._settle = False
            _LOGGER.debug("the current year is selected again - the yearly values are updated with the next update")
            return self._discard(data)

        year = _number(data, WKHPTag.DATE_YEAR)
        energies = {tag: value for tag in YEAR_ENERGY_TAGS if (value := _number(data, tag)) is not None}
        implausible = self._implausible_values(energies, year, now)
        if implausible:
            self._implausible += 1
            if self._implausible < _MAX_IMPLAUSIBLE_UPDATES:
                _LOGGER.info("implausible yearly values (another year selected in the web interface?) - the yearly "
                             "values are not updated: %s", implausible)
                return self._discard(data)
            _LOGGER.warning("the yearly values have changed: %s", implausible)
        self._implausible = 0
        if year is not None:
            self._year = int(year)
        self._reference.update({tag: (now, value) for tag, value in energies.items()})
        return data

    def _implausible_values(self, energies: dict[WKHPTag, float], year: float | None, now: float) -> dict:
        if year is None or self._year is None or int(year) != self._year:
            # a new year: the counters start at 0
            return {}
        implausible = {}
        for tag, value in energies.items():
            if tag not in self._reference:
                continue
            since, last = self._reference[tag]
            max_increase = _MAX_KWH_PER_HOUR * (now - since) / 3600 + _MAX_KWH_PER_UPDATE
            if value < last - 0.1 or value > last + max_increase:
                implausible[tag.name] = f"{last} -> {value}"
        return implausible

    @staticmethod
    def _discard(data: dict) -> dict:
        return {tag: value for tag, value in data.items() if tag not in YEAR_BALANCE_TAGS}


# the coordinator of a loaded config entry is stored as its runtime_data
type WaterkotteConfigEntry = ConfigEntry[WKHPDataUpdateCoordinator]


class WKHPDataUpdateCoordinator(DataUpdateCoordinator[dict[WKHPTag, dict]]):
    """The values of the tags (of all enabled entities) - polled from the heat pump"""

    config_entry: WaterkotteConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: WaterkotteConfigEntry):
        # the serial number of the heat pump (or the config entry id, when the heat pump does not provide a
        # serial number) is used for the device identifier and as prefix of the unique_id's of the entities
        serial = config_entry.data.get(CONF_SERIAL)
        if not is_real_serial(serial):
            serial = None
        self.serial = serial
        self.unique_id_base = serial if serial is not None else config_entry.entry_id

        self.available_features = [feature for flag, feature in _FEATURE_FLAGS.items() if config_entry.data.get(flag)]
        _LOGGER.debug("available_features: %s", self.available_features)

        def setting(key, default):
            # settings that have not been changed via the options yet, are taken from the initial configuration
            return config_entry.options.get(key, config_entry.data.get(key, default))

        self.add_readonly_copies = setting(CONF_ADD_READONLY_COPIES, False)
        self.read_only = setting(CONF_READ_ONLY, False)
        self.monthly_statistics = setting(CONF_MONTHLY_STATISTICS, False)

        # the connection data (incl. the credentials) is only stored in the config entry data (not in the options)
        _system_type = config_entry.data.get(CONF_SYSTEMTYPE, ECOTOUCH)
        _host = config_entry.data.get(CONF_HOST)
        # by default, EASYCON does not have a password option... BUT if the user specified login credentials,
        # then we must use them!
        _default_credential = None if _system_type == EASYCON else "waterkotte"
        _user = config_entry.data.get(CONF_USERNAME, _default_credential)
        _pwd = config_entry.data.get(CONF_PASSWORD, _default_credential)
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

        # the heat pump allows only a few sessions - so it is accessed by one request at a time (the regular updates,
        # the monthly statistics, the service actions and the writes of the entities)
        self._lock = asyncio.Lock()
        self._year_balance_guard = YearBalanceGuard()

        # update_interval can be adjusted in the options
        super().__init__(hass, _LOGGER, config_entry=config_entry, name=DOMAIN,
                         update_interval=timedelta(seconds=max(MIN_POLLING_INTERVAL, setting(CONF_POLLING_INTERVAL, 60))))

    async def _async_setup(self) -> None:
        """Connect to the heat pump (once, during the first refresh)."""
        async with self._lock:
            await self._async_setup_locked()

    async def _async_setup_locked(self) -> None:
        async with self._map_errors():
            # the EasyCon interface has no login - so we also read a tag to check the connection
            await self.bridge.async_check_login()
            if not await self.bridge.async_read_values([WKHPTag.VERSION_BIOS]):
                raise UpdateFailed(f"no data could be read from the heat pump at {self.config_entry.data.get(CONF_HOST)}")

        await self._async_complete_device_information()

        # we check if the operation hours will be returned as TOTAL's (and if this is
        # not the case, we enable it! - but not in read-only mode)
        if self.read_only:
            return
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
        tags = set(self.async_contexts())
        check_year = not tags.isdisjoint(YEAR_BALANCE_TAGS)
        if check_year:
            tags.update(_YEAR_CHECK_TAGS)
        self.bridge.tags = list(tags)
        _LOGGER.debug("number of entities to query: %s (1 entity can consist of n-tags)", len(self.bridge.tags))
        async with self._lock:
            async with self._map_errors():
                result = await self.bridge.async_get_data()
            _LOGGER.debug("number of entity values read: %s", len(result))

            # only the values that have been read in this update - the entities of the other tags are unavailable
            # (and don't show an outdated value)
            data = {tag: value for tag, value in result.items() if _is_ok(value)}

            # a value, that could be read in the last update but not in this one, is read again (once) - so that a
            # single failed request doesn't make the entity unavailable for a moment
            lost = [tag for tag in tags if tag in (self.data or {}) and tag not in data]
            if lost:
                _LOGGER.debug("read again: %s", {tag.name: (result.get(tag) or {}).get("status") for tag in lost})
                try:
                    again = await self.bridge.async_read_values(lost)
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.debug("the values could not be read again: %s %s", type(err).__name__, err)
                    again = {}
                data.update({tag: value for tag, value in again.items() if _is_ok(value)})

        if check_year:
            data = self._year_balance_guard.filter(data, time.monotonic())
        return data

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
            async with self._lock:
                return await self.bridge.async_read_values(tags)
        except (StatusException, aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="read_failed",
                                     translation_placeholders={"error": f"{type(err).__name__} {err}"}) from err

    async def async_write_tag(self, tag: WKHPTag, value):
        """Write the value of a tag to the heat pump - the errors are raised as HomeAssistantError"""
        placeholders = {"tag": tag.name, "value": str(value)}
        if self.read_only:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="read_only",
                                         translation_placeholders=placeholders)
        try:
            async with self._lock:
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
