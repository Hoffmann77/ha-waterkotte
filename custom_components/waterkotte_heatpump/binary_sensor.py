import logging
from dataclasses import dataclass
from typing import Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from .coordinator import WaterkotteConfigEntry
from .const import FEATURE_POOL, FEATURE_VENT
from .entity import WKHPBaseEntity, WKHPEntityDescription

_LOGGER = logging.getLogger(__name__)

# the entities are updated by the coordinator
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ExtBinarySensorEntityDescription(WKHPEntityDescription, BinarySensorEntityDescription):
    """The description of an entity of the platform (with the tag of the heat pump)."""


BINARY_SENSORS: Final = [
    ExtBinarySensorEntityDescription(
        key="STATE_SOURCEPUMP",
        tag=WKHPTag.STATE_SOURCEPUMP,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_HEATINGPUMP",
        tag=WKHPTag.STATE_HEATINGPUMP,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    # EVD: -> Überhitzungsregler
    ExtBinarySensorEntityDescription(
        key="STATE_EVD",
        tag=WKHPTag.STATE_EVD,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_COMPRESSOR",
        tag=WKHPTag.STATE_COMPRESSOR,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_COMPRESSOR2",
        tag=WKHPTag.STATE_COMPRESSOR2,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_EXTERNAL_HEATER",
        tag=WKHPTag.STATE_EXTERNAL_HEATER,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_ALARM",
        tag=WKHPTag.STATE_ALARM,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_COOLING",
        tag=WKHPTag.STATE_COOLING,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_WATER",
        tag=WKHPTag.STATE_WATER,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_POOL",
        tag=WKHPTag.STATE_POOL,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_POOL
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_SOLAR",
        tag=WKHPTag.STATE_SOLAR,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_COOLING4WAY",
        tag=WKHPTag.STATE_COOLING4WAY,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False
    ),
    # status sensors (Operation Mode 0=off, 1=on or 2=disabled)
    ExtBinarySensorEntityDescription(
        key="STATUS_HEATING",
        tag=WKHPTag.STATUS_HEATING,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATUS_WATER",
        tag=WKHPTag.STATUS_WATER,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATUS_COOLING",
        tag=WKHPTag.STATUS_COOLING,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATUS_POOL",
        tag=WKHPTag.STATUS_POOL,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_POOL
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_BLOCKING_TIME",
        tag=WKHPTag.STATE_BLOCKING_TIME,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_TEST_RUN",
        tag=WKHPTag.STATE_TEST_RUN,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=True
    ),
    # this is just indicates if the heating circulation pump is running -
    # unfortunately this can't TAG is not writable (at least write does
    # not have any effect)
    ExtBinarySensorEntityDescription(
        key="STATE_HEATING_CIRCULATION_PUMP_D425",
        tag=WKHPTag.STATE_HEATING_CIRCULATION_PUMP_D425,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_BUFFERTANK_CIRCULATION_PUMP_D377",
        tag=WKHPTag.STATE_BUFFERTANK_CIRCULATION_PUMP_D377,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_POOL_CIRCULATION_PUMP_D549",
        tag=WKHPTag.STATE_POOL_CIRCULATION_PUMP_D549,
        entity_registry_enabled_default=False,
        feature=FEATURE_POOL
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_MIX1_CIRCULATION_PUMP_D248",
        tag=WKHPTag.STATE_MIX1_CIRCULATION_PUMP_D248,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_MIX1_CIRCULATION_PUMP_D563",
        tag=WKHPTag.STATE_MIX1_CIRCULATION_PUMP_D563,
        entity_registry_enabled_default=True
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_MIX2_CIRCULATION_PUMP_D291",
        tag=WKHPTag.STATE_MIX2_CIRCULATION_PUMP_D291,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_MIX2_CIRCULATION_PUMP_D564",
        tag=WKHPTag.STATE_MIX2_CIRCULATION_PUMP_D564,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_MIX3_CIRCULATION_PUMP_D334",
        tag=WKHPTag.STATE_MIX3_CIRCULATION_PUMP_D334,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATE_MIX3_CIRCULATION_PUMP_D565",
        tag=WKHPTag.STATE_MIX3_CIRCULATION_PUMP_D565,
        entity_registry_enabled_default=False
    ),
    ExtBinarySensorEntityDescription(
        key="STATUS_SOLAR",
        tag=WKHPTag.STATUS_SOLAR,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False
    ),

    ExtBinarySensorEntityDescription(
        key="BASICVENT_STATUS_BYPASS_ACTIVE_D1432",
        tag=WKHPTag.BASICVENT_STATUS_BYPASS_ACTIVE_D1432,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    ExtBinarySensorEntityDescription(
        key="BASICVENT_STATUS_HUMIDIFIER_ACTIVE_D1433",
        tag=WKHPTag.BASICVENT_STATUS_HUMIDIFIER_ACTIVE_D1433,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    ExtBinarySensorEntityDescription(
        key="BASICVENT_STATUS_COMFORT_BYPASS_ACTIVE_D1465",
        tag=WKHPTag.BASICVENT_STATUS_COMFORT_BYPASS_ACTIVE_D1465,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    ExtBinarySensorEntityDescription(
        key="BASICVENT_STATUS_SMART_BYPASS_ACTIVE_D1466",
        tag=WKHPTag.BASICVENT_STATUS_SMART_BYPASS_ACTIVE_D1466,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    ExtBinarySensorEntityDescription(
        key="BASICVENT_STATUS_HOLIDAY_ENABLED_D1503",
        tag=WKHPTag.BASICVENT_STATUS_HOLIDAY_ENABLED_D1503,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    ),
    ExtBinarySensorEntityDescription(
        key="BASICVENT_FILTER_CHANGE_DISPLAY_D1469",
        tag=WKHPTag.BASICVENT_FILTER_CHANGE_DISPLAY_D1469,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        feature=FEATURE_VENT
    )

    # "STATUS_HEATING_CIRCULATION_PUMP",
    #     "Status circulation pump heating",
    #     tag=WKHPTag.STATUS_HEATING_CIRCULATION_PUMP,
    #     device_class=BinarySensorDeviceClass.RUNNING,
    #     #     icon="mdi:pump",
    #     entity_registry_enabled_default=True,
    #     #     #     "I1270"
    # ],
    # "STATUS_SOLAR_CIRCULATION_PUMP",
    #     "Status circulation pump Solar",
    #     tag=WKHPTag.STATUS_SOLAR_CIRCULATION_PUMP,
    #     device_class=BinarySensorDeviceClass.RUNNING,
    #     #     icon="mdi:pump",
    #     entity_registry_enabled_default=False,
    #     #     #     "I1287"
    # ],
    # "STATUS_BUFFER_TANK_CIRCULATION_PUMP",
    #     "Status circulation pump buffer tank",
    #     tag=WKHPTag.STATUS_BUFFER_TANK_CIRCULATION_PUMP,
    #     device_class=BinarySensorDeviceClass.RUNNING,
    #     icon="mdi:pump",
    #     entity_registry_enabled_default=True,
    #     #     #     "I1291"
    # ],
    # "STATUS_COMPRESSOR",
    #     "Status compressor",
    #     tag=WKHPTag.STATUS_COMPRESSOR,
    #     device_class=BinarySensorDeviceClass.RUNNING,
    #     icon="mdi:gauge",
    #     entity_registry_enabled_default=True,
    #     #     #     "I1307"
    # ],
]



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
