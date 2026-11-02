"""Cloud configuration submission and authoritative readback through HA services."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.mova_energy.api import MovaEnergyApiClientCommunicationError
from custom_components.mova_energy.const import DEFAULT_CLOUD_API_URL, DOMAIN
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

TEST_GROUP_ID = "test-group-001"

URL = f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/config"
STATUS_URL = f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/status"
PREFIX = "mova_cloud_group_"


async def write(hass: HomeAssistant, key: str, value: Any) -> None:
    """Write one cloud setting through its HA platform service."""
    if key == "work_mode":
        domain, service, data = "select", "select_option", {"option": value}
    elif key == "backup_enabled":
        domain, service, data = "switch", "turn_on" if value else "turn_off", {}
    else:
        domain, service, data = "number", "set_value", {"value": value}
    await hass.services.async_call(domain, service, {"entity_id": f"{domain}.{PREFIX}{key}", **data}, blocking=True)
    await hass.async_block_till_done()


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Read reported settings using the public refresh action."""
    await hass.services.async_call(DOMAIN, "refresh_data", {"config_entry_id": entry.entry_id}, blocking=True)
    await hass.async_block_till_done()


async def test_cloud_settings(hass: HomeAssistant, init_cloud_integration: MockConfigEntry) -> None:
    """Cloud settings read the GET envelope; unsupported options are not exposed."""
    assert hass.states.get(f"number.{PREFIX}charge_limit").state == "5000"
    assert hass.states.get(f"number.{PREFIX}backup_soc").state == "20"
    assert hass.states.get(f"switch.{PREFIX}backup_enabled").state == "on"
    mode = hass.states.get(f"select.{PREFIX}work_mode")
    assert mode.state == "self_consumption"
    assert mode.attributes["options"] == ["self_consumption", "dynamic_ev", "custom_mode"]
    assert len(hass.states.async_all()) == 21
    assert hass.states.get(f"sensor.{PREFIX}load_power").state == "2900"
    assert hass.states.get(f"sensor.{PREFIX}battery_temperature").state == "30.6"
    assert hass.states.get(f"sensor.{PREFIX}pv_total_energy").state == "4560000"
    assert hass.states.get(f"binary_sensor.{PREFIX}meter_online").state == "on"
    assert hass.states.get(f"sensor.{PREFIX}firmware_version").state == "1.2.3"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, init_cloud_integration.entry_id), init_cloud_integration.entry_id
    )
    assert device.model == "mova.bkw.ge2505"
    assert device.serial_number == "MOVA-TEST-0001"


@pytest.mark.parametrize(
    ("key", "value", "type_code", "state"),
    [
        ("charge_limit", 1500, 1, "5000"),
        ("discharge_limit", 1700, 2, "5000"),
        ("soc_lower_limit", 15, 3, "10"),
        ("soc_upper_limit", 80, 4, "100"),
        ("work_mode", "custom_mode", 5, "self_consumption"),
        ("backup_soc", 30, 6, "20"),
        ("backup_enabled", False, 7, "on"),
    ],
)
async def test_type_mapping_and_no_optimistic_state(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    key: str,
    value: Any,
    type_code: int,
    state: str,
) -> None:
    """Accepted submission sends one pair and retains old values until GET confirms."""
    mock_cloud_api.reset_mock()
    await write(hass, key, value)
    target = 6 if key == "work_mode" else int(value)
    assert mock_cloud_api.await_args_list == [
        call(method="post", url=URL, data={"type": type_code, "value": target}),
        call(method="get", url=URL),
    ]
    domain = "select" if key == "work_mode" else "switch" if key == "backup_enabled" else "number"
    assert hass.states.get(f"{domain}.{PREFIX}{key}").state == state


@pytest.mark.parametrize(("option", "code"), [("self_consumption", 0), ("dynamic_ev", 3), ("custom_mode", 6)])
async def test_cloud_modes(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    cloud_device_config: dict[str, Any],
    option: str,
    code: int,
) -> None:
    """Cloud modes map only the currently supported cloud values."""
    cloud_device_config["mode"] = code
    await write(hass, "work_mode", option)
    mock_cloud_api.assert_any_await(method="post", url=URL, data={"type": 5, "value": code})
    assert hass.states.get(f"select.{PREFIX}work_mode").state == option


@pytest.mark.parametrize(
    "response",
    [
        {"code": 200, "data": False},
        {"code": 200, "data": 1},
        {"code": 200},
        {"code": 500, "data": True},
        {"code": 200, "data": "true"},
    ],
)
async def test_rejected_or_invalid_ack(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    response: dict[str, Any],
) -> None:
    """Rejected and malformed submissions never publish requested values or resend."""
    mock_cloud_api.reset_mock()
    mock_cloud_api.side_effect = None
    mock_cloud_api.return_value = response
    with pytest.raises(HomeAssistantError) as error:
        await write(hass, "charge_limit", 1500)
    assert error.value.translation_key == (
        "cloud_config_rejected" if response.get("data") is False else "config_write_failed"
    )
    assert mock_cloud_api.await_count == 1
    assert hass.states.get(f"number.{PREFIX}charge_limit").state == "5000"


async def test_delayed_execution_is_confirmed_without_resending(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    cloud_device_config: dict[str, Any],
    freezer: Any,
) -> None:
    """A later GET sees device execution; the integration sends the command only once."""
    mock_cloud_api.reset_mock()
    await write(hass, "charge_limit", 1500)
    assert hass.states.get(f"number.{PREFIX}charge_limit").state == "5000"
    cloud_device_config["chargeLimit"] = 1400
    freezer.tick(timedelta(seconds=6))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(f"number.{PREFIX}charge_limit").state == "1400"
    posts = [item for item in mock_cloud_api.await_args_list if item.kwargs["method"] == "post"]
    assert len(posts) == 1


async def test_get_failure_then_recovery(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
) -> None:
    """Failure reading configuration marks entities unavailable and can recover."""
    normal = mock_cloud_api.side_effect
    mock_cloud_api.side_effect = MovaEnergyApiClientCommunicationError("offline")
    await refresh(hass, init_cloud_integration)
    assert hass.states.get(f"select.{PREFIX}work_mode").state == STATE_UNAVAILABLE
    mock_cloud_api.side_effect = normal
    await refresh(hass, init_cloud_integration)
    assert hass.states.get(f"select.{PREFIX}work_mode").state == "self_consumption"


async def test_cloud_status_refreshes_every_minute_by_default(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    freezer: Any,
) -> None:
    """Cloud data is polled again after the one-minute default interval."""
    mock_cloud_api.reset_mock()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    assert mock_cloud_api.await_count == 3
    mock_cloud_api.assert_any_await(method="get", url=STATUS_URL)


async def test_unknown_backup_and_unsupported_mode(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    cloud_device_config: dict[str, Any],
) -> None:
    """Missing or unsupported values remain unknown rather than being guessed."""
    cloud_device_config.update(mode=9, backupEn=None)
    await refresh(hass, init_cloud_integration)
    assert hass.states.get(f"switch.{PREFIX}backup_enabled").state == STATE_UNKNOWN
    assert hass.states.get(f"select.{PREFIX}work_mode").state == STATE_UNKNOWN


@pytest.mark.parametrize("option", ["emergency_charge", "forced_charge_discharge", "schedule", "default"])
async def test_local_only_modes_are_not_sent(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    option: str,
) -> None:
    """Cloud selection rejects mode codes absent from its command set."""
    mock_cloud_api.reset_mock()
    with pytest.raises(HomeAssistantError):
        await write(hass, "work_mode", option)
    mock_cloud_api.assert_not_awaited()


async def test_submitted_but_readback_failed(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
) -> None:
    """A failed GET after submission reports uncertainty and never resends the command."""
    mock_cloud_api.reset_mock()
    mock_cloud_api.side_effect = [
        {"code": 200, "data": True},
        MovaEnergyApiClientCommunicationError("GET failed"),
    ]
    with pytest.raises(HomeAssistantError) as error:
        await write(hass, "charge_limit", 1500)
    assert error.value.translation_key == "cloud_config_readback_failed"
    assert mock_cloud_api.await_count == 2
    assert hass.states.get(f"number.{PREFIX}charge_limit").state == "5000"


async def test_unload_cancels_pending_confirmation(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    freezer: Any,
) -> None:
    """Removing the entry cancels its pending readback without more HTTP requests."""
    await write(hass, "charge_limit", 1500)
    assert await hass.config_entries.async_unload(init_cloud_integration.entry_id)
    mock_cloud_api.reset_mock()
    freezer.tick(timedelta(seconds=6))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    mock_cloud_api.assert_not_awaited()


async def test_real_http_submission_retains_get_value(
    hass: HomeAssistant,
    cloud_config_entry: MockConfigEntry,
    cloud_device_config: dict[str, Any],
    aioclient_mock: Any,
) -> None:
    """The aiohttp transport sends exactly type/value and does not interpret true as execution."""
    aioclient_mock.get(
        f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/devices",
        json={"code": 200, "data": [{"master": True, "model": "Cloud Energy Device", "sn": "CLOUD-1"}]},
    )
    aioclient_mock.get(STATUS_URL, json={"code": 200, "data": {}})
    aioclient_mock.get(URL, json={"code": 200, "data": cloud_device_config})
    aioclient_mock.post(URL, json={"code": 200, "data": True})
    cloud_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(cloud_config_entry.entry_id)
    await hass.async_block_till_done()
    await write(hass, "charge_limit", 1500)
    assert aioclient_mock.mock_calls[-2][2] == {"type": 1, "value": 1500}
    assert hass.states.get(f"number.{PREFIX}charge_limit").state == "5000"
