"""Local configuration reads and writes through Home Assistant's entity services."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mova_energy.api import MovaEnergyApiClientCommunicationError
from custom_components.mova_energy.const import DOMAIN
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

NUMBER = "number.mova_simulated_energy_device_"
MODE = "select.mova_simulated_energy_device_work_mode"
URL = "http://simulator:18080/api/config"


def number_id(key: str) -> str:
    """Resolve entity IDs derived from translated display names."""
    suffix = {"soc_upper": "soc_upper_limit", "soc_lower": "soc_lower_limit"}.get(key, key)
    return f"{NUMBER}{suffix}"


async def set_number(hass: HomeAssistant, key: str, value: float) -> None:
    """Set a local parameter through the number platform."""
    await hass.services.async_call("number", "set_value", {"entity_id": number_id(key), "value": value}, blocking=True)
    await hass.async_block_till_done()


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Poll through the integration's public refresh action."""
    await hass.services.async_call(DOMAIN, "refresh_data", {"config_entry_id": entry.entry_id}, blocking=True)
    await hass.async_block_till_done()


async def test_config_entities_and_categories(hass: HomeAssistant, init_local_integration: MockConfigEntry) -> None:
    """Five integer controls and all defined modes are associated with the energy device."""
    for key, value, unit, maximum in (
        ("charge_limit", "2500", "W", 65535),
        ("discharge_limit", "1837", "W", 65535),
        ("soc_upper", "100", "%", 100),
        ("soc_lower", "7", "%", 100),
        ("backup_soc", "96", "%", 100),
    ):
        state = hass.states.get(number_id(key))
        assert state is not None
        assert state.state == value
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["min"] == 0
        assert state.attributes["max"] == maximum
        assert state.attributes["step"] == 1
        assert state.attributes["mode"] == "box"
        entity = er.async_get(hass).async_get(number_id(key))
        assert entity.entity_category is er.EntityCategory.CONFIG
        assert entity.unique_id == f"{init_local_integration.entry_id}_{key}"
    mode = hass.states.get(MODE)
    assert mode.state == "ai"
    assert len(mode.attributes["options"]) == 9
    assert "default" in mode.attributes["options"]
    assert hass.states.get("switch.mova_simulated_energy_device_backup_en") is None
    assert hass.states.get("number.mova_simulated_energy_device_target_humidity") is None
    assert hass.states.get("select.mova_simulated_energy_device_fan_speed") is None


@pytest.mark.parametrize(
    ("key", "field", "value", "expected"),
    [
        ("charge_limit", "chargeLimit", 65535, "2500"),
        ("discharge_limit", "dischargeLimit", 65535, "2500"),
        ("soc_upper", "socUpper", 80, "80"),
        ("soc_lower", "socLower", 0, "0"),
        ("backup_soc", "backupSoc", 100, "100"),
    ],
)
async def test_number_writes_use_actual_readback(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    key: str,
    field: str,
    value: int,
    expected: str,
) -> None:
    """Writes send one protocol field and publish clamped values without another GET."""
    mock_local_api.reset_mock()
    await set_number(hass, key, value)
    mock_local_api.assert_awaited_once_with(method="post", url=URL, data={field: value})
    assert hass.states.get(number_id(key)).state == expected
    if key == "soc_upper":
        assert hass.states.get(f"{NUMBER}backup_soc").state == "80"
    assert hass.states.get("sensor.mova_simulated_energy_device_pv_power").state == "500"


@pytest.mark.parametrize(
    ("code", "option"),
    [
        (0, "self_consumption"),
        (1, "emergency_charge"),
        (2, "forced_charge_discharge"),
        (3, "dynamic_ev"),
        (4, "smart_plug"),
        (5, "schedule"),
        (6, "dynamic_tariff"),
        (7, "ai"),
        (9, "default"),
    ],
)
async def test_mode_mapping_both_directions(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    local_device_config: dict[str, Any],
    code: int,
    option: str,
) -> None:
    """Each option sends the documented code and is also decoded on the next poll."""
    await hass.services.async_call("select", "select_option", {"entity_id": MODE, "option": option}, blocking=True)
    await hass.async_block_till_done()
    mock_local_api.assert_any_await(method="post", url=URL, data={"mode": code})
    assert hass.states.get(MODE).state == option
    await refresh(hass, init_local_integration)
    assert hass.states.get(MODE).state == option
    assert local_device_config["mode"] == code


async def test_rejection_readback_and_manual_retry(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    local_device_config: dict[str, Any],
) -> None:
    """A rejected write still publishes actual settings and never automatically resends."""
    normal = mock_local_api.side_effect
    mock_local_api.reset_mock()
    mock_local_api.side_effect = None
    mock_local_api.return_value = {"ok": False, "applied": {**local_device_config, "chargeLimit": 1400}}
    with pytest.raises(HomeAssistantError) as error:
        await set_number(hass, "charge_limit", 1500)
    assert error.value.translation_key == "config_write_rejected"
    await hass.async_block_till_done()
    assert hass.states.get(f"{NUMBER}charge_limit").state == "1400"
    assert mock_local_api.await_count == 1
    mock_local_api.side_effect = normal
    await set_number(hass, "charge_limit", 1500)
    assert hass.states.get(f"{NUMBER}charge_limit").state == "1500"


@pytest.mark.parametrize(
    "response",
    [
        {"ok": True},
        {"ok": "false", "applied": {}},
        {"ok": 1, "applied": {}},
        {"ok": True, "applied": []},
    ],
)
async def test_malformed_ack_does_not_publish_submitted_value(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    response: dict[str, Any],
) -> None:
    """Malformed device responses report failure instead of assuming success."""
    mock_local_api.side_effect = None
    mock_local_api.return_value = response
    with pytest.raises(HomeAssistantError) as error:
        await set_number(hass, "charge_limit", 1500)
    assert error.value.translation_key == "config_write_failed"
    assert hass.states.get(f"{NUMBER}charge_limit").state == "2500"


async def test_communication_failure_then_recovery(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Write failure leaves reported values intact; failed polls mark all entities unavailable."""
    normal = mock_local_api.side_effect
    mock_local_api.side_effect = MovaEnergyApiClientCommunicationError(
        "GET /api/status: error fetching information - offline"
    )
    with pytest.raises(HomeAssistantError):
        await set_number(hass, "charge_limit", 1500)
    assert hass.states.get(f"{NUMBER}charge_limit").state == "2500"
    await refresh(hass, init_local_integration)
    assert hass.states.get(MODE).state == STATE_UNAVAILABLE
    assert "GET /api/status: error fetching information - offline" in caplog.text
    mock_local_api.side_effect = normal
    await refresh(hass, init_local_integration)
    assert hass.states.get(MODE).state == "ai"


async def test_config_get_failure_and_external_change(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    local_device_config: dict[str, Any],
) -> None:
    """Configuration GET failures are detected even when status works; external changes are polled."""
    normal = mock_local_api.side_effect

    async def response(**kwargs: Any) -> dict[str, Any]:
        if kwargs["url"].endswith("/api/config"):
            raise MovaEnergyApiClientCommunicationError("config endpoint unavailable")
        return await normal(**kwargs)

    mock_local_api.side_effect = response
    await refresh(hass, init_local_integration)
    assert hass.states.get(MODE).state == STATE_UNAVAILABLE
    mock_local_api.side_effect = normal
    local_device_config.update(mode=9, chargeLimit=1234)
    await refresh(hass, init_local_integration)
    assert hass.states.get(MODE).state == "default"
    assert hass.states.get(f"{NUMBER}charge_limit").state == "1234"


@pytest.mark.parametrize("value", [-1, 101, 50.5, float("inf"), float("nan")])
async def test_invalid_numbers_never_sent(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    value: float,
) -> None:
    """Out-of-range and non-integer service values cannot reach the device."""
    mock_local_api.reset_mock()
    with pytest.raises((ServiceValidationError, HomeAssistantError)):
        await set_number(hass, "soc_upper", value)
    mock_local_api.assert_not_awaited()


@pytest.mark.parametrize("value", [8, True, "7", None])
async def test_invalid_or_missing_config_is_unknown(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    local_device_config: dict[str, Any],
    value: Any,
) -> None:
    """Invalid mode, missing parameter and invalid percentage do not break readings."""
    local_device_config.update(mode=value, socUpper=101)
    local_device_config.pop("backupSoc")
    await refresh(hass, init_local_integration)
    assert hass.states.get(MODE).state == STATE_UNKNOWN
    assert hass.states.get(number_id("soc_upper")).state == STATE_UNKNOWN
    assert hass.states.get(f"{NUMBER}backup_soc").state == STATE_UNKNOWN
    assert hass.states.get(number_id("soc_lower")).state == "7"


async def test_real_http_config_write(
    hass: HomeAssistant,
    local_config_entry: MockConfigEntry,
    local_status: dict[str, Any],
    local_device_config: dict[str, Any],
    aioclient_mock: Any,
) -> None:
    """The real aiohttp client sends JSON to the local endpoint and consumes applied."""
    aioclient_mock.get(
        "http://simulator:18080/api/device",
        json={
            "sn": "MOVA-SIM-0001",
            "did": "MOVA-DID-0001",
            "mac": "02:00:00:00:00:01",
            "model": "Energy Simulator",
        },
    )
    aioclient_mock.get("http://simulator:18080/api/status", json=local_status)
    aioclient_mock.get(URL, json=local_device_config)
    aioclient_mock.post(URL, json={"ok": True, "applied": {**local_device_config, "chargeLimit": 1500}})
    local_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(local_config_entry.entry_id)
    await hass.async_block_till_done()
    await set_number(hass, "charge_limit", 1500)
    assert aioclient_mock.mock_calls[-1][2] == {"chargeLimit": 1500}
    assert hass.states.get(f"{NUMBER}charge_limit").state == "1500"
    assert aioclient_mock.call_count == 4


async def test_cross_platform_writes_are_serialized(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
) -> None:
    """Concurrent mode and number writes wait for one another and preserve both settings."""
    normal = mock_local_api.side_effect
    started = asyncio.Event()
    release = asyncio.Event()
    active = 0

    async def response(**kwargs: Any) -> dict[str, Any]:
        nonlocal active
        active += 1
        assert active == 1
        started.set()
        await release.wait()
        result = await normal(**kwargs)
        active -= 1
        return result

    mock_local_api.side_effect = response
    first = hass.async_create_task(
        hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": number_id("soc_upper"), "value": 80},
            blocking=True,
        )
    )
    await started.wait()
    second = hass.async_create_task(
        hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": MODE, "option": "schedule"},
            blocking=True,
        )
    )
    release.set()
    await asyncio.gather(first, second)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "schedule"
    assert hass.states.get(number_id("soc_upper")).state == "80"
    assert hass.states.get(f"{NUMBER}backup_soc").state == "80"
