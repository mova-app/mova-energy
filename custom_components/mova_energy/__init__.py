"""
Custom integration to integrate mova_energy with Home Assistant.

For more details about this integration, please refer to:
https://github.com/your-org/mova-energy
"""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, Platform
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.loader import async_get_loaded_integration

from .api import MovaEnergyApiClient
from .api.auth import MovaEnergyCloudAuth
from .const import (
    CLOUD_ENVIRONMENT_BASE_URLS,
    CLOUD_ENVIRONMENT_TOKEN_URLS,
    CLOUD_ENVIRONMENT_UAT,
    CONF_CLOUD_API_URL,
    CONF_CLOUD_ENVIRONMENT,
    CONF_CONNECTION_MODE,
    CONF_GROUP_ID,
    CONF_HOST,
    CONF_PORT,
    CONF_UPDATE_INTERVAL_HOURS,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DEFAULT_CLOUD_UPDATE_INTERVAL_SECONDS,
    DEFAULT_LOCAL_UPDATE_INTERVAL_SECONDS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    LOGGER,
)
from .coordinator import MovaEnergyDataUpdateCoordinator
from .data import MovaEnergyData
from .service_actions import async_setup_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import MovaEnergyConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
LOCAL_PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]
CLOUD_PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _get_platforms(entry: MovaEnergyConfigEntry) -> list[Platform]:
    """Return only platforms supported by the selected connection mode."""
    if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_LOCAL:
        return LOCAL_PLATFORMS
    if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
        return CLOUD_PLATFORMS
    return PLATFORMS


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_migrate_entry(hass: HomeAssistant, entry: MovaEnergyConfigEntry) -> bool:
    """Migrate older config entries to the environment-aware cloud settings."""
    if entry.version > 1:
        return False
    if entry.version == 1 and entry.minor_version < 1:
        data = dict(entry.data)
        if data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
            data.setdefault(CONF_CLOUD_ENVIRONMENT, CLOUD_ENVIRONMENT_UAT)
        hass.config_entries.async_update_entry(entry, data=data, minor_version=1)
        LOGGER.info("Migrated MOVA Energy config entry %s to minor version 1", entry.entry_id)
    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """
    Register the service actions.

    Returns:
        True once the actions are registered.

    """
    await async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovaEnergyConfigEntry,
) -> bool:
    """
    Set up a config entry.

    Returns:
        True once the coordinator has data and every platform is forwarded.

    """
    base_url = None
    auth = None
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_LOCAL:
        base_url = f"http://{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}"
    elif entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
        environment = entry.data.get(CONF_CLOUD_ENVIRONMENT, CLOUD_ENVIRONMENT_UAT)
        base_url = entry.data.get(CONF_CLOUD_API_URL) or CLOUD_ENVIRONMENT_BASE_URLS.get(environment)
        token_url = CLOUD_ENVIRONMENT_TOKEN_URLS.get(environment)
        if not base_url or not token_url:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="authentication_failed")
        token = entry.data.get(CONF_TOKEN)
        if not isinstance(token, dict) or not token.get("access_token"):
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="authentication_failed")

        @callback
        def async_save_token(token: dict[str, Any]) -> None:
            hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKEN: token})

        auth = MovaEnergyCloudAuth(async_get_clientsession(hass), token, async_save_token, token_url)

    client = MovaEnergyApiClient(
        username=username,
        password=password,
        session=async_get_clientsession(hass),
        base_url=base_url,
        group_id=entry.data.get(CONF_GROUP_ID),
        auth=auth,
    )

    connection_mode = entry.data.get(CONF_CONNECTION_MODE)
    if CONF_UPDATE_INTERVAL_HOURS in entry.options:
        update_interval = timedelta(hours=float(entry.options[CONF_UPDATE_INTERVAL_HOURS]))
    elif connection_mode == CONNECTION_MODE_LOCAL:
        update_interval = timedelta(seconds=DEFAULT_LOCAL_UPDATE_INTERVAL_SECONDS)
    elif connection_mode == CONNECTION_MODE_CLOUD:
        update_interval = timedelta(seconds=DEFAULT_CLOUD_UPDATE_INTERVAL_SECONDS)
    else:
        update_interval = timedelta(hours=DEFAULT_UPDATE_INTERVAL_HOURS)
    coordinator = MovaEnergyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        config_entry=entry,
        update_interval=update_interval,
        always_update=False,
    )

    entry.runtime_data = MovaEnergyData(
        client=client,
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
    )

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, _get_platforms(entry))
    previous_data = {key: value for key, value in entry.data.items() if key != CONF_TOKEN}
    previous_options = dict(entry.options)

    async def async_entry_updated(hass: HomeAssistant, updated_entry: MovaEnergyConfigEntry) -> None:
        current_data = {key: value for key, value in updated_entry.data.items() if key != CONF_TOKEN}
        if current_data != previous_data or updated_entry.options != previous_options:
            await async_reload_entry(hass, updated_entry)

    entry.async_on_unload(entry.add_update_listener(async_entry_updated))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: MovaEnergyConfigEntry,
) -> bool:
    """
    Unload a config entry.

    Returns:
        True if every platform unloaded cleanly.

    """
    return await hass.config_entries.async_unload_platforms(entry, _get_platforms(entry))


async def async_reload_entry(
    hass: HomeAssistant,
    entry: MovaEnergyConfigEntry,
) -> None:
    """Reload the config entry after its data or options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
