"""Account group discovery and selection through Home Assistant config flows."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.mova_energy.api import (
    MovaEnergyApiClient,
    MovaEnergyApiClientAuthenticationError,
    MovaEnergyApiClientCommunicationError,
)
from custom_components.mova_energy.api.auth import MovaEnergyCloudAuth
from custom_components.mova_energy.const import (
    CLOUD_ENVIRONMENT_UAT,
    CLOUD_TENANT_ID,
    CONF_CLOUD_ENVIRONMENT,
    CONF_GROUP_ID,
    DEFAULT_CLOUD_API_URL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

TEST_GROUP_ID = "test-group-001"

GROUPS_URL = f"{DEFAULT_CLOUD_API_URL}/open/v1/query/groups"
LOGIN = {
    CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_UAT,
    CONF_USERNAME: "test-account",
    CONF_PASSWORD: "test-password",
}


async def start_cloud_login(hass: HomeAssistant) -> dict[str, Any]:
    """Submit login credentials through the public flow manager."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "cloud"})
    assert CONF_GROUP_ID not in result["data_schema"].schema
    return await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)


async def test_select_group_name_uses_id_in_requests(
    hass: HomeAssistant, mock_cloud_api: AsyncMock, mock_cloud_login: AsyncMock, cloud_groups: list[dict[str, Any]]
) -> None:
    """Labels show group names while the selected ID identifies the entry and all requests."""
    cloud_groups.append({"id": "second-id", "groupName": "Second home"})
    result = await start_cloud_login(hass)
    assert result["step_id"] == "cloud_group"
    selector = result["data_schema"].schema[CONF_GROUP_ID]
    assert selector.config["options"] == [
        {"value": TEST_GROUP_ID, "label": "Test group"},
        {"value": "second-id", "label": "Second home"},
    ]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: "second-id"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "second-id"
    assert result["data"][CONF_GROUP_ID] == "second-id"
    assert CONF_PASSWORD not in result["data"]
    mock_cloud_api.assert_any_await(method="get", url=f"{DEFAULT_CLOUD_API_URL}/open/v1/second-id/devices")


async def test_duplicate_and_missing_group_names(
    hass: HomeAssistant, mock_cloud_api: AsyncMock, mock_cloud_login: AsyncMock, cloud_groups: list[dict[str, Any]]
) -> None:
    """Repeated names include their IDs and a missing name falls back to the ID."""
    cloud_groups[:] = [
        {"id": "1", "groupName": "Home"},
        {"id": "2", "groupName": "Home"},
        {"id": "3", "groupName": None},
    ]
    result = await start_cloud_login(hass)
    assert result["data_schema"].schema[CONF_GROUP_ID].config["options"] == [
        {"value": "1", "label": "Home (1)"},
        {"value": "2", "label": "Home (2)"},
        {"value": "3", "label": "3"},
    ]


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"code": 0, "data": []}, "no_groups"),
        ({"code": 0, "data": None}, "cannot_connect"),
        ({"code": 0, "data": [{"id": ""}]}, "cannot_connect"),
        ({"code": 0, "data": [{"id": 123}]}, "cannot_connect"),
        ({"code": 0, "data": [{"id": "123", "groupName": 456}]}, "cannot_connect"),
        ({"code": 0, "success": False, "data": [{"id": "123"}]}, "cannot_connect"),
        ({"code": 500, "data": []}, "cannot_connect"),
    ],
)
async def test_invalid_group_list_recovers(
    hass: HomeAssistant, mock_cloud_api: AsyncMock, mock_cloud_login: AsyncMock, response: Any, error: str
) -> None:
    """An empty or malformed response stays on login and allows another attempt."""
    original = mock_cloud_api.side_effect
    mock_cloud_api.side_effect = None
    mock_cloud_api.return_value = response
    result = await start_cloud_login(hass)
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": error}
    assert hass.config_entries.async_entries(DOMAIN) == []
    mock_cloud_api.side_effect = original
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["step_id"] == "cloud_group"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MovaEnergyApiClientCommunicationError("offline"), "cannot_connect"),
        (MovaEnergyApiClientAuthenticationError("denied"), "cloud_device_access_denied"),
    ],
)
async def test_group_validation_retry_does_not_repeat_login(
    hass: HomeAssistant, mock_cloud_api: AsyncMock, mock_cloud_login: AsyncMock, error: Exception, expected: str
) -> None:
    """A failed device-list query can retry the selected group without losing its session."""
    result = await start_cloud_login(hass)
    original = mock_cloud_api.side_effect
    mock_cloud_api.side_effect = error
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: TEST_GROUP_ID})
    assert result["step_id"] == "cloud_group"
    assert result["errors"] == {"base": expected}
    mock_cloud_api.side_effect = original
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: TEST_GROUP_ID})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_cloud_login.assert_awaited_once()


async def test_group_request_authenticated_before_selection(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Group discovery carries Dreame-Auth even though there is no group ID yet."""
    aioclient_mock.get(GROUPS_URL, json={"code": 0, "success": True, "data": [{"id": "123", "groupName": "Home"}]})
    auth = MovaEnergyCloudAuth(async_get_clientsession(hass), {"access_token": "test-access"})
    api = MovaEnergyApiClient(None, None, async_get_clientsession(hass), DEFAULT_CLOUD_API_URL, auth=auth)
    response = await api.async_get_cloud_groups()
    assert response["data"][0]["id"] == "123"
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["Dreame-Auth"] == "test-access"
    assert headers["tenant-id"] == CLOUD_TENANT_ID
    assert headers["Accept"] == "application/json"
