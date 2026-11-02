"""Work mode selector for local devices and cloud device groups."""

from custom_components.mova_energy.const import (
    CLOUD_WORK_MODE_OPTIONS,
    CONF_CONNECTION_MODE,
    CONNECTION_MODE_CLOUD,
    DOMAIN,
    WORK_MODE_OPTIONS,
)
from custom_components.mova_energy.entity import MovaEnergyEntity
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError

ENTITY_DESCRIPTIONS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key="work_mode",
        translation_key="work_mode",
        entity_category=EntityCategory.CONFIG,
        options=list(WORK_MODE_OPTIONS.values()),
    ),
)


CLOUD_ENTITY_DESCRIPTIONS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key="work_mode",
        translation_key="work_mode",
        entity_category=EntityCategory.CONFIG,
        options=list(CLOUD_WORK_MODE_OPTIONS.values()),
    ),
)


class MovaEnergyWorkModeSelect(SelectEntity, MovaEnergyEntity):
    """Work mode selection independent from the reported run status."""

    @property
    def current_option(self) -> str | None:
        """Return the work mode read from the device."""
        return self.coordinator.data.get("work_mode")

    async def async_select_option(self, option: str) -> None:
        """Map the selected option to the device's mode code."""
        modes = (
            CLOUD_WORK_MODE_OPTIONS
            if self.coordinator.config_entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD
            else WORK_MODE_OPTIONS
        )
        code = next((code for code, name in modes.items() if name == option), None)
        if code is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_config_value")
        await self.coordinator.async_write_config("work_mode", code)
