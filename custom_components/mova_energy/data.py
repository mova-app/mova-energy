"""
Runtime data types for mova_energy.

Access pattern: entry.runtime_data.client / entry.runtime_data.coordinator
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import MovaEnergyApiClient
    from .coordinator import MovaEnergyDataUpdateCoordinator


type MovaEnergyConfigEntry = ConfigEntry[MovaEnergyData]


@dataclass
class MovaEnergyData:
    """Runtime data stored on the config entry after a successful setup."""

    client: MovaEnergyApiClient
    coordinator: MovaEnergyDataUpdateCoordinator
    integration: Integration
