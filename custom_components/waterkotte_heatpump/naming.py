"""Names of the config entries and devices of the Waterkotte Heatpump integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DEVICE_NAME, DOMAIN, TITLE


def str_or_none(value) -> str | None:
    """Device information as string - or None, if the heat pump did not provide the value"""
    if value is None or str(value) in ("", "None"):
        return None
    return str(value)


def entry_title(series: str | None, serial: str | None) -> str:
    """Title of the config entry: 'Waterkotte <series> (<serial>)' - unknown parts are left out"""
    title = TITLE
    if str_or_none(series) is not None and not series.upper().startswith("UNKNOWN"):
        title = f"{title} {series}"
    if serial is not None:
        title = f"{title} ({serial})"
    return title


def device_name(hass: HomeAssistant, config_entry: ConfigEntry, serial: str | None) -> str:
    """Name of the device: 'Waterkotte' - or 'Waterkotte <serial>', when more than one heat pump is configured.

    The device name is only used for the entity_id's of new entities (and as default name of the device), so
    the entity_id's of the first heat pump don't change, when a second heat pump is added later."""
    if serial is not None and any(
        entry.entry_id != config_entry.entry_id
        for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=False)
    ):
        return f"{DEVICE_NAME} {serial}"
    return DEVICE_NAME
