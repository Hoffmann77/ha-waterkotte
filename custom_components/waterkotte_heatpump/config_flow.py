"""Adds config flow for Waterkotte Heatpump."""
import logging

import aiohttp
import voluptuous as vol

from custom_components.waterkotte_heatpump.pywaterkotte_ha import WaterkotteClient
from custom_components.waterkotte_heatpump.pywaterkotte_ha.const import EASYCON, ECOTOUCH
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag
from homeassistant import config_entries
from homeassistant.const import CONF_ID, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.util import uuid as uuid_util
from .const import (
    DOMAIN,
    TITLE,
    CONF_POLLING_INTERVAL,
    CONF_TAGS_PER_REQUEST,
    CONF_BIOS,
    CONF_FW,
    CONF_SERIAL,
    CONF_SERIES,
    CONF_SYSTEMTYPE,
    CONF_ADD_SCHEDULE_ENTITIES,
    CONF_ADD_SERIAL_AS_ID,
    CONF_USE_DISINFECTION,
    CONF_USE_HEATING_CURVE,
    CONF_USE_VENT,
    CONF_USE_POOL,
    CONFIG_VERSION, CONFIG_MINOR_VERSION
)
from .pywaterkotte_ha.error import Http404Exception, InvalidPasswordException, TooManyUsersException

_LOGGER: logging.Logger = logging.getLogger(__package__)


def _tag_value(values: dict, tag: WKHPTag) -> str | None:
    """Return the value of a tag as string - or None, if the heat pump did not provide a value"""
    entry = values.get(tag)
    if entry is None or entry.get("value") is None or str(entry["value"]) in ("", "None"):
        return None
    return str(entry["value"])


class WaterkotteHeatpumpFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for waterkotte_heatpump."""

    VERSION = CONFIG_VERSION
    MINOR_VERSION = CONFIG_MINOR_VERSION
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}
        self._user_step_user_input = None
        self._bios = ""
        self._firmware = ""
        self._id = ""
        self._series = ""
        self._serial = ""

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            if CONF_SYSTEMTYPE in user_input:
                # it really sucks, that translation keys have to be lower case...
                user_input[CONF_SYSTEMTYPE] = user_input[CONF_SYSTEMTYPE].upper()

                if user_input[CONF_SYSTEMTYPE] == EASYCON:
                    return await self.async_step_user_easycon()
                else:
                    return await self.async_step_user_ecotouch()
        else:
            user_input = {}
            user_input[CONF_SYSTEMTYPE] = ECOTOUCH

        # it really sucks, that translation keys have to be lower case... so we need to make sure that our
        # options are all translate to lower case!
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SYSTEMTYPE, default=(user_input.get(CONF_SYSTEMTYPE, ECOTOUCH)).lower()):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[ECOTOUCH.lower(), EASYCON.lower()],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_SYSTEMTYPE
                        )
                    ),
            }),
            description_placeholders={"repo": "https://github.com/marq24/ha-waterkotte"},
            last_step=False,
            errors=self._errors
        )

    async def async_step_user_easycon(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        # Uncomment the next 2 lines if only a single instance of the integration is allowed:
        # if self._async_current_entries():
        #     return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            user_input[CONF_SYSTEMTYPE] = EASYCON
            user_input[CONF_ADD_SCHEDULE_ENTITIES] = False
            error = await self._test_connection(
                host=user_input[CONF_HOST],
                username=user_input.get(CONF_USERNAME),
                pwd=user_input.get(CONF_PASSWORD),
                system_type=user_input[CONF_SYSTEMTYPE],
                tags_per_request=user_input[CONF_TAGS_PER_REQUEST],
            )
            if error is None:
                await self._async_abort_if_already_configured(user_input[CONF_HOST])
                user_input[CONF_BIOS] = self._bios
                user_input[CONF_FW] = self._firmware
                user_input[CONF_SERIES] = self._series
                user_input[CONF_SERIAL] = self._serial if self._serial is not None else uuid_util.random_uuid_hex()
                user_input[CONF_ID] = self._id
                self._user_step_user_input = dict(user_input)
                return await self.async_step_features()
            else:
                self._errors["base"] = error
        else:
            user_input = {}
            user_input[CONF_HOST] = ""
            user_input[CONF_USERNAME] = ""
            user_input[CONF_PASSWORD] = ""
            user_input[CONF_ADD_SERIAL_AS_ID] = False

        return self.async_show_form(
            step_id="user_easycon",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST)): str,
                vol.Optional(CONF_USERNAME, default=user_input.get(CONF_USERNAME)): str,
                vol.Optional(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD)): str,
                vol.Required(CONF_POLLING_INTERVAL, default=500): int,
                vol.Required(CONF_TAGS_PER_REQUEST, default=25): int,
                vol.Required(CONF_ADD_SERIAL_AS_ID, default=False): bool
            }),
            description_placeholders={"repo": "https://github.com/marq24/ha-waterkotte"},
            last_step=False,
            errors=self._errors
        )

    async def async_step_user_ecotouch(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        # Uncomment the next 2 lines if only a single instance of the integration is allowed:
        # if self._async_current_entries():
        #     return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            user_input[CONF_SYSTEMTYPE] = ECOTOUCH
            error = await self._test_connection(
                host=user_input[CONF_HOST],
                username=user_input.get(CONF_USERNAME),
                pwd=user_input[CONF_PASSWORD],
                system_type=user_input[CONF_SYSTEMTYPE],
                tags_per_request=user_input[CONF_TAGS_PER_REQUEST],
            )
            if error is None:
                await self._async_abort_if_already_configured(user_input[CONF_HOST])
                user_input[CONF_BIOS] = self._bios
                user_input[CONF_FW] = self._firmware
                user_input[CONF_SERIES] = self._series
                user_input[CONF_SERIAL] = self._serial if self._serial is not None else uuid_util.random_uuid_hex()
                user_input[CONF_ID] = self._id
                self._user_step_user_input = dict(user_input)
                return await self.async_step_features()
            else:
                self._errors["base"] = error
        else:
            user_input = {}
            user_input[CONF_HOST] = ""
            user_input[CONF_USERNAME] = "waterkotte"
            user_input[CONF_PASSWORD] = "waterkotte"
            user_input[CONF_ADD_SCHEDULE_ENTITIES] = False
            user_input[CONF_ADD_SERIAL_AS_ID] = False

        return self.async_show_form(
            step_id="user_ecotouch",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST)): str,
                vol.Optional(CONF_USERNAME, default=user_input.get(CONF_USERNAME)): str,
                vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD)): str,
                vol.Required(CONF_POLLING_INTERVAL, default=60): int,
                vol.Required(CONF_TAGS_PER_REQUEST, default=75): int,
                vol.Required(CONF_ADD_SCHEDULE_ENTITIES, default=False): bool,
                vol.Required(CONF_ADD_SERIAL_AS_ID, default=False): bool,
            }),
            last_step=False,
            errors=self._errors
        )

    async def async_step_features(self, user_input=None):
        self._errors = {}
        if user_input is not None:
            for k, v in user_input.items():
                self._user_step_user_input[k] = v

            return self.async_create_entry(title=TITLE, data=self._user_step_user_input)
        else:
            return self.async_show_form(
                step_id="features",
                data_schema=vol.Schema({
                    vol.Required(CONF_USE_VENT, default=False): bool,
                    vol.Required(CONF_USE_HEATING_CURVE, default=False): bool,
                    vol.Required(CONF_USE_DISINFECTION, default=False): bool,
                    vol.Required(CONF_USE_POOL, default=False): bool,
                }),
                last_step=True,
                errors=self._errors
            )

    async def async_step_reconfigure(self, user_input=None):
        """Change the host of an existing configuration."""
        self._errors = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            error = await self._test_connection(
                host=user_input[CONF_HOST],
                username=entry.options.get(CONF_USERNAME, entry.data.get(CONF_USERNAME)),
                pwd=entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD)),
                system_type=entry.data.get(CONF_SYSTEMTYPE, ECOTOUCH),
                tags_per_request=entry.options.get(CONF_TAGS_PER_REQUEST, entry.data.get(CONF_TAGS_PER_REQUEST, 10)),
            )
            if error is None:
                if entry.unique_id is not None:
                    # make sure that the new host is still the same heat pump
                    await self.async_set_unique_id(self._serial)
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: user_input[CONF_HOST]})
            else:
                self._errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST)): str,
            }),
            errors=self._errors
        )

    async def _test_connection(self, host, username, pwd, system_type, tags_per_request) -> str | None:
        """Connect to the heat pump and read the device information - returns an error key on failure"""
        # remove login credentials if not specified...
        if username is not None and len(str(username)) == 0:
            username = None
        if pwd is not None and len(str(pwd)) == 0:
            pwd = None

        client = WaterkotteClient(host=host, username=username, pwd=pwd, system_type=system_type,
                                  web_session=async_create_clientsession(self.hass), tags=None,
                                  tags_per_request=tags_per_request, lang=self.hass.config.language.lower())
        try:
            # the client.login() would swallow all errors (and retry) - so we check the login directly
            await client.async_check_login()
            ret = await client.async_read_values([
                WKHPTag.VERSION_BIOS,
                WKHPTag.VERSION_CONTROLLER,
                WKHPTag.INFO_ID,
                WKHPTag.INFO_SERIAL,
                WKHPTag.INFO_SERIES,
            ])
        except InvalidPasswordException:
            return "invalid_auth"
        except TooManyUsersException:
            return "too_many_users"
        except (Http404Exception, aiohttp.ClientError, TimeoutError) as exc:
            # a HTTP 404 is also the result, when the wrong interface type have been selected
            _LOGGER.info(f"could not connect to waterkotte@{host}: {type(exc).__name__} {exc}")
            return "cannot_connect"
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception(f"unexpected exception while connecting to waterkotte@{host}: {exc}")
            return "unknown"

        if not ret:
            # nothing could be read (e.g. wrong interface type or wrong BasicAuth credentials for EasyCon)
            return "cannot_connect"

        _LOGGER.info(f"successfully validated login -> result: {ret}")
        self._bios = _tag_value(ret, WKHPTag.VERSION_BIOS)
        self._firmware = _tag_value(ret, WKHPTag.VERSION_CONTROLLER)
        self._id = _tag_value(ret, WKHPTag.INFO_ID)
        self._series = _tag_value(ret, WKHPTag.INFO_SERIES)
        self._serial = _tag_value(ret, WKHPTag.INFO_SERIAL)
        return None

    async def _async_abort_if_already_configured(self, host: str) -> None:
        """Abort the flow, if the heat pump is already configured (identified by its serial number or its host)"""
        if self._serial is not None:
            await self.async_set_unique_id(self._serial)
            self._abort_if_unique_id_configured()
        else:
            self._async_abort_entries_match({CONF_HOST: host})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WaterkotteHeatpumpOptionsFlowHandler()


class WaterkotteHeatpumpOptionsFlowHandler(config_entries.OptionsFlow):

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            # the options contain only the settings of this form - the connection data (like the host)
            # stays in the config entry data
            return self.async_create_entry(data=user_input)

        # settings that have not been changed via the options yet, are taken from the initial configuration
        entry = self.config_entry
        def current(key, default):
            return entry.options.get(key, entry.data.get(key, default))

        if entry.data.get(CONF_SYSTEMTYPE, ECOTOUCH) == EASYCON:
            def_user = ""
            def_pass = ""
        else:
            def_user = "waterkotte"
            def_pass = "waterkotte"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional(CONF_USERNAME, default=current(CONF_USERNAME, def_user)): str,
                vol.Optional(CONF_PASSWORD, default=current(CONF_PASSWORD, def_pass)): str,
                vol.Required(CONF_POLLING_INTERVAL, default=current(CONF_POLLING_INTERVAL, 60)): int,
                vol.Required(CONF_TAGS_PER_REQUEST, default=current(CONF_TAGS_PER_REQUEST, 75)): int,
                vol.Required(CONF_ADD_SCHEDULE_ENTITIES, default=current(CONF_ADD_SCHEDULE_ENTITIES, False)): bool
            }),
            description_placeholders={"repo": "https://github.com/marq24/ha-waterkotte"},
        )
