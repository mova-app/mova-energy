"""Configuration switches for mova_energy."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from custom_components.mova_energy.entity import MovaEnergyEntity
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory


@dataclass(frozen=True, kw_only=True)
class MovaEnergySwitchEntityDescription(SwitchEntityDescription):
    """Describes a switch and how to read it from coordinator data."""

    value_fn: Callable[[dict[str, Any]], bool | None]


ENTITY_DESCRIPTIONS: tuple[MovaEnergySwitchEntityDescription, ...] = (
    MovaEnergySwitchEntityDescription(
        key="child_lock",
        translation_key="child_lock",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.get("child_lock"),
    ),
    MovaEnergySwitchEntityDescription(
        key="led_display",
        translation_key="led_display",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("led_display"),
    ),
)


class MovaEnergySwitch(SwitchEntity, MovaEnergyEntity):
    """Switch for one of the device's boolean settings."""

    entity_description: MovaEnergySwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the value read from coordinator data."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self._async_set(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self._async_set(enabled=False)

    async def _async_set(self, *, enabled: bool) -> None:
        """Write the setting to the device and refresh."""
        await self._async_write(
            lambda client: client.async_set_toggle(self.entity_description.key, enabled=enabled),
            "switch_set_failed",
            name=self.entity_description.key,
        )
