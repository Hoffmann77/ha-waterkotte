"""Tests for the values of the energy balance of a year (the year can be changed in the web interface)."""
from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump.const import CONF_SERIAL, CONF_SYSTEMTYPE, DOMAIN
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .conftest import HOST, SERIAL


def _data(balance_year: int | None, consumption: float = 3026.7, year: int = 26) -> dict:
    values = {
        WKHPTag.DATE_YEAR: year,
        WKHPTag.ENERGY_CONSUMPTION_TOTAL_YEAR: consumption,
        WKHPTag.TEMPERATURE_OUTSIDE: 7.5,
    }
    if balance_year is not None:
        values[WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO] = balance_year
    return {tag: {"value": value, "status": "S_OK"} for tag, value in values.items()}


def _state(hass: HomeAssistant, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_{key}".lower())
    return hass.states.get(entity_id).state


async def test_other_year_selected(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the yearly values are unavailable, while the balance of an older year is selected in the web
    interface - and that the other values are not affected."""
    mock_bridge.async_get_data.return_value = _data(2026)
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # the selected year is read together with the yearly values
    assert WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO in mock_bridge.tags
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == "3026.7"

    # someone looks at the balance of 2024 in the web interface
    mock_bridge.async_get_data.return_value = _data(2024)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == STATE_UNAVAILABLE
    assert _state(hass, "TEMPERATURE_OUTSIDE") == "7.5"

    # the current year is selected again: the values are updated after they have settled
    mock_bridge.async_get_data.return_value = _data(2026, consumption=0.0)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == STATE_UNAVAILABLE
    mock_bridge.async_get_data.return_value = _data(2026, consumption=3026.8)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == "3026.8"

    # the year can't be read: the values are shown (like before)
    mock_bridge.async_get_data.return_value = _data(None, consumption=3026.9)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == "3026.9"


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry, data: dict) -> str:
    entry.runtime_data.bridge.async_get_data.return_value = data
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    return _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR")


async def test_implausible_values(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the values of another year are discarded, when the heat pump still reports the current year."""
    mock_bridge.async_get_data.return_value = _data(2026, consumption=5068.782)
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "ENERGY_CONSUMPTION_TOTAL_YEAR") == "5068.782"

    # the values of another year - with the current year
    assert await _refresh(hass, entry, _data(2026, consumption=16739.35)) == STATE_UNAVAILABLE
    assert await _refresh(hass, entry, _data(2026, consumption=0.0)) == STATE_UNAVAILABLE
    assert await _refresh(hass, entry, _data(2026, consumption=5068.833)) == "5068.833"

    # the counters are reset with a new year
    assert await _refresh(hass, entry, _data(2027, consumption=0.1, year=27)) == "0.1"

    # the counters really changed (e.g. reset by the service): accepted after 3 updates
    assert await _refresh(hass, entry, _data(2027, consumption=500.0, year=27)) == STATE_UNAVAILABLE
    assert await _refresh(hass, entry, _data(2027, consumption=500.0, year=27)) == STATE_UNAVAILABLE
    assert await _refresh(hass, entry, _data(2027, consumption=500.0, year=27)) == "500.0"


async def test_total_of_all_years_selected(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that the yearly values are unavailable, while the total of all years ('Gesamt') is selected in the web
    interface - the selected year doesn't change then."""
    mock_bridge.async_get_data.return_value = _data(2026, consumption=5068.782)
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=3, unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_SERIAL: SERIAL, CONF_SYSTEMTYPE: "ECOTOUCH"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert WKHPTag.COP_HEATPUMP_TOTAL_SELECTED in mock_bridge.tags

    total = _data(2026, consumption=16739.35)
    total[WKHPTag.COP_HEATPUMP_TOTAL_SELECTED] = {"value": True, "status": "S_OK"}
    # the total stays selected longer than the implausible values are discarded
    for _ in range(5):
        assert await _refresh(hass, entry, total) == STATE_UNAVAILABLE

    current = _data(2026, consumption=5068.9)
    current[WKHPTag.COP_HEATPUMP_TOTAL_SELECTED] = {"value": False, "status": "S_OK"}
    assert await _refresh(hass, entry, current) == STATE_UNAVAILABLE
    assert await _refresh(hass, entry, current) == "5068.9"
