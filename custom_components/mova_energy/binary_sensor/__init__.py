"""Binary sensor platform for mova_energy."""

from typing import TYPE_CHECKING

from custom_components.mova_energy.const import CONF_CONNECTION_MODE, CONNECTION_MODE_CLOUD, CONNECTION_MODE_LOCAL

from .filter import ENTITY_DESCRIPTIONS, MovaEnergyFilterSensor
from .meter import ENTITY_DESCRIPTIONS as METER_DESCRIPTIONS, MovaEnergyMeterSensor

# Read-only platform: the coordinator already serializes the fetch.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.mova_energy.data import MovaEnergyConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovaEnergyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary_sensor platform."""
    if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_LOCAL:
        async_add_entities(
            MovaEnergyMeterSensor(entry.runtime_data.coordinator, description) for description in METER_DESCRIPTIONS
        )
        return
    if entry.data.get(CONF_CONNECTION_MODE) == CONNECTION_MODE_CLOUD:
        async_add_entities(
            MovaEnergyMeterSensor(entry.runtime_data.coordinator, description) for description in METER_DESCRIPTIONS
        )
        return
    async_add_entities(
        MovaEnergyFilterSensor(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
