import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from . import WaterkotteConfigEntry
from .entity import WKHPBaseEntity
from .const import SELECT_SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback):
    _LOGGER.debug("SELECT async_setup_entry")
    coordinator = config_entry.runtime_data
    async_add_entities(WKHPSelect(coordinator, description) for description in SELECT_SENSORS)


class WKHPSelect(WKHPBaseEntity, SelectEntity):

    @property
    def current_option(self) -> str | None:
        value = self._tag_value
        if value is None:
            return None
        if isinstance(value, bool):
            # for "switches" that we want to show as selects, we need to convert
            # the bool True/False to 1 and 0
            return "1" if value else "0"
        return str(value)

    async def async_select_option(self, option: str) -> None:
        value = option
        if self.wkhp_tag.tags[0].startswith("D"):
            # the digital tags ("switches" that we show as selects) are written as bool
            value = option == "1"
        try:
            await self.coordinator.async_write_tag(self.wkhp_tag, value)
        except ValueError:
            return "unavailable"
