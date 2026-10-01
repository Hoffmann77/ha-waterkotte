"""Service actions of the Waterkotte Heatpump integration."""
import datetime
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .const import (
    DOMAIN,
    SERVICE_SET_HOLIDAY,
    SERVICE_SET_DISINFECTION_START_TIME,
    SERVICE_GET_ENERGY_BALANCE,
    SERVICE_GET_ENERGY_BALANCE_MONTHLY,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)

# the monthly values: key in the service response -> prefix of the 12 tags (one tag per month: '<prefix>01'...'<prefix>12')
_MONTHLY_TAG_PREFIXES = {
    "cop": "ENG_HEATPUMP_COP_MONTH",
    "compressor": "ENG_CONSUMPTION_COMPRESSOR",
    "sourcepump": "ENG_CONSUMPTION_SOURCEPUMP",
    "externalheater": "ENG_CONSUMPTION_EXTERNALHEATER",
    "heating": "ENG_PRODUCTION_HEATING",
    "warmwater": "ENG_PRODUCTION_WARMWATER",
    "pool": "ENG_PRODUCTION_POOL",
}
_MONTHS = range(1, 13)


def _time_hhmm(value) -> datetime.time:
    """A time of the day - '24:00' is the end of the day"""
    value = str(value)
    if value.startswith("24:"):
        return datetime.time.max
    try:
        return datetime.time.fromisoformat(value)
    except ValueError as err:
        raise vol.Invalid(f"invalid time: {value}") from err


# the config entry is optional - it's only required, when more than one heat pump is configured
_BASE_SCHEMA = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}

_SERVICES = {
    SERVICE_SET_HOLIDAY: (
        vol.Schema({**_BASE_SCHEMA, vol.Required("start"): cv.datetime, vol.Required("end"): cv.datetime}),
        SupportsResponse.OPTIONAL,
    ),
    SERVICE_SET_DISINFECTION_START_TIME: (
        vol.Schema({**_BASE_SCHEMA, vol.Required("starthhmm"): _time_hhmm}),
        SupportsResponse.OPTIONAL,
    ),
    SERVICE_GET_ENERGY_BALANCE: (vol.Schema(_BASE_SCHEMA), SupportsResponse.ONLY),
    SERVICE_GET_ENERGY_BALANCE_MONTHLY: (vol.Schema(_BASE_SCHEMA), SupportsResponse.ONLY),
}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the service actions of the integration."""

    async def handle(call: ServiceCall) -> ServiceResponse:
        service = WaterkotteHeatpumpService(_get_coordinator(hass, call))
        return await getattr(service, call.service)(call)

    for name, (schema, supports_response) in _SERVICES.items():
        hass.services.async_register(DOMAIN, name, handle, schema=schema, supports_response=supports_response)


def _get_coordinator(hass: HomeAssistant, call: ServiceCall):
    """The coordinator of the heat pump, the service action is called for."""
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id is None:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if len(entries) != 1:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="config_entry_required")
        return entries[0].runtime_data

    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="config_entry_not_found",
                                     translation_placeholders={"entry_id": entry_id})
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="config_entry_not_loaded",
                                     translation_placeholders={"title": entry.title})
    return entry.runtime_data


def _value(res: dict, tag: WKHPTag):
    """The value of a tag from a read result - or 'unknown', if the tag could not be read"""
    return res.get(tag, {"value": "unknown"})["value"]


def _now() -> str:
    return str(datetime.datetime.now().time())


class WaterkotteHeatpumpService:
    """The service actions for one heat pump (the methods have the names of the service actions)."""

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def set_holiday(self, call: ServiceCall):
        """Handle the service call."""
        start = call.data["start"]
        end = call.data["end"]
        _LOGGER.debug(f"set_holiday start: {start} end: {end}")
        try:
            await self._coordinator.async_write_tag(WKHPTag.HOLIDAY_START_TIME, start)
            await self._coordinator.async_write_tag(WKHPTag.HOLIDAY_END_TIME, end)
            await self._coordinator.async_refresh()
        except ValueError as exc:
            if call.return_response:
                return {"error": str(exc), "date": _now()}
            return None

        if call.return_response:
            return {"success": "yes", "date": _now()}
        return None

    async def set_disinfection_start_time(self, call: ServiceCall):
        start_time = call.data["starthhmm"]
        _LOGGER.debug(f"set_disinfection_start_time: {start_time}")
        try:
            await self._coordinator.async_write_tag(WKHPTag.SCHEDULE_WATER_DISINFECTION_START_TIME, start_time)
            await self._coordinator.async_refresh()
        except ValueError as exc:
            if call.return_response:
                return {"error": str(exc), "date": _now()}
            return None

        if call.return_response:
            return {"success": "yes", "date": _now()}
        return None

    async def _read_with_retry(self, tags: list[WKHPTag]) -> dict:
        """Read the tags - and retry once, when not all tags could be read"""
        for _ in range(2):
            res = await self._coordinator.async_read_values(tags)
            if len(res) == len(tags) and all(_value(res, tag) != "unknown" for tag in tags):
                break
        return res

    async def get_energy_balance(self, call: ServiceCall) -> ServiceResponse:
        try:
            tags = [WKHPTag.COMPRESSOR_ELECTRIC_CONSUMPTION_YEAR,
                    WKHPTag.SOURCEPUMP_ELECTRIC_CONSUMPTION_YEAR,
                    WKHPTag.ELECTRICAL_HEATER_ELECTRIC_CONSUMPTION_YEAR,
                    WKHPTag.HEATING_ENERGY_PRODUCTION_YEAR,
                    WKHPTag.HOT_WATER_ENERGY_PRODUCTION_YEAR,
                    WKHPTag.POOL_ENERGY_PRODUCTION_YEAR,
                    WKHPTag.COP_HEATPUMP_YEAR,
                    WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO]
            res = await self._coordinator.async_read_values(tags)

        except ValueError:
            return "unavailable"
        return {
            "year": _value(res, WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO),
            "cop": _value(res, WKHPTag.COP_HEATPUMP_YEAR),
            "compressor": _value(res, WKHPTag.COMPRESSOR_ELECTRIC_CONSUMPTION_YEAR),
            "sourcepump": _value(res, WKHPTag.SOURCEPUMP_ELECTRIC_CONSUMPTION_YEAR),
            "externalheater": _value(res, WKHPTag.ELECTRICAL_HEATER_ELECTRIC_CONSUMPTION_YEAR),
            "heating": _value(res, WKHPTag.HEATING_ENERGY_PRODUCTION_YEAR),
            "warmwater": _value(res, WKHPTag.HOT_WATER_ENERGY_PRODUCTION_YEAR),
            "pool": _value(res, WKHPTag.POOL_ENERGY_PRODUCTION_YEAR),
        }

    async def get_energy_balance_monthly(self, call: ServiceCall) -> ServiceResponse:
        try:
            monthly = {}
            for key, prefix in _MONTHLY_TAG_PREFIXES.items():
                tags = [WKHPTag[f"{prefix}{month:02d}"] for month in _MONTHS]
                monthly[key] = (tags, await self._read_with_retry(tags))

            res_date = await self._read_with_retry([WKHPTag.DATE_MONTH,
                                                    WKHPTag.DATE_YEAR,
                                                    WKHPTag.COP_HEATPUMP_YEAR,
                                                    WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO])
        except ValueError:
            return "unavailable"

        ret = {
            "cop_year": _value(res_date, WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO),
            "cop": _value(res_date, WKHPTag.COP_HEATPUMP_YEAR),
            "heatpump_month": _value(res_date, WKHPTag.DATE_MONTH),
            "heatpump_year": _value(res_date, WKHPTag.DATE_YEAR),
        }
        for idx, month in enumerate(_MONTHS):
            ret[f"month_{month:02d}"] = {key: _value(res, tags[idx]) for key, (tags, res) in monthly.items()}
        return ret
