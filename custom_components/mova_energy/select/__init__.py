"""Select platform for mova_energy."""

from typing import TYPE_CHECKING

from custom_components.mova_energy.const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD, CONNECTION_MODE_LOCAL

from .fan_speed import ENTITY_DESCRIPTIONS, MovaEnergyFanSpeedSelect
from .work_mode import CLOUD_ENTITY_DESCRIPTIONS, ENTITY_DESCRIPTIONS as ENERGY_DESCRIPTIONS, MovaEnergyWorkModeSelect

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
    """Set up the select platform."""
    mode = entry.data.get(CONF_CONNECTION_MODE)
    if mode in (CONNECTION_MODE_LOCAL, CONNECTION_MODE_CLOUD):
        descriptions = CLOUD_ENTITY_DESCRIPTIONS if mode == CONNECTION_MODE_CLOUD else ENERGY_DESCRIPTIONS
        async_add_entities(
            MovaEnergyWorkModeSelect(entry.runtime_data.coordinator, description) for description in descriptions
        )
        return
    async_add_entities(
        MovaEnergyFanSpeedSelect(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
