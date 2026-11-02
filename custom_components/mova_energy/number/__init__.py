"""Number platform for mova_energy."""

from typing import TYPE_CHECKING

from custom_components.mova_energy.const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD, CONNECTION_MODE_LOCAL

from .energy_config import ENTITY_DESCRIPTIONS as ENERGY_DESCRIPTIONS, MovaEnergyConfigNumber
from .target_humidity import ENTITY_DESCRIPTIONS, MovaEnergyHumidityNumber

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
    """Set up the number platform."""
    if entry.data.get(CONF_CONNECTION_MODE) in (CONNECTION_MODE_LOCAL, CONNECTION_MODE_CLOUD):
        async_add_entities(
            MovaEnergyConfigNumber(entry.runtime_data.coordinator, description) for description in ENERGY_DESCRIPTIONS
        )
        return
    async_add_entities(
        MovaEnergyHumidityNumber(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
