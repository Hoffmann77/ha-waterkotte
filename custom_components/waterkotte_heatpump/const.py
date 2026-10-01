from typing import Final

from custom_components.waterkotte_heatpump.pywaterkotte_ha.const import FOUR_STEPS_MODES, SIX_STEPS_MODES
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)

# Base component constants
NAME: Final = "Waterkotte Heatpump [+2020]"
DOMAIN: Final = "waterkotte_heatpump"

TITLE: Final = "Waterkotte"
DEVICE_NAME: Final = "Waterkotte"
MANUFACTURER: Final = "Waterkotte"
ISSUE_URL: Final = "https://github.com/marq24/ha-waterkotte/issues"

CONFIG_VERSION: Final = 2
CONFIG_MINOR_VERSION: Final = 2

FEATURE_DISINFECTION: Final = "DISINFECTION"
FEATURE_HEATING_CURVE: Final = "HEATING_CURVE"
FEATURE_VENT: Final = "VENT"
FEATURE_POOL: Final = "POOL"

# Device classes
DEVICE_CLASS_ENUM: Final = "enum"

# States
STATE_AUTO: Final = "auto"
STATE_MANUAL: Final = "manual"
STATE_OFF: Final = "off"
# # #### Enum Options ####
ENUM_OFFAUTOMANUAL: Final = [STATE_OFF, STATE_AUTO, STATE_MANUAL]
ENUM_POOL_MODE: Final = list(FOUR_STEPS_MODES.values())
ENUM_HEATING_MODE: Final = list(SIX_STEPS_MODES.values())
ENUM_VENT_OPERATION_MODE: Final = list(SIX_STEPS_MODES.values())
ENUM_OPTIONS_0_1: Final = ["0", "1"]
ENUM_OPTIONS_0_2: Final = ["0", "1", "2"]
ENUM_OPTIONS_0_4: Final = ["0", "1", "2", "3", "4"]


# Configuration and options
CONF_POLLING_INTERVAL: Final = "polling_interval"
# the minimal polling interval in seconds
MIN_POLLING_INTERVAL: Final = 10
CONF_TAGS_PER_REQUEST: Final = "tags_per_request"
CONF_BIOS: Final = "bios"
CONF_FW: Final = "fw"
CONF_SERIAL: Final = "serial"
CONF_SERIES: Final = "series"
CONF_SYSTEMTYPE: Final = "system_type"
# only used for the migration of old config entries (the optional schedule entities have been removed)
CONF_ADD_SCHEDULE_ENTITIES: Final = "add_schedule_entities"
# only used for the migration of old config entries (the serial number is always part of the unique_id's now)
CONF_ADD_SERIAL_AS_ID = "add_serial_as_id"
CONF_USE_DISINFECTION: Final = "use_disinfection"
CONF_USE_HEATING_CURVE: Final = "use_heating_curve"
CONF_USE_VENT: Final = "use_vent"
CONF_USE_POOL: Final = "use_pool"

# the settings that can be changed via the options flow - everything else (like the host) is only stored
# in the data of the config entry
OPTIONS_KEYS: Final = (CONF_USERNAME, CONF_PASSWORD, CONF_POLLING_INTERVAL, CONF_TAGS_PER_REQUEST)

STARTUP_MESSAGE: Final = f"""
-------------------------------------------------------------------
{NAME}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""

SERVICE_SET_HOLIDAY: Final = "set_holiday"
SERVICE_SET_DISINFECTION_START_TIME: Final = "set_disinfection_start_time"
SERVICE_GET_ENERGY_BALANCE: Final = "get_energy_balance"
SERVICE_GET_ENERGY_BALANCE_MONTHLY: Final = "get_energy_balance_monthly"

TENTH_STEP = 0.1
FIFTH_STEP = 0.5

PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]
