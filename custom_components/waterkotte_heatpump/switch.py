import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from . import WaterkotteConfigEntry
from .entity import WKHPBaseEntity
from .const import SWITCH_SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback):
    _LOGGER.debug("SWITCH async_setup_entry")
    coordinator = config_entry.runtime_data
    async_add_entities(WKHPSwitch(coordinator, description) for description in SWITCH_SENSORS)


class WKHPSwitch(WKHPBaseEntity, SwitchEntity):

    async def async_turn_on(self, **kwargs):
        """Turn on the switch."""
        try:
            await self.coordinator.async_write_tag(self.wkhp_tag, True)
        except ValueError:
            return "unavailable"

    async def async_turn_off(self, **kwargs):
        """Turn off the switch."""
        try:
            await self.coordinator.async_write_tag(self.wkhp_tag, False)
        except ValueError:
            return "unavailable"

    @property
    def is_on(self) -> bool | None:
        return self._tag_value
