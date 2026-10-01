import datetime
import logging
from homeassistant.core import ServiceCall, ServiceResponse

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag

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


def _value(res: dict, tag: WKHPTag):
    """The value of a tag from a read result - or 'unknown', if the tag could not be read"""
    return res.get(tag, {"value": "unknown"})["value"]


class WaterkotteHeatpumpService():
    """waterkotte_heatpump switch class."""

    def __init__(self, hass, config, coordinator):  # pylint: disable=unused-argument
        """Initialize the sensor."""
        self._hass = hass
        self._config = config
        self._coordinator = coordinator

    async def set_holiday(self, call: ServiceCall):
        """Handle the service call."""
        start = call.data.get('start', None)
        end = call.data.get('end', None)
        if start is not None and end is not None:
            start = datetime.datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
            end = datetime.datetime.strptime(end, '%Y-%m-%d %H:%M:%S')
            _LOGGER.debug(f"set_holiday start: {start} end: {end}")
            try:
                await self._coordinator.async_write_tag(WKHPTag.HOLIDAY_START_TIME, start)
                await self._coordinator.async_write_tag(WKHPTag.HOLIDAY_END_TIME, end)
                await self._coordinator.async_refresh()
            except ValueError as exc:
                if call.return_response:
                    return {"error": str(exc), "date": str(datetime.datetime.now().time())}

            if call.return_response:
                return {"success": "yes", "date": str(datetime.datetime.now().time())}

        if call.return_response:
            return {"error": "No Start and/or End Time", "date": str(datetime.datetime.now().time())}

    async def set_disinfection_start_time(self, call: ServiceCall):
        start_time = self._get_time("starthhmm", call)
        if start_time is not None:
            _LOGGER.debug(f"set_disinfection_start_time: {start_time}")
            try:
                await self._coordinator.async_write_tag(WKHPTag.SCHEDULE_WATER_DISINFECTION_START_TIME, start_time)
                await self._coordinator.async_refresh()
                if call.return_response:
                    return {
                        "success": "yes",
                        "date": str(datetime.datetime.now().time())
                    }
            except ValueError as exe:
                if call.return_response:
                    return {"error": str(exe), "date": str(datetime.datetime.now().time())}
        else:
            if call.return_response:
                return {"error": "no start_time provided", "date": str(datetime.datetime.now().time())}

    def _get_time(self, key: str, call: ServiceCall):
        a_time = call.data.get(key, None)
        if a_time is not None:
            temp = str(a_time)
            if temp.startswith("24:"):
                return datetime.time.max
            else:
                return datetime.time.fromisoformat(temp)
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
