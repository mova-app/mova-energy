"""Data update coordinator for mova_energy."""

import asyncio
from collections.abc import Callable
from datetime import datetime
import math
from typing import TYPE_CHECKING, Any

from custom_components.mova_energy.api import MovaEnergyApiClientAuthenticationError, MovaEnergyApiClientError
from custom_components.mova_energy.const import (
    CLOUD_CONFIG_CONFIRM_DELAY_SECONDS,
    CLOUD_SUCCESS_CODES,
    CLOUD_WORK_MODE_OPTIONS,
    CONF_CONNECTION_MODE,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
    LOCAL_CONFIG_NUMBERS,
    LOGGER,
    RUN_STATUS_OPTIONS,
    WORK_MODE_OPTIONS,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

if TYPE_CHECKING:
    from custom_components.mova_energy.data import MovaEnergyConfigEntry


class MovaEnergyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch the device state once per interval and hand it to every entity."""

    config_entry: MovaEnergyConfigEntry

    def __init__(self, **kwargs: Any) -> None:
        """Serialize polling and configuration writes across entity platforms."""
        super().__init__(**kwargs)
        self._device_lock = asyncio.Lock()
        self._cancel_cloud_refresh: Callable[[], None] | None = None
        self.config_entry.async_on_unload(self._cancel_pending_cloud_refresh)

    @callback
    def _cancel_pending_cloud_refresh(self) -> None:
        """Cancel the pending cloud readback on replacement or entry unload."""
        if self._cancel_cloud_refresh is not None:
            self._cancel_cloud_refresh()
            self._cancel_cloud_refresh = None

    @callback
    def _async_confirm_cloud_config(self, now: datetime) -> None:
        """Read again after allowing time for the IoT command to reach the device."""
        self._cancel_cloud_refresh = None
        self.config_entry.async_create_task(self.hass, self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Fetch the current device state.

        Returns:
            The payload entities read by key.

        Raises:
            ConfigEntryAuthFailed: If the credentials were rejected; triggers reauth.
            UpdateFailed: If the fetch failed for any other reason.

        """
        try:
            async with self._device_lock:
                data = await self.config_entry.runtime_data.client.async_get_data()
                if self.config_entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
                    return self._normalize_cloud_data(data)
        except MovaEnergyApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="authentication_failed",
            ) from exception
        except MovaEnergyApiClientError as exception:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
            ) from exception
        else:
            if self.config_entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_LOCAL:
                return self._normalize_local_data(data)
            return data

    async def async_write_config(self, key: str, value: int) -> None:
        """Write one parameter and publish device-reported configuration.

        Local responses supply the readback; cloud submissions trigger immediate and delayed GET requests.

        Raises:
            ServiceValidationError: If the requested field or value is unsupported.
            HomeAssistantError: If communication fails or the device rejects the write.
        """
        cloud = self.config_entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD
        modes = CLOUD_WORK_MODE_OPTIONS if cloud else WORK_MODE_OPTIONS
        if key == "work_mode" and type(value) is int and value in modes:
            field = "mode"
        elif cloud and key == "backup_en" and type(value) is int and value in (0, 1):
            field = "backupEn"
        elif key in LOCAL_CONFIG_NUMBERS:
            field, minimum, maximum = LOCAL_CONFIG_NUMBERS[key]
            if type(value) is not int or not minimum <= value <= maximum:
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_config_value")
        else:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_config_value")

        async with self._device_lock:
            try:
                response = await self.config_entry.runtime_data.client.async_set_config({field: value})
                if cloud:
                    if not response["data"]:
                        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="cloud_config_rejected")
                    # Only GET readback can update states; submission does not imply execution.
                    self._cancel_pending_cloud_refresh()
                    self._cancel_cloud_refresh = async_call_later(
                        self.hass, CLOUD_CONFIG_CONFIRM_DELAY_SECONDS, self._async_confirm_cloud_config
                    )
                    try:
                        config = await self.config_entry.runtime_data.client.async_get_cloud_config()
                    except MovaEnergyApiClientAuthenticationError:
                        raise
                    except MovaEnergyApiClientError as exception:
                        raise HomeAssistantError(
                            translation_domain=DOMAIN, translation_key="cloud_config_readback_failed"
                        ) from exception
                    self.async_set_updated_data(self._normalize_cloud_data({**self.data, "config": config}))
                    return
            except MovaEnergyApiClientAuthenticationError as exception:
                self.config_entry.async_start_reauth(self.hass)
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="authentication_failed"
                ) from exception
            except MovaEnergyApiClientError as exception:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="config_write_failed"
                ) from exception

            # A rejected multi-field write may still change other fields; trust the complete readback.
            self.async_set_updated_data(self._normalize_local_data({**self.data, "config": response["applied"]}))
            if not response["ok"]:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="config_write_rejected")

    @staticmethod
    def _normalize_cloud_data(data: dict[str, Any]) -> dict[str, Any]:
        """Unwrap cloud responses and expose group settings using their GET values.

        Raises:
            MovaEnergyApiClientError: If the cloud device list is malformed or unsuccessful.
        """
        devices = data.get("devices", {})
        if (
            not isinstance(devices, dict)
            or devices.get("code") not in CLOUD_SUCCESS_CODES
            or devices.get("success") is False
            or not isinstance(devices.get("data"), list)
            or any(not isinstance(device, dict) for device in devices["data"])
        ):
            raise MovaEnergyApiClientError("Invalid cloud device list")
        master = next((device for device in devices["data"] if device.get("master") is True), {})
        status_response = data.get("status", {})
        if (
            not isinstance(status_response, dict)
            or status_response.get("code") not in CLOUD_SUCCESS_CODES
            or not isinstance(status_response.get("data"), dict)
        ):
            raise MovaEnergyApiClientError("Invalid cloud status response")
        status = status_response["data"]
        config_response = data.get("config", {})
        if (
            not isinstance(config_response, dict)
            or config_response.get("code") not in CLOUD_SUCCESS_CODES
            or not isinstance(config_response.get("data"), dict)
        ):
            raise MovaEnergyApiClientError("Invalid cloud configuration response")
        config = config_response["data"]
        LOGGER.debug(
            "MOVA cloud refresh normalized: status_null_fields=%s, config_null_fields=%s",
            sorted(key for key, value in status.items() if value is None),
            sorted(key for key, value in config.items() if value is None),
        )
        values: dict[str, Any] = {
            **data,
            "model": master.get("model") or "MOVA Energy Group",
            "serial_number": master.get("sn"),
            "sw_version": master.get("fwVersion"),
            "firmware_version": status.get("ver"),
        }
        for field, key in (
            ("pv", "pv_power"),
            ("batt", "battery_power"),
            ("grid", "grid_power"),
            ("offgrid", "eps_power"),
            ("soc", "battery_soc"),
            ("pvDayWh", "pv_daily_energy"),
            ("pvSumWh", "pv_total_energy"),
            ("gridImportWh", "grid_import_daily_energy"),
            ("gridExportWh", "grid_export_daily_energy"),
        ):
            value = status.get(field)
            values[key] = (
                value
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                else None
            )
        battery_temperature = status.get("battTemp")
        values["battery_temperature"] = (
            battery_temperature / 10
            if isinstance(battery_temperature, (int, float))
            and not isinstance(battery_temperature, bool)
            and math.isfinite(battery_temperature)
            else None
        )
        run_status = status.get("runStatus")
        values["run_status"] = RUN_STATUS_OPTIONS.get(run_status) if type(run_status) is int else None
        meter_online = status.get("meterOnline")
        values["meter_online"] = meter_online == 1 if type(meter_online) is int and meter_online in (0, 1) else None
        power_fields = (status.get("pv"), status.get("batt"), status.get("grid"), status.get("offgrid"))
        values["load_power"] = (
            sum(power_fields[:3]) - power_fields[3]
            if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in power_fields)
            else None
        )
        mode = config.get("mode")
        values["work_mode"] = CLOUD_WORK_MODE_OPTIONS.get(mode) if type(mode) is int else None
        for key, (field, minimum, maximum) in LOCAL_CONFIG_NUMBERS.items():
            value = config.get(field)
            values[key] = value if type(value) is int and minimum <= value <= maximum else None
        enabled = config.get("backupEn")
        values["backup_en"] = enabled == 1 if type(enabled) is int and enabled in (0, 1) else None
        return values

    @staticmethod
    def _normalize_local_data(data: dict[str, Any]) -> dict[str, Any]:
        """Translate protocol fields into entity values, keeping missing values unknown."""
        values: dict[str, Any] = {
            **data,
            "model": data.get("model", "MOVA Energy Device"),
            "serial_number": data.get("serial_number"),
            "sw_version": data.get("ver") or data.get("sw_version"),
            "firmware_version": data.get("ver"),
        }
        for field, key in (
            ("pv", "pv_power"),
            ("batt", "battery_power"),
            ("grid", "grid_power"),
            ("load", "load_power"),
            ("offgrid", "eps_power"),
            ("soc", "battery_soc"),
            ("battTemp", "battery_temperature"),
            ("pvDayWh", "pv_daily_energy"),
            ("gridImportWh", "grid_import_daily_energy"),
            ("gridExportWh", "grid_export_daily_energy"),
        ):
            value = data.get(field)
            values[key] = (
                value
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                else None
            )

        # battTemp uses tenths of a degree; HA expects the native Celsius value.
        if values["battery_temperature"] is not None:
            values["battery_temperature"] /= 10
        status = data.get("runStatus")
        values["run_status"] = RUN_STATUS_OPTIONS.get(status) if type(status) is int else None
        online = data.get("meterOnline")
        values["meter_online"] = online == 1 if type(online) is int and online in (0, 1) else None
        config = data.get("config", {})
        if not isinstance(config, dict):
            config = {}
        mode = config.get("mode")
        values["work_mode"] = WORK_MODE_OPTIONS.get(mode) if type(mode) is int else None
        for key, (field, minimum, maximum) in LOCAL_CONFIG_NUMBERS.items():
            value = config.get(field)
            values[key] = value if type(value) is int and minimum <= value <= maximum else None
        return values
