import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import WKHPBaseEntity
from .const import DOMAIN, SELECT_SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    _LOGGER.debug("SELECT async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    add_entity_cb(WKHPSelect(coordinator, description) for description in SELECT_SENSORS)


class WKHPSelect(WKHPBaseEntity, SelectEntity):

    @property
    def current_option(self) -> str | None:
        value = self._tag_value
        if value is None:
            return "unknown"
        if isinstance(value, bool):
            # for "switches" that we want to show as selects, we need to convert
            # the bool True/False to 1 and 0
            return "1" if value else "0"
        return str(value)

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.async_write_tag(self.wkhp_tag, option, self)
        except ValueError:
            return "unavailable"
