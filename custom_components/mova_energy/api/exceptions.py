"""Exceptions shared by the MOVA API and authentication clients."""


class MovaEnergyApiClientError(Exception):
    """An invalid request or response."""


class MovaEnergyApiClientCommunicationError(MovaEnergyApiClientError):
    """The server could not be reached."""


class MovaEnergyApiClientAuthenticationError(MovaEnergyApiClientError):
    """Credentials or tokens require user attention."""


class MovaEnergyCloudLoginError(MovaEnergyApiClientAuthenticationError):
    """A token endpoint rejection with a safe, classified reason."""

    def __init__(self, reason: str) -> None:
        """Expose only an integration-defined reason, never the response body."""
        super().__init__(reason)
        self.reason = reason
