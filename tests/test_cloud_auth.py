"""Cloud RSA login, transport authentication, renewal and HA reauthentication."""

from base64 import b64decode, b64encode
import time
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mova_energy.api import (
    MovaEnergyApiClient,
    MovaEnergyApiClientAuthenticationError,
    MovaEnergyApiClientCommunicationError,
    MovaEnergyApiClientError,
)
from custom_components.mova_energy.api.auth import MovaEnergyCloudAuth, encrypt_password
from custom_components.mova_energy.api.exceptions import MovaEnergyCloudLoginError
from custom_components.mova_energy.const import (
    CLOUD_CLIENT_AUTHORIZATION,
    CLOUD_ENVIRONMENT_CN,
    CLOUD_ENVIRONMENT_UAT,
    CLOUD_TENANT_ID,
    CLOUD_TOKEN_URL,
    CONF_CLOUD_API_URL,
    CONF_CLOUD_ENVIRONMENT,
    CONF_CONNECTION_MODE,
    CONF_GROUP_ID,
    CONNECTION_MODE_CLOUD,
    DEFAULT_CLOUD_API_URL,
    DOMAIN,
)
from custom_components.mova_energy.diagnostics import async_get_config_entry_diagnostics
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

TEST_GROUP_ID = "test-group-001"

DEVICES_URL = f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/devices"
CONFIG_URL = f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/config"
LOGIN = {
    CONF_USERNAME: "test-account",
    CONF_PASSWORD: "test-plaintext",
    CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_UAT,
}


def test_rsa_encryption() -> None:
    """The ciphertext decrypts with PKCS1v15 and preserves UTF-8 plaintext."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with patch("custom_components.mova_energy.api.auth.CLOUD_PUBLIC_KEY", b64encode(public_key).decode()):
        encrypted = encrypt_password("测试-Pass+123")
    assert private_key.decrypt(b64decode(encrypted), padding.PKCS1v15()).decode() == "测试-Pass+123"


@pytest.mark.usefixtures("socket_enabled")
async def test_login_form_encoding(hass: HomeAssistant, aiohttp_client: Any) -> None:
    """A real HTTP receiver decodes +, / and = once and never sees plaintext."""
    from aiohttp import web  # noqa: PLC0415 - Test server is only needed for this transport test.

    received = {}

    async def login(request: web.Request) -> web.Response:
        received["raw"] = request.query_string
        received["body"] = await request.text()
        received["headers"] = request.headers
        return web.json_response({"access_token": "access", "refresh_token": "refresh", "expires_in": 3600})

    app = web.Application()
    app.router.add_post("/token", login)
    client = await aiohttp_client(app)
    auth = MovaEnergyCloudAuth(async_get_clientsession(hass), token_url=str(client.make_url("/token")))
    with (
        patch("custom_components.mova_energy.api.auth.encrypt_password", return_value="ab+c/d=="),
    ):
        await auth.async_login("test-account", "plaintext")
    assert parse_qs(received["raw"]) == {
        "grant_type": ["password"],
        "username": ["test-account"],
        "password": ["ab+c/d=="],
        "signtype": ["pk"],
        "scope": ["all"],
        "type": ["account"],
        "login_system": ["management_system"],
    }
    assert "password=ab%2Bc/d%3D%3D" in received["raw"]
    assert "plaintext" not in received["raw"]
    assert received["headers"]["Authorization"] == CLOUD_CLIENT_AUTHORIZATION
    assert received["headers"]["tenant-id"] == CLOUD_TENANT_ID
    assert received["body"] == ""
    assert auth.token["access_token"] == "access"
    assert auth.token["expires_at"] > time.time()


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_login_rejected(hass: HomeAssistant, aioclient_mock: Any, status: int) -> None:
    """Rejected credentials raise an authentication error without response contents."""
    aioclient_mock.post(CLOUD_TOKEN_URL, status=status, json={"error": "invalid_grant"})
    auth = MovaEnergyCloudAuth(async_get_clientsession(hass))
    with pytest.raises(MovaEnergyApiClientAuthenticationError):
        await auth.async_login("test-account", "test-password")


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"error": "invalid_client"}, "cloud_client_rejected"),
        ({"error": "invalid_grant", "error_description": "RSA decryption failed"}, "cloud_password_decryption_failed"),
        ({"code": 400, "msg": "密码解密失败"}, "cloud_password_decryption_failed"),
        ({"error": "invalid_grant", "error_description": "Captcha required"}, "cloud_verification_required"),
        ({"error": "invalid_scope"}, "cloud_login_request_rejected"),
        ({"error": "invalid_grant", "error_description": "Bad credentials"}, "cloud_login_rejected"),
    ],
)
async def test_token_error_classification(
    hass: HomeAssistant,
    aioclient_mock: Any,
    payload: dict[str, Any],
    reason: str,
) -> None:
    """Server rejection categories distinguish client, request and RSA failures."""
    aioclient_mock.post(CLOUD_TOKEN_URL, status=400, json=payload)
    auth = MovaEnergyCloudAuth(async_get_clientsession(hass))
    with pytest.raises(MovaEnergyCloudLoginError) as error:
        await auth.async_login("test-account", "test-password")
    assert error.value.reason == reason


async def test_rejection_log_does_not_echo_credentials(
    hass: HomeAssistant,
    aioclient_mock: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Untrusted server text is classified without exposing echoed request secrets."""
    aioclient_mock.post(
        CLOUD_TOKEN_URL,
        status=400,
        json={
            "error": "invalid_grant",
            "error_description": "test-password echoed-token test-account",
            "access_token": "echoed-token",
        },
    )
    auth = MovaEnergyCloudAuth(async_get_clientsession(hass))
    with pytest.raises(MovaEnergyCloudLoginError):
        await auth.async_login("test-account", "test-password")
    assert "HTTP 400" in caplog.text
    assert "invalid_grant" in caplog.text
    assert all(secret not in caplog.text for secret in ("test-password", "echoed-token", "test-account"))


@pytest.mark.parametrize("payload", [{}, {"access_token": ""}, {"access_token": "a", "expires_in": "nan"}])
async def test_invalid_token_response(hass: HomeAssistant, aioclient_mock: Any, payload: Any) -> None:
    """Malformed success responses are rejected rather than storing unusable tokens."""
    aioclient_mock.post(CLOUD_TOKEN_URL, json=payload)
    auth = MovaEnergyCloudAuth(async_get_clientsession(hass))
    with pytest.raises(MovaEnergyApiClientError):
        await auth.async_login("test-account", "test-password")


async def test_headers_and_proactive_refresh(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Expired tokens rotate before business requests and notify the persistence callback."""
    saved = []
    aioclient_mock.post(
        CLOUD_TOKEN_URL, json={"access_token": "new-access", "refresh_token": "rotated", "expires_in": 3600}
    )
    aioclient_mock.get(
        DEVICES_URL,
        json={"code": 200, "data": []},
        headers={"Dreame-Auth": "new-access", "tenant-id": CLOUD_TENANT_ID},
    )
    auth = MovaEnergyCloudAuth(
        async_get_clientsession(hass),
        {"access_token": "expired", "refresh_token": "old-refresh", "expires_at": time.time() - 60},
        saved.append,
    )
    api = MovaEnergyApiClient(None, None, async_get_clientsession(hass), DEFAULT_CLOUD_API_URL, TEST_GROUP_ID, auth)
    await api.async_get_devices()
    assert aioclient_mock.mock_calls[-1][3]["Dreame-Auth"] == "new-access"
    assert aioclient_mock.mock_calls[-1][3]["tenant-id"] == CLOUD_TENANT_ID
    assert auth.token["refresh_token"] == "rotated"
    assert saved == [auth.token]
    assert aioclient_mock.call_count == 2


@pytest.mark.parametrize("method", ["get", "post"])
async def test_rejected_token_refreshes_but_never_replays_commands(
    hass: HomeAssistant, aioclient_mock: Any, method: str
) -> None:
    """GET can retry once; POST is never submitted a second time after rejection."""
    aioclient_mock.post(CLOUD_TOKEN_URL, json={"access_token": "new-access", "expires_in": 3600})
    rejected = aioclient_mock.request(method, CONFIG_URL, status=401)
    accepted = aioclient_mock.request(method, CONFIG_URL, json={"code": 200, "data": {}})

    async def respond(*args: Any) -> Any:
        return rejected if aioclient_mock.mock_calls[-1][3]["Dreame-Auth"] == "old-access" else accepted

    rejected.side_effect = respond
    auth = MovaEnergyCloudAuth(
        async_get_clientsession(hass), {"access_token": "old-access", "refresh_token": "refresh"}
    )
    api = MovaEnergyApiClient(None, None, async_get_clientsession(hass), DEFAULT_CLOUD_API_URL, TEST_GROUP_ID, auth)
    if method == "get":
        await api.async_get_cloud_config()
        assert aioclient_mock.call_count == 3
    else:
        with pytest.raises(MovaEnergyApiClientCommunicationError):
            await api.async_set_config({"chargeLimit": 1500})
        assert aioclient_mock.call_count == 2


async def test_missing_refresh_requires_login(hass: HomeAssistant) -> None:
    """Sessions without renewal credentials ask for login when they expire."""
    auth = MovaEnergyCloudAuth(async_get_clientsession(hass), {"access_token": "access", "expires_at": 1})
    with pytest.raises(MovaEnergyApiClientAuthenticationError):
        await auth.async_get_access_token()


@pytest.mark.parametrize("source", [SOURCE_REAUTH, SOURCE_RECONFIGURE])
async def test_cloud_account_update_preserves_entry(
    hass: HomeAssistant,
    cloud_config_entry: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    mock_cloud_login: AsyncMock,
    source: str,
) -> None:
    """Reauth and reconfigure replace sessions on the same entry without saving passwords."""
    cloud_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source, "entry_id": cloud_config_entry.entry_id, "unique_id": cloud_config_entry.unique_id},
        data=dict(cloud_config_entry.data) if source == SOURCE_REAUTH else None,
    )
    assert result["step_id"] == ("reauth_cloud" if source == SOURCE_REAUTH else "reconfigure_cloud")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["step_id"] == ("reauth_cloud_group" if source == SOURCE_REAUTH else "reconfigure_cloud_group")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: TEST_GROUP_ID})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == ("reauth_successful" if source == SOURCE_REAUTH else "reconfigure_successful")
    assert cloud_config_entry.data[CONF_TOKEN]["access_token"] == "test-access-token"
    assert CONF_PASSWORD not in cloud_config_entry.data
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MovaEnergyApiClientAuthenticationError("rejected"), "cloud_login_rejected"),
        (MovaEnergyApiClientCommunicationError("offline"), "cannot_connect"),
    ],
)
async def test_cloud_flow_login_error_and_recovery(
    hass: HomeAssistant,
    mock_cloud_api: AsyncMock,
    mock_cloud_login: AsyncMock,
    error: Exception,
    expected: str,
) -> None:
    """A failed login leaves the form usable and a second attempt can succeed."""
    mock_cloud_login.side_effect = error
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "cloud"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["errors"] == {"base": expected}
    assert result["data_schema"]({CONF_PASSWORD: "replacement"})[CONF_USERNAME] == "test-account"
    mock_cloud_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["step_id"] == "cloud_group"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: TEST_GROUP_ID})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PASSWORD not in result["data"]


async def test_login_success_group_rejection_is_not_password_error(
    hass: HomeAssistant,
    mock_cloud_api: AsyncMock,
    mock_cloud_login: AsyncMock,
) -> None:
    """The form differentiates a successful login from a denied group-list request."""
    mock_cloud_api.side_effect = MovaEnergyApiClientAuthenticationError("device request rejected")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "cloud"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["errors"] == {"base": "cloud_group_access_denied"}
    assert result["type"] is FlowResultType.FORM
    mock_cloud_login.assert_awaited()


async def test_old_entry_requests_reauth(hass: HomeAssistant, mock_cloud_api: AsyncMock) -> None:
    """An old unauthenticated entry starts reauth instead of making anonymous requests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_GROUP_ID,
        data={
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_CLOUD_API_URL: "http://legacy-cloud.example:8080",
            CONF_GROUP_ID: TEST_GROUP_ID,
        },
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(flow["step_id"] == "reauth_cloud" for flow in hass.config_entries.flow.async_progress())
    mock_cloud_api.assert_not_awaited()


async def test_token_persistence_does_not_reload(
    hass: HomeAssistant,
    init_cloud_integration: MockConfigEntry,
) -> None:
    """Token rotation updates storage without replacing the running coordinator."""
    entry = init_cloud_integration
    runtime = entry.runtime_data
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKEN: {"access_token": "rotated"}})
    await hass.async_block_till_done()
    assert entry.runtime_data is runtime
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "rotated" not in str(diagnostics)
    assert diagnostics["entry"]["data"][CONF_TOKEN] == "**REDACTED**"


async def test_unavailable_cloud_environment_does_not_login(hass: HomeAssistant, mock_cloud_login: AsyncMock) -> None:
    """Reject environments without configured endpoints before signing in."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "cloud"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**LOGIN, CONF_CLOUD_ENVIRONMENT: CLOUD_ENVIRONMENT_CN}
    )
    assert result["errors"] == {CONF_CLOUD_ENVIRONMENT: "environment_not_available"}
    mock_cloud_login.assert_not_awaited()


async def test_reauth_rejects_another_group(
    hass: HomeAssistant,
    cloud_config_entry: MockConfigEntry,
    mock_cloud_api: AsyncMock,
    mock_cloud_login: AsyncMock,
) -> None:
    """Reauthentication cannot silently attach existing entities to a different group."""
    cloud_config_entry.add_to_hass(hass)
    original = mock_cloud_api.side_effect

    async def response(**kwargs: Any) -> dict[str, Any]:
        if kwargs["url"].endswith("/query/groups"):
            return {"code": 0, "data": [{"id": "another-group", "groupName": "Another group"}]}
        return await original(**kwargs)

    mock_cloud_api.side_effect = response
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": cloud_config_entry.entry_id,
            "unique_id": cloud_config_entry.unique_id,
        },
        data=dict(cloud_config_entry.data),
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["step_id"] == "reauth_cloud_group"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_GROUP_ID: "another-group"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert cloud_config_entry.data[CONF_GROUP_ID] == TEST_GROUP_ID


async def test_ha_setup_refreshes_and_persists_token(
    hass: HomeAssistant,
    cloud_config_entry: MockConfigEntry,
    aioclient_mock: Any,
) -> None:
    """The production setup callback saves renewed tokens before loading entities."""
    cloud_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        cloud_config_entry,
        data={
            **cloud_config_entry.data,
            CONF_TOKEN: {"access_token": "expired", "refresh_token": "refresh", "expires_at": 1},
        },
    )
    aioclient_mock.post(
        CLOUD_TOKEN_URL, json={"access_token": "renewed", "refresh_token": "rotated", "expires_in": 3600}
    )
    aioclient_mock.get(DEVICES_URL, json={"code": 200, "data": [{"master": True, "model": "Energy", "sn": "TEST"}]})
    aioclient_mock.get(
        f"{DEFAULT_CLOUD_API_URL}/open/v1/{TEST_GROUP_ID}/status", json={"code": 200, "data": {"grid": 123}}
    )
    aioclient_mock.get(CONFIG_URL, json={"code": 200, "data": {}})
    assert await hass.config_entries.async_setup(cloud_config_entry.entry_id)
    await hass.async_block_till_done()
    assert cloud_config_entry.data[CONF_TOKEN]["access_token"] == "renewed"
    assert cloud_config_entry.data[CONF_TOKEN]["refresh_token"] == "rotated"
    assert hass.states.get("sensor.mova_cloud_group_grid_power").state == "123"
    assert all(call[3]["Dreame-Auth"] == "renewed" for call in aioclient_mock.mock_calls[1:])
