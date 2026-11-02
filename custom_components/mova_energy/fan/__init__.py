"""Fan platform for mova_energy."""

from typing import TYPE_CHECKING

from .air_purifier_fan import ENTITY_DESCRIPTIONS, MovaEnergyFan

# Acts on the device: the coordinator does not limit outbound calls.
PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from custom_components.mova_energy.data import MovaEnergyConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovaEnergyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the fan platform."""
    async_add_entities(
        MovaEnergyFan(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )
