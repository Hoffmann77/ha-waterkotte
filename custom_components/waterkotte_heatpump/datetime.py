"""The date and time values of the heat pump, that can be changed (the holiday)."""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from homeassistant.components.datetime import DateTimeEntity, DateTimeEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .coordinator import WaterkotteConfigEntry
from .entity import WKHPBaseEntity, WKHPEntityDescription

_LOGGER = logging.getLogger(__name__)

# one write at a time (the heat pump allows only a few sessions) - the entities are updated by the coordinator
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ExtDateTimeEntityDescription(WKHPEntityDescription, DateTimeEntityDescription):
    """The description of an entity of the platform (with the tag of the heat pump)."""


DATETIME_ENTITIES: Final = [
    ExtDateTimeEntityDescription(
        key="HOLIDAY_START_TIME",
        tag=WKHPTag.HOLIDAY_START_TIME,
    ),
    ExtDateTimeEntityDescription(
        key="HOLIDAY_END_TIME",
        tag=WKHPTag.HOLIDAY_END_TIME,
    ),
]


async def async_setup_entry(hass: HomeAssistant, config_entry: WaterkotteConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback):
    _LOGGER.debug("DATETIME async_setup_entry")
    coordinator = config_entry.runtime_data
    async_add_entities(WKHPDateTime(coordinator, description) for description in DATETIME_ENTITIES)


class WKHPDateTime(WKHPBaseEntity, DateTimeEntity):

    @property
    def native_value(self) -> datetime | None:
        value = self._tag_value
        if not isinstance(value, datetime):
            return None
        # the heat pump provides the local time
        return value.replace(tzinfo=dt_util.get_default_time_zone())

    async def async_set_value(self, value: datetime) -> None:
        # the heat pump expects the local time (without time zone)
        await self.coordinator.async_write_tag(self.wkhp_tag, dt_util.as_local(value).replace(tzinfo=None))
