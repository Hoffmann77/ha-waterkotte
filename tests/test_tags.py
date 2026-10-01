"""Tests for the tags (decoding of the values of the heat pump)."""
from custom_components.waterkotte_heatpump.pywaterkotte_ha.const import TRANSLATIONS
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
