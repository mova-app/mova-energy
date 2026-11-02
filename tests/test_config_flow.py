"""Tests for choosing a MOVA connection mode."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mova_energy.const import (
    CLOUD_ENVIRONMENT_UAT,
    CONF_CLOUD_API_URL,
    CONF_CLOUD_ENVIRONMENT,
    CONF_CONNECTION_MODE,
    CONF_GROUP_ID,
    CONF_HOST,
    CONF_PORT,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DEFAULT_CLOUD_API_URL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

TEST_GROUP_ID = "test-group-001"


async def test_user_sees_cloud_and_local_modes(hass: HomeAssistant) -> None:
    """The initial flow presents both supported connection choices."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert result["menu_options"] == [CONNECTION_MODE_CLOUD, CONNECTION_MODE_LOCAL]


async def test_cloud_mode_validates_device_list_and_creates_entry(
    hass: HomeAssistant,
    mock_cloud_api,
    mock_cloud_login,
) -> None:
    """Cloud setup checks the group device list and stores connection details."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": CONNECTION_MODE_CLOUD},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == CONNECTION_MODE_CLOUD

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_UAT,
            CONF_USERNAME: "test-account",
            CONF_PASSWORD: "test-password",
        },
    )

    assert result["step_id"] == "cloud_group"
    mock_cloud_api.assert_awaited_once_with(method="get", url=f"{DEFAULT_CLOUD_API_URL}/open/v1/query/groups")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: TEST_GROUP_ID})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "mova.bkw.ge2505"
    assert result["data"] == {
        CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
        CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_UAT,
        CONF_CLOUD_API_URL: DEFAULT_CLOUD_API_URL,
        CONF_GROUP_ID: TEST_GROUP_ID,
        CONF_USERNAME: "test-account",
        CONF_TOKEN: {"access_token": "test-access-token", "refresh_token": "test-refresh-token"},
    }
    mock_cloud_api.assert_any_await(
        method="get",
        url=f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/devices",
    )


async def test_cloud_mode_accepts_uat_success_code_zero(
    hass: HomeAssistant,
    mock_cloud_api,
    mock_cloud_login,
) -> None:
    """The UAT cloud API uses code zero for successful device-list responses."""
    original = mock_cloud_api.side_effect

    async def response(**kwargs):
        return {**await original(**kwargs), "code": 0}

    mock_cloud_api.side_effect = response
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": CONNECTION_MODE_CLOUD})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_UAT,
            CONF_USERNAME: "test-account",
            CONF_PASSWORD: "test-password",
        },
    )
    assert result["step_id"] == "cloud_group"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: TEST_GROUP_ID})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_cloud_mode_rejects_empty_device_list(
    hass: HomeAssistant,
    mock_cloud_api,
    mock_cloud_login,
) -> None:
    """An empty group stays on the cloud form and does not create an entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": CONNECTION_MODE_CLOUD})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_UAT,
            CONF_USERNAME: "test-account",
            CONF_PASSWORD: "test-password",
        },
    )

    assert result["step_id"] == "cloud_group"
    mock_cloud_api.side_effect = None
    mock_cloud_api.return_value = {"code": 200, "msg": "success", "data": [], "success": True}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: TEST_GROUP_ID})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_cloud_entry_refreshes_devices_without_creating_placeholder_entities(
    hass: HomeAssistant,
    mock_cloud_api,
) -> None:
    """Cloud entries expose real settings and status entities, without demo entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="mova.bkw.ge2505",
        unique_id=TEST_GROUP_ID,
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_CLOUD_API_URL: DEFAULT_CLOUD_API_URL,
            CONF_GROUP_ID: TEST_GROUP_ID,
            CONF_TOKEN: {"access_token": "test-access-token"},
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mock_cloud_api.assert_any_await(
        method="get",
        url=f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/devices",
    )
    mock_cloud_api.assert_any_await(
        method="get",
        url=f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/status",
    )
    mock_cloud_api.assert_any_await(
        method="get",
        url=f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/config",
    )
    states = hass.states.async_all()
    assert len(states) == 21
    assert hass.states.get("sensor.mova_bkw_ge2505_pv_power").state == "3200"


async def test_local_mode_creates_entry_from_device(
    hass: HomeAssistant,
    mock_local_api,
) -> None:
    """The local form validates the device and stores its address in the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": CONNECTION_MODE_LOCAL},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == CONNECTION_MODE_LOCAL
    assert result["data_schema"]({})[CONF_PORT] == 80

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "localhost", CONF_PORT: 18080},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Energy Simulator"
    assert result["result"].unique_id is None
    assert result["data"] == {
        CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
        CONF_HOST: "localhost",
        CONF_PORT: 18080,
    }
    mock_local_api.assert_any_await(method="get", url="http://localhost:18080/api/status")
    mock_local_api.assert_any_await(method="get", url="http://localhost:18080/api/config")
    mock_local_api.assert_any_await(method="get", url="http://localhost:18080/api/device")


async def test_local_entry_exposes_simulator_pv_power(
    hass: HomeAssistant,
    mock_local_api,
) -> None:
    """The sensor state comes from the local simulator's pv_power response."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MOVA Simulated Energy Device",
        unique_id="MOVA-SIM-0001",
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_HOST: "simulator",
            CONF_PORT: 18080,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mova_simulated_energy_device_pv_power").state == "500"
    assert hass.states.get("sensor.mova_simulated_energy_device_air_quality_index") is None
    mock_local_api.assert_any_await(method="get", url="http://simulator:18080/api/status")
    mock_local_api.assert_any_await(method="get", url="http://simulator:18080/api/config")
