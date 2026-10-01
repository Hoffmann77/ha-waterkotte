"""Tests for the config flow of the Waterkotte Heatpump integration."""
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterkotte_heatpump.const import (
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
    assert result["title"] == "Waterkotte Ai1+ (WE15123456)"
    assert result["result"].unique_id == SERIAL
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
    assert result["result"].unique_id is None
    assert result["data"][CONF_SERIAL] is None
    assert result["title"] == "Waterkotte Ai1+"


async def test_already_configured_serial(hass: HomeAssistant, mock_client: MagicMock, mock_setup_entry: AsyncMock) -> None:
    """Test that the same heat pump (same serial number) can't be added twice - even with another host."""
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_HOST: "192.168.1.99"}).add_to_hass(hass)
    result = await _start_ecotouch_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT_ECOTOUCH)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_already_configured_host(hass: HomeAssistant, mock_client: MagicMock, mock_setup_entry: AsyncMock) -> None:
    """Test that a heat pump without serial number can't be added twice with the same host."""
    MockConfigEntry(domain=DOMAIN, data={CONF_HOST: HOST}).add_to_hass(hass)
    mock_client.async_read_values.return_value = device_info_values(serial=None)
    result = await _start_ecotouch_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT_ECOTOUCH)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test that the options flow stores only its own settings (and not the connection data)."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=2, unique_id=SERIAL, data={**USER_INPUT_ECOTOUCH, CONF_SYSTEMTYPE: "ECOTOUCH"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "waterkotte",
            CONF_PASSWORD: "new-password",
            CONF_POLLING_INTERVAL: 30,
            CONF_TAGS_PER_REQUEST: 50,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_USERNAME: "waterkotte",
        CONF_PASSWORD: "new-password",
        CONF_POLLING_INTERVAL: 30,
        CONF_TAGS_PER_REQUEST: 50,
    }
    assert entry.data[CONF_HOST] == HOST


async def _start_reconfigure_flow(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    """Start a reconfigure flow for the given entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    return result


async def test_reconfigure(hass: HomeAssistant, mock_client: MagicMock, mock_setup_entry: AsyncMock) -> None:
    """Test that the host of the same heat pump can be changed."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=2, unique_id=SERIAL, data={**USER_INPUT_ECOTOUCH, CONF_SYSTEMTYPE: "ECOTOUCH"})
    entry.add_to_hass(hass)
    result = await _start_reconfigure_flow(hass, entry)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "192.168.1.60"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.1.60"


async def test_reconfigure_wrong_device(hass: HomeAssistant, mock_client: MagicMock, mock_setup_entry: AsyncMock) -> None:
    """Test that the host can't be changed to another heat pump."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=2, unique_id=SERIAL, data={**USER_INPUT_ECOTOUCH, CONF_SYSTEMTYPE: "ECOTOUCH"})
    entry.add_to_hass(hass)
    mock_client.async_read_values.return_value = device_info_values(serial="WE15999999")
    result = await _start_reconfigure_flow(hass, entry)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "192.168.1.60"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == HOST
