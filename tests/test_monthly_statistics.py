"""Tests for the monthly values of the heat pump in the long-term statistics."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.components.recorder import Recorder, get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.waterkotte_heatpump.const import CONF_MONTHLY_STATISTICS, CONF_SERIAL, CONF_SYSTEMTYPE, DOMAIN
from custom_components.waterkotte_heatpump.monthly_statistics import async_update_monthly_statistics
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .conftest import HOST, SERIAL, device_info_values



@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock: Recorder, enable_custom_integrations):
    """The recorder must be set up before Home Assistant (overrides the fixture of conftest.py)."""
    yield


COP_ID = f"{DOMAIN}:{SERIAL.lower()}_cop_monthly"
COMPRESSOR_ID = f"{DOMAIN}:{SERIAL.lower()}_compressor_consumption_monthly"
CONSUMPTION_ID = f"{DOMAIN}:{SERIAL.lower()}_consumption_monthly"
PRODUCTION_ID = f"{DOMAIN}:{SERIAL.lower()}_production_monthly"


def _heat_pump_values(month: int, year: int, april: float = 104.0, balance_year: int | None = None) -> dict:
    """The values of the heat pump: the COP of month m is 3 + m/10, the compressor consumption 100 + m, the source
    pump consumption 10 and the external heater consumption 0 (kWh) - without the production of the pool"""
    values = {WKHPTag.DATE_MONTH: month, WKHPTag.DATE_YEAR: year}
    for m in range(1, 13):
        values[WKHPTag[f"ENG_HEATPUMP_COP_MONTH{m:02d}"]] = 3 + m / 10
        values[WKHPTag[f"ENG_CONSUMPTION_COMPRESSOR{m:02d}"]] = april if m == 4 else 100.0 + m
        values[WKHPTag[f"ENG_CONSUMPTION_SOURCEPUMP{m:02d}"]] = 10.0
        values[WKHPTag[f"ENG_CONSUMPTION_EXTERNALHEATER{m:02d}"]] = 0.0
    # the heat pump did not run in December - no COP
    values[WKHPTag.ENG_HEATPUMP_COP_MONTH12] = 0.0
    if balance_year is not None:
        # the year of the energy balance, that is selected in the web interface
        values[WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO] = balance_year

    def read_values(tags):
        known = {**device_info_values(), **{tag: {"value": value, "status": "S_OK"} for tag, value in values.items()}}
        return {tag: known[tag] for tag in tags if tag in known}

    return read_values


async def _statistics(hass: HomeAssistant, statistic_id: str) -> list[dict]:
    await async_wait_recording_done(hass)
    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, datetime(2024, 1, 1, tzinfo=dt_util.UTC), None, {statistic_id}, "hour", None,
        {"mean", "sum", "state"}
    )
    return result.get(statistic_id, [])


def _start(year: int, month: int) -> float:
    return datetime(year, month, 1, tzinfo=dt_util.get_default_time_zone()).timestamp()


async def test_monthly_statistics(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the values of the last 12 months are added - and continued, when a new month starts."""
    mock_bridge.async_read_values.side_effect = _heat_pump_values(month=3, year=26)
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
        options={CONF_MONTHLY_STATISTICS: True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # the rolling window: April 2025 ... March 2026 (without the COP of December)
    cop = await _statistics(hass, COP_ID)
    assert [row["start"] for row in cop] == [
        _start(2025, m) for m in range(4, 12)] + [_start(2026, m) for m in range(1, 4)]
    assert cop[0]["mean"] == 3.4
    compressor = await _statistics(hass, COMPRESSOR_ID)
    assert len(compressor) == 12
    assert compressor[0]["state"] == 104.0
    assert compressor[-1]["sum"] == sum(100.0 + m for m in range(1, 13))
    # the total consumption (compressor + source pump + external heater) - the total production is unknown,
    # because the heat pump did not provide the production of the pool
    consumption = await _statistics(hass, CONSUMPTION_ID)
    assert [row["state"] for row in consumption] == [
        110.0 + m for m in range(4, 13)] + [110.0 + m for m in range(1, 4)]
    assert await _statistics(hass, PRODUCTION_ID) == []

    # April 2026: the window moves - the sum continues the sum of April 2025 (not provided anymore)
    mock_bridge.async_read_values.side_effect = _heat_pump_values(month=4, year=2026, april=50.0)
    await async_update_monthly_statistics(entry.runtime_data)
    compressor = await _statistics(hass, COMPRESSOR_ID)
    assert len(compressor) == 13
    assert compressor[0]["start"] == _start(2025, 4)
    assert compressor[0]["sum"] == 104.0
    assert compressor[-1]["start"] == _start(2026, 4)
    assert compressor[-1]["state"] == 50.0
    assert compressor[-1]["sum"] == compressor[-2]["sum"] + 50.0


async def test_no_monthly_statistics_by_default(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    mock_bridge.async_read_values.side_effect = _heat_pump_values(month=3, year=2026)
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await _statistics(hass, COP_ID) == []


async def test_no_monthly_statistics_of_other_year(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that nothing is added, while the balance of another year is selected in the web interface."""
    mock_bridge.async_read_values.side_effect = _heat_pump_values(month=3, year=2026, balance_year=2024)
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
        options={CONF_MONTHLY_STATISTICS: True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await _statistics(hass, COP_ID) == []
