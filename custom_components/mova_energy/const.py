"""Constants for mova_energy."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "mova_energy"
ATTRIBUTION = "Data provided by MOVA"

CONNECTION_MODE_CLOUD = "cloud"
CONNECTION_MODE_LOCAL = "local"

CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"
CONF_CONNECTION_MODE = "connection_mode"
CONF_CLOUD_ENVIRONMENT = "cloud_environment"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_CLOUD_API_URL = "cloud_api_url"
CONF_GROUP_ID = "group_id"

DEFAULT_LOCAL_HOST = "localhost"
DEFAULT_LOCAL_PORT = 80
DEFAULT_CLOUD_API_URL = "https://admin-cn-uat.iot.mova-tech.com:30376/api/mova-hass-server"
CLOUD_GROUPS_PATH = "/open/v1/query/groups"

CLOUD_TOKEN_URL = "https://admin-cn-uat.iot.mova-tech.com:30376/api/dreame-auth/oauth/token"
CLOUD_ENVIRONMENT_UAT = "uat"
CLOUD_ENVIRONMENT_CN = "cn"
CLOUD_ENVIRONMENT_EU = "eu"
CLOUD_ENVIRONMENT_OPTIONS = (CLOUD_ENVIRONMENT_UAT, CLOUD_ENVIRONMENT_CN, CLOUD_ENVIRONMENT_EU)
CLOUD_ENVIRONMENT_BASE_URLS: dict[str, str | None] = {
    CLOUD_ENVIRONMENT_UAT: DEFAULT_CLOUD_API_URL,
    CLOUD_ENVIRONMENT_CN: None,
    CLOUD_ENVIRONMENT_EU: None,
}
CLOUD_ENVIRONMENT_TOKEN_URLS: dict[str, str | None] = {
    CLOUD_ENVIRONMENT_UAT: CLOUD_TOKEN_URL,
    CLOUD_ENVIRONMENT_CN: None,
    CLOUD_ENVIRONMENT_EU: None,
}
CLOUD_CLIENT_AUTHORIZATION = "Basic aGFzczpLM3BRejhSd1RuNVl4Mkxt"
CLOUD_TENANT_ID = "000002"
CLOUD_SUCCESS_CODES = (0, 200)
CLOUD_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCUeGmR+UuuGRP4Xt6OG48OkHUjzRb8+13dq0MNAuNWK6kv"
    "Oxl/eYHwC71blRTi9Zy5q8J/emw4ISYYShyp4FDBaMBGkr/s+KUkiM9bthNms+jYB5gDUit6mF2y7GEcedvxY5C871"
    "RH/k/3YsZcgZQLKmXSyjPZJBSV1UamizOWwQIDAQAB"
)

DEFAULT_UPDATE_INTERVAL_HOURS = 1.0
DEFAULT_CLOUD_UPDATE_INTERVAL_SECONDS = 60
DEFAULT_LOCAL_UPDATE_INTERVAL_SECONDS = 10

RUN_STATUS_OPTIONS = {
    0: "off",
    1: "standby",
    2: "off_grid",
    3: "on_grid",
    4: "fault",
    5: "grid_and_off_grid_load",
}

WORK_MODE_OPTIONS = {
    0: "self_consumption",
    1: "emergency_charge",
    2: "forced_charge_discharge",
    3: "dynamic_ev",
    4: "smart_plug",
    5: "schedule",
    6: "dynamic_tariff",
    7: "ai",
    9: "default",
}

CLOUD_WORK_MODE_OPTIONS = {
    0: "self_consumption",
    3: "dynamic_ev",
    6: "custom_mode",
}

# The cloud endpoint accepts one type/value pair per request.
CLOUD_CONFIG_TYPES = {
    "chargeLimit": 1,
    "dischargeLimit": 2,
    "socLower": 3,
    "socUpper": 4,
    "mode": 5,
    "backupSoc": 6,
    "backupEn": 7,
}

CLOUD_CONFIG_CONFIRM_DELAY_SECONDS = 5

LOCAL_CONFIG_NUMBERS = {
    "charge_limit": ("chargeLimit", 0, 65535),
    "discharge_limit": ("dischargeLimit", 0, 65535),
    "soc_upper": ("socUpper", 0, 100),
    "soc_lower": ("socLower", 0, 100),
    "backup_soc": ("backupSoc", 0, 100),
}
