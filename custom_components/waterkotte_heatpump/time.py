"""The times of the day of the heat pump, that can be changed (the start of the water disinfection)."""
import logging
from dataclasses import dataclass
from datetime import time
from typing import Final

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .const import FEATURE_DISINFECTION
from .coordinator import WaterkotteConfigEntry
from .entity import WKHPBaseEntity, WKHPEntityDescription

_LOGGER = logging.getLogger(__name__)

# one write at a time (the heat pump allows only a few sessions) - the entities are updated by the coordinator
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ExtTimeEntityDescription(WKHPEntityDescription, TimeEntityDescription):
    """The description of an entity of the platform (with the tag of the heat pump)."""


TIME_ENTITIES: Final = [
    ExtTimeEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_START_TIME",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_START_TIME,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
]


async def async_setup_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback):
    _LOGGER.debug("TIME async_setup_entry")
    coordinator = config_entry.runtime_data
    async_add_entities(WKHPTime(coordinator, description) for description in TIME_ENTITIES)


class WKHPTime(WKHPBaseEntity, TimeEntity):

    @property
    def native_value(self) -> time | None:
        value = self._tag_value
        return value if isinstance(value, time) else None

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_write_tag(self.wkhp_tag, value)
