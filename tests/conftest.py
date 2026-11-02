"""Shared fixtures for the mova_energy tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mova_energy.const import (
    CLOUD_ENVIRONMENT_UAT,
    CONF_CLOUD_API_URL,
    CONF_CLOUD_ENVIRONMENT,
    CONF_CONNECTION_MODE,
    CONF_GROUP_ID,
    CONNECTION_MODE_CLOUD,
    DEFAULT_CLOUD_API_URL,
    DOMAIN,
)
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant

TEST_GROUP_ID = "test-group-001"

API_RESPONSE: dict[str, Any] = {
    "sn": "MOVA-SIM-0001",
    "did": "MOVA-DID-0001",
    "mac": "02:00:00:00:00:01",
    "model": "Energy Simulator",
}

STATUS_RESPONSE: dict[str, Any] = {
    "pv": 500,
    "batt": 23,
    "grid": 12,
    "load": 0,
    "offgrid": 0,
    "soc": 48,
    "battTemp": 306,
    "runStatus": 3,
    "meterOnline": 1,
    "pvDayWh": 1200,
    "gridImportWh": 300,
    "gridExportWh": 100,
    "ver": "1.1.0_1305,4049,6191,2008",
}

CONFIG_RESPONSE: dict[str, Any] = {
    "mode": 7,
    "chargeLimit": 2500,
    "dischargeLimit": 1837,
    "socUpper": 100,
    "socLower": 7,
    "backupSoc": 96,
    "backupEn": 0,
    "antiReverse": 0,
}

CLOUD_GROUPS_RESPONSE: dict[str, Any] = {
    "code": 0,
    "success": True,
    "data": [{"id": TEST_GROUP_ID, "groupName": "Test group", "groupType": 1}],
    "msg": "success",
}

CLOUD_DEVICES_RESPONSE: dict[str, Any] = {
    "code": 200,
    "msg": "success",
    "data": [
        {
            "sn": "MOVA-TEST-0001",
            "model": "mova.bkw.ge2505",
            "uid": "test-user-001",
            "name": "",
            "did": -100000001,
            "fwVersion": "1.1.0_1308",
            "master": True,
        },
    ],
    "success": True,
}

CLOUD_CONFIG_RESPONSE: dict[str, Any] = {
    "code": 200,
    "msg": "success",
    "data": {
        "mode": 0,
        "chargeLimit": 5000,
        "dischargeLimit": 5000,
        "socUpper": 100,
        "socLower": 10,
        "backupSoc": 20,
        "backupEn": 1,
        "antiReverse": None,
    },
}

CLOUD_STATUS_RESPONSE: dict[str, Any] = {
    "code": 200,
    "msg": "success",
    "data": {
        "pv": 3200,
        "batt": -800,
        "grid": 500,
        "load": None,
        "offgrid": 0,
        "soc": 76,
        "battTemp": 306,
        "runStatus": 3,
        "meterOnline": 1,
        "pvDayWh": 12500,
        "pvSumWh": 4560000,
        "gridImportWh": 800,
        "gridExportWh": 1200,
        "ver": "1.2.3",
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom integrations in every test."""


@pytest.fixture
def mock_api() -> Generator[AsyncMock]:
    """Replace the client's HTTP layer, keeping its payload logic under test."""
    with patch(
        "custom_components.mova_energy.api.client.MovaEnergyApiClient._api_wrapper",
        new_callable=AsyncMock,
        return_value=API_RESPONSE,
    ) as api_wrapper:
        yield api_wrapper


@pytest.fixture
def mock_cloud_login() -> Generator[AsyncMock]:
    """Return a login session without contacting the UAT service."""
    with patch(
        "custom_components.mova_energy.api.auth.MovaEnergyCloudAuth._async_token_request",
        new_callable=AsyncMock,
        return_value={"access_token": "test-access-token", "refresh_token": "test-refresh-token"},
    ) as login:
        yield login


@pytest.fixture
def local_status() -> dict[str, Any]:
    """Return an independent copy of the local status protocol response."""
    return dict(STATUS_RESPONSE)


@pytest.fixture
def local_device_config() -> dict[str, Any]:
    """Return independent device parameters for each local test."""
    return dict(CONFIG_RESPONSE)


@pytest.fixture
def mock_local_api(mock_api: AsyncMock, local_status: dict[str, Any], local_device_config: dict[str, Any]) -> AsyncMock:
    """Route local HTTP requests to separate metadata and status responses."""

    async def response(*, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if url.endswith("/api/status"):
            return dict(local_status)
        if url.endswith("/api/device"):
            return dict(API_RESPONSE)
        if url.endswith("/api/config") and method == "get":
            return dict(local_device_config)
        if url.endswith("/api/config") and method == "post":
            local_device_config.update(kwargs["data"])
            local_device_config["chargeLimit"] = min(local_device_config["chargeLimit"], 2500)
            local_device_config["dischargeLimit"] = min(local_device_config["dischargeLimit"], 2500)
            local_device_config["backupSoc"] = min(local_device_config["backupSoc"], local_device_config["socUpper"])
            return {"ok": True, "applied": dict(local_device_config)}
        raise AssertionError(f"Unexpected local request: {method} {url}")

    mock_api.side_effect = response
    return mock_api


@pytest.fixture
def cloud_device_config() -> dict[str, Any]:
    """Return independent reported settings, separate from submitted commands."""
    return dict(CLOUD_CONFIG_RESPONSE["data"])


@pytest.fixture
def cloud_groups() -> list[dict[str, Any]]:
    """Return an independent account group list for flow tests."""
    return [dict(group) for group in CLOUD_GROUPS_RESPONSE["data"]]


@pytest.fixture
def mock_cloud_api(
    mock_api: AsyncMock, cloud_device_config: dict[str, Any], cloud_groups: list[dict[str, Any]]
) -> AsyncMock:
    """Route cloud requests to the sample devices and configuration responses."""

    async def response(*, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if url.endswith("/query/groups"):
            return {**CLOUD_GROUPS_RESPONSE, "data": list(cloud_groups)}
        if url.endswith("/devices"):
            return dict(CLOUD_DEVICES_RESPONSE)
        if url.endswith("/status"):
            return dict(CLOUD_STATUS_RESPONSE)
        if url.endswith("/config") and method == "get":
            return {**CLOUD_CONFIG_RESPONSE, "data": dict(cloud_device_config)}
        if url.endswith("/config") and method == "post":
            return {"code": 200, "msg": "success", "data": True}
        raise AssertionError(f"Unexpected cloud request: {method} {url}")

    mock_api.side_effect = response
    return mock_api


@pytest.fixture
def cloud_config_entry() -> MockConfigEntry:
    """Return a cloud device-group entry with a saved session."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="MOVA Cloud Group",
        unique_id=TEST_GROUP_ID,
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_UAT,
            CONF_CLOUD_API_URL: DEFAULT_CLOUD_API_URL,
            CONF_GROUP_ID: TEST_GROUP_ID,
            CONF_TOKEN: {"access_token": "test-access-token", "refresh_token": "test-refresh-token"},
        },
    )


@pytest.fixture
async def init_cloud_integration(
    hass: HomeAssistant,
    mock_cloud_api: AsyncMock,
    cloud_config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Load cloud settings through Home Assistant's setup path."""
    cloud_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(cloud_config_entry.entry_id)
    await hass.async_block_till_done()
    return cloud_config_entry


@pytest.fixture
def local_config_entry() -> MockConfigEntry:
    """Return the existing shape of a local config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="MOVA Simulated Energy Device",
        unique_id="MOVA-SIM-0001",
        data={"connection_mode": "local", "host": "simulator", "port": 18080},
    )


@pytest.fixture
async def init_local_integration(
    hass: HomeAssistant,
    mock_local_api: AsyncMock,
    local_config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Load the local entry through Home Assistant's setup path."""
    local_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(local_config_entry.entry_id)
    await hass.async_block_till_done()
    return local_config_entry


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for this integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="demo",
        unique_id="demo",
        data={CONF_USERNAME: "demo", CONF_PASSWORD: "secret"},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """
    Set up the integration from a config entry.

    Returns:
        The config entry, now loaded.

    """
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
