"""MOVA password grant with RSA encryption and optional refresh-token renewal."""

import asyncio
from base64 import b64decode, b64encode
from collections.abc import Callable
import math
import time
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from custom_components.mova_energy.const import (
    CLOUD_CLIENT_AUTHORIZATION,
    CLOUD_PUBLIC_KEY,
    CLOUD_TENANT_ID,
    CLOUD_TOKEN_URL,
    LOGGER,
)

from .exceptions import (
    MovaEnergyApiClientAuthenticationError,
    MovaEnergyApiClientCommunicationError,
    MovaEnergyApiClientError,
    MovaEnergyCloudLoginError,
)

_OAUTH_ERRORS = {
    "invalid_client",
    "unauthorized_client",
    "invalid_grant",
    "invalid_request",
    "unsupported_grant_type",
    "invalid_scope",
    "access_denied",
    "server_error",
    "temporarily_unavailable",
}


def _raise_token_rejection(status: int, payload: Any) -> None:
    """Classify rejection details without logging server text that may echo credentials."""
    payload = payload if isinstance(payload, dict) else {}
    oauth_error = payload.get("error")
    oauth_error = oauth_error if isinstance(oauth_error, str) and oauth_error in _OAUTH_ERRORS else "unspecified"
    code = payload.get("code")
    code = code if type(code) is int else None
    description = " ".join(
        value.lower() for key in ("error_description", "msg", "message") if isinstance(value := payload.get(key), str)
    )
    reason = "cloud_login_rejected"
    if oauth_error in ("invalid_client", "unauthorized_client"):
        reason = "cloud_client_rejected"
    elif any(value in description for value in ("解密", "decrypt", "badpadding", "padding error")):
        reason = "cloud_password_decryption_failed"
    elif any(value in description for value in ("验证码", "captcha", "verification code")):
        reason = "cloud_verification_required"
    elif oauth_error in ("invalid_request", "unsupported_grant_type", "invalid_scope"):
        reason = "cloud_login_request_rejected"
    LOGGER.warning(
        "MOVA cloud token exchange rejected: HTTP %s, code=%s, oauth_error=%s, reason=%s",
        status,
        code,
        oauth_error,
        reason,
    )
    raise MovaEnergyCloudLoginError(reason)


def encrypt_password(password: str) -> str:
    """Encrypt UTF-8 plaintext using the UAT SPKI public key and PKCS#1 v1.5."""
    public_key = serialization.load_der_public_key(b64decode(CLOUD_PUBLIC_KEY))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise MovaEnergyApiClientError("Expected an RSA public key")
    try:
        encrypted = public_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    except ValueError as exception:
        raise MovaEnergyApiClientError("Password exceeds the RSA plaintext length limit") from exception
    return b64encode(encrypted).decode("ascii")


class MovaEnergyCloudAuth:
    """Manage tokens in memory; the config entry persists changes via a callback."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: dict[str, Any] | None = None,
        on_token: Callable[[dict[str, Any]], None] | None = None,
        token_url: str | None = None,
    ) -> None:
        """Use HA's shared session without retaining a plaintext password."""
        self._session = session
        self._token = dict(token or {})
        self._on_token = on_token
        self._token_url = token_url or CLOUD_TOKEN_URL
        self._lock = asyncio.Lock()

    @property
    def token(self) -> dict[str, Any]:
        """Return a copy suitable for config entry storage."""
        return dict(self._token)

    async def async_login(self, username: str, password: str) -> None:
        """Exchange credentials for tokens, encrypting the password off the event loop."""
        encrypted = await asyncio.to_thread(encrypt_password, password)
        token = await self._async_token_request(
            {
                "grant_type": "password",
                "username": username,
                "password": encrypted,
                "signtype": "pk",
                "scope": "all",
                "type": "account",
                "login_system": "management_system",
            }
        )
        self._set_token(token)

    async def async_get_access_token(self) -> str:
        """Return the access token used by MOVA business APIs."""
        async with self._lock:
            access_token = self._token.get("access_token")
            expires_at = self._token.get("expires_at")
            if not isinstance(access_token, str) or not access_token:
                raise MovaEnergyApiClientAuthenticationError("Cloud login is required")
            if isinstance(expires_at, (int, float)) and expires_at <= time.time() + 30:
                await self._async_refresh()
            return str(self._token["access_token"])

    async def async_refresh_rejected_token(self, rejected_token: str) -> None:
        """Renew a rejected token once, coalescing concurrent authentication failures."""
        async with self._lock:
            if self._token.get("access_token") == rejected_token:
                await self._async_refresh()

    async def _async_refresh(self) -> None:
        refresh_token = self._token.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise MovaEnergyApiClientAuthenticationError("Cloud login has expired")
        LOGGER.debug("Refreshing MOVA cloud access token")
        token = await self._async_token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}, use_form_body=True
        )
        token.setdefault("refresh_token", refresh_token)
        self._set_token(token)

    def _set_token(self, token: dict[str, Any]) -> None:
        self._token = token
        if self._on_token is not None:
            self._on_token(dict(token))

    async def _async_token_request(self, form: dict[str, str], *, use_form_body: bool = False) -> dict[str, Any]:
        try:
            async with asyncio.timeout(15):
                async with self._session.post(
                    self._token_url,
                    params=None if use_form_body else form,
                    data=form if use_form_body else None,
                    headers={
                        "Accept": "application/json",
                        "Authorization": CLOUD_CLIENT_AUTHORIZATION,
                        "tenant-id": CLOUD_TENANT_ID,
                    },
                    allow_redirects=False,
                ) as response:
                    LOGGER.debug("MOVA cloud token endpoint returned HTTP status %s", response.status)
                    if response.status in (400, 401, 403):
                        try:
                            rejection = await response.json()
                        except ValueError, aiohttp.ContentTypeError:
                            rejection = None
                        _raise_token_rejection(response.status, rejection)
                    response.raise_for_status()
                    if response.status != 200:
                        raise MovaEnergyApiClientError("Unexpected cloud authentication HTTP status")
                    payload = await response.json()
        except (TimeoutError, aiohttp.ClientError) as exception:
            raise MovaEnergyApiClientCommunicationError("Unable to contact the cloud login service") from exception
        except ValueError as exception:
            raise MovaEnergyApiClientError("Invalid JSON from the cloud login service") from exception

        if not isinstance(payload, dict):
            raise MovaEnergyApiClientError("Invalid cloud token response")
        if payload.get("error") or payload.get("code") in (400, 401, 403):
            _raise_token_rejection(200, payload)
        token = payload.get("data", payload)
        if not isinstance(token, dict):
            raise MovaEnergyApiClientError("Cloud response did not contain an access token")
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise MovaEnergyApiClientError("Cloud response did not contain an access token")
        result = {"access_token": access_token}
        if isinstance(token.get("refresh_token"), str) and token["refresh_token"]:
            result["refresh_token"] = token["refresh_token"]
        expires_in = token.get("expires_in")
        if expires_in is not None:
            try:
                lifetime = float(expires_in)
            except (ValueError, TypeError) as exception:
                raise MovaEnergyApiClientError("Invalid cloud token expiry") from exception
            if not math.isfinite(lifetime) or lifetime <= 0:
                raise MovaEnergyApiClientError("Invalid cloud token expiry")
            result["expires_at"] = time.time() + lifetime
        return result
