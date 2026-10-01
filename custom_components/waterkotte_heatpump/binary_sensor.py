import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import WKHPBaseEntity
from .const import DOMAIN, BINARY_SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    _LOGGER.debug("BINARY_SENSOR async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    add_entity_cb(WKHPBinarySensor(coordinator, description) for description in BINARY_SENSORS)


class WKHPBinarySensor(WKHPBaseEntity, BinarySensorEntity):

    @property
    def is_on(self) -> bool:
        value = self._tag_value
        if isinstance(value, bool):
            return value
        # parse anything else then 'on' to False!
        return isinstance(value, str) and value.lower() == "on"
