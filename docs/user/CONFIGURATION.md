# MOVA Energy configuration

## Initial setup

Add MOVA Energy through **Settings → Devices & services → Add integration**. YAML setup is not supported.

### Cloud mode

| Setting           | What to enter                                                       |
| ----------------- | ------------------------------------------------------------------- |
| Cloud environment | **UAT (test)**; CN and EU are reserved and unavailable.             |
| Account           | Your MOVA UAT account.                                              |
| Password          | Your account password. The plaintext password is not saved.         |
| Device group      | Select a group returned for your account, using its displayed name. |

Service addresses are selected automatically for the chosen environment. You do not need to enter server addresses,
login tokens or a device-group ID manually. Add another integration to connect a different group.

Home Assistant stores the login tokens. The integration checks token expiry before cloud requests and renews the
session when necessary. If renewal is no longer possible, follow Home Assistant's reauthentication prompt and
confirm the same device group to preserve the existing setup.

### Local mode

| Setting     | Required | Default | What to enter                                                    |
| ----------- | -------- | ------- | ---------------------------------------------------------------- |
| Device host | Yes      | None    | The device hostname or IP address reachable from Home Assistant. |
| Device port | Yes      | 80      | The device's HTTP port.                                          |

The local device must have compatible firmware. If its address changes, use **Reconfigure** from the integration
entry's menu to update the connection details.

## Refresh interval

Open **Settings → Devices & services → MOVA Energy** and use the entry's **Configure** button.
The current options form exposes only the refresh interval.

| Behavior                                | Interval                                    |
| --------------------------------------- | ------------------------------------------- |
| Cloud, without a saved override         | 60 seconds                                  |
| Local, without a saved override         | 10 seconds                                  |
| Saved interval option                   | 0.25–24 hours, in steps of 0.25 hours       |
| Initial value shown in the options form | 1 hour, unless an override is already saved |

A saved option takes priority over the connection-mode default. For example, **0.25 hours is 15 minutes** and
**1 hour is 60 minutes**. Saving the initial value shown in the form changes the polling interval to one hour;
it does not retain the faster cloud or local default.

Changing a dashboard graph's time range does not change how often the integration fetches data.

## Refresh immediately

1. Open **Developer tools → Actions**.
2. Select **MOVA Energy: Refresh data**.
3. Choose the integration entry and run the action.

This fetches current data without changing the regular interval. See the [action example](EXAMPLES.md#refresh-action)
for automation YAML.

## Device controls

Cloud and local modes expose charge/discharge power limits, upper/lower battery SOC limits, backup SOC reserve and
work mode. Cloud mode also exposes the backup switch.

Cloud work mode choices are **Self-consumption**, **Dynamic EV** and **Custom mode**. Local choices follow the local
interface. Requested settings may be constrained or rejected by device firmware; the displayed state uses the
reported value after the write.

Cloud commands can take time to reach the device. Submission alone does not mean execution succeeded. Allow the
following updates to confirm the result rather than repeatedly sending the same command.

## Entity names and dashboards

An entity is one measurement or control, such as battery SOC or charge limit. Home Assistant generates entity IDs
from the device and entity names; your IDs can differ from those in the examples.

Find them under **Settings → Devices & services → Entities**. You can rename entities or change their icons in the
entity settings. If you change an entity ID, update any dashboards and automations that reference it.

See the [complete dashboard example](EXAMPLES.md) for the card configuration.

## Logs and diagnostics

Open **Settings → System → Logs** and search for `custom_components.mova_energy`.
Use **Enable debug logging** in the integration's menu to capture a problem, then disable it to download the log.
The same menu offers **Download diagnostics**.

Diagnostics redact credentials and tokens. Review diagnostics, logs and screenshots for hostnames and device
identifiers before posting them publicly.

See [Troubleshooting](../../README.md#troubleshooting) for common symptoms and checks.
