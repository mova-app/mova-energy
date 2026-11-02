"""Switch platform for mova_energy."""

from typing import TYPE_CHECKING

from custom_components.mova_energy.const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD

from .backup import ENTITY_DESCRIPTIONS as ENERGY_DESCRIPTIONS, MovaEnergyBackupSwitch
from .example_switch import ENTITY_DESCRIPTIONS, MovaEnergySwitch

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
    """Set up the switch platform."""
    if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
        async_add_entities(
            MovaEnergyBackupSwitch(entry.runtime_data.coordinator, description) for description in ENERGY_DESCRIPTIONS
        )
        return
    async_add_entities(
        MovaEnergySwitch(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
