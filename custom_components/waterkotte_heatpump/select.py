import logging
from dataclasses import dataclass
from typing import Final

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from . import WaterkotteConfigEntry
from .const import (
    DEVICE_CLASS_ENUM,
    ENUM_HEATING_MODE,
    ENUM_OFFAUTOMANUAL,
    ENUM_OPTIONS_0_1,
    ENUM_OPTIONS_0_2,
    ENUM_OPTIONS_0_4,
    ENUM_POOL_MODE,
    ENUM_VENT_OPERATION_MODE,
    FEATURE_POOL,
    FEATURE_VENT,
)
from .entity import WKHPBaseEntity, WKHPEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ExtSelectEntityDescription(WKHPEntityDescription, SelectEntityDescription):
    """The description of an entity of the platform (with the tag of the heat pump)."""


SELECT_SENSORS: Final = [
    ExtSelectEntityDescription(
        key="ENABLE_COOLING",
        tag=WKHPTag.ENABLE_COOLING,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=True,
        options=ENUM_OFFAUTOMANUAL,
    ),
    ExtSelectEntityDescription(
        key="ENABLE_HEATING",
        tag=WKHPTag.ENABLE_HEATING,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=True,
        options=ENUM_OFFAUTOMANUAL,
    ),
    ExtSelectEntityDescription(
        key="ENABLE_PV",
        tag=WKHPTag.ENABLE_PV,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_OFFAUTOMANUAL,
    ),
    ExtSelectEntityDescription(
        key="ENABLE_WARMWATER",
        tag=WKHPTag.ENABLE_WARMWATER,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=True,
        options=ENUM_OFFAUTOMANUAL,
    ),
    ExtSelectEntityDescription(
        key="ENABLE_POOL",
        tag=WKHPTag.ENABLE_POOL,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_OFFAUTOMANUAL,
        feature=FEATURE_POOL
    ),
    ExtSelectEntityDescription(
        key="ENABLE_EXTERNAL_HEATER",
        tag=WKHPTag.ENABLE_EXTERNAL_HEATER,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=True,
        options=ENUM_OFFAUTOMANUAL,
    ),
    ExtSelectEntityDescription(
        key="ENABLE_MIXING1",
        tag=WKHPTag.ENABLE_MIXING1,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=True,
        options=ENUM_OFFAUTOMANUAL,
    ),
    ExtSelectEntityDescription(
        key="ENABLE_MIXING2",
        tag=WKHPTag.ENABLE_MIXING2,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_OFFAUTOMANUAL,
    ),
    ExtSelectEntityDescription(
        key="ENABLE_MIXING3",
        tag=WKHPTag.ENABLE_MIXING3,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_OFFAUTOMANUAL,
    ),
    # I265
    ExtSelectEntityDescription(
        key="TEMPERATURE_HEATING_MODE",
        tag=WKHPTag.TEMPERATURE_HEATING_MODE,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=True,
        options=ENUM_HEATING_MODE,
    ),
    ExtSelectEntityDescription(
        key="BASICVENT_OPERATION_MODE_I4582",
        tag=WKHPTag.BASICVENT_OPERATION_MODE_I4582,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_VENT_OPERATION_MODE,
        feature=FEATURE_VENT
    ),
    ExtSelectEntityDescription(
        key="BASICVENT_OPERATION_MODE_ALT",
        tag=WKHPTag.BASICVENT_OPERATION_MODE_ALT,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_VENT_OPERATION_MODE,
        feature=FEATURE_VENT
    ),
    # Service-Sourcepump
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_I1281",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_I1281,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_2,
    ),
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_MODE_I1764",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_MODE_I1764,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_2,
    ),
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_HEATMODE_REGULATION_BY_I1752",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_HEATMODE_REGULATION_BY_I1752,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_1,
    ),
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_HEATMODE_CONTROL_BEHAVIOUR_D789",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_HEATMODE_CONTROL_BEHAVIOUR_D789,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_1,
    ),
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_HEATMODE_REGULATION_START_D996",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_HEATMODE_REGULATION_START_D996,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_1,
    ),
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_COOLINGMODE_REGULATION_BY_I2102",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_COOLINGMODE_REGULATION_BY_I2102,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_2,
    ),
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_COOLINGMODE_CONTROL_BEHAVIOUR_D995",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_COOLINGMODE_CONTROL_BEHAVIOUR_D995,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_1,
    ),
    ExtSelectEntityDescription(
        key="PUMPSERVICE_SOURCEPUMP_COOLINGMODE_REGULATION_START_D997",
        tag=WKHPTag.PUMPSERVICE_SOURCEPUMP_COOLINGMODE_REGULATION_START_D997,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_1,
    ),
    ExtSelectEntityDescription(
        key="ROOM_INFLUENCE_A101_OR_I264",
        tag=WKHPTag.ROOM_INFLUENCE_A101_OR_I264,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_OPTIONS_0_4,
    ),
    ExtSelectEntityDescription(
        key="TEMPERATURE_POOL_MODE",
        tag=WKHPTag.TEMPERATURE_POOL_MODE,
        device_class=DEVICE_CLASS_ENUM,
        entity_registry_enabled_default=False,
        options=ENUM_POOL_MODE,
    ),
]



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
