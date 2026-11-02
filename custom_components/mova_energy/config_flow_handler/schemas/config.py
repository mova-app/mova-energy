"""Setup, reconfigure and reauth form schemas for local and cloud connections."""

import probatio

from custom_components.mova_energy.const import (
    CLOUD_ENVIRONMENT_CN,
    CLOUD_ENVIRONMENT_EU,
    CLOUD_ENVIRONMENT_UAT,
    CONF_CLOUD_ENVIRONMENT,
    CONF_GROUP_ID,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_LOCAL_PORT,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector

_USERNAME_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(
        type=selector.TextSelectorType.TEXT,
        autocomplete="username",
    ),
)
_PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(
        type=selector.TextSelectorType.PASSWORD,
        autocomplete="current-password",
    ),
)


def get_credentials_schema(username: str) -> probatio.Schema:
    """
    Build the schema for the reconfigure and reauth steps.

    Args:
        username: The entry's current username, used to pre-fill the form.

    Returns:
        The probatio schema for the credentials form.

    """
    return probatio.Schema(
        {
            probatio.Required(CONF_USERNAME, default=username): _USERNAME_SELECTOR,
            probatio.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        },
    )


def get_local_schema(host: str = "localhost", port: int = DEFAULT_LOCAL_PORT) -> probatio.Schema:
    """Build the form used to connect directly to a local HTTP device."""
    return probatio.Schema(
        {
            probatio.Required(CONF_HOST, default=host): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
            ),
            probatio.Required(
                CONF_PORT,
                default=port,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=65535,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                ),
            ),
        },
    )


_CLOUD_ENVIRONMENT_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=CLOUD_ENVIRONMENT_UAT, label="UAT (test)"),
            selector.SelectOptionDict(value=CLOUD_ENVIRONMENT_CN, label="CN (China, unavailable)"),
            selector.SelectOptionDict(value=CLOUD_ENVIRONMENT_EU, label="EU (Europe, unavailable)"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    ),
)


def get_cloud_schema(environment: str, username: str = "") -> probatio.Schema:
    """Collect cloud environment and login credentials."""
    return probatio.Schema(
        {
            probatio.Required(CONF_CLOUD_ENVIRONMENT, default=environment): _CLOUD_ENVIRONMENT_SELECTOR,
            probatio.Required(CONF_USERNAME, default=username): _USERNAME_SELECTOR,
            probatio.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        },
    )


def get_cloud_group_schema(groups: list[dict[str, str]], group_id: str = "") -> probatio.Schema:
    """Build a selector for the groups returned by the MOVA cloud account."""
    names = [group.get("groupName") or group["id"] for group in groups]
    options = [
        selector.SelectOptionDict(
            value=group["id"],
            label=f"{name} ({group['id']})" if names.count(name) > 1 else name,
        )
        for group, name in zip(groups, names, strict=True)
    ]
    return probatio.Schema(
        {
            probatio.Required(
                CONF_GROUP_ID,
                default=group_id if group_id in {group["id"] for group in groups} else options[0]["value"],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
        },
    )


__all__ = [
    "get_cloud_group_schema",
    "get_cloud_schema",
    "get_credentials_schema",
    "get_local_schema",
]
