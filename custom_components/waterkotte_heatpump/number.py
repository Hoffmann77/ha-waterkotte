import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import WKHPBaseEntity
from .const import DOMAIN, NUMBER_SENSORS

_LOGGER = logging.getLogger(__name__)

TEMP_ADJUST_LOOKUP = [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    _LOGGER.debug("NUMBER async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    add_entity_cb(WKHPNumber(coordinator, description) for description in NUMBER_SENSORS)


class WKHPNumber(WKHPBaseEntity, NumberEntity):

    @property
    def native_value(self) -> float | None:
        value = self._tag_value
        if value is None:
            return "unknown"
        try:
            if str(self.wkhp_tag.name).upper().endswith("_ADJUST"):
                value = TEMP_ADJUST_LOOKUP[value]
        except TypeError:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        try:
            if str(self.wkhp_tag.name).upper().endswith("_ADJUST"):
                value = TEMP_ADJUST_LOOKUP.index(value)
            if self.wkhp_tag[0][0][0] == 'I':
                value = int(value)
            await self.coordinator.async_write_tag(self.wkhp_tag, value, self)
        except ValueError:
            return "unavailable"
