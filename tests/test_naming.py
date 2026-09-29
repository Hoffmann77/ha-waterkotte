"""Tests for the names of the config entries and devices of the Waterkotte Heatpump integration."""
import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump.const import DOMAIN
from custom_components.waterkotte_heatpump.naming import device_name, entry_title
from .conftest import HOST, SERIAL


@pytest.mark.parametrize(
    ("series", "serial", "expected"),
    [
        ("Ai1+", SERIAL, "Waterkotte Ai1+ (WE15123456)"),
        ("Ai1+", None, "Waterkotte Ai1+"),
        ("UNKNOWN_SERIES_42", SERIAL, "Waterkotte (WE15123456)"),
        ("None", None, "Waterkotte"),
        (None, None, "Waterkotte"),
    ],
)
def test_entry_title(series: str | None, serial: str | None, expected: str) -> None:
    """Test that unknown parts are left out of the config entry title."""
    assert entry_title(series, serial) == expected


async def test_device_name(hass: HomeAssistant) -> None:
    """Test that the serial number is only added to the device name, when more than one heat pump is configured."""
    first = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_HOST: HOST})
    first.add_to_hass(hass)
    assert device_name(hass, first, SERIAL) == "Waterkotte"

    second = MockConfigEntry(domain=DOMAIN, unique_id="WE15999999", data={CONF_HOST: "192.168.1.60"})
    second.add_to_hass(hass)
    assert device_name(hass, second, "WE15999999") == "Waterkotte WE15999999"
    assert device_name(hass, first, SERIAL) == "Waterkotte WE15123456"

    # without a serial number, Home Assistant will add a suffix to the entity_id's (e.g. '_2')
    assert device_name(hass, second, None) == "Waterkotte"
