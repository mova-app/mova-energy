"""API client for mova_energy."""

import asyncio
import socket
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp

from custom_components.mova_energy.const import (
    CLOUD_CONFIG_TYPES,
    CLOUD_GROUPS_PATH,
    CLOUD_SUCCESS_CODES,
    CLOUD_TENANT_ID,
    CLOUD_WORK_MODE_OPTIONS,
    LOGGER,
)

from .auth import MovaEnergyCloudAuth
from .exceptions import (
    MovaEnergyApiClientAuthenticationError,
    MovaEnergyApiClientCommunicationError,
    MovaEnergyApiClientError,
)

API_URL = "https://jsonplaceholder.typicode.com/posts/1"
COMMAND_URL = "https://jsonplaceholder.typicode.com/posts"
REQUEST_TIMEOUT = 10

FAN_SPEEDS = ("low", "medium", "high", "auto")
SPEED_PERCENTAGES = {"low": 33, "medium": 66, "high": 100, "auto": 66}


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """
    Verify that the API response is valid.

    Raises:
        MovaEnergyApiClientAuthenticationError: For 401 and 403 responses.
        aiohttp.ClientResponseError: For every other unsuccessful status.

    """
    if response.status in (401, 403):
        msg = "Invalid credentials"
        raise MovaEnergyApiClientAuthenticationError(msg)
    if 300 <= response.status < 400:
        raise MovaEnergyApiClientError("Unexpected API redirect")
    response.raise_for_status()


def _verify_payload_or_raise(payload: Any) -> dict[str, Any]:
    """Return the decoded object or reject an invalid response shape."""
    if not isinstance(payload, dict):
        raise MovaEnergyApiClientError("Expected a JSON object from device")
    if payload.get("code") in (401, 403):
        raise MovaEnergyApiClientAuthenticationError("Cloud token was rejected")
    return payload


class MovaEnergyApiClient:
    """
    HTTP client for MOVA local devices and cloud device groups.

    MOVA cloud responses retain their envelopes for the coordinator to interpret.
    The legacy template endpoint remains for entries without a connection mode.
    """

    def __init__(
        self,
        username: str | None,
        password: str | None,
        session: aiohttp.ClientSession,
        base_url: str | None = None,
        group_id: str | None = None,
        auth: MovaEnergyCloudAuth | None = None,
    ) -> None:
        """Initialize the API client."""
        self._username = username
        self._password = password
        self._session = session
        self._base_url = base_url.rstrip("/") if base_url else None
        self._group_id = group_id
        self._auth = auth
        self._device_info: dict[str, Any] | None = None
        self._settings: dict[str, Any] = {
            "fan_on": True,
            "fan_speed": "auto",
            "child_lock": False,
            "led_display": True,
            "target_humidity": 50.0,
        }
        self._filter_reset_offset = 0

    async def async_get_data(self) -> dict[str, Any]:
        """
        Fetch the current device state.

        Returns:
            Local metadata, status and config, or cloud response envelopes for normalization.

        """
        if self._group_id and self._base_url:
            devices = await self.async_get_devices()
            status = await self.async_get_cloud_status()
            config = await self.async_get_cloud_config()
            return {"devices": devices, "status": status, "config": config}

        if self._base_url:
            if self._device_info is None:
                self._device_info = await self.async_get_local_device_info()
            status = await self._api_wrapper(method="get", url=f"{self._base_url}/api/status")
            config = await self._api_wrapper(method="get", url=f"{self._base_url}/api/config")
            return {**self._device_info, **status, "config": config}

        response = await self._api_wrapper(method="get", url=API_URL)
        return self._build_payload(response)

    async def async_get_local_device_info(self) -> dict[str, Any]:
        """Fetch local device metadata and map it to the integration's common fields."""
        response = await self._api_wrapper(method="get", url=f"{self._base_url}/api/device")
        if not isinstance(response, dict):
            raise MovaEnergyApiClientError("Invalid local device information response")
        model = response.get("model")
        serial_number = response.get("sn")
        device_id = response.get("did")
        mac = response.get("mac")
        if model is not None and not isinstance(model, str):
            raise MovaEnergyApiClientError("Invalid local device model")
        if serial_number is not None and not isinstance(serial_number, str):
            raise MovaEnergyApiClientError("Invalid local device serial number")
        if device_id is not None and not isinstance(device_id, str):
            raise MovaEnergyApiClientError("Invalid local device ID")
        if mac is not None and not isinstance(mac, str):
            raise MovaEnergyApiClientError("Invalid local device MAC address")
        model = model or "MOVA Energy Device"
        return {
            "name": model,
            "manufacturer": "MOVA Energy",
            "model": model,
            "serial_number": serial_number,
            "device_id": device_id,
            "mac": mac,
            "sw_version": None,
        }

    async def async_get_devices(self) -> dict[str, Any]:
        """Fetch the raw MOVA cloud device-group response."""
        if not self._base_url or not self._group_id:
            raise MovaEnergyApiClientError("Cloud API URL and group ID are required")
        group_id = quote(self._group_id, safe="")
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/open/v1/{group_id}/devices",
        )
        self._log_cloud_response("devices", response)
        return response

    async def async_get_cloud_groups(self) -> dict[str, Any]:
        """Fetch the groups available to the authenticated cloud account."""
        if not self._base_url:
            raise MovaEnergyApiClientError("Cloud API URL is required")
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}{CLOUD_GROUPS_PATH}",
        )
        self._log_cloud_response("groups", response)
        groups = response.get("data")
        if (
            response.get("code") not in CLOUD_SUCCESS_CODES
            or response.get("success") is False
            or not isinstance(groups, list)
            or any(
                not isinstance(group, dict)
                or not isinstance(group.get("id"), str)
                or not group["id"].strip()
                or (group.get("groupName") is not None and not isinstance(group["groupName"], str))
                for group in groups
            )
        ):
            raise MovaEnergyApiClientError("Invalid cloud groups response")
        return response

    async def async_get_cloud_config(self) -> dict[str, Any]:
        """Fetch the raw MOVA cloud device-group configuration response."""
        if not self._base_url or not self._group_id:
            raise MovaEnergyApiClientError("Cloud API URL and group ID are required")
        group_id = quote(self._group_id, safe="")
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/open/v1/{group_id}/config",
        )
        self._log_cloud_response("config", response)
        if response.get("code") not in CLOUD_SUCCESS_CODES or not isinstance(response.get("data"), dict):
            raise MovaEnergyApiClientError("Invalid cloud configuration response")
        return response

    async def async_get_cloud_status(self) -> dict[str, Any]:
        """Fetch the raw MOVA cloud device-group status response."""
        if not self._base_url or not self._group_id:
            raise MovaEnergyApiClientError("Cloud API URL and group ID are required")
        group_id = quote(self._group_id, safe="")
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/open/v1/{group_id}/status",
        )
        self._log_cloud_response("status", response)
        if response.get("code") not in CLOUD_SUCCESS_CODES or not isinstance(response.get("data"), dict):
            raise MovaEnergyApiClientError("Invalid cloud status response")
        return response

    async def async_set_config(self, changes: dict[str, int]) -> dict[str, Any]:
        """Write parameters and return the protocol-specific acknowledgement.

        Raises:
            MovaEnergyApiClientError: If the request or response is invalid.
        """
        if not self._base_url:
            raise MovaEnergyApiClientError("Configuration writes require an API base URL")
        if self._group_id:
            return await self._async_set_cloud_config(changes)
        response = await self._api_wrapper(method="post", url=f"{self._base_url}/api/config", data=changes)
        if type(response.get("ok")) is not bool or not isinstance(response.get("applied"), dict):
            raise MovaEnergyApiClientError("Expected boolean ok and object applied in configuration response")
        return response

    async def _async_set_cloud_config(self, changes: dict[str, int]) -> dict[str, Any]:
        """Submit exactly one cloud command without assuming it was executed.

        Raises:
            MovaEnergyApiClientError: If the field, value or response is invalid.
        """
        if len(changes) != 1:
            raise MovaEnergyApiClientError("Cloud configuration requires exactly one field")
        field, value = next(iter(changes.items()))
        if field not in CLOUD_CONFIG_TYPES or type(value) is not int:
            raise MovaEnergyApiClientError("Unsupported cloud configuration field or value")
        if field == "mode":
            valid = value in CLOUD_WORK_MODE_OPTIONS
        elif field == "backupEn":
            valid = value in (0, 1)
        elif field in ("socLower", "socUpper", "backupSoc"):
            valid = 0 <= value <= 100
        else:
            valid = 0 <= value <= 65535
        if not valid:
            raise MovaEnergyApiClientError("Cloud configuration value is out of range")
        group_id = quote(str(self._group_id), safe="")
        response = await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/open/v1/{group_id}/config",
            data={"type": CLOUD_CONFIG_TYPES[field], "value": value},
        )
        if response.get("code") not in CLOUD_SUCCESS_CODES or type(response.get("data")) is not bool:
            raise MovaEnergyApiClientError("Expected a successful cloud response and boolean data")
        return response

    async def async_set_fan_speed(self, speed: str) -> None:
        """Set the fan speed."""
        await self._async_patch(fan_speed=speed, fan_on=True)

    async def async_set_fan_state(self, *, is_on: bool) -> None:
        """Turn the fan on or off."""
        await self._async_patch(fan_on=is_on)

    async def async_set_target_humidity(self, humidity: float) -> None:
        """Set the target humidity."""
        await self._async_patch(target_humidity=humidity)

    async def async_set_toggle(self, key: str, *, enabled: bool) -> None:
        """Set one of the device's boolean settings."""
        await self._async_patch(**{key: enabled})

    async def async_reset_filter(self) -> None:
        """Reset the filter timer."""
        await self._api_wrapper(method="post", url=COMMAND_URL, data={"command": "reset_filter"})
        self._filter_reset_offset = 0

    async def _async_patch(self, **changes: Any) -> None:
        """Send changed settings to the device and remember them."""
        url = f"{self._base_url}/api/device" if self._base_url else API_URL
        await self._api_wrapper(method="patch", url=url, data=changes)
        self._settings.update(changes)

    def _build_payload(self, response: dict[str, Any]) -> dict[str, Any]:
        """Derive a device-shaped payload from the demo endpoint's response."""
        seed = int(response.get("userId", 1)) * 47 + int(response.get("id", 1)) * 13
        fan_speed = str(self._settings["fan_speed"])
        filter_life = max(0, 100 - (seed % 100) - self._filter_reset_offset)

        return {
            "model": "Blueprint Air Purifier",
            "serial_number": f"BP-{seed:06d}",
            "sw_version": "1.4.2",
            "air_quality_index": seed % 501,
            "pm25": round((seed * 0.37) % 300, 1),
            "filter_life": filter_life,
            "filter_replacement": filter_life < 10,
            "runtime": (seed * 12) % 10000,
            "fan_on": self._settings["fan_on"],
            "fan_speed": fan_speed,
            "fan_percentage": SPEED_PERCENTAGES[fan_speed] if self._settings["fan_on"] else 0,
            "child_lock": self._settings["child_lock"],
            "led_display": self._settings["led_display"],
            "target_humidity": self._settings["target_humidity"],
        }

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Perform a request and translate transport errors into client exceptions.

        Returns:
            The decoded JSON response.

        Raises:
            MovaEnergyApiClientAuthenticationError: If the credentials are rejected.
            MovaEnergyApiClientCommunicationError: If the request does not complete.
            MovaEnergyApiClientError: For any other failure.

        """
        access_token = None
        if self._auth is not None:
            access_token = await self._auth.async_get_access_token()
        try:
            return await self._async_request(method, url, data, access_token)
        except MovaEnergyApiClientAuthenticationError as exception:
            if self._auth is None or access_token is None:
                raise
            await self._auth.async_refresh_rejected_token(access_token)
            if method.lower() != "get":
                raise MovaEnergyApiClientCommunicationError(
                    "Cloud authentication was renewed; the command was not retried, check reported settings"
                ) from exception
            return await self._async_request(method, url, data, await self._auth.async_get_access_token())

    async def _async_request(
        self, method: str, url: str, data: dict[str, Any] | None, access_token: str | None
    ) -> dict[str, Any]:
        endpoint = urlsplit(url).path
        headers = (
            {"Accept": "application/json", "Dreame-Auth": access_token, "tenant-id": CLOUD_TENANT_ID}
            if access_token
            else {}
        )
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method=method,
                    url=url,
                    json=data,
                    headers=headers,
                    allow_redirects=False,
                ) as response:
                    LOGGER.debug("MOVA API %s %s returned HTTP status %s", method.upper(), url, response.status)
                    _verify_response_or_raise(response)
                    return _verify_payload_or_raise(await response.json(content_type=None))

        except TimeoutError as exception:
            msg = f"{method.upper()} {endpoint}: timeout while fetching information - {exception}"
            raise MovaEnergyApiClientCommunicationError(msg) from exception
        except aiohttp.ClientResponseError as exception:
            msg = f"{method.upper()} {endpoint}: HTTP {exception.status} {exception.message}"
            raise MovaEnergyApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"{method.upper()} {endpoint}: error fetching information - {exception}"
            raise MovaEnergyApiClientCommunicationError(msg) from exception
        except MovaEnergyApiClientAuthenticationError as exception:
            raise MovaEnergyApiClientAuthenticationError(f"{method.upper()} {endpoint}: {exception}") from exception
        except MovaEnergyApiClientCommunicationError as exception:
            raise MovaEnergyApiClientCommunicationError(f"{method.upper()} {endpoint}: {exception}") from exception
        except MovaEnergyApiClientError as exception:
            raise MovaEnergyApiClientError(f"{method.upper()} {endpoint}: {exception}") from exception
        except Exception as exception:
            msg = f"{method.upper()} {endpoint}: unexpected error talking to the API - {exception}"
            raise MovaEnergyApiClientError(msg) from exception

    @staticmethod
    def _log_cloud_response(endpoint: str, response: dict[str, Any]) -> None:
        """Log a non-sensitive summary of a cloud response for troubleshooting."""
        payload = response.get("data")
        if isinstance(payload, dict):
            null_fields = sorted(key for key, value in payload.items() if value is None)
            LOGGER.debug(
                "MOVA cloud %s response: code=%s, data_keys=%s, null_fields=%s",
                endpoint,
                response.get("code"),
                sorted(payload),
                null_fields,
            )
        elif isinstance(payload, list):
            LOGGER.debug(
                "MOVA cloud %s response: code=%s, data_items=%s",
                endpoint,
                response.get("code"),
                len(payload),
            )
        else:
            LOGGER.debug(
                "MOVA cloud %s response: code=%s, data_type=%s",
                endpoint,
                response.get("code"),
                type(payload).__name__,
            )
