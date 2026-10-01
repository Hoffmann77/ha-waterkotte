"""Tests for the tags (decoding of the values of the heat pump)."""
import pytest

from custom_components.waterkotte_heatpump.pywaterkotte_ha.const import TRANSLATIONS
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import InvalidValueException
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag

LANG_MAP = TRANSLATIONS["en"]


def test_decode_alarms() -> None:
    """Test that the alarm bits (provided as strings by the heat pump) are decoded with the labels of the bits."""
    tag = WKHPTag.ALARM_BITS
    values = ["0"] * len(tag.tags)
    # I52: bit 0 and bit 15 (bit 13 & 14 are no alarms)
    values[0] = str((1 << 0) | (1 << 13) | (1 << 14) | (1 << 15))
    # I2608: bit 2 (as float string)
    values[1] = "4.0"

    assert tag.decode_f(tag, values, LANG_MAP) == ", ".join([
        LANG_MAP["I52"][0], LANG_MAP["I52"][15], LANG_MAP["I2608"][2],
    ])


def test_decode_no_alarms() -> None:
    tag = WKHPTag.ALARM_BITS
    assert tag.decode_f(tag, ["0"] * len(tag.tags), LANG_MAP) == ""
    assert tag.decode_f(tag, [None] * len(tag.tags), LANG_MAP) == ""


def test_monthly_tags_are_unique() -> None:
    """Test that each month has its own tag (an alias would report the value of another month)."""
    for prefix in ("ENG_HEATPUMP_COP_MONTH", "ENG_CONSUMPTION_COMPRESSOR", "ENG_CONSUMPTION_SOURCEPUMP",
                   "ENG_CONSUMPTION_EXTERNALHEATER", "ENG_PRODUCTION_HEATING", "ENG_PRODUCTION_WARMWATER",
                   "ENG_PRODUCTION_POOL"):
        tags = [WKHPTag[f"{prefix}{month:02d}"] for month in range(1, 13)]
        assert len({tag.tags[0] for tag in tags}) == 12, prefix
        assert all(tag.name == f"{prefix}{month:02d}" for month, tag in zip(range(1, 13), tags, strict=True)), prefix


@pytest.mark.parametrize(
    ("tag", "raw", "expected"),
    [
        # the raw values of the heat pump are strings
        (WKHPTag.INFO_SERIES, ["2"], "Ai1+"),
        (WKHPTag.INFO_SERIES, ["999"], "UNKNOWN_SERIES_999"),
        (WKHPTag.INFO_SERIES, [""], None),
        (WKHPTag.INFO_ID, ["0"], "Ai1 5005.4"),
        (WKHPTag.ENABLE_HEATING, ["2"], "manual"),
        (WKHPTag.ENABLE_HEATING, ["7"], "Error"),
        (WKHPTag.TEMPERATURE_POOL_MODE, ["3"], "mode3"),
        # the value after the last mode (an IndexError/KeyError before)
        (WKHPTag.TEMPERATURE_POOL_MODE, ["4"], "Error"),
        (WKHPTag.TEMPERATURE_HEATING_MODE, ["5.0"], "mode5"),
        (WKHPTag.TEMPERATURE_HEATING_MODE, [None], None),
        (WKHPTag.STATUS_HEATING, ["1"], "on"),
        (WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO, ["26"], 2026),
        (WKHPTag.COP_HEATPUMP_ACTUAL_YEAR_INFO, [None], None),
        (WKHPTag.VERSION_BIOS, ["405"], "4.05"),
        (WKHPTag.INFO_SERIAL, ["1015", "123456"], "WE15123456"),
        (WKHPTag.INFO_SERIAL, ["1015", None], None),
    ],
)
def test_decode(tag: WKHPTag, raw: list, expected) -> None:
    assert tag.decode_f(tag, raw) == expected


@pytest.mark.parametrize(
    ("tag", "value", "expected"),
    [
        (WKHPTag.ENABLE_HEATING, "auto", {"I30": "1"}),
        (WKHPTag.TEMPERATURE_POOL_MODE, "mode2", {"I527": "2"}),
        (WKHPTag.HOLIDAY_ENABLED, True, {"D420": "1"}),
        (WKHPTag.TEMPERATURE_HEATING_SETPOINT_FOR_SOLAR, 21.5, {"A1710": "215"}),
        (WKHPTag.TEMPERATURE_HEATING_SETPOINT_FOR_SOLAR, 21, {"A1710": "210"}),
    ],
)
def test_encode(tag: WKHPTag, value, expected: dict) -> None:
    encoded = {}
    tag.encode_f(tag, value, encoded)
    assert encoded == expected


@pytest.mark.parametrize(
    ("tag", "value"),
    [
        (WKHPTag.ENABLE_HEATING, "unknown_state"),
        (WKHPTag.TEMPERATURE_POOL_MODE, "mode9"),
        (WKHPTag.HOLIDAY_ENABLED, "1"),
        (WKHPTag.TEMPERATURE_HEATING_SETPOINT_FOR_SOLAR, "21.5"),
        (WKHPTag.HOLIDAY_START_TIME, "2026-12-20"),
    ],
)
def test_encode_invalid_value(tag: WKHPTag, value) -> None:
    """Test that an invalid value is raised (instead of an assert or of writing nothing)."""
    with pytest.raises(InvalidValueException):
        tag.encode_f(tag, value, {})
