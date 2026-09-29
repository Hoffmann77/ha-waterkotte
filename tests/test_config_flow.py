"""Tests for the config flow of the Waterkotte Heatpump integration."""
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.waterkotte_heatpump.const import (
    CONF_ADD_SCHEDULE_ENTITIES,
    CONF_ADD_SERIAL_AS_ID,
    CONF_POLLING_INTERVAL,
    CONF_SERIAL,
    CONF_SYSTEMTYPE,
    CONF_TAGS_PER_REQUEST,
    DOMAIN,
)
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import (
    Http404Exception,
    InvalidPasswordException,
    TooManyUsersException,
)
from .conftest import HOST, SERIAL, device_info_values

USER_INPUT_ECOTOUCH = {
    CONF_HOST: HOST,
    CONF_USERNAME: "waterkotte",
    CONF_PASSWORD: "waterkotte",
    CONF_POLLING_INTERVAL: 60,
    CONF_TAGS_PER_REQUEST: 75,
    CONF_ADD_SCHEDULE_ENTITIES: False,
    CONF_ADD_SERIAL_AS_ID: False,
}


async def _start_ecotouch_flow(hass: HomeAssistant) -> dict:
    """Start a flow and select the EcoTouch interface type."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SYSTEMTYPE: "ecotouch"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user_ecotouch"
    return result


async def test_full_flow_ecotouch(hass: HomeAssistant, mock_client: MagicMock, mock_setup_entry: AsyncMock) -> None:
    """Test a successful setup of an EcoTouch heat pump."""
    result = await _start_ecotouch_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT_ECOTOUCH)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "features"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_SERIAL] == SERIAL
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("login_error", "read_result", "expected_error"),
    [
        (InvalidPasswordException("INVALID_PWD"), None, "invalid_auth"),
        (TooManyUsersException("TOO_MANY_USERS"), None, "too_many_users"),
        (aiohttp.ClientConnectionError(), None, "cannot_connect"),
        (Http404Exception("HTTP 404"), None, "cannot_connect"),
        (ValueError("boom"), None, "unknown"),
        (None, {}, "cannot_connect"),
    ],
)
async def test_connection_errors(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_setup_entry: AsyncMock,
    login_error: Exception | None,
    read_result: dict | None,
    expected_error: str,
) -> None:
    """Test that connection problems are reported on the form - and that the user can recover."""
    result = await _start_ecotouch_flow(hass)

    mock_client.async_check_login.side_effect = login_error
    if read_result is not None:
        mock_client.async_read_values.return_value = read_result
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT_ECOTOUCH)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user_ecotouch"
    assert result["errors"] == {"base": expected_error}

    mock_client.async_check_login.side_effect = None
    mock_client.async_read_values.return_value = device_info_values()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT_ECOTOUCH)
    assert result["step_id"] == "features"


async def test_missing_serial_is_no_error(hass: HomeAssistant, mock_client: MagicMock, mock_setup_entry: AsyncMock) -> None:
    """Test that a heat pump that does not provide a serial number can be set up."""
    mock_client.async_read_values.return_value = device_info_values(serial=None)
    result = await _start_ecotouch_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT_ECOTOUCH)
    assert result["step_id"] == "features"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
