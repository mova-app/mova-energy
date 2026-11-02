"""Local energy protocol values exposed through Home Assistant entities."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, call

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.mova_energy.api import MovaEnergyApiClient, MovaEnergyApiClientCommunicationError
from custom_components.mova_energy.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

PREFIX = "sensor.mova_simulated_energy_device_"
METER = "binary_sensor.mova_simulated_energy_device_meter_online"


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Fetch updated readings via the integration's public service action."""
    await hass.services.async_call(
        DOMAIN,
        "refresh_data",
        {"config_entry_id": entry.entry_id},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_all_metrics_and_metadata(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
) -> None:
    """All protocol fields have the correct state, unit and device association."""
    for suffix, expected, unit, device_class, state_class in (
        ("pv_power", "500", "W", "power", "measurement"),
        ("battery_power", "23", "W", "power", "measurement"),
        ("grid_power", "12", "W", "power", "measurement"),
        ("load_power", "0", "W", "power", "measurement"),
        ("eps_power", "0", "W", "power", "measurement"),
        ("battery_soc", "48", "%", "battery", "measurement"),
        ("battery_temperature", "30.6", "°C", "temperature", "measurement"),
        ("pv_daily_energy", "1200", "Wh", "energy", "total_increasing"),
        ("grid_import_daily_energy", "300", "Wh", "energy", "total_increasing"),
        ("grid_export_daily_energy", "100", "Wh", "energy", "total_increasing"),
    ):
        state = hass.states.get(f"{PREFIX}{suffix}")
        assert state is not None
        assert state.state == expected
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["device_class"] == device_class
        assert state.attributes["state_class"] == state_class

    assert hass.states.get(f"{PREFIX}run_status").state == "on_grid"
    assert hass.states.get(f"{PREFIX}firmware_version").state == "1.1.0_1305,4049,6191,2008"
    assert hass.states.get(METER).state == "on"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, init_local_integration.entry_id),
        init_local_integration.entry_id,
    )
    assert device is not None
    assert device.sw_version == "1.1.0_1305,4049,6191,2008"
    entities = er.async_entries_for_config_entry(er.async_get(hass), init_local_integration.entry_id)
    assert len(entities) == 19
    assert {entity.device_id for entity in entities} == {device.id}
    pv = er.async_get(hass).async_get(f"{PREFIX}pv_power")
    assert pv.unique_id == f"{init_local_integration.entry_id}_pv_power"


async def test_http_client_reads_status_endpoint(
    hass: HomeAssistant,
    local_config_entry: MockConfigEntry,
    local_status: dict[str, Any],
    local_device_config: dict[str, Any],
    aioclient_mock: Any,
) -> None:
    """Exercise the real API client with mocked HTTP responses rather than its wrapper."""
    aioclient_mock.get(
        "http://simulator:18080/api/device",
        json={
            "sn": "MOVA-SIM-0001",
            "did": "MOVA-DID-0001",
            "mac": "02:00:00:00:00:01",
            "model": "Energy Simulator",
        },
        headers={"Content-Type": "text/html"},
    )
    aioclient_mock.get("http://simulator:18080/api/status", json=local_status)
    aioclient_mock.get("http://simulator:18080/api/config", json=local_device_config)
    local_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(local_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(f"{PREFIX}pv_power").state == "500"
    assert hass.states.get(f"{PREFIX}battery_temperature").state == "30.6"
    assert aioclient_mock.call_count == 3
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, local_config_entry.entry_id), local_config_entry.entry_id
    )
    assert device is not None
    assert device.manufacturer == "MOVA Energy"
    assert device.model == "Energy Simulator"
    assert device.serial_number == "MOVA-SIM-0001"
    assert device.sw_version == local_status["ver"]
    await refresh(hass, local_config_entry)
    assert aioclient_mock.call_count == 5


async def test_local_device_metadata_accepts_json_with_html_content_type(
    hass: HomeAssistant,
) -> None:
    """Device firmware may label a JSON metadata response as HTML."""
    response = Mock(status=200)
    response.raise_for_status = Mock()

    async def json_response(*, content_type: str | None = "application/json") -> dict[str, str]:
        assert content_type is None
        return {"sn": "MOVA-SIM-0001", "model": "Energy Simulator"}

    response.json = json_response
    response_context = AsyncMock()
    response_context.__aenter__.return_value = response
    session = Mock()
    session.request.return_value = response_context
    api = MovaEnergyApiClient(
        username=None,
        password=None,
        session=session,
        base_url="http://device",
    )

    metadata = await api.async_get_local_device_info()

    assert metadata["serial_number"] == "MOVA-SIM-0001"
    assert metadata["model"] == "Energy Simulator"


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (0, "off"),
        (1, "standby"),
        (2, "off_grid"),
        (3, "on_grid"),
        (4, "fault"),
        (5, "grid_and_off_grid_load"),
        (99, STATE_UNKNOWN),
    ],
)
async def test_run_status_codes(
    hass: HomeAssistant,
    local_status: dict[str, Any],
    init_local_integration: MockConfigEntry,
    code: int,
    state: str,
) -> None:
    """Operating modes map to declared enum options; unknown codes stay unknown."""
    local_status["runStatus"] = code
    await refresh(hass, init_local_integration)
    assert hass.states.get(f"{PREFIX}run_status").state == state


async def test_signed_power_meter_offline_and_daily_reset(
    hass: HomeAssistant,
    local_status: dict[str, Any],
    init_local_integration: MockConfigEntry,
) -> None:
    """Charging, exporting, an offline meter and daily resets retain their meaning."""
    local_status.update(batt=-230, grid=-120, meterOnline=0, pvDayWh=0, gridImportWh=0, gridExportWh=0)
    await refresh(hass, init_local_integration)
    assert hass.states.get(f"{PREFIX}battery_power").state == "-230"
    assert hass.states.get(f"{PREFIX}grid_power").state == "-120"
    assert hass.states.get(METER).state == "off"
    assert hass.states.get(f"{PREFIX}pv_power").state == "500"
    for key in ("pv_daily_energy", "grid_import_daily_energy", "grid_export_daily_energy"):
        assert hass.states.get(f"{PREFIX}{key}").state == "0"


@pytest.mark.parametrize("invalid", [None, True, "306", float("nan"), float("inf")])
async def test_missing_or_invalid_field_is_unknown(
    hass: HomeAssistant,
    local_status: dict[str, Any],
    init_local_integration: MockConfigEntry,
    invalid: Any,
) -> None:
    """A bad temperature or missing PV value does not break the other entities."""
    local_status["battTemp"] = invalid
    local_status.pop("pv")
    local_status.pop("meterOnline")
    await refresh(hass, init_local_integration)
    assert hass.states.get(f"{PREFIX}battery_temperature").state == STATE_UNKNOWN
    assert hass.states.get(f"{PREFIX}pv_power").state == STATE_UNKNOWN
    assert hass.states.get(METER).state == STATE_UNKNOWN
    assert hass.states.get(f"{PREFIX}battery_soc").state == "48"


async def test_polling_interval_and_metadata_cache(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
    local_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A local entry polls status every ten seconds without refetching device identity."""
    mock_local_api.reset_mock()
    local_status["pv"] = 765
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(f"{PREFIX}pv_power").state == "765"
    assert mock_local_api.await_args_list == [
        call(method="get", url="http://simulator:18080/api/status"),
        call(method="get", url="http://simulator:18080/api/config"),
    ]


async def test_failed_status_poll_recovers_and_entry_unloads(
    hass: HomeAssistant,
    init_local_integration: MockConfigEntry,
    mock_local_api: AsyncMock,
) -> None:
    """HTTP errors make entities unavailable, recovery and unloading work for both platforms."""
    normal_response = mock_local_api.side_effect
    mock_local_api.side_effect = MovaEnergyApiClientCommunicationError("Device offline")
    await refresh(hass, init_local_integration)
    assert hass.states.get(f"{PREFIX}pv_power").state == STATE_UNAVAILABLE
    assert hass.states.get(METER).state == STATE_UNAVAILABLE
    mock_local_api.side_effect = normal_response
    await refresh(hass, init_local_integration)
    assert hass.states.get(f"{PREFIX}pv_power").state == "500"
    assert hass.states.get(METER).state == "on"
    assert await hass.config_entries.async_unload(init_local_integration.entry_id)
    await hass.async_block_till_done()
    assert init_local_integration.state is ConfigEntryState.NOT_LOADED
