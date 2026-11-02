"""
API package for mova_energy.

Exception hierarchy:
    MovaEnergyApiClientError (base)
    ├── MovaEnergyApiClientCommunicationError (network/timeout)
    └── MovaEnergyApiClientAuthenticationError (401/403)

The coordinator maps authentication and communication errors to Home Assistant
exceptions; config flows use the same types for form errors.
"""

from .client import FAN_SPEEDS, MovaEnergyApiClient
from .exceptions import (
    MovaEnergyApiClientAuthenticationError,
    MovaEnergyApiClientCommunicationError,
    MovaEnergyApiClientError,
)

__all__ = [
    "FAN_SPEEDS",
    "MovaEnergyApiClient",
    "MovaEnergyApiClientAuthenticationError",
    "MovaEnergyApiClientCommunicationError",
    "MovaEnergyApiClientError",
]
