"""Tests for the config flow of the Waterkotte Heatpump integration."""
from unittest.mock import AsyncMock, MagicMock

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
from .conftest import HOST, SERIAL

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
