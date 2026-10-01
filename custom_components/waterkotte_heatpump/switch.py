import logging
from dataclasses import dataclass
from typing import Final

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from . import WaterkotteConfigEntry
from .const import FEATURE_DISINFECTION, FEATURE_VENT
from .entity import WKHPBaseEntity, WKHPEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ExtSwitchEntityDescription(WKHPEntityDescription, SwitchEntityDescription):
    """The description of an entity of the platform (with the tag of the heat pump)."""


SWITCH_SENSORS: Final = [
    ExtSwitchEntityDescription(
        key="HOLIDAY_ENABLED",
        tag=WKHPTag.HOLIDAY_ENABLED,
        entity_registry_enabled_default=True
    ),
    ExtSwitchEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_1MO",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_1MO,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
    ExtSwitchEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_2TU",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_2TU,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
    ExtSwitchEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_3WE",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_3WE,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
    ExtSwitchEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_4TH",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_4TH,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
    ExtSwitchEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_5FR",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_5FR,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
    ExtSwitchEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_6SA",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_6SA,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
    ExtSwitchEntityDescription(
        key="SCHEDULE_WATER_DISINFECTION_7SU",
        tag=WKHPTag.SCHEDULE_WATER_DISINFECTION_7SU,
        entity_registry_enabled_default=False,
        feature=FEATURE_DISINFECTION
    ),
    ExtSwitchEntityDescription(
        key="PERMANENT_HEATING_CIRCULATION_PUMP_WINTER_D1103",
        tag=WKHPTag.PERMANENT_HEATING_CIRCULATION_PUMP_WINTER_D1103,
        entity_registry_enabled_default=True
    ),
    ExtSwitchEntityDescription(
        key="PERMANENT_HEATING_CIRCULATION_PUMP_SUMMER_D1104",
        tag=WKHPTag.PERMANENT_HEATING_CIRCULATION_PUMP_SUMMER_D1104,
        entity_registry_enabled_default=False
    ),
    ExtSwitchEntityDescription(
        key="BASICVENT_FILTER_CHANGE_OPERATING_HOURS_RESET_D1544",
        tag=WKHPTag.BASICVENT_FILTER_CHANGE_OPERATING_HOURS_RESET_D1544,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    ExtSwitchEntityDescription(
        key="BASICVENT_INCOMING_FAN_MANUAL_MODE",
        tag=WKHPTag.BASICVENT_INCOMING_FAN_MANUAL_MODE,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    ExtSwitchEntityDescription(
        key="BASICVENT_OUTGOING_FAN_MANUAL_MODE",
        tag=WKHPTag.BASICVENT_OUTGOING_FAN_MANUAL_MODE,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    # Service-Sourcepump
    ExtSwitchEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_CABLE_BREAK_MONITORING_D881",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_CABLE_BREAK_MONITORING_D881,
        entity_registry_enabled_default=False
    ),
    ExtSwitchEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_REGENERATION_D1294",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_REGENERATION_D1294,
        entity_registry_enabled_default=False
    ),
]



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
