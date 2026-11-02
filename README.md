# MOVA Energy

MOVA Energy is a Home Assistant custom integration for MOVA energy storage devices. It supports two connection modes:

- **MOVA cloud** — sign in to the UAT cloud, choose a device group, and read or write the group's energy data.
- **Local HTTP** — connect directly to a device on the local network.

The integration is configured from Home Assistant's UI. It does not use YAML setup.

## Supported connection modes

### MOVA cloud

Cloud setup currently supports the **UAT** environment. CN and EU are shown in the setup form but are reserved until
their service URLs are provided.

The setup flow is:

1. Select **MOVA cloud** and the UAT environment.
2. Enter the MOVA account and password.
3. The integration requests the available device groups.
4. Select a group by its name. Its ID is saved and used for subsequent requests.

The password is RSA/PKCS#1 v1.5 encrypted before it is sent to the token endpoint. The plaintext password is not
stored. Access and refresh tokens are stored in the Home Assistant config entry and redacted from diagnostics. Access
tokens are refreshed with the returned `refresh_token` before they expire.

The UAT endpoints are:

```text
Token:    https://admin-cn-uat.iot.mova-tech.com:30376/api/dreame-auth/oauth/token
Business: https://admin-cn-uat.iot.mova-tech.com:30376/api/mova-hass-server
```

Business requests use the selected group ID:

```text
GET  /open/v1/{groupId}/devices
GET  /open/v1/{groupId}/status
GET  /open/v1/{groupId}/config
POST /open/v1/{groupId}/config
```

The cloud status endpoint does not provide a load value. The integration calculates it as:

```text
load = pv + batt + grid - offgrid
```

Cloud configuration writes submit one `type` and `value` pair at a time. A successful `POST` means that the
command was submitted to the platform; it does not guarantee that the device has already applied it. Home Assistant
reads the configuration back immediately and schedules another read after five seconds. Entity states always use the
reported readback values.

Cloud work modes currently exposed by the integration are:

| Code | Mode             |
| ---: | ---------------- |
|    0 | Self-consumption |
|    3 | Dynamic EV       |
|    6 | Custom mode      |

### Local HTTP

Enter the device host or IP address and port in the setup form. The host is required and the port defaults to `80`.

The integration reads:

```text
GET  http://{host}:{port}/api/device
GET  http://{host}:{port}/api/status
GET  http://{host}:{port}/api/config
POST http://{host}:{port}/api/config
```

`/api/device` supplies the model, serial number, device ID and MAC address used for Home Assistant device metadata.
`/api/status` supplies live energy values. `/api/config` supplies and accepts configuration values. The
integration also accepts JSON responses whose HTTP content type is incorrectly reported as `text/html`, as some
devices do.

The local default polling interval is 10 seconds. Cloud entries default to 60 seconds. An update interval configured
in the integration's **Configure** dialog takes precedence over these defaults.

## Entities

Energy entities are created under the MOVA device in Home Assistant.

| Entity                   | Source                                   | Unit or values                                                |
| ------------------------ | ---------------------------------------- | ------------------------------------------------------------- |
| PV power                 | `pv`                                     | W                                                             |
| Battery power            | `batt`                                   | W; negative means charging                                    |
| Grid power               | `grid`                                   | W                                                             |
| Load power               | `load` locally, calculated in cloud mode | W                                                             |
| EPS power                | `offgrid`                                | W                                                             |
| Battery SOC              | `soc`                                    | %                                                             |
| Battery temperature      | `battTemp`                               | °C; raw value is divided by 10                                |
| Run status               | `runStatus`                              | Off, standby, off-grid, on-grid, fault, or grid/off-grid load |
| Meter online             | `meterOnline`                            | Connectivity binary sensor                                    |
| PV daily energy          | `pvDayWh`                                | Wh                                                            |
| PV total energy          | `pvSumWh`                                | Wh; cloud status only when provided                           |
| Grid import daily energy | `gridImportWh`                           | Wh                                                            |
| Grid export daily energy | `gridExportWh`                           | Wh                                                            |
| Firmware version         | `ver`                                    | Diagnostic sensor                                             |

Daily and cumulative energy sensors use Home Assistant's `total_increasing` state class, so they can be used by the
Energy dashboard and long-term statistics. Power and temperature sensors use the `measurement` state class.

Configuration entities are exposed as controls:

- **Numbers:** charge limit, discharge limit, SOC upper limit, SOC lower limit and backup SOC.
- **Select:** work mode.
- **Switch:** backup enabled in cloud mode.

Local mode supports the device's local work-mode values. Cloud mode exposes the three cloud work modes listed above.
The `antiReverse` field is not exposed because the cloud protocol does not provide a write command for it.

## Installation

### HACS

1. Install [HACS](https://hacs.xyz/) in Home Assistant.
2. Open **HACS → Integrations**.
3. Add this repository as a custom repository and select **Integration**.
4. Download **MOVA Energy**.
5. Restart Home Assistant.

### Manual installation

Copy the `custom_components/mova_energy/` directory into the `custom_components` directory of Home Assistant, then
restart Home Assistant.

After the restart, open **Settings → Devices & services → Add integration**, search for **MOVA Energy**, and choose
the cloud or local connection mode.

## Dashboard example

Replace the entity IDs with the IDs created for your device:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: MOVA Energy
    entities:
      - sensor.mova_energy_pv_power
      - sensor.mova_energy_battery_power
      - sensor.mova_energy_grid_power
      - sensor.mova_energy_load_power
      - sensor.mova_energy_battery_soc
  - type: history-graph
    title: Grid power
    hours_to_show: 6
    entities:
      - sensor.mova_energy_grid_power
  - type: gauge
    entity: sensor.mova_energy_battery_soc
    name: Battery SOC
    min: 0
    max: 100
    needle: true
```

## Refresh action

The integration provides `mova_energy.refresh_data` for an immediate refresh instead of waiting for the next poll:

```yaml
action: mova_energy.refresh_data
data:
  config_entry_id: YOUR_CONFIG_ENTRY_ID
```

The config entry ID can be found in the integration's diagnostics or in Home Assistant's config entry details.

## Troubleshooting

If an entity is unavailable:

1. Check that the local device is reachable from the Home Assistant host, or that the cloud service is reachable.
2. Confirm the selected cloud group still contains a device.
3. Open **Settings → System → Logs** and search for `custom_components.mova_energy`.
4. Enable debug logging temporarily:

   ```yaml
   logger:
     logs:
       custom_components.mova_energy: debug
   ```

5. Download diagnostics from **Settings → Devices & services → MOVA Energy → Download diagnostics**. Credentials,
   tokens and identifying fields are redacted by the integration.

If cloud authentication expires, Home Assistant starts a reauthentication flow. Sign in again to restore the same
device group. A cloud `POST /config` response of `data: true` confirms submission only; check the following GET
readback for the actual device value.

## Development

The repository was created from the
[HACS integration blueprint](https://github.com/jpawlowski/hacs.integration_blueprint). The integration source is in
`custom_components/mova_energy/`, and tests are in `tests/`.

Use the project scripts from a Linux, WSL or Dev Container environment:

```bash
script/python
script/test
script/hassfest
```

The repository also contains shared development instructions under `.agents/`, `.claude/`, `.codex/` and
`.vscode/`. They are development tooling only and are not required by Home Assistant at runtime.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
