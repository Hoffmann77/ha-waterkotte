import logging
import math
import struct
from datetime import datetime, timedelta, time
from enum import Enum
from typing import (
    NamedTuple,
    Callable,
    List,
    Collection
)

from custom_components.waterkotte_heatpump.pywaterkotte_ha.const import (
    SERIES,
    SYSTEM_IDS,
    FOUR_STEPS_MODES,
    SIX_STEPS_MODES,
)
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import (
    InvalidValueException,
)

# from aenum import Enum, extend_enum

_LOGGER: logging.Logger = logging.getLogger(__package__)


class DataTag(NamedTuple):

    def _decode_value_default(self, str_vals: List[str]):
        return self.__decode_value_default(str_vals, factor=10.0)

    def _decode_value_analog(self, str_vals: List[str]):
        return self.__decode_value_default(str_vals, factor=-1.0)

    def __decode_value_default(self, str_vals: List[str], factor: float):
        if str_vals is None:
            return None

        first_val = str_vals[0]
        if first_val is None:
            # do not check any further if for whatever reason the first value of the str_vals is None
            return None

        # for whatever reason it can be the case, that the 'str_vals' will look like this:
        # ['17714.0', '27838.0'] - so we must clean the .0
        if first_val.endswith('.0'):
            str_vals = list(map(lambda x:str(int(float(x))), str_vals))
            first_val = str_vals[0]

        first_tag = self.tags[0]
        assert first_tag[0] in ["A", "I", "D", "3"]

        if first_tag[0] == "A":
            if len(self.tags) == 1:
                # SIM VENT OperatingHour Sensors...
                # if self.tags[0] == "A4498":
                #    return float('180.000000')
                # if self.tags[0] == "A4504":
                #    return float('19')
                if factor > -1.0:
                    return float(first_val) / factor
                else:
                    return float(first_val)
            # elif len(self.tags) == 2:
            #     high_word = (int(str_vals[0]) << 16) & 0xFFFFFFFF
            #     low_word = (int(str_vals[1])) & 0xFFFF
            #     i32 = (high_word | low_word) & 0xFFFFFFFF
            #     hex_string = f"{i32:08x}"
            else:
                int_vals = [int(xxl) & 0xFFFF for xxl in str_vals]
                hex_string = "".join(f"{hex_val:04x}" for hex_val in int_vals)

            return round(float(struct.unpack("!f", bytes.fromhex(hex_string))[0]), 3)

        else:
            assert len(self.tags) == 1
            if first_tag[0] == "I":
                # single bit field
                if self.bit is not None:
                    return (int(first_val) & (1 << self.bit)) > 0

                # a bit array?
                elif self.bits is not None:
                    ret = [False] * len(self.bits)
                    for idx in range(len(self.bits)):
                        ret[idx] = (int(first_val) & (1 << self.bits[idx])) > 0
                    # _LOGGER.debug(f"BITS: {first_tag} ({first_val}) -> {ret}")
                    return ret

                # default implementation
                else:
                    return int(first_val)

            elif first_tag[0] == "D":
                if first_val == "1":
                    return True
                elif first_val == "0":
                    return False

            elif first_tag[0:6] == "3:HREG":
                # currently only supporting integers from HERG registers (only in use for manual vent speeds)
                try:
                    return int(first_val)
                except ValueError:
                    return int(float(first_val))
            else:
                raise InvalidValueException(
                    # "%s is not a valid value for %s" % (val, ecotouch_tag)
                    f"{first_val} is not a valid value for {first_tag}"
                )

        return None

    def _encode_value_default(self, value, encoded_values):
        self.__encode_value_default(value, encoded_values, factor=10)

    def __encode_value_default(self, value, encoded_values, factor: int):
        assert len(self.tags) == 1
        ecotouch_tag = self.tags[0]
        assert ecotouch_tag[0] in ["A", "I", "D", "3"]

        if ecotouch_tag[0] == "I":
            # check, if we receive a str as value, if we can convert it to int, without
            # loosing any data...
            if isinstance(value, str):
                value_as_int = int(value)
                if str(value_as_int) == value:
                    value = value_as_int
            assert isinstance(value, int)
            encoded_values[ecotouch_tag] = str(value)
        elif ecotouch_tag[0] == "D":
            assert isinstance(value, bool)
            encoded_values[ecotouch_tag] = "1" if value else "0"
        elif ecotouch_tag[0] == "A":
            assert isinstance(value, float)
            if factor > -1:
                encoded_values[ecotouch_tag] = str(int(value * factor))
            else:
                encoded_values[ecotouch_tag] = str(float(value))
        elif ecotouch_tag[0:6] == "3:HREG":
            # we force INT values for 3:HREG (only in use for 'manual vent speed' anyhow)
            encoded_values[ecotouch_tag] = str(int(value))

    def _decode_alarms(self, str_vals: List[str], lang_map: dict):
        if str_vals is None:
            return None

        alarms = []
        for error_tag_index, a_val in enumerate(str_vals):
            # the values of the heat pump are strings (e.g. '8' or '8.0')
            if a_val is None or str(a_val).strip() == "" or self.tags[error_tag_index] not in lang_map:
                continue
            if error_tag_index + 1 == len(str_vals):
                # the last error field [I2614] only contain 13 bits
                bits = range(13)
            elif error_tag_index == 0:
                # the bit13 (= "-") & bit14(= "Kommunikationstrigger") of I52 are NO alarms
                bits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15]
            else:
                bits = range(16)

            int_val = int(float(a_val))
            labels = lang_map[self.tags[error_tag_index]]
            # the labels are mapped by the bit number
            alarms.extend(str(labels[bit]) for bit in bits if int_val & (1 << bit))

        return ", ".join(alarms)

    def _decode_datetime(self, str_vals: List[str]):
        try:
            if str_vals is None or not all(v is not None for v in str_vals):
                return None

            int_vals = list(map(int, str_vals))
            if int_vals[0] < 2000:
                int_vals[0] = int_vals[0] + 2000
            next_day = False
            if int_vals[3] == 24:
                int_vals[3] = 0
                next_day = True

            dt_val = datetime(*int_vals)
            return dt_val + timedelta(days=1) if next_day else dt_val
        except BaseException as ex:
            _LOGGER.info(f"_decode_datetime(): values: '{str_vals}' caused {type(ex)}.__name__ {ex}")
            return None

    def _encode_datetime(self, value, encoded_values):
        assert isinstance(value, datetime)
        vals = [
            str(val)
            for val in [
                value.year % 100,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
            ]
        ]
        # check if result is the same
        # for i in range(len(tag.tags)):
        #     et_values[tag.tags[i]] = vals[i]
        for i, tags in enumerate(self.tags):
            encoded_values[tags] = vals[i]

    def _decode_time_hhmm(self, str_vals: List[str]):
        if str_vals is None or not all(v is not None for v in str_vals):
            return None

        int_vals = list(map(int, str_vals))
        if int_vals[0] > 23:
            int_vals[0] = 0
        if int_vals[1] > 59:
            int_vals[1] = 0
        dt = time(hour=int_vals[0], minute=int_vals[1])
        return dt

    def _encode_time_hhmm(self, value, encoded_values):
        assert isinstance(value, time)
        if value == time.max:
            vals = ["24", "0"]
        else:
            vals = [str(val) for val in [value.hour, value.minute]]

        for i, tags in enumerate(self.tags):
            encoded_values[tags] = vals[i]

    def _decode_state(self, str_vals: List[str]):
        if str_vals is None and str_vals[0] is not None:
            return None

        assert len(self.tags) == 1
        if str_vals[0] == "0":
            return "off"
        elif str_vals[0] == "1":
            return "auto"
        elif str_vals[0] == "2":
            return "manual"
        else:
            return "Error"

    def _encode_state(self, value, encoded_values):
        assert len(self.tags) == 1
        ecotouch_tag = self.tags[0]
        assert ecotouch_tag[0] in ["I"]
        if value == "off":
            encoded_values[ecotouch_tag] = "0"
        elif value == "auto":
            encoded_values[ecotouch_tag] = "1"
        elif value == "manual":
            encoded_values[ecotouch_tag] = "2"

    def _decode_four_steps_mode(self, str_vals: List[str]):
        if str_vals is None and str_vals[0] is not None:
            return None

        assert len(self.tags) == 1
        if str_vals[0] is not None:
            int_val = int(str_vals[0])
            if 0 <= int_val <= len(FOUR_STEPS_MODES):
                return FOUR_STEPS_MODES[int_val]
        return "Error"

    def _encode_four_steps_mode(self, value, encoded_values):
        assert len(self.tags) == 1
        ecotouch_tag = self.tags[0]
        # there is an alternative tag for the four/six steps mode with '3:HREG' notation
        # see https://github.com/marq24/ha-waterkotte/issues/49
        assert ecotouch_tag[0] in ["I", "3"]
        index = self._get_key_from_value(FOUR_STEPS_MODES, value)
        if index is not None:
            encoded_values[ecotouch_tag] = str(index)

    def _decode_six_steps_mode(self, str_vals: List[str]):
        if str_vals is None is None and str_vals[0] is not None:
            return None

        assert len(self.tags) == 1
        if str_vals[0] is not None:
            int_val = int(str_vals[0])
            if 0 <= int_val <= len(SIX_STEPS_MODES):
                return SIX_STEPS_MODES[int_val]
        return "Error"

    def _encode_six_steps_mode(self, value, encoded_values):
        assert len(self.tags) == 1
        ecotouch_tag = self.tags[0]
        # there is an alternative tag for the six steps mode with '3:HREG' notation
        # see https://github.com/marq24/ha-waterkotte/issues/49
        assert ecotouch_tag[0] in ["I", "3"]
        index = self._get_key_from_value(SIX_STEPS_MODES, value)
        if index is not None:
            encoded_values[ecotouch_tag] = str(index)

    @staticmethod
    def _get_key_from_value(a_dict: dict, value_to_find):
        # a very simple "find first key" of dict method...
        keys = [k for k, v in a_dict.items() if v == value_to_find]
        if keys:
            return keys[0]
        return None

    def _decode_status(self, str_vals: List[str]):
        if str_vals is None and str_vals[0] is not None:
            return None

        assert len(self.tags) == 1
        if str_vals[0] == "0":
            return "off"
        elif str_vals[0] == "1":
            return "on"
        elif str_vals[0] == "2":
            return "disabled"
        else:
            return "Error"

    def _decode_ro_series(self, str_vals: List[str]):
        if str_vals is None and str_vals[0] is not None:
            return None

        if str_vals[0]:
            if isinstance(str_vals[0], int):
                idx = int(str_vals[0])
                if len(SERIES) > idx:
                    return SERIES[idx]
                else:
                    return f"UNKNOWN_SERIES_{idx}"
        else:
            return "UNKNOWN_SERIES"

    def _decode_ro_id(self, str_vals: List[str]):
        if str_vals is None and str_vals[0] is not None:
            return None

        assert len(self.tags) == 1
        if str_vals[0]:
            if isinstance(str_vals[0], int):
                idx = int(str_vals[0])
                if len(SYSTEM_IDS) > idx:
                    return SYSTEM_IDS[idx]
                else:
                    return f"UNKNOWN_SYSTEM_{idx}"
        else:
            return "UNKNOWN_SYSTEM"

    def _decode_ro_bios(self, str_vals: List[str]):
        if str_vals is None and str_vals[0] is not None:
            return None

        assert len(self.tags) == 1
        str_val = str_vals[0]
        if len(str_val) > 2:
            return f"{str_val[:-2]}.{str_val[-2:]}"
        else:
            return str_val

    def _decode_ro_fw(self, str_vals: List[str]):
        if str_vals is None:
            return None

        assert len(self.tags) == 2
        str_val1 = str_vals[0]
        str_val2 = str_vals[1]
        try:
            # str fw2 = f"{str_val1[:-4]:0>2}.{str_val1[-4:-2]}.{str_val1[-2:]}"
            return f"0{str_val1[0]}.{str_val1[1:3]}.{str_val1[3:]}-{str_val2}"
        except Exception as ex:
            _LOGGER.warning("could not decode FW",ex)
            return f"FW_{str_val1}-{str_val2}"

    def _decode_ro_sn(self, str_vals: List[str]):
        if str_vals is None:
            return None

        assert len(self.tags) == 2
        sn1 = int(str_vals[0])
        sn2 = int(str_vals[1])
        try:
            s1 = "WE" if math.floor(sn1 / 1000) > 0 else "00"  # pylint: disable=invalid-name
            s2 = (sn1 - 1000 if math.floor(sn1 / 1000) > 0 else sn1)  # pylint: disable=invalid-name
            s2 = "0" + str(s2) if s2 < 10 else s2  # pylint: disable=invalid-name
            return str(s1) + str(s2) + str(sn2)
        except Exception as ex:
            _LOGGER.warning("could not decode Serial",ex)
            return f"Serial_{sn1}-{sn2}"

    def _decode_year(self, str_vals: List[str]):
        if str_vals is None and str_vals[0] is not None:
            return None

        assert len(self.tags) == 1
        return int(str_vals[0]) + 2000

    tags: Collection[str]
    unit: str = None
    writeable: bool = False
    decode_f: Callable = _decode_value_default
    encode_f: Callable = _encode_value_default
    bit: int = None
    bits: list[int] = None
    translate: bool = False


class WKHPTag(DataTag, Enum):
    def __hash__(self) -> int:
        return hash(self.name)

    #################################################
    # waterkotte operational hours [/easycon/pgOpH.html]
    # please note, that the original webUI have a bug and DOES NOT SHOW the
    # correct values!

    # SHOW TOTAL/GESAMT Values for operation hours...
    OPERATING_HOURS_V2_SHOW_TOTALS_SWITCH_D634 = DataTag(["D634"], writeable=True)

    # Verdichter 1
    OPERATING_HOURS_V2_COMPRESSOR_1_A516 = DataTag(["A516", "A517"])
    # Verdichter 2 / Außeneinheit
    OPERATING_HOURS_V2_COMPRESSOR_2_A518 = DataTag(["A518", "A519"])
    # Vollbetriebsstunden
    OPERATING_HOURS_V2_FULL_OPERATING_HOURS_A520 = DataTag(["A520", "A521"])
    # Heizungspumpe
    OPERATING_HOURS_V2_HEATINGPUMP_A522 = DataTag(["A522", "A523"])
    # Wärmequellenpumpe
    OPERATING_HOURS_V2_SOURCE_PUMP_A524 = DataTag(["A524", "A525"])
    # Solarkreispumpe
    OPERATING_HOURS_V2_SOLAR_CIRCULATION_PUMP_A526 = DataTag(["A526", "A527"])
    # Externer Wärmeerzeuger
    OPERATING_HOURS_V2_EXTERNALHEATER_A528 = DataTag(["A528", "A529"])
    # Heizbetrieb
    OPERATING_HOURS_V2_HEATING_A530 = DataTag(["A530", "A531"])
    # Kühlbetrieb
    OPERATING_HOURS_V2_COOLING_A532 = DataTag(["A532", "A533"])
    # Warmwasserbetrieb
    OPERATING_HOURS_V2_HOT_WATER_A534 = DataTag(["A534", "A535"])
    # Pool-Heizbetrieb
    OPERATING_HOURS_V2_POOL_HEATING_A536 = DataTag(["A536", "A537"])
    # Solarbetrieb
    OPERATING_HOURS_V2_SOLAR_A538 = DataTag(["A538", "A539"])
    # Funktionsheizbetrieb
    OPERATING_HOURS_V2_FUNCTIONAL_HEATING_A540 = DataTag(["A540", "A541"])
    # Abtauvorgang
    OPERATING_HOURS_V2_DEFROSTER_A542 = DataTag(["A542", "A543"])
    # Bivalent parallel
    OPERATING_HOURS_V2_BIVALENT_PARALLEL_A544 = DataTag(["A544", "A545"])
    # Bivalent alternativ
    OPERATING_HOURS_V2_BIVALENT_ALTERNATIVE_A546 = DataTag(["A546", "A547"])

    # PV-Ertrag
    OPERATING_HOURS_V2_PV_YIELD_ALT_A576 = DataTag(["A576", "A577"])
    # PV-Ertrag
    OPERATING_HOURS_V2_PV_YIELD_A963 = DataTag(["A963", "A964"])

    # Außeneinheit 3
    OPERATING_HOURS_V2_COMPRESSOR_3_A706 = DataTag(["A706", "A707"])
    # Außeneinheit 4
    OPERATING_HOURS_V2_COMPRESSOR_4_A708 = DataTag(["A708", "A709"])

    # Abtauvorgang 2
    OPERATING_HOURS_V2_DEFROSTER_2_A710 = DataTag(["A710", "A711"])
    # Abtauvorgang 3
    OPERATING_HOURS_V2_DEFROSTER_3_A712 = DataTag(["A712", "A713"])
    # Abtauvorgang 4
    OPERATING_HOURS_V2_DEFROSTER_4_A714 = DataTag(["A714", "A715"])
    # Heizungspumpe 2
    OPERATING_HOURS_V2_HEATINGPUMP_2_A716 = DataTag(["A716", "A717"])
    # Heizungspumpe 3
    OPERATING_HOURS_V2_HEATINGPUMP_3_A718 = DataTag(["A718", "A719"])
    # Heizungspumpe 4
    OPERATING_HOURS_V2_HEATINGPUMP_4_A720 = DataTag(["A720", "A721"])

    # D628 - Externer Wärmeerzeuger für Notbetrieb verwenden


    #################################################
    # waterkotte DATE/time stuff

    # #use set date...
    # #I1758	S_OK
    # 192	08
    # #I1759	S_OK
    # 192	03
    # #I1760	S_OK
    # 192	2024
    # #I1761	S_OK
    # 192	17
    # #I1762	S_OK
    # 192	09
    # #D801	S_OK
    # 192	1
    #
    # second request...
    # #I1758	S_OK
    # 192	8.03
    #
    # write data...
    # #D22	S_OK
    # 192	1

    # day: I5,       month: I6,      year: I7,       hour: I8,       minute: I9
    WATERKOTTE_BIOS_TIME = DataTag(["I7", "I6", "I5", "I8", "I9"], decode_f=DataTag._decode_datetime)
    # day: I1758,    month: I1759,   year: I1760,    hour: I1761,    minute: I1762
    # WATERKOTTE_TIME_SET = DataTag(
    #    ["I1760", "I1759", "I1758", "I1761", "I1762"], writeable=True, decode_f=DataTag._decode_datetime,
    #    encode_f=DataTag._encode_datetime
    # )
    # WATERKOTTE_TIME_X1 = DataTag(["D801"], writeable=True)
    # WATERKOTTE_TIME_X2 = DataTag(["D22"], writeable=True)

    HOLIDAY_ENABLED = DataTag(["D420"], writeable=True)
    HOLIDAY_START_TIME = DataTag(["I1254", "I1253", "I1252", "I1250", "I1251"], writeable=True, decode_f=DataTag._decode_datetime,
        encode_f=DataTag._encode_datetime
    )
    HOLIDAY_END_TIME = DataTag(["I1259", "I1258", "I1257", "I1255", "I1256"], writeable=True, decode_f=DataTag._decode_datetime,
        encode_f=DataTag._encode_datetime
    )
    TEMPERATURE_OUTSIDE = DataTag(["A1"], "°C")
    TEMPERATURE_OUTSIDE_1H = DataTag(["A2"], "°C")
    TEMPERATURE_OUTSIDE_24H = DataTag(["A3"], "°C")
    TEMPERATURE_SOURCE_ENTRY = DataTag(["A4"], "°C")
    TEMPERATURE_SOURCE_EXIT = DataTag(["A5"], "°C")
    TEMPERATURE_EVAPORATION = DataTag(["A6"], "°C")
    TEMPERATURE_SUCTION_LINE = DataTag(["A7"], "°C")
    PRESSURE_EVAPORATION = DataTag(["A8"], "bar")
    TEMPERATURE_RETURN_SETPOINT = DataTag(["A10"], "°C")
    TEMPERATURE_RETURN = DataTag(["A11"], "°C")
    TEMPERATURE_FLOW = DataTag(["A12"], "°C")
    TEMPERATURE_CONDENSATION = DataTag(["A13"], "°C")
    TEMPERATURE_BUBBLEPOINT = DataTag(["A14"], "°C")
    PRESSURE_CONDENSATION = DataTag(["A15"], "bar")
    TEMPERATURE_BUFFERTANK = DataTag(["A16"], "°C")
    TEMPERATURE_ROOM = DataTag(["A17"], "°C")
    TEMPERATURE_ROOM_1H = DataTag(["A18"], "°C")

    TEMPERATURE_SOLAR = DataTag(["A21"], "°C")
    TEMPERATURE_SOLAR_EXIT = DataTag(["A22"], "°C")
    POSITION_EXPANSION_VALVE = DataTag(["A23"], "")
    SUCTION_GAS_OVERHEATING = DataTag(["A24"], "")

    POWER_ELECTRIC = DataTag(["A25"], "kW")
    POWER_HEATING = DataTag(["A26"], "kW")
    POWER_COOLING = DataTag(["A27"], "kW")
    COP_HEATING = DataTag(["A28"], "")
    COP_COOLING = DataTag(["A29"], "")

    # ENERGY-YEAR-BALANCE
    COP_HEATPUMP_YEAR = DataTag(["A460"], "")  # HEATPUMP_COP
    COP_HEATPUMP_ACTUAL_YEAR_INFO = DataTag(["I1261"], decode_f=DataTag._decode_year)  # HEATPUMP_COP_YEAR
    COP_TOTAL_SYSTEM_YEAR = DataTag(["A461"], "")
    COP_HEATING_YEAR = DataTag(["A695"])
    COP_HOT_WATER_YEAR = DataTag(["A697"])

    ENERGY_CONSUMPTION_TOTAL_YEAR = DataTag(["A450", "A451"], "kWh")
    COMPRESSOR_ELECTRIC_CONSUMPTION_YEAR = DataTag(["A444", "A445"], "kWh")  # ANUAL_CONSUMPTION_COMPRESSOR
    SOURCEPUMP_ELECTRIC_CONSUMPTION_YEAR = DataTag(["A446", "A447"], "kWh")  # ANUAL_CONSUMPTION_SOURCEPUMP
    ELECTRICAL_HEATER_ELECTRIC_CONSUMPTION_YEAR = DataTag(["A448", "A449"], "kWh")  # ANUAL_CONSUMPTION_EXTERNALHEATER
    ENERGY_PRODUCTION_TOTAL_YEAR = DataTag(["A458", "A459"], "kWh")
    HEATING_ENERGY_PRODUCTION_YEAR = DataTag(["A452", "A453"], "kWh")  # ANUAL_CONSUMPTION_HEATING
    HOT_WATER_ENERGY_PRODUCTION_YEAR = DataTag(["A454", "A455"], "kWh")  # ANUAL_CONSUMPTION_WATER
    POOL_ENERGY_PRODUCTION_YEAR = DataTag(["A456", "A457"], "kWh")  # ANUAL_CONSUMPTION_POOL
    COOLING_ENERGY_YEAR = DataTag(["A462", "A463"], "kWh")

    # The LAST12M values for ENERGY_CONSUMPTION_TOTAL (also the individual values for compressor, sourcepump & e-heater
    # will be calculated based on values for each month (and will be summarized in the FE))
    # The same applies to the ENERGY_PRODUCTION_TOTAL (with the individual values for heating, hot_water & pool)
    COP_TOTAL_SYSTEM_LAST12M = DataTag(["A435"])
    COOLING_ENERGY_LAST12M = DataTag(["A436"], "kWh")

    ENG_CONSUMPTION_COMPRESSOR01 = DataTag(["A782"])
    ENG_CONSUMPTION_COMPRESSOR02 = DataTag(["A783"])
    ENG_CONSUMPTION_COMPRESSOR03 = DataTag(["A784"])
    ENG_CONSUMPTION_COMPRESSOR04 = DataTag(["A785"])
    ENG_CONSUMPTION_COMPRESSOR05 = DataTag(["A786"])
    ENG_CONSUMPTION_COMPRESSOR06 = DataTag(["A787"])
    ENG_CONSUMPTION_COMPRESSOR07 = DataTag(["A788"])
    ENG_CONSUMPTION_COMPRESSOR08 = DataTag(["A789"])
    ENG_CONSUMPTION_COMPRESSOR09 = DataTag(["A790"])
    ENG_CONSUMPTION_COMPRESSOR10 = DataTag(["A791"])
    ENG_CONSUMPTION_COMPRESSOR11 = DataTag(["A792"])
    ENG_CONSUMPTION_COMPRESSOR12 = DataTag(["A793"])

    ENG_CONSUMPTION_SOURCEPUMP01 = DataTag(["A794"])
    ENG_CONSUMPTION_SOURCEPUMP02 = DataTag(["A795"])
    ENG_CONSUMPTION_SOURCEPUMP03 = DataTag(["A796"])
    ENG_CONSUMPTION_SOURCEPUMP04 = DataTag(["A797"])
    ENG_CONSUMPTION_SOURCEPUMP05 = DataTag(["A798"])
    ENG_CONSUMPTION_SOURCEPUMP06 = DataTag(["A799"])
    ENG_CONSUMPTION_SOURCEPUMP07 = DataTag(["A800"])
    ENG_CONSUMPTION_SOURCEPUMP08 = DataTag(["A802"])
    ENG_CONSUMPTION_SOURCEPUMP09 = DataTag(["A804"])
    ENG_CONSUMPTION_SOURCEPUMP10 = DataTag(["A805"])
    ENG_CONSUMPTION_SOURCEPUMP11 = DataTag(["A806"])
    ENG_CONSUMPTION_SOURCEPUMP12 = DataTag(["A807"])

    # Docs say it should start at 806 for external heater but there is an overlapp to source pump
    ENG_CONSUMPTION_EXTERNALHEATER01 = DataTag(["A808"])
    ENG_CONSUMPTION_EXTERNALHEATER02 = DataTag(["A809"])
    ENG_CONSUMPTION_EXTERNALHEATER03 = DataTag(["A810"])
    ENG_CONSUMPTION_EXTERNALHEATER04 = DataTag(["A811"])
    ENG_CONSUMPTION_EXTERNALHEATER05 = DataTag(["A812"])
    ENG_CONSUMPTION_EXTERNALHEATER06 = DataTag(["A813"])
    ENG_CONSUMPTION_EXTERNALHEATER07 = DataTag(["A814"])
    ENG_CONSUMPTION_EXTERNALHEATER08 = DataTag(["A815"])
    ENG_CONSUMPTION_EXTERNALHEATER09 = DataTag(["A816"])
    ENG_CONSUMPTION_EXTERNALHEATER10 = DataTag(["A817"])
    ENG_CONSUMPTION_EXTERNALHEATER11 = DataTag(["A818"])
    ENG_CONSUMPTION_EXTERNALHEATER12 = DataTag(["A819"])

    ENG_PRODUCTION_HEATING01 = DataTag(["A830"])
    ENG_PRODUCTION_HEATING02 = DataTag(["A831"])
    ENG_PRODUCTION_HEATING03 = DataTag(["A832"])
    ENG_PRODUCTION_HEATING04 = DataTag(["A833"])
    ENG_PRODUCTION_HEATING05 = DataTag(["A834"])
    ENG_PRODUCTION_HEATING06 = DataTag(["A835"])
    ENG_PRODUCTION_HEATING07 = DataTag(["A836"])
    ENG_PRODUCTION_HEATING08 = DataTag(["A837"])
    ENG_PRODUCTION_HEATING09 = DataTag(["A838"])
    ENG_PRODUCTION_HEATING10 = DataTag(["A839"])
    ENG_PRODUCTION_HEATING11 = DataTag(["A840"])
    ENG_PRODUCTION_HEATING12 = DataTag(["A841"])

    ENG_PRODUCTION_WARMWATER01 = DataTag(["A842"])
    ENG_PRODUCTION_WARMWATER02 = DataTag(["A843"])
    ENG_PRODUCTION_WARMWATER03 = DataTag(["A844"])
    ENG_PRODUCTION_WARMWATER04 = DataTag(["A845"])
    ENG_PRODUCTION_WARMWATER05 = DataTag(["A846"])
    ENG_PRODUCTION_WARMWATER06 = DataTag(["A847"])
    ENG_PRODUCTION_WARMWATER07 = DataTag(["A848"])
    ENG_PRODUCTION_WARMWATER08 = DataTag(["A849"])
    ENG_PRODUCTION_WARMWATER09 = DataTag(["A850"])
    ENG_PRODUCTION_WARMWATER10 = DataTag(["A851"])
    ENG_PRODUCTION_WARMWATER11 = DataTag(["A852"])
    ENG_PRODUCTION_WARMWATER12 = DataTag(["A853"])

    ENG_PRODUCTION_POOL01 = DataTag(["A854"])
    ENG_PRODUCTION_POOL02 = DataTag(["A855"])
    ENG_PRODUCTION_POOL03 = DataTag(["A856"])
    ENG_PRODUCTION_POOL04 = DataTag(["A857"])
    ENG_PRODUCTION_POOL05 = DataTag(["A858"])
    ENG_PRODUCTION_POOL06 = DataTag(["A859"])
    ENG_PRODUCTION_POOL07 = DataTag(["A860"])
    ENG_PRODUCTION_POOL08 = DataTag(["A861"])
    ENG_PRODUCTION_POOL09 = DataTag(["A862"])
    ENG_PRODUCTION_POOL10 = DataTag(["A863"])
    ENG_PRODUCTION_POOL11 = DataTag(["A864"])
    ENG_PRODUCTION_POOL12 = DataTag(["A865"])

    ENG_HEATPUMP_COP_MONTH01 = DataTag(["A924"])
    ENG_HEATPUMP_COP_MONTH02 = DataTag(["A925"])
    ENG_HEATPUMP_COP_MONTH03 = DataTag(["A926"])
    ENG_HEATPUMP_COP_MONTH04 = DataTag(["A927"])
    ENG_HEATPUMP_COP_MONTH05 = DataTag(["A928"])
    ENG_HEATPUMP_COP_MONTH06 = DataTag(["A929"])
    ENG_HEATPUMP_COP_MONTH07 = DataTag(["A930"])
    ENG_HEATPUMP_COP_MONTH08 = DataTag(["A930"])
    ENG_HEATPUMP_COP_MONTH09 = DataTag(["A931"])
    ENG_HEATPUMP_COP_MONTH10 = DataTag(["A932"])
    ENG_HEATPUMP_COP_MONTH11 = DataTag(["A933"])
    ENG_HEATPUMP_COP_MONTH12 = DataTag(["A934"])

    # Temperature stuff
    TEMPERATURE_HEATING = DataTag(["A30"], "°C")
    TEMPERATURE_HEATING_DEMAND = DataTag(["A31"], "°C")
    TEMPERATURE_HEATING_ADJUST = DataTag(["I263"], "K", writeable=True)
    TEMPERATURE_HEATING_HYSTERESIS = DataTag(["A61"], "K", writeable=True)
    TEMPERATURE_HEATING_PV_CHANGE = DataTag(["A682"], "K", writeable=True)
    TEMPERATURE_HEATING_HC_OUTDOOR_1H = DataTag(["A90"], "°C")
    TEMPERATURE_HEATING_HC_LIMIT = DataTag(["A93"], "°C", writeable=True)
    TEMPERATURE_HEATING_HC_TARGET = DataTag(["A94"], "°C", writeable=True)
    TEMPERATURE_HEATING_HC_OUTDOOR_NORM = DataTag(["A91"], "°C", writeable=True)
    TEMPERATURE_HEATING_HC_NORM = DataTag(["A92"], "°C", writeable=True)
    TEMPERATURE_HEATING_HC_RESULT = DataTag(["A96"], "°C")
    TEMPERATURE_HEATING_ANTIFREEZE = DataTag(["A1231"], "°C", writeable=True)
    TEMPERATURE_HEATING_SETPOINTLIMIT_MAX = DataTag(["A95"], "°C", writeable=True)
    TEMPERATURE_HEATING_SETPOINTLIMIT_MIN = DataTag(["A104"], "°C", writeable=True)
    TEMPERATURE_HEATING_POWLIMIT_MAX = DataTag(["A504"], "%", writeable=True)
    TEMPERATURE_HEATING_POWLIMIT_MIN = DataTag(["A505"], "%", writeable=True)
    TEMPERATURE_HEATING_SGREADY_STATUS4 = DataTag(["A967"], "°C", writeable=True)

    # TEMPERATURE_HEATING_BUFFERTANK_ROOM_SETPOINT = DataTag(["A413"], "°C", writeable=True)

    TEMPERATURE_HEATING_MODE = DataTag(["I265"], writeable=True, decode_f=DataTag._decode_six_steps_mode, encode_f=DataTag._encode_six_steps_mode)
    # this A32 value is not visible in the GUI - and IMHO (marq24) there should
    # be no way to set the heating temperature directly - use the values of the
    # 'TEMPERATURE_HEATING_HC' instead (HC = HeatCurve)
    TEMPERATURE_HEATING_SETPOINT = DataTag(["A32"], "°C", writeable=True)
    # same as A32 ?!
    TEMPERATURE_HEATING_SETPOINT_FOR_SOLAR = DataTag(["A1710"], "°C", writeable=True)

    TEMPERATURE_COOLING = DataTag(["A33"], "°C")
    TEMPERATURE_COOLING_DEMAND = DataTag(["A34"], "°C")
    TEMPERATURE_COOLING_SETPOINT = DataTag(["A109"], "°C", writeable=True)
    TEMPERATURE_COOLING_OUTDOOR_LIMIT = DataTag(["A108"], "°C", writeable=True)
    TEMPERATURE_COOLING_FLOW_LIMIT = DataTag(["A110"], "°C", writeable=True)
    TEMPERATURE_COOLING_HYSTERESIS = DataTag(["A107"], "K", writeable=True)
    TEMPERATURE_COOLING_PV_CHANGE = DataTag(["A683"], "K", writeable=True)

    TEMPERATURE_WATER = DataTag(["A19"], "°C")
    TEMPERATURE_WATER_DEMAND = DataTag(["A37"], "°C")
    TEMPERATURE_WATER_SETPOINT = DataTag(["A38"], "°C", writeable=True)
    TEMPERATURE_WATER_HYSTERESIS = DataTag(["A139"], "K", writeable=True)
    TEMPERATURE_WATER_PV_CHANGE = DataTag(["A684"], "K", writeable=True)
    TEMPERATURE_WATER_DISINFECTION = DataTag(["A168"], "°C", writeable=True)
    SCHEDULE_WATER_DISINFECTION_START_TIME = DataTag(["I505", "I506"], writeable=True, decode_f=DataTag._decode_time_hhmm, encode_f=DataTag._encode_time_hhmm)
    # SCHEDULE_WATER_DISINFECTION_START_HOUR = DataTag(["I505"], "", writeable=True)
    # SCHEDULE_WATER_DISINFECTION_START_MINUTE = DataTag(["I506"], "", writeable=True)
    SCHEDULE_WATER_DISINFECTION_DURATION = DataTag(["I507"], "h", writeable=True)
    SCHEDULE_WATER_DISINFECTION_1MO = DataTag(["D153"], "", writeable=True)
    SCHEDULE_WATER_DISINFECTION_2TU = DataTag(["D154"], "", writeable=True)
    SCHEDULE_WATER_DISINFECTION_3WE = DataTag(["D155"], "", writeable=True)
    SCHEDULE_WATER_DISINFECTION_4TH = DataTag(["D156"], "", writeable=True)
    SCHEDULE_WATER_DISINFECTION_5FR = DataTag(["D157"], "", writeable=True)
    SCHEDULE_WATER_DISINFECTION_6SA = DataTag(["D158"], "", writeable=True)
    SCHEDULE_WATER_DISINFECTION_7SU = DataTag(["D159"], "", writeable=True)

    # DISINFECTION protocol (no clue how to enable this)
    # <div id="infoThDis"><h4 id="h4Documentation">Dokumentation</h4><table class="table table-condensed"><thead><tr><th id="txtDate">Datum</th><th id="txtTime">Zeit</th><th id="txtTemp">Temperatur</th></tr></thead><tbody><tr id="trD1005"><td id="I2181">01.10.23</td><td id="I2184">14:08</td><td id="A1090">55.9&nbsp;°C</td></tr><tr id="trD1006"><td id="I2188">02.03.23</td><td id="I2191">12:28</td><td id="A1091">60.8&nbsp;°C</td></tr></tbody></table></div>

    TEMPERATURE_WATER_SETPOINT_FOR_SOLAR = DataTag(["A169"], "°C", writeable=True)
    # Changeover temperature to extern heating when exceeding T hot water
    # Umschalttemperatur ext. Waermeerzeuger bei Ueberschreitung der T Warmwasser
    TEMPERATURE_WATER_CHANGEOVER_EXT_HOTWATER = DataTag(["A1019"], "°C", writeable=True)
    # Changeover temperature to extern heating when exceeding T flow
    # Umschalttemperatur ext. Waermeerzeuger bei Ueberschreitung der T Vorlauf
    TEMPERATURE_WATER_CHANGEOVER_EXT_FLOW = DataTag(["A1249"], "°C", writeable=True)
    TEMPERATURE_WATER_POWLIMIT_MAX = DataTag(["A171"], "%", writeable=True)
    TEMPERATURE_WATER_POWLIMIT_MIN = DataTag(["A172"], "%", writeable=True)

    TEMPERATURE_POOL = DataTag(["A20"], "°C")
    TEMPERATURE_POOL_DEMAND = DataTag(["A40"], "°C")
    TEMPERATURE_POOL_ADJUST = DataTag(["I1740"], "K", writeable=True)
    TEMPERATURE_POOL_SETPOINT = DataTag(["A41"], "°C", writeable=True)
    TEMPERATURE_POOL_HYSTERESIS = DataTag(["A174"], "K", writeable=True)
    TEMPERATURE_POOL_PV_CHANGE = DataTag(["A685"], "K", writeable=True)
    TEMPERATURE_POOL_HC_OUTDOOR_1H = DataTag(["A746"], "°C")
    TEMPERATURE_POOL_HC_LIMIT = DataTag(["A749"], "°C", writeable=True)
    TEMPERATURE_POOL_HC_TARGET = DataTag(["A750"], "°C", writeable=True)
    TEMPERATURE_POOL_HC_OUTDOOR_NORM = DataTag(["A747"], "°C", writeable=True)
    TEMPERATURE_POOL_HC_NORM = DataTag(["A748"], "°C", writeable=True)
    TEMPERATURE_POOL_HC_RESULT = DataTag(["A752"], "°C")

    TEMPERATURE_POOL_MODE = DataTag(["I527"], writeable=True, decode_f=DataTag._decode_four_steps_mode, encode_f=DataTag._encode_four_steps_mode)
    TEMPERATURE_POOL_MAX_RUNTIME = DataTag(["I640"], "min", writeable=True) # 5min - 180min
    TEMPERATURE_POOL_SETPOINTLIMIT = DataTag(["A751"], "°C", writeable=True)
    TEMPERATURE_POOL_POWLIMIT_MAX = DataTag(["A203"], "%", writeable=True)
    TEMPERATURE_POOL_POWLIMIT_MIN = DataTag(["A204"], "%", writeable=True)

    TEMPERATURE_MIX1 = DataTag(["A44"], "°C")  # TEMPERATURE_MIXING1_CURRENT
    TEMPERATURE_MIX1_DEMAND = DataTag(["A45"], "°C")  # TEMPERATURE_MIXING1_SET
    TEMPERATURE_MIX1_ADJUST = DataTag(["I776"], "K", writeable=True)  # ADAPT_MIXING1
    TEMPERATURE_MIX1_PV_CHANGE = DataTag(["A1094"], "K", writeable=True)
    TEMPERATURE_MIX1_PERCENT = DataTag(["A510"], "%")
    TEMPERATURE_MIX1_HC_LIMIT = DataTag(["A276"], "°C", writeable=True)  # T_HEATING_LIMIT_MIXING1
    TEMPERATURE_MIX1_HC_TARGET = DataTag(["A277"], "°C", writeable=True)  # T_HEATING_LIMIT_TARGET_MIXING1
    TEMPERATURE_MIX1_HC_OUTDOOR_NORM = DataTag(["A274"], "°C", writeable=True)  # T_NORM_OUTDOOR_MIXING1
    TEMPERATURE_MIX1_HC_HEATING_NORM = DataTag(["A275"], "°C", writeable=True)  # T_NORM_HEATING_CICLE_MIXING1
    TEMPERATURE_MIX1_HC_MAX = DataTag(["A278"], "°C", writeable=True)  # MAX_TEMP_MIXING1

    TEMPERATURE_MIX2 = DataTag(["A46"], "°C")  # TEMPERATURE_MIXING2_CURRENT
    TEMPERATURE_MIX2_DEMAND = DataTag(["A47"], "°C")  # TEMPERATURE_MIXING2_SET
    TEMPERATURE_MIX2_ADJUST = DataTag(["I896"], "K", writeable=True)  # ADAPT_MIXING2
    TEMPERATURE_MIX2_PV_CHANGE = DataTag(["A1095"], "K", writeable=True)
    TEMPERATURE_MIX2_PERCENT = DataTag(["A512"], "%")
    TEMPERATURE_MIX2_HC_LIMIT = DataTag(["A322"], "°C", writeable=True)
    TEMPERATURE_MIX2_HC_TARGET = DataTag(["A323"], "°C", writeable=True)
    TEMPERATURE_MIX2_HC_OUTDOOR_NORM = DataTag(["A320"], "°C", writeable=True)
    TEMPERATURE_MIX2_HC_HEATING_NORM = DataTag(["A321"], "°C", writeable=True)
    TEMPERATURE_MIX2_HC_MAX = DataTag(["A324"], "°C", writeable=True)

    TEMPERATURE_MIX3 = DataTag(["A48"], "°C")  # TEMPERATURE_MIXING3_CURRENT
    TEMPERATURE_MIX3_DEMAND = DataTag(["A49"], "°C")  # TEMPERATURE_MIXING3_SET
    TEMPERATURE_MIX3_ADJUST = DataTag(["I1017"], "K", writeable=True)  # ADAPT_MIXING3
    TEMPERATURE_MIX3_PV_CHANGE = DataTag(["A1096"], "K", writeable=True)
    TEMPERATURE_MIX3_PERCENT = DataTag(["A514"], "%")
    TEMPERATURE_MIX3_HC_LIMIT = DataTag(["A368"], "°C", writeable=True)
    TEMPERATURE_MIX3_HC_TARGET = DataTag(["A369"], "°C", writeable=True)
    TEMPERATURE_MIX3_HC_OUTDOOR_NORM = DataTag(["A366"], "°C", writeable=True)
    TEMPERATURE_MIX3_HC_HEATING_NORM = DataTag(["A367"], "°C", writeable=True)
    TEMPERATURE_MIX3_HC_MAX = DataTag(["A370"], "°C", writeable=True)

    # no information found in <host>/easycon/js/dictionary.js
    # COMPRESSOR_POWER = DataTag(["A50"], "?°C")
    PERCENT_HEAT_CIRC_PUMP = DataTag(["A51"], "%")
    PERCENT_SOURCE_PUMP = DataTag(["A52"], "%")
    # A58 is listed as 'Power compressor' in <host>/easycon/js/dictionary.js
    # even if this value will not be displayed in the Waterkotte GUI - looks
    # like that this is really the same as the other two values (A51 & A52)
    # just a percentage value (from 0.0 - 100.0)
    PERCENT_COMPRESSOR_DEMAND = DataTag(["A50"], "%")
    PERCENT_COMPRESSOR = DataTag(["A58"], "%")
    PERCENT_COMPRESSOR2 = DataTag(["A703"], "%")
    PERCENT_COMPRESSOR3 = DataTag(["A704"], "%")
    PERCENT_COMPRESSOR4 = DataTag(["A705"], "%")

    # just found... Druckgastemperatur
    TEMPERATURE_DISCHARGE = DataTag(["A1462"], "°C")

    # implement https://github.com/marq24/ha-waterkotte/issues/3
    PRESSURE_WATER = DataTag(["A1669"], "bar")

    # I1264 -> Heizstab Leistung?! -> 6000

    # keep but not found in Waterkotte GUI
    TEMPERATURE_COLLECTOR = DataTag(["A42"], "°C")  # aktuelle Temperatur Kollektor
    TEMPERATURE_FLOW2 = DataTag(["A43"], "°C")  # aktuelle Temperatur Vorlauf

    VERSION_CONTROLLER = DataTag(["I1", "I2"], decode_f=DataTag._decode_ro_fw)
    # VERSION_CONTROLLER_BUILD = DataTag(["I2"])
    VERSION_BIOS = DataTag(["I3"], decode_f=DataTag._decode_ro_bios)
    DATE_DAY = DataTag(["I5"])
    DATE_MONTH = DataTag(["I6"])
    DATE_YEAR = DataTag(["I7"])
    TIME_HOUR = DataTag(["I8"])
    TIME_MINUTE = DataTag(["I9"])

    # AI-Phantasie
    # I10–I19: Betriebsstunden & Betriebsdaten
    # I10	Betriebsstunden Verdichter (Kompressor)
    # I11	Verdichterstarts
    # I12	Betriebsstunden Heizbetrieb
    # I13	Betriebsstunden Warmwasser
    # I14	Betriebsstunden Kühlbetrieb (falls aktiviert)
    # I15	Betriebsstunden Heizkreispumpe (HKP)
    # I16	Betriebsstunden Solepumpe (Primärkreis) / Ventilator (je nach Modell)
    # I17	Betriebsstunden Elektroheizstab Stufe 1
    # I18	Betriebsstunden Elektroheizstab Stufe 2 oder Bivalenzanforderung (je nach Softwarestand)
    # I19	Betriebsstunden externer Wärmeerzeuger (falls Bivalenz aktiv) / Außeneinheit (bei Luft‑WP)

    # AI-Phantasie
    # I20–I29: Verdichter & interne Leistungsdaten
    # I20	Verdichterstatus (0 = aus, 1 = ein) oder Leistungsstufe
    # I21	Hochdrucksensor (bar)
    # I22	Niederdrucksensor (bar)
    # I23	Verdichterstrom (A)
    # I24	Verdichterleistung (kW)
    # I25	COP‑Momentanwert (falls aktiviert)
    # I26	Verdichterfrequenz (bei Inverter‑Modellen)
    # I27	interne Regelgröße (z. B. Sollwertabweichung)
    # I28	interne Diagnosevariable
    # I29	interne Diagnosevariable

    OPERATING_HOURS_COMPRESSOR_1 = DataTag(["I10"])
    OPERATING_HOURS_COMPRESSOR_2 = DataTag(["I14"])
    OPERATING_HOURS_CIRCULATION_PUMP = DataTag(["I18"])
    OPERATING_HOURS_SOURCE_PUMP = DataTag(["I20"])
    OPERATING_HOURS_SOLAR = DataTag(["I22"])

    # AI-Phantasie
    # I30–I39: Pumpen, Ventile, Durchfluss, Betriebszustände
    # I30	Status Heizkreispumpe (0/1 oder % bei PWM)
    # I31	Status Solepumpe (0/1 oder % bei PWM)
    # I32	3‑Wege‑Ventil Heizen/Warmwasser (0 = Heizen, 1 = WW)
    # I33	Umschaltventil Kühlung (falls vorhanden)
    # I34	Durchfluss Sole (l/min) – nur bei Sensor
    # I35	Durchfluss Heizung (l/min) – nur bei Sensor
    # I36	Status Brauchwasserladepumpe (falls extern)
    # I37	Status Zirkulationspumpe (falls angeschlossen)
    # I38	Status externer Wärmeerzeuger / Bivalenz (0/1)
    # I39	Status Kühlfunktion (0/1)
    ENABLE_HEATING = DataTag(["I30"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_COOLING = DataTag(["I31"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_WARMWATER = DataTag(["I32"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_POOL = DataTag(["I33"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_EXTERNAL_HEATER = DataTag(["I35"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_MIXING1 = DataTag(["I37"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_MIXING2 = DataTag(["I38"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_MIXING3 = DataTag(["I39"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_PV = DataTag(["I41"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)

    # UNKNOWN OPERATION-ENABLE Switches!
    ENABLE_X1 = DataTag(["I34"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_X2 = DataTag(["I36"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_X4 = DataTag(["I40"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)
    ENABLE_X5 = DataTag(["I42"], writeable=True, decode_f=DataTag._decode_state, encode_f=DataTag._encode_state)

    STATE_SOURCEPUMP = DataTag(["I51"], bit=0)
    STATE_HEATINGPUMP = DataTag(["I51"], bit=1)
    STATE_HEATINGPUMP2 = DataTag(["I54"], bit=5)
    STATE_HEATINGPUMP3 = DataTag(["I54"], bit=3)
    STATE_HEATINGPUMP4 = DataTag(["I54"], bit=4)
    STATE_EVD = DataTag(["I51"], bit=2)
    STATE_COMPRESSOR = DataTag(["I51"], bit=3)
    STATE_COMPRESSOR2 = DataTag(["I51"], bit=4)
    STATE_COMPRESSOR3 = DataTag(["I54"], bit=12)
    STATE_COMPRESSOR4 = DataTag(["I54"], bit=13)
    STATE_EXTERNAL_HEATER = DataTag(["I51"], bit=5)
    STATE_ALARM = DataTag(["I51"], bit=6)
    STATE_COOLING = DataTag(["I51"], bit=7)
    STATE_WATER = DataTag(["I51"], bit=8)
    STATE_POOL = DataTag(["I51"], bit=9)
    STATE_SOLAR = DataTag(["I51"], bit=10)
    STATE_SOLAR2 = DataTag(["I51"], bit=11)
    STATE_COOLING4WAY = DataTag(["I51"], bit=12)
    STATE_COOLING4WAY2 = DataTag(["I54"], bit=6)
    STATE_COOLING4WAY3 = DataTag(["I54"], bit=7)
    STATE_COOLING4WAY4 = DataTag(["I54"], bit=8)
    STATE_STORAGEPUMP =  DataTag(["I54"], bit=0)
    STATE_EMERGENCYOFF = DataTag(["I54"], bit=1)
    STATE_EMERGENCYOFF2 = DataTag(["I54"], bit=9)
    STATE_EMERGENCYOFF3 = DataTag(["I54"], bit=10)
    STATE_EMERGENCYOFF4 = DataTag(["I54"], bit=11)
    STATE_SILENTMODE = DataTag(["I54"], bit=2)
    STATE_MIX1_PUMP = DataTag(["I51"], bit=13)
    STATE_MIX1_MIXER_OPEN = DataTag(["I51"], bit=14)
    STATE_MIX1_MIXER_CLOSE = DataTag(["I51"], bit=15)
    STATE_ENGINEVENT = DataTag(["I54"], bit=14)

    # https://github.com/flautze/home_assistant_waterkotte/issues/1#issuecomment-1916288553
    INTERRUPTION_BITS = DataTag(["I53"], bits=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], translate=True)
    ALARM_BITS = DataTag(["I52", "I2608", "I2609", "I2610", "I2611", "I2612", "I2613", "I2614"], decode_f=DataTag._decode_alarms)

    # when we are logged in as ServiceOperator, then I135 return 1 -> in the FE this will be set the currentUserLevel
    # 1: Service
    # 2: Werksebene
    # 3: Entwickler
    STATE_SERVICE = DataTag(["I135"])

    STATUS_HEATING = DataTag(["I137"], decode_f=DataTag._decode_status)
    STATUS_COOLING = DataTag(["I138"], decode_f=DataTag._decode_status)
    STATUS_WATER = DataTag(["I139"], decode_f=DataTag._decode_status)
    STATUS_POOL = DataTag(["I140"], decode_f=DataTag._decode_status)
    STATUS_SOLAR = DataTag(["I141"], decode_f=DataTag._decode_status)
    # returned 2='disabled' (even if the pump is running) - could be, that this TAG has to be set to 1='on' in order
    # to allow manual enable/disable the pump??? So it's then better to rename this then operation_mode and move it to
    # the switch section [just like the 'ENABLE_*' tags]
    STATUS_HEATING_CIRCULATION_PUMP = DataTag(["I1270"], decode_f=DataTag._decode_status)
    MANUAL_SOURCEPUMP = DataTag(["I1281"])
    # see STATUS_HEATING_CIRCULATION_PUMP
    STATUS_SOLAR_CIRCULATION_PUMP = DataTag(["I1287"], decode_f=DataTag._decode_status)
    MANUAL_SOLARPUMP1 = DataTag(["I1287"])
    MANUAL_SOLARPUMP2 = DataTag(["I1289"])
    # see STATUS_HEATING_CIRCULATION_PUMP
    STATUS_BUFFER_TANK_CIRCULATION_PUMP = DataTag(["I1291"], decode_f=DataTag._decode_status)
    MANUAL_VALVE = DataTag(["I1293"])
    MANUAL_POOLVALVE = DataTag(["I1295"])
    MANUAL_COOLVALVE = DataTag(["I1297"])
    MANUAL_4WAYVALVE = DataTag(["I1299"])
    # see STATUS_HEATING_CIRCULATION_PUMP
    STATUS_COMPRESSOR = DataTag(["I1307"], decode_f=DataTag._decode_status)
    MANUAL_MULTIEXT = DataTag(["I1319"])

    INFO_SERIES = DataTag(["I105"], decode_f=DataTag._decode_ro_series)
    INFO_ID = DataTag(["I110"], decode_f=DataTag._decode_ro_id)
    INFO_SERIAL = DataTag(["I114", "I115"], decode_f=DataTag._decode_ro_sn)
    ADAPT_HEATING = DataTag(["I263"], writeable=True)

    STATE_BLOCKING_TIME = DataTag(["D71"])
    STATE_TEST_RUN = DataTag(["D581"])

    # SERVICE_HEATING = DataTag(["D251"])
    # SERVICE_COOLING = DataTag(["D252"])
    # SERVICE_WATER = DataTag(["D117"])
    # SERVICE_HEATING_D23 = DataTag(["D23"])
    # SERVICE_HEATING_SCHEDULE D24 = DataTag(["D24"])
    # SERVICE_WATER_D118 = DataTag(["D118"])
    # SERVICE_OPMODE = DataTag(["I136"])
    # RAW_D430 = DataTag(["D430"])  # animation
    # RAW_D28 = DataTag(["D28"])  # ?QE
    # RAW_D879 = DataTag(["D879"])  # ?RMH
    # MODE_HEATING_PUMP = DataTag(["A522"])
    # MODE_HEATING = DataTag(["A530"])
    # MODE_HEATING_EXTERNAL = DataTag(["A528"])
    # MODE_COOLING = DataTag(["A532"])
    # MODE_WATER = DataTag(["A534"])
    # MODE_POOL = DataTag(["A536"])
    # MODE_SOLAR = DataTag(["A538"])

    # found on the "extended" Tab in the Waterkotte WebGui
    # (all values can be read/write) - no clue about the unit yet
    # reading the values always returned '0' -> so I guess they have
    # no use for us?!
    # ENERGY_THERMAL_WORK_1 = DataTag("I1923")
    # ENERGY_THERMAL_WORK_2 = DataTag("I1924")
    # ENERGY_COOLING = DataTag("I1925")
    # ENERGY_HEATING = DataTag("I1926")
    # ENERGY_HOT_WATER = DataTag("I1927")
    # ENERGY_POOL_HEATER = DataTag("I1928")
    # ENERGY_COMPRESSOR = DataTag("I1929")
    # ENERGY_HEAT_SOURCE_PUMP = DataTag("I1930")
    # ENERGY_EXTERNAL_HEATER = DataTag("I1931")

    # D1273 "Heizungsumwäzpumpe ET 6900 Q" does not change it's value
    # HEATING_CIRCULATION_PUMP_D1273 = DataTag(["D1273"], writeable=True)
    STATE_HEATING_CIRCULATION_PUMP_D425 = DataTag(["D425"])
    STATE_BUFFERTANK_CIRCULATION_PUMP_D377 = DataTag(["D377"])
    STATE_POOL_CIRCULATION_PUMP_D549 = DataTag(["D549"])
    STATE_MIX1_CIRCULATION_PUMP_D248 = DataTag(["D248"])
    STATE_MIX2_CIRCULATION_PUMP_D291 = DataTag(["D291"])
    STATE_MIX3_CIRCULATION_PUMP_D334 = DataTag(["D334"])
    # alternative MIX pump tags...
    STATE_MIX1_CIRCULATION_PUMP_D563 = DataTag(["D563"])
    STATE_MIX2_CIRCULATION_PUMP_D564 = DataTag(["D564"])
    STATE_MIX3_CIRCULATION_PUMP_D565 = DataTag(["D565"])

    PERMANENT_HEATING_CIRCULATION_PUMP_WINTER_D1103 = DataTag(["D1103"], writeable=True)
    PERMANENT_HEATING_CIRCULATION_PUMP_SUMMER_D1104 = DataTag(["D1104"], writeable=True)

    # lngA520 = ["Vollbetriebsstunden", "Operating hours", "Heures activit\xe9"],

    # assuming that I1752 will be set to "Spreizung"=0 the A479 is a DELTA Temperature
    # lngA479 = ΔT Wärmequelle - ["T Wärmequelle", "T heat source", "T captage"],
    # REPLACED by PUMPSERVICE_SOURCEPUMP_HEATMODE_SOURCE_TEMPERATURE_A479
    # SOURCE_PUMP_CAPTURE_TEMPERATURE_A479 = DataTag(["A479"], writeable=True)

    SGREADY_SWITCH_D795 = DataTag(["D795"], writeable=True)
    # lngD796 = ["SG1: EVU-Sperre", "SG1: Extern switch off", "SG1: Coupure externe"],
    SGREADY_SG1_EXTERN_OFF_SWITCH_D796 = DataTag(["D796"])
    # lngD797 = ["SG2: Normalbetrieb", "SG2: Normal operation", "SG2: Fonction normal"],
    SGREADY_SG2_NORMAL_D797 = DataTag(["D797"])
    # lngD798 = ["SG3: Sollwerterh.", "SG3: Setpoint change", "SG3: Augment. consigne"],
    SGREADY_SG3_SETPOINT_CHANGE_D798 = DataTag(["D798"])
    # lngD799 = ["SG4: Zwangslauf", "SG4: Forced run", "SG4: Marche forc\xe9e"],
    SGREADY_SG4_FORCE_RUN_D799 = DataTag(["D799"])

    ##################################################################################
    # BASICVENT / ECOVENT Stuff...
    # PID-Regler: Proportional-Integral-Differenzial-Regler
    ##################################################################################
    # A4387: uom: '', 'Energieersparnis gesamt'
    BASICVENT_ENERGY_SAVE_TOTAL_A4387 = DataTag(["A4387"], decode_f=DataTag._decode_value_analog)
    # A4389: uom: '', 'Energieersparnis aktuell'
    BASICVENT_ENERGY_SAVE_CURRENT_A4389 = DataTag(["A4389"], decode_f=DataTag._decode_value_analog)
    # A4391: uom: '', 'Wärmerückgewinnungsgrad'
    BASICVENT_ENERGY_RECOVERY_RATE_A4391 = DataTag(["A4391"], decode_f=DataTag._decode_value_analog)
    # A4498: uom: 'Tage', 'Luftfilter Wechsel Betriebsstunden'
    BASICVENT_FILTER_CHANGE_OPERATING_DAYS_A4498 = DataTag(["A4498"], decode_f=DataTag._decode_value_analog)
    # A4504: uom: 'Tage', 'Luftfilter Wechsel Betriebsstunden Restlaufzeit dd'
    BASICVENT_FILTER_CHANGE_REMAINING_OPERATING_DAYS_A4504 = DataTag(["A4504"], decode_f=DataTag._decode_value_analog)
    # D1544: uom: '', 'Luftfilter Wechsel Betriebsstunden Reset'
    BASICVENT_FILTER_CHANGE_OPERATING_HOURS_RESET_D1544 = DataTag(["D1544"], writeable=True)
    # D1469: uom: '', 'Luftfilter Wechselanzeige'
    BASICVENT_FILTER_CHANGE_DISPLAY_D1469 = DataTag(["D1469"])
    # D1626: uom: '', 'Luftfilter Wechselanzeige Animation'
    # BASICVENT_FILTER_CHANGE_DISPLAY_ANIMATION_D1626 = DataTag(["D1626"])

    # A4506: uom: '', 'Hu Luftfeuchtigkeit PID'
    # BASICVENT_HUMIDITY_SETPOINT_A4506 = DataTag(["A4506"], writeable=True, decode_f=DataTag._decode_value_analog)
    # A4508: uom: '', 'Hu Luftfeuchtigkeit Sollwert'
    # BASICVENT_HUMIDITY_DEMAND_A4508 = DataTag(["A4508"], decode_f=DataTag._decode_value_analog)
    # A4510: uom: '', 'Hu Luftfeuchtigkeit'
    # BASICVENT_HUMIDITY_SECOND_VALUE_A4510 = DataTag(["A4510"], decode_f=DataTag._decode_value_analog)
    # A4990: uom: '', 'Luftfeuchtigkeit'
    BASICVENT_HUMIDITY_VALUE_A4990 = DataTag(["A4990"], decode_f=DataTag._decode_value_analog)

    # A4512: uom: '', 'CO2-Konzentration PID'
    # BASICVENT_CO2_SETPOINT_A4512 = DataTag(["A4512"], writeable=True, decode_f=DataTag._decode_value_analog)
    # A4514: uom: '', 'CO2-Konzentration Sollwert'
    # BASICVENT_CO2_DEMAND_A4514 = DataTag(["A4514"], decode_f=DataTag._decode_value_analog)
    # A4516: uom: '', 'CO2-Konzentration'
    # BASICVENT_CO2_SECOND_VALUE_A4516 = DataTag(["A4516"], decode_f=DataTag._decode_value_analog)
    # A4992: uom: '', 'CO2'
    BASICVENT_CO2_VALUE_A4992 = DataTag(["A4992"], decode_f=DataTag._decode_value_analog)

    # A4518: uom: '', 'VOC Kohlenwasserstoffverbindungen PID'
    # BASICVENT_VOC_SETPOINT_A4518 = DataTag(["A4518"], writeable=True, decode_f=DataTag._decode_value_analog)
    # A4520: uom: '', 'VOC Kohlenwasserstoffverbindungen Sollwert'
    # BASICVENT_VOC_DEMAND_A4520 = DataTag(["A4520"], decode_f=DataTag._decode_value_analog)
    # A4522: uom: '', 'VOC Kohlenwasserstoffverbindungen'
    BASICVENT_VOC_VALUE_A4522 = DataTag(["A4522"], decode_f=DataTag._decode_value_analog)

    # I4523: uom: '', 'Luftqualitaet Messung VOC CO2 Sensor'

    # I4582: uom: '', opts: { type:'select', options: ['Tag','Nacht','Zeitprogramm','Party','Urlaub','Bypass'] }, 'i_Mode'
    BASICVENT_OPERATION_MODE_I4582 = DataTag(["I4582"], writeable=True, decode_f=DataTag._decode_six_steps_mode, encode_f=DataTag._encode_six_steps_mode)

    # https://github.com/marq24/ha-waterkotte/issues/49 (I4582 might not be in use - could be that "3:HREG400418" does it)
    BASICVENT_OPERATION_MODE_ALT = DataTag(["3:HREG400418"], writeable=True, decode_f=DataTag._decode_six_steps_mode, encode_f=DataTag._encode_six_steps_mode)

    # mdi:air-filter
    # mdi:hvac
    # mdi:wind-power

    # A4549: uom: '', 'Luefter 1 Rueckmeldung'
    BASICVENT_INCOMING_FAN_FEEDBACK_A4549 = DataTag(["A4549"])
    # D1605: uom: '', 'Luefter 1 - Manuell Drehzahl'
    BASICVENT_INCOMING_FAN_MANUAL_MODE = DataTag(["3:HREG400447"], writeable=True)
    BASICVENT_INCOMING_FAN_MANUAL_SPEED_PERCENT = DataTag(["3:HREG400443"], writeable=True)
    # A4551: uom: 'U/min', 'Luefter 1 Umdrehungen pro Minute'
    BASICVENT_INCOMING_FAN_RPM_A4551 = DataTag(["A4551"], decode_f=DataTag._decode_value_analog)
    # A4986: uom: '%', 'Analogausgang Y1' - Rotation Incoming air drive percent
    BASICVENT_INCOMING_FAN_A4986 = DataTag(["A4986"], decode_f=DataTag._decode_value_analog)
    # A5000: uom: '', 'T1' - Außenluft/Frischluft - Outdoor air
    BASICVENT_TEMPERATURE_INCOMING_AIR_BEFORE_ODA_A5000 = DataTag(["A5000"], decode_f=DataTag._decode_value_analog)
    # A4996: uom: '', 'T3' - Zuluft - Supply air
    BASICVENT_TEMPERATURE_INCOMING_AIR_AFTER_SUP_A4996 = DataTag(["A4996"], decode_f=DataTag._decode_value_analog)

    # A4545: uom: '', 'Luefter 2 Rueckmeldung'
    BASICVENT_OUTGOING_FAN_FEEDBACK_A4545 = DataTag(["A4545"])
    # D1603: uom: '', 'Luefter 2 - Manuell Drehzahl'
    BASICVENT_OUTGOING_FAN_MANUAL_MODE = DataTag(["3:HREG400448"], writeable=True)
    BASICVENT_OUTGOING_FAN_MANUAL_SPEED_PERCENT = DataTag(["3:HREG400445"], writeable=True)
    # A4547: uom: 'U/min', 'Luefter 2 Umdrehungen pro Minute'
    BASICVENT_OUTGOING_FAN_RPM_A4547 = DataTag(["A4547"], decode_f=DataTag._decode_value_analog)
    # A4984: uom: '%', 'Analogausgang Y2' - Rotation Ongoing air drive percent
    BASICVENT_OUTGOING_FAN_A4984 = DataTag(["A4984"], decode_f=DataTag._decode_value_analog)
    # A4998: uom: '', 'T2' -> Abluft - Extract air
    BASICVENT_TEMPERATURE_OUTGOING_AIR_BEFORE_ETH_A4998 = DataTag(["A4998"], decode_f=DataTag._decode_value_analog)
    # A4994: uom: '', 'T4' -> Fortluft - Exhaust air
    BASICVENT_TEMPERATURE_OUTGOING_AIR_AFTER_EEH_A4994 = DataTag(["A4994"], decode_f=DataTag._decode_value_analog)

    # D1432: uom: '', 'Bypass Aktiv' -
    BASICVENT_STATUS_BYPASS_ACTIVE_D1432 = DataTag(["D1432"])
    # D1433: uom: '', 'HU En'
    BASICVENT_STATUS_HUMIDIFIER_ACTIVE_D1433 = DataTag(["D1433"])
    # D1465: uom: '', 'Comfort-Bypass'
    BASICVENT_STATUS_COMFORT_BYPASS_ACTIVE_D1465 = DataTag(["D1465"])
    # D1466: uom: '', 'Smartbypass'
    BASICVENT_STATUS_SMART_BYPASS_ACTIVE_D1466 = DataTag(["D1466"])
    # D1503: uom: '', 'Holiday enabled'
    BASICVENT_STATUS_HOLIDAY_ENABLED_D1503 = DataTag(["D1503"])

    #############################
    # UNKNOWN BASIC VENT VALUES #
    #############################
    # A4420: uom: '', 'Luftmenge Stufe 2 - Nennlüftung NL'

    # A4525: uom: '', 'Schutzfunktion Ablufttemperatur Schaltdifferenz'
    # A4527: uom: '', 'Schutzfunktion Ablufttemperatur Unterbrechung'
    # A4529: uom: '', 'Schutzfunktion Ablufttemperatur Warnung'

    # A4531: uom: '', 'Frostschutzfunktion Fortluft EHH NotAus'
    # A4533: uom: '', 'Frostschutzfunktion Taktbetrieb High'
    # A4535: uom: '', 'Frostschutzfunktion Taktbetrieb Low'
    # A4537: uom: '', 'Frostschutzfunktion Schaltdifferenz'
    # A4539: uom: '', 'Frostschutzfunktion Fortluft EHH'
    # A4541: uom: '', 'Frostschutzfunktion Aussenluft ODA'

    # A4542: uom: '', 'Feuerstaetten Funktion FPF Betriebsmodus Abluft'
    # A4543: uom: '', 'Feuerstaetten Funktion FPF Betriebsmodus Aussenluft'

    # D1488: uom: '', 'Warnung Wxxx'
    # D1489: uom: '', 'Fehler Fxxx'
    # D1490: uom: '', 'Fehler Fxxx'
    # D1491: uom: '', 'Fehler Fxxx'

    # D1508: uom: '', 'Frostschutz Auskuehlschutz T1'
    # D1507: uom: '', 'Frostschutz Auskuehlschutz T2'

    # D1627: uom: '', 'Feuerstaetten Funktion FPF Animation'
    # D1628: uom: '', 'Rauchmelder Brandschutz Funktion SDF Animation'
    # D1629: uom: '', 'Frostschutzfunktion Aussenluft ODA FALSE OK'

    # D2035: uom: '', 'Anschlussseite Rechts TRUE oder Rechts FALSE'
    # D2036: uom: '', 'Anschlussseite Links TRUE oder Rechts FALSE'
    # I2331: uom: '', 'TT_b_enabled[5,6]'
    # I2484: uom: '', 'TT_b_enabled[5,2]'
    # I2889: uom: '', 'TT_b_enabled[6,5]'

    ###############################
    ###############################
    #### from ioBroker impl... ####
    ###############################
    ###############################
    # ignore D74     coolingIndicatorState = getServiceIndicator('D74'); -> ['Kühlbetrieb'];
    # ignore D75     getIndicator(coolingStatus, 'D75')); -> Kühlbetrieb Zeitprogram
    # ignore D160    poolIndicatorState = getServiceIndicator('D160'); -> ['Pool-Heizbetrieb'];
    # ignore D196    solarIndicatorState = getServiceIndicator('D196'); -> ['Solarbetrieb'];
    # ignore D232    extHeaterIndicatorState = getServiceIndicator('D232'); -> ['Ext. Wärmeerzeuger'];
    # ignore D635    pvIndicatorState = getServiceIndicator('D635'); -> ['Photovoltaik'];

    # HEATING ROOM INFLUENCE Settings... MAIN question tag A101 - will it be witten as A101 or as I264 ???!
    TEMPERATURE_ROOM_1H_A98 = DataTag(["A98"], "°C")  # ['Raumtemperatur Ø1h', 'T room 1h', 'T-pi\xe8ce 1h'];
    TEMPERATURE_ROOM_TARGET_A100 = DataTag(["A100"], "°C", writeable=True)  # from 15°C - 30°C
    ROOM_INFLUENCE_A101_OR_I264 = DataTag(["I264"], "%", writeable=True)  # not really writable?!
    # <select id="I264" class="form-control" style="width: 100px; color: rgb(85, 85, 85);">
    #    <option value="0">0%</option>
    #    <option value="1">50%</option>
    #    <option value="2">100%</option>
    #    <option value="3">150%</option>
    #    <option value="4">200%</option>
    # </select>
    # A102    getState(heatingInfluence, 'A102', '+/-30 K')); -> ['kleinster Wert'];
    # A103    getState(heatingInfluence, 'A103', '+/-30 K')); -> ['grösster Wert'];
    # ignore A99     getReadOnlyState(heatingInfluence, 'A99', 'K')); -> ['aktueller Wert'];

    # THERMAL DESINFECTION MODE: NONE, (selected) DAYs, ALL
    # ignore I508	getEnumState(waterThermalDis, 'I508', dict.noneDayAll)); -> ['Wochenprogramm', 'Schedule', 'Programme hebdomadaire'];

    # HOT WATER - SOLAR-SUPPORT Values
    # A169 -> TEMPERATURE_WATER_SETPOINT_FOR_SOLAR
    # ignore I517	getState(waterSolarSupp, 'I517', '')); -> ['Verzögerung Kompressorstart', 'Delay for compressor during solar heating', 'Temps de retard pour Start compresseur',
    # ignore I518	getReadOnlyState(waterSolarSupp, 'I518')); -> ['Zeit bis Kompressorstart', 'Compressor starting in...', 'Le compresseur d\xe9marre dans'];

    # SOLAR SUPPORT -> pgSolar.html
    # A205	getState(solarSettings, 'A205', 'K')); -> ['Einschalttemperaturdifferenz', 'Switch on temperature difference', "Diff\xe9rence de temp\xe9rature d'enclenchement",
    # A206	getState(solarSettings, 'A206', 'K')); -> ['Ausschalttemperaturdifferenz', 'Switch off temperature difference',"Diff\xe9rence de temp\xe9rature d'arr\xeat",
    # A207	getState(solarSettings, 'A207', 'K')); -> ['Maximale Kollektortemperatur', 'Maximum collector temperature','Temp\xe9rature maximale du collecteur',
    # A209	getReadOnlyState(solarSettings, 'A209', '°C')); -> ['geforderte Temperatur Vorlauf', 'Required temperature flow', 'Consigne d\xe9part'];
    # SOLAR SUPORT REGENERATION
    # A686	getReadOnlyState(solarRegen, 'A686', '°C')); -> ['Sondentemperatur'];
    # A687	getState(solarRegen, 'A687', '°C')); -> ['Max. Sonden Temperatur'];
    # A688	getState(solarRegen, 'A688', 'K')); -> ['Schaltdifferenz max. Temperatur'];
    # I2253	getEnumState(solarRegen, 'I2253', "OPEN" or "CLOSED")); -> ['Motorventil Warmwasser bei Sonden Regenerierung'];

    # PV SUPPORT (there is much much more!
    # A1223	getReadOnlyState(pvSettings, 'A1223', 'kW')); -> ['Photovoltaik Überschuss'];
    # A1194	getReadOnlyState(pvSettings, 'A1194', 'kW')); -> ['15 Min.-Mittelwert der Netzeinspeisung'];
    # A1224	getReadOnlyState(pvSettings, 'A1224', 'kW')); -> ['Einschaltgrenzwert für PV'];

    PREASSURE_P1_SUCTION_GAS_I2017 = DataTag(["I2017"], "bar")  # -> ['p1 Sauggas'];
    PREASSURE_P2_EXIT_I2018 = DataTag(["I2018"], "bar")  # -> ['p2 Austritt'];
    PREASSURE_P3_INTERMEDIATE_INJECTION_I2019 = DataTag(["I2019"], "bar")  # -> ['p3 Zwischeneinspritzung'];
    TEMPERATURE_T2_SURROUNDING_I2020 = DataTag(["I2020"], "°C")  # -> ['T2 Umgebung'];
    TEMPERATURE_T3_SUCTION_GAS_I2021 = DataTag(["I2021"], "°C")  # -> ['T3 Sauggas'];
    TEMPERATURE_T4_COMPRESSOR_I2022 = DataTag(["I2022"], "°C")  # -> ['T4 Verdichter'];
    TEMPERATURE_T5_EVI_I2025 = DataTag(["I2025"], "°C")  # -> ['T5 EVI'];
    TEMPERATURE_T6_FLUID_I2024 = DataTag(["I2024"], "°C")  # -> ['T6 Flüssig'];
    TEMPERATURE_T7_OIL_SUMP_I2023 = DataTag(["I2023"], "°C")  # -> ['T7 Ölsumpf'];
    TEMPERATURE_EVAPORATOR_I2032 = DataTag(["I2032"], "°C")  # -> ['T Verdampfer'];
    TEMPERATURE_OVERHEATING_I2033 = DataTag(["I2033"], "°K")  # -> ['Überhitzung'];
    TEMPERATURE_CONDENTATION_I2034 = DataTag(["I2034"], "°C")  # ['T Kondensation'];
    TEMPERATURE_COMPRESSED_GAS_I2039 = DataTag(["I2039"], "°C")  # -> ['T Druckgas'];
    FLOW_VORTEX_SENSOR_A1022 = DataTag(["A1022"], "l/s")  # -> ['Durchfluss (Vortex Sensor)'];
    TEMPERATURE_VORTEX_SENSOR_A1023 = DataTag(["A1023"], "°C")  # -> ['Temperatur (Vortex Sensor)'];

    # pgService_IO
    # D815	getIndicator(statusDI, 'D815')); -> ['SM Quellenseite'];
    # D816	getIndicator(statusDI, 'D816')); -> ['SM Heizungsseite'];
    # D817	getIndicator(statusDI, 'D817')); -> ['SG Ready-A/ EVU'];
    # D818	getIndicator(statusDI, 'D818')); -> ['SG Ready-B/ Sollwert'];
    # D821	getIndicator(statusDI, 'D821')); -> ['HD-Pressostat'];
    # D822	getIndicator(statusDI, 'D822')); -> ['ND-Pressostat'];
    # D823	getIndicator(statusDI, 'D823')); -> ['Motorschutz 1'];
    # D824	getIndicator(statusDI, 'D824')); -> ['Motorschutz 2'];
    # D1010	getIndicator(statusDI, 'D1010')); -> ['SM Phase/Drehf.'];

    # A699	getReadOnlyState(measurements, 'A699', '°C')); -> UNKNOWN
    # A700	getReadOnlyState(measurements, 'A700', '°C')); -> UNKNOWN
    # A701	getReadOnlyState(measurements, 'A701', '°C')); -> UNKNOWN
    # A702	getReadOnlyState(measurements, 'A702', '°C')); -> UNKNOWN
    # D701	getIndicator(status, 'D701')); -> UNKNOWN


    # pgService_Pump

    # Quellenpumpe
    PUMPSERVICE_SOURCEPUMP_I1281 = DataTag(['I1281'], writeable=True) # Select
    PUMPSERVICE_SOURCEPUMP_MODE_I1764 = DataTag(['I1764'], writeable=True) # Select
    PUMPSERVICE_SOURCEPUMP_CABLE_BREAK_MONITORING_D881 = DataTag(['D881'], writeable=True) # ON/OFF Switch
    PUMPSERVICE_SOURCEPUMP_PRE_RUNTIME_I1278 = DataTag(['I1278'], writeable=True) # Number select TIME Sec (min 25)
    PUMPSERVICE_SOURCEPUMP_POST_RUNTIME_I1279 = DataTag(['I1279'], writeable=True) # Number select TIME Sec
    PUMPSERVICE_SOURCEPUMP_ANTI_JAMMING_I1280 = DataTag(['I1280'], writeable=True) # Number select TIME Sec

    # Erweiterte Einstellungen für die Baureihe ET 6900
    # D1273 - Heizungsumw\xe4lzpumpe ET 6900 Q
    # <option value="0">Single</option>
    # <option value="1">Duo</option>
    # D1274 - Quellenpumpe ET 6900 Q
    # <option value="0">Single</option>
    # <option value="1">Duo</option>

    # Wärmequellenregeneration
    # D1294 - Quellenpumpe Regeneration
    PUMPSERVICE_SOURCEPUMP_REGENERATION_D1294 = DataTag(['D1294'], writeable=True) # Switch ON/OFF
    # A1539 - T Quelle ein < : -50.00 - +50.00 °C
    PUMPSERVICE_SOURCEPUMP_TEMP_ON_LOWER_A1539 = DataTag(['A1539'], writeable=True) # Number range -50/+50°C

    # Heizbetrieb
    PUMPSERVICE_SOURCEPUMP_HEATMODE_REGULATION_BY_I1752 = DataTag(['I1752'], writeable=True) # select
    PUMPSERVICE_SOURCEPUMP_HEATMODE_CONTROL_BEHAVIOUR_D789 = DataTag(['D789'], writeable=True) # select
    PUMPSERVICE_SOURCEPUMP_HEATMODE_REGULATION_START_D996 = DataTag(['D996'], writeable=True) # select
    PUMPSERVICE_SOURCEPUMP_HEATMODE_MINSPEED_A485 = DataTag(['A485'], writeable=True) # Number range 0-100%
    PUMPSERVICE_SOURCEPUMP_HEATMODE_MAXSPEED_A486 = DataTag(['A486'], writeable=True) # Number range 0-100%
    PUMPSERVICE_SOURCEPUMP_HEATMODE_SOURCE_TEMPERATURE_A479 = DataTag(['A479'], writeable=True) # Number range 0-50 °K

    # Kühlbetrieb
    PUMPSERVICE_SOURCEPUMP_COOLINGMODE_REGULATION_BY_I2102 = DataTag(['I2102'], writeable=True) # select
    PUMPSERVICE_SOURCEPUMP_COOLINGMODE_CONTROL_BEHAVIOUR_D995 = DataTag(['D995'], writeable=True) # select
    PUMPSERVICE_SOURCEPUMP_COOLINGMODE_REGULATION_START_D997 = DataTag(['D997'], writeable=True) # select
    PUMPSERVICE_SOURCEPUMP_COOLINGMODE_MINSPEED_A1032 = DataTag(['A1032'], writeable=True) # Number range 0-100%
    PUMPSERVICE_SOURCEPUMP_COOLINGMODE_MAXSPEED_A1033 = DataTag(['A1033'], writeable=True) # Number range 0-100%
    PUMPSERVICE_SOURCEPUMP_COOLINGMODE_SOURCE_TEMPERATURE_A1034 = DataTag(['A1034'], writeable=True) # Number range 0-50 °C

    # PID-Control...
