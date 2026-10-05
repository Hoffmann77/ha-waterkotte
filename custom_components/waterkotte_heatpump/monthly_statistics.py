"""The monthly values of the heat pump (COP and energy) as long-term statistics of Home Assistant.

The heat pump provides the values of the last 12 months (a rolling window: one tag per calendar month, the tag of the
current month contains the value of the running month). The values are added as external statistics (one row at the
start of each month), so that the history of all months is kept - and can be shown with a statistics graph card (with
the period 'month').
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics, statistics_during_period
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import WKHPDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_MONTHS = range(1, 13)


@dataclass(frozen=True)
class MonthlyStatistic:
    """A monthly value of the heat pump: the COP (mean) or an energy (sum) - or the total of other statistics."""

    key: str
    # the 12 tags of the months: '<prefix>01' (January) ... '<prefix>12' (December) - None for a total
    tag_prefix: str | None
    name: str
    is_energy: bool
    # the keys of the statistics, whose sum is this statistic (the heat pump provides no monthly total)
    parts: tuple[str, ...] = ()

    def tags(self) -> list[WKHPTag]:
        if self.tag_prefix is None:
            return []
        return [WKHPTag[f"{self.tag_prefix}{month:02d}"] for month in _MONTHS]


MONTHLY_STATISTICS = [
    MonthlyStatistic("cop_monthly", "ENG_HEATPUMP_COP_MONTH", "COP", is_energy=False),
    MonthlyStatistic("compressor_consumption_monthly", "ENG_CONSUMPTION_COMPRESSOR",
                     "Electrical consumption compressor", is_energy=True),
    MonthlyStatistic("source_pump_consumption_monthly", "ENG_CONSUMPTION_SOURCEPUMP",
                     "Electrical consumption source pump", is_energy=True),
    MonthlyStatistic("external_heater_consumption_monthly", "ENG_CONSUMPTION_EXTERNALHEATER",
                     "Electrical consumption external heater", is_energy=True),
    MonthlyStatistic("consumption_monthly", None, "Electrical consumption", is_energy=True,
                     parts=("compressor_consumption_monthly", "source_pump_consumption_monthly",
                            "external_heater_consumption_monthly")),
    MonthlyStatistic("heating_production_monthly", "ENG_PRODUCTION_HEATING",
                     "Thermal production heating", is_energy=True),
    MonthlyStatistic("hot_water_production_monthly", "ENG_PRODUCTION_WARMWATER",
                     "Thermal production hot water", is_energy=True),
    MonthlyStatistic("pool_production_monthly", "ENG_PRODUCTION_POOL",
                     "Thermal production pool", is_energy=True),
    MonthlyStatistic("production_monthly", None, "Thermal production", is_energy=True,
                     parts=("heating_production_monthly", "hot_water_production_monthly", "pool_production_monthly")),
]


def statistic_id(coordinator: WKHPDataUpdateCoordinator, statistic: MonthlyStatistic) -> str:
    return f"{DOMAIN}:{coordinator.unique_id_base}_{statistic.key}".lower()


def _number(values: dict, tag: WKHPTag) -> float | None:
    value = values.get(tag, {}).get("value")
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def month_starts(month: int, year: int) -> dict[int, datetime]:
    """The start of the months of the rolling window (the current month and the 11 months before) - in local time"""
    if year < 100:
        year += 2000
    tz = dt_util.get_default_time_zone()
    return {m: datetime(year if m <= month else year - 1, m, 1, tzinfo=tz) for m in _MONTHS}


async def async_update_monthly_statistics(coordinator: WKHPDataUpdateCoordinator) -> None:
    """Read the monthly values of the heat pump and add them to the statistics - the read errors are raised as
    HomeAssistantError"""
    hass = coordinator.hass
    tags = [WKHPTag.DATE_MONTH, WKHPTag.DATE_YEAR] + [tag for stat in MONTHLY_STATISTICS for tag in stat.tags()]
    values = await coordinator.async_read_values(tags)

    month = _number(values, WKHPTag.DATE_MONTH)
    year = _number(values, WKHPTag.DATE_YEAR)
    if month is None or year is None or not 1 <= month <= 12:
        _LOGGER.debug("monthly statistics: the date of the heat pump could not be read (%s/%s)", month, year)
        return
    starts = month_starts(int(month), int(year))
    # the months of the window (from the oldest to the current month) -> the value of the month of each statistic
    ordered = sorted(_MONTHS, key=lambda m: starts[m])
    monthly: dict[str, list[float | None]] = {}

    for stat in MONTHLY_STATISTICS:
        if stat.parts:
            # a total is only known, when all of its parts are known
            month_values = [
                None if any(monthly[part][idx] is None for part in stat.parts)
                else sum(monthly[part][idx] for part in stat.parts)
                for idx in range(len(ordered))
            ]
        else:
            month_tags = dict(zip(_MONTHS, stat.tags(), strict=True))
            month_values = [_number(values, month_tags[m]) for m in ordered]
        monthly[stat.key] = month_values

        months = [(starts[m], value) for m, value in zip(ordered, month_values, strict=True)]
        if stat.is_energy:
            await _async_add_energy(hass, coordinator, stat, months)
        else:
            _async_add_mean(hass, coordinator, stat, months)


def _metadata(coordinator: WKHPDataUpdateCoordinator, stat: MonthlyStatistic) -> StatisticMetaData:
    return StatisticMetaData(
        mean_type=StatisticMeanType.NONE if stat.is_energy else StatisticMeanType.ARITHMETIC,
        has_sum=stat.is_energy,
        name=f"{coordinator.device_info.get('name') or 'Waterkotte'} {stat.name} monthly",
        source=DOMAIN,
        statistic_id=statistic_id(coordinator, stat),
        unit_class="energy" if stat.is_energy else None,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR if stat.is_energy else None,
    )


def _async_add_mean(hass: HomeAssistant, coordinator: WKHPDataUpdateCoordinator, stat: MonthlyStatistic,
                    months: list[tuple[datetime, float | None]]) -> None:
    # a COP of 0 means, that the heat pump did not run (or has no value for the month)
    rows = [StatisticData(start=start, mean=value, min=value, max=value)
            for start, value in months if value is not None and value > 0]
    if rows:
        async_add_external_statistics(hass, _metadata(coordinator, stat), rows)


async def _async_add_energy(hass: HomeAssistant, coordinator: WKHPDataUpdateCoordinator, stat: MonthlyStatistic,
                            months: list[tuple[datetime, float | None]]) -> None:
    # the sum must continue the sum of the months before the window (that are not provided by the heat pump anymore)
    total = await _async_sum_before(hass, statistic_id(coordinator, stat), months[0][0])
    rows = []
    for start, value in months:
        if value is None:
            continue
        total += value
        rows.append(StatisticData(start=start, state=value, sum=total))
    if rows:
        async_add_external_statistics(hass, _metadata(coordinator, stat), rows)


async def _async_sum_before(hass: HomeAssistant, stat_id: str, start: datetime) -> float:
    """The sum of the last month before the start (0, when there is no older month)"""
    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start - timedelta(days=366), start, {stat_id}, "hour", None, {"sum"}
    )
    rows = result.get(stat_id)
    return float(rows[-1]["sum"] or 0.0) if rows else 0.0
