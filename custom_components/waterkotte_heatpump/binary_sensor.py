import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from . import WaterkotteConfigEntry, WKHPBaseEntity
from .const import BINARY_SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback):
    _LOGGER.debug("BINARY_SENSOR async_setup_entry")
    coordinator = config_entry.runtime_data
    async_add_entities(WKHPBinarySensor(coordinator, description) for description in BINARY_SENSORS)


class WKHPBinarySensor(WKHPBaseEntity, BinarySensorEntity):

    @property
    def is_on(self) -> bool:
        value = self._tag_value
        if isinstance(value, bool):
            return value
        # parse anything else then 'on' to False!
        return isinstance(value, str) and value.lower() == "on"
