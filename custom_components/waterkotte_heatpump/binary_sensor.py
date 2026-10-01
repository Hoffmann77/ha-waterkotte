import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import WKHPBaseEntity
from .const import DOMAIN, BINARY_SENSORS

_LOGGER = logging.getLogger(__name__)

# the circulation pump sensors (without an icon in their description) - shown with a pump icon, that reflects the state
_PUMP_KEYS = frozenset({
    "STATE_HEATING_CIRCULATION_PUMP_D425",
    "STATE_BUFFERTANK_CIRCULATION_PUMP_D377",
    "STATE_POOL_CIRCULATION_PUMP_D549",
    "STATE_MIX1_CIRCULATION_PUMP_D248",
    "STATE_MIX1_CIRCULATION_PUMP_D563",
    "STATE_MIX2_CIRCULATION_PUMP_D291",
    "STATE_MIX2_CIRCULATION_PUMP_D564",
    "STATE_MIX3_CIRCULATION_PUMP_D334",
    "STATE_MIX3_CIRCULATION_PUMP_D565",
})


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

    @property
    def icon(self):
        ret = super().icon
        if ret is None and self.entity_description.key in _PUMP_KEYS:
            return "mdi:pump" if self.is_on else "mdi:pump-off"
        return ret
