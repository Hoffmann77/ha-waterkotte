import logging
from datetime import datetime, time

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import WKHPBaseEntity
from .const import DOMAIN, SENSOR_SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    _LOGGER.debug("SENSOR async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    add_entity_cb(WKHPSensor(coordinator, description) for description in SENSOR_SENSORS)


class WKHPSensor(WKHPBaseEntity, SensorEntity):

    @property
    def _is_bit_field(self) -> bool:
        return self.entity_description.key == "ALARM_BITS" or self.entity_description.key == "INTERRUPTION_BITS"

    @property
    def state(self):
        # for SensorDeviceClass.DATE we will use out OWN 'state' render impl!!!
        if self.entity_description.device_class == SensorDeviceClass.DATE:
            value = self.native_value
            if value is None:
                value = "unknown"
            return value
        else:
            return SensorEntity.state.fget(self)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        value = self._tag_value
        if value is None:
            return "none" if self._is_bit_field else None
        if isinstance(value, datetime):
            return value.isoformat(sep=' ', timespec="minutes")
        if isinstance(value, time):
            return value.isoformat(timespec="minutes")
        if isinstance(value, bool):
            return "on" if value else "off"
        return value
