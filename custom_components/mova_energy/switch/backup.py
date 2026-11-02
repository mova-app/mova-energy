"""Cloud device-group backup configuration switch."""

from typing import Any

from custom_components.mova_energy.entity import MovaEnergyEntity
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

ENTITY_DESCRIPTIONS: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="backup_en",
        translation_key="backup_en",
        entity_category=EntityCategory.CONFIG,
    ),
)


class MovaEnergyBackupSwitch(SwitchEntity, MovaEnergyEntity):
    """Show the backup switch's reported value, independent of submitted commands."""

    @property
    def is_on(self) -> bool | None:
        """Return the backup switch value from configuration GET."""
        return self.coordinator.data.get("backup_en")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Submit a request to enable backup."""
        await self.coordinator.async_write_config("backup_en", 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Submit a request to disable backup."""
        await self.coordinator.async_write_config("backup_en", 0)
