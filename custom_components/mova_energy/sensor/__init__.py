"""Sensor platform for mova_energy."""

from typing import TYPE_CHECKING

from custom_components.mova_energy.const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD, CONNECTION_MODE_LOCAL

from .air_quality import ENTITY_DESCRIPTIONS as AIR_QUALITY_DESCRIPTIONS
from .diagnostic import ENTITY_DESCRIPTIONS as DIAGNOSTIC_DESCRIPTIONS
from .energy import ENTITY_DESCRIPTIONS as ENERGY_DESCRIPTIONS, PV_TOTAL_ENTITY_DESCRIPTION
from .entity import MovaEnergySensor
from .power import ENTITY_DESCRIPTIONS as POWER_DESCRIPTIONS
from .status import ENTITY_DESCRIPTIONS as STATUS_DESCRIPTIONS

# Read-only platform: the coordinator already serializes the fetch.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.mova_energy.data import MovaEnergyConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

ENTITY_DESCRIPTIONS = (*AIR_QUALITY_DESCRIPTIONS, *DIAGNOSTIC_DESCRIPTIONS, *POWER_DESCRIPTIONS)
LOCAL_ENTITY_DESCRIPTIONS = (*POWER_DESCRIPTIONS, *ENERGY_DESCRIPTIONS, *STATUS_DESCRIPTIONS)
CLOUD_ENTITY_DESCRIPTIONS = (
    *POWER_DESCRIPTIONS,
    *ENERGY_DESCRIPTIONS,
    PV_TOTAL_ENTITY_DESCRIPTION,
    *STATUS_DESCRIPTIONS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovaEnergyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    mode = entry.data.get(CONF_CONNECTION_MODE)
    descriptions = (
        LOCAL_ENTITY_DESCRIPTIONS
        if mode == CONNECTION_MODE_LOCAL
        else CLOUD_ENTITY_DESCRIPTIONS
        if mode == CONNECTION_MODE_CLOUD
        else ENTITY_DESCRIPTIONS
    )
    async_add_entities(MovaEnergySensor(entry.runtime_data.coordinator, description) for description in descriptions)
