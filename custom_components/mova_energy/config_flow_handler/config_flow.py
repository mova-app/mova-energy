"""Config flow for mova_energy — user setup, reconfigure and reauth."""

from typing import Any

from custom_components.mova_energy.api import (
    MovaEnergyApiClient,
    MovaEnergyApiClientAuthenticationError,
    MovaEnergyApiClientCommunicationError,
    MovaEnergyApiClientError,
)
from custom_components.mova_energy.api.auth import MovaEnergyCloudAuth
from custom_components.mova_energy.api.exceptions import MovaEnergyCloudLoginError
from custom_components.mova_energy.const import (
    CLOUD_ENVIRONMENT_BASE_URLS,
    CLOUD_ENVIRONMENT_OPTIONS,
    CLOUD_ENVIRONMENT_TOKEN_URLS,
    CLOUD_ENVIRONMENT_UAT,
    CLOUD_SUCCESS_CODES,
    CONF_CLOUD_API_URL,
    CONF_CLOUD_ENVIRONMENT,
    CONF_CONNECTION_MODE,
    CONF_GROUP_ID,
    CONF_HOST,
    CONF_PORT,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DEFAULT_LOCAL_HOST,
    DEFAULT_LOCAL_PORT,
    DOMAIN,
    LOGGER,
)
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .options_flow import MovaEnergyOptionsFlow
from .schemas import get_cloud_group_schema, get_cloud_schema, get_credentials_schema, get_local_schema
from .validators import validate_credentials


class MovaEnergyConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for mova_energy."""

    VERSION = 1
    MINOR_VERSION = 1

    _cloud_pending: dict[str, Any] | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MovaEnergyOptionsFlow:
        """
        Return the options flow for this handler.

        Returns:
            The options flow instance.

        """
        return MovaEnergyOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Let the user choose how Home Assistant will connect to MOVA devices.

        Returns:
            The connection-mode menu.

        """
        return self.async_show_menu(
            step_id="user",
            menu_options=[CONNECTION_MODE_CLOUD, CONNECTION_MODE_LOCAL],
        )

    async def async_step_cloud(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Log in and validate the cloud group before creating an entry."""
        return await self._async_cloud_form(user_input, CONNECTION_MODE_CLOUD)

    async def _async_cloud_form(
        self,
        user_input: dict[str, Any] | None,
        step_id: str,
        entry: config_entries.ConfigEntry | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Share cloud login validation across setup, reconfigure and reauth."""
        errors: dict[str, str] = {}
        current = {**(entry.data if entry is not None else {}), **(user_input or {})}

        if user_input is not None:
            environment = str(user_input[CONF_CLOUD_ENVIRONMENT]).strip()
            api_url = CLOUD_ENVIRONMENT_BASE_URLS.get(environment)
            token_url = CLOUD_ENVIRONMENT_TOKEN_URLS.get(environment)
            if environment not in CLOUD_ENVIRONMENT_OPTIONS or not api_url or not token_url:
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=get_cloud_schema(environment, str(user_input[CONF_USERNAME]).strip()),
                    errors={CONF_CLOUD_ENVIRONMENT: "environment_not_available"},
                )
            auth = MovaEnergyCloudAuth(async_get_clientsession(self.hass), token_url=token_url)
            client = MovaEnergyApiClient(
                username=None,
                password=None,
                session=async_get_clientsession(self.hass),
                base_url=api_url,
                auth=auth,
            )
            stage = "token_exchange"
            try:
                await auth.async_login(str(user_input[CONF_USERNAME]).strip(), user_input[CONF_PASSWORD])
                stage = "group_list"
                response = await client.async_get_cloud_groups()
            except MovaEnergyCloudLoginError as exception:
                errors["base"] = exception.reason
            except MovaEnergyApiClientAuthenticationError:
                errors["base"] = "cloud_group_access_denied" if stage == "group_list" else "cloud_login_rejected"
                LOGGER.warning("MOVA cloud setup authentication rejected during %s", stage)
            except MovaEnergyApiClientCommunicationError:
                errors["base"] = "cannot_connect"
                LOGGER.warning("MOVA cloud setup could not connect during %s", stage)
            except MovaEnergyApiClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - malformed responses must be shown in the form.
                LOGGER.exception("Unable to read MOVA cloud group list")
                errors["base"] = "unknown"
            else:
                groups = response.get("data")
                if (
                    response.get("code") not in CLOUD_SUCCESS_CODES
                    or response.get("success") is False
                    or not isinstance(groups, list)
                ):
                    errors["base"] = "cannot_connect"
                elif not groups:
                    errors["base"] = "no_groups"
                else:
                    self._cloud_pending = {
                        "environment": environment,
                        "api_url": api_url,
                        "token_url": token_url,
                        "username": str(user_input[CONF_USERNAME]).strip(),
                        "token": auth.token,
                        "groups": groups,
                        "entry": entry,
                    }
                    return await self._async_cloud_group_form(None, step_id=f"{step_id}_group")

        environment = current.get(CONF_CLOUD_ENVIRONMENT, CLOUD_ENVIRONMENT_UAT)
        if environment not in CLOUD_ENVIRONMENT_OPTIONS:
            environment = CLOUD_ENVIRONMENT_UAT
        return self.async_show_form(
            step_id=step_id,
            data_schema=get_cloud_schema(environment, current.get(CONF_USERNAME, "")),
            errors=errors,
        )

    async def async_step_cloud_group(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Let the user choose one of the groups returned by the cloud account."""
        return await self._async_cloud_group_form(user_input, "cloud_group")

    async def async_step_reconfigure_cloud_group(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose a group while reconfiguring the cloud entry."""
        return await self._async_cloud_group_form(user_input, "reconfigure_cloud_group")

    async def async_step_reauth_cloud_group(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose the existing account's group while reauthenticating."""
        return await self._async_cloud_group_form(user_input, "reauth_cloud_group")

    async def _async_cloud_group_form(
        self, user_input: dict[str, Any] | None, step_id: str
    ) -> config_entries.ConfigFlowResult:
        """Validate the selected group and create or update the config entry."""
        pending = self._cloud_pending
        if pending is None:
            return self.async_abort(reason="cloud_session_expired")
        groups = pending["groups"]
        entry = pending["entry"]
        group_id = str((user_input or {}).get(CONF_GROUP_ID, entry.data[CONF_GROUP_ID] if entry is not None else ""))
        valid_ids = {group["id"] for group in groups}
        errors: dict[str, str] = {}
        if user_input is not None and group_id in valid_ids:
            await self.async_set_unique_id(group_id)
            if entry is not None:
                self._abort_if_unique_id_mismatch()
            else:
                self._abort_if_unique_id_configured()
            auth = MovaEnergyCloudAuth(
                async_get_clientsession(self.hass), pending["token"], token_url=pending["token_url"]
            )
            client = MovaEnergyApiClient(
                username=None,
                password=None,
                session=async_get_clientsession(self.hass),
                base_url=pending["api_url"],
                group_id=group_id,
                auth=auth,
            )
            try:
                devices_response = await client.async_get_devices()
            except MovaEnergyApiClientAuthenticationError:
                errors["base"] = "cloud_device_access_denied"
            except MovaEnergyApiClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - keep unexpected failures recoverable in the form.
                LOGGER.exception("Unable to validate MOVA cloud device group")
                errors["base"] = "unknown"
            else:
                devices = devices_response.get("data")
                if (
                    devices_response.get("code") not in CLOUD_SUCCESS_CODES
                    or devices_response.get("success") is False
                    or not isinstance(devices, list)
                ):
                    errors["base"] = "cannot_connect"
                elif not devices:
                    errors["base"] = "no_devices"
            # A token may have refreshed while validating; keep it for retries and persistence.
            pending["token"] = auth.token
            if errors:
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=get_cloud_group_schema(groups, group_id),
                    errors=errors,
                )
            connection_data = {
                CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
                CONF_CLOUD_ENVIRONMENT: pending["environment"],
                CONF_CLOUD_API_URL: pending["api_url"],
                CONF_GROUP_ID: group_id,
                CONF_USERNAME: pending["username"],
                CONF_TOKEN: auth.token,
            }
            self._cloud_pending = None
            if entry is not None:
                return self.async_update_reload_and_abort(entry, data_updates=connection_data)
            selected_group = next(group for group in groups if group["id"] == group_id)
            first_device = devices[0] if devices else {}
            device_name = (
                first_device.get("name") or first_device.get("model") if isinstance(first_device, dict) else None
            )
            return self.async_create_entry(
                title=str(device_name or selected_group.get("groupName") or f"MOVA Energy ({group_id})"),
                data=connection_data,
            )
        return self.async_show_form(
            step_id=step_id,
            data_schema=get_cloud_group_schema(groups, group_id),
            errors={"base": "invalid_group"} if user_input is not None else {},
        )

    async def async_step_local(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Connect to a local MOVA device over HTTP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            base_url = f"http://{host}:{port}"
            client = MovaEnergyApiClient(
                username=None,
                password=None,
                session=async_get_clientsession(self.hass),
                base_url=base_url,
            )
            try:
                device = await client.async_get_data()
            except Exception:  # noqa: BLE001 - show connection errors in the form.
                LOGGER.exception("Unable to connect to local MOVA device at %s", base_url)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=str(device.get("name") or device.get("model") or f"MOVA Energy ({host})"),
                    data={
                        CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                )

        return self.async_show_form(
            step_id=CONNECTION_MODE_LOCAL,
            data_schema=get_local_schema(DEFAULT_LOCAL_HOST, DEFAULT_LOCAL_PORT),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Handle reconfiguration of an existing entry.

        Returns:
            The form, or the abort that follows the entry update.

        """
        entry = self._get_reconfigure_entry()

        if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_LOCAL:
            return await self.async_step_reconfigure_local(user_input)
        if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
            return await self.async_step_reconfigure_cloud(user_input)

        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                get_credentials_schema(entry.data.get(CONF_USERNAME, "")),
                entry.data,
            ),
            errors=errors,
        )

    async def async_step_reconfigure_cloud(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Verify the cloud account and connection before updating the entry."""
        return await self._async_cloud_form(user_input, "reconfigure_cloud", self._get_reconfigure_entry())

    async def async_step_reauth_cloud(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Restore cloud access without replacing the existing entry or entities."""
        return await self._async_cloud_form(user_input, "reauth_cloud", self._get_reauth_entry())

    async def async_step_reconfigure_local(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Update a local device address after checking that it responds."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            client = MovaEnergyApiClient(
                username=None,
                password=None,
                session=async_get_clientsession(self.hass),
                base_url=f"http://{host}:{port}",
            )
            try:
                await client.async_get_data()
            except Exception:  # noqa: BLE001 - show connection errors in the form.
                LOGGER.exception("Unable to reconnect to local MOVA device")
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: host, CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="reconfigure_local",
            data_schema=self.add_suggested_values_to_schema(
                get_local_schema(
                    entry.data.get(CONF_HOST, DEFAULT_LOCAL_HOST),
                    entry.data.get(CONF_PORT, DEFAULT_LOCAL_PORT),
                ),
                entry.data,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """
        Start reauthentication after the coordinator reported invalid credentials.

        Returns:
            The cloud login or legacy credentials form for the entry's connection mode.

        """
        if entry_data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
            return await self.async_step_reauth_cloud()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Collect and verify replacement credentials.

        Returns:
            The form, or the abort that follows the entry update.

        """
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=get_credentials_schema(entry.data.get(CONF_USERNAME, "")),
            errors=errors,
            description_placeholders={
                "username": entry.data.get(CONF_USERNAME, ""),
            },
        )

    async def _async_validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        """
        Test the submitted credentials.

        Returns:
            An empty dict when they work, otherwise the errors for the form.

        """
        try:
            await validate_credentials(
                self.hass,
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )
        except MovaEnergyApiClientAuthenticationError:
            return {"base": "invalid_auth"}
        except MovaEnergyApiClientCommunicationError:
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - Anything unexpected still has to reach the form.
            LOGGER.exception("Unexpected exception")
            return {"base": "unknown"}

        return {}


__all__ = ["MovaEnergyConfigFlowHandler"]
