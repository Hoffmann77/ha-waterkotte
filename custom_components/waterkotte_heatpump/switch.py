import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import WKHPBaseEntity
from .const import DOMAIN, SWITCH_SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    _LOGGER.debug("SWITCH async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    add_entity_cb(WKHPSwitch(coordinator, description) for description in SWITCH_SENSORS)


class WKHPSwitch(WKHPBaseEntity, SwitchEntity):

    async def async_turn_on(self, **kwargs):
        """Turn on the switch."""
        try:
            await self.coordinator.async_write_tag(self.wkhp_tag, True, self)
            return self.coordinator.data[self.wkhp_tag]["value"]
        except ValueError:
            return "unavailable"

    async def async_turn_off(self, **kwargs):
        """Turn off the switch."""
        try:
            await self.coordinator.async_write_tag(self.wkhp_tag, False, self)
            return self.coordinator.data[self.wkhp_tag]["value"]
        except ValueError:
            return "unavailable"

    @property
    def is_on(self) -> bool | None:
        return self._tag_value

    @property
    def icon(self):
        """Return the icon of the sensor."""
        if self.entity_description.icon_off is not None and self.state == STATE_OFF:
            return self.entity_description.icon_off
        return super().icon
