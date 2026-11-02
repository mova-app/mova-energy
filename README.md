# MOVA Energy

> [!IMPORTANT]
> Adding this integration offers **MOVA cloud** (UAT account login) or **Local HTTP**
> (direct device HTTP access). Local HTTP reads `/api/status` for energy measurements.
> Device metadata is read once from `/api/device`; energy measurements are read from `/api/status`.
> `/api/config` supplies user parameters and accepts configuration writes.
> The air purifier platforms and capabilities described below are inherited template examples, not MOVA device support.

## Cloud energy controls

Cloud setup accepts an account and plaintext password, then lets you choose a returned device group by name. The
selected group's ID is saved automatically. Passwords are encrypted with
the UAT RSA public key using PKCS#1 v1.5, then submitted as URL-encoded form fields with `signtype=pk` to
`https://admin-cn-uat.iot.mova-tech.com:30376/api/dreame-auth/oauth/token`.
The login request includes the client Basic authorization and tenant `000002`. This uses the password grant,
not a browser authorization-code redirect. The plaintext password is never stored in the config entry.

The business API defaults to `https://admin-cn-uat.iot.mova-tech.com:30376/api/mova-hass-server`.
Business requests carry `Dreame-Auth: <access_token>` and `tenant-id: 000002`.
Access and refresh tokens are saved in the config entry and redacted from diagnostics. When the server supplies
`expires_in`, access tokens are renewed before expiry using `refresh_token`. A rejected GET can be retried once
after renewal; POST commands are never replayed automatically. If renewal is unavailable or rejected, HA asks
the user to sign in again. Existing cloud entries without a token also request reauthentication, preserving entities.

The integration reads `/open/v1/{groupId}/devices` and
`GET /open/v1/{groupId}/config`. The group exposes five numbers, a work mode selector, and a backup switch.
Cloud status sensors read `/open/v1/{groupId}/status`.

| Setting         | POST type | Values                                                              |
| --------------- | --------- | ------------------------------------------------------------------- |
| Charge limit    | 1         | Integer watts                                                       |
| Discharge limit | 2         | Integer watts                                                       |
| SOC lower limit | 3         | 0–100%                                                              |
| SOC upper limit | 4         | 0–100%                                                              |
| Work mode       | 5         | 0 self-consumption, 3 dynamic EV, 4 smart plug, 6 custom mode, 7 AI |
| Backup SOC      | 6         | 0–100%                                                              |
| Backup enabled  | 7         | 0 off, 1 on                                                         |

Each change sends one JSON object, such as `{"type": 1, "value": 1500}`, to `POST /open/v1/{groupId}/config`.
`code:200, data:true` means submitted to the IoT platform, including when no master exists; it does not prove execution.
HA immediately reads configuration again and schedules one additional refresh after 5 seconds. Only reported GET values
update controls, including any device clamping. There are no automatic POST retries or assumed target states.
If execution takes longer, the normal polling interval or the refresh action retrieves the eventual result.
The cloud default polling interval is one minute. An explicitly configured update interval in integration options
takes precedence.
`data:false`, malformed responses and transport failures report errors. A failed readback after submission reports
that the actual outcome is unknown. The integration cannot identify a missing-master no-op from a `true` response.
`antiReverse` is not exposed because it has no command mapping and is reported as null.

Power controls currently retain the existing 0–65535 W input range; cloud-specific limits have not been specified.
Local mode retains its own work mode values and `ok`/`applied` write response handling.

Cloud status fields map to the same power, SOC, temperature and run status entities as local mode. `battTemp` is
converted from tenths of a degree to Celsius. `load` is calculated as `pv + batt + grid - offgrid` because the cloud
protocol does not provide a load point. The cumulative `pvSumWh` field is exposed as PV total energy. When the cloud
status response contains an empty `data` object, these status entities remain unknown until a later poll contains
values; the device and configuration entities remain available.
Validation uses mocked HTTP responses and HA service calls; no commands are sent to the real test server by the tests.
Restart Home Assistant after updating to load the new cloud controls.

## Local energy device metrics

| API field      | Entity                   | Unit / interpretation                                          |
| -------------- | ------------------------ | -------------------------------------------------------------- |
| `pv`           | PV Power                 | W                                                              |
| `batt`         | Battery power            | W; negative charging, positive discharging                     |
| `grid`         | Grid power               | W; positive importing, negative exporting                      |
| `load`         | Load power               | W                                                              |
| `offgrid`      | EPS power                | W                                                              |
| `soc`          | Battery SOC              | %                                                              |
| `battTemp`     | Battery temperature      | °C; raw value divided by 10                                    |
| `runStatus`    | Run status               | Off, standby, off-grid, on-grid, fault, grid and off-grid load |
| `meterOnline`  | Meter online             | Connectivity binary sensor                                     |
| `pvDayWh`      | PV daily energy          | Wh; daily counter                                              |
| `gridImportWh` | Grid import daily energy | Wh; daily counter                                              |
| `gridExportWh` | Grid export daily energy | Wh; daily counter                                              |
| `ver`          | Firmware version         | Diagnostic sensor and device firmware metadata                 |

The daily energy sensors use `total_increasing` so Home Assistant can account for daily resets.
Local devices poll every 10 seconds by default; an existing explicit update interval in hours takes precedence.
Missing or invalid measurements show as unknown; failed status requests make the entities unavailable.
Restart Home Assistant after updating the integration. Existing local entries gain the new entities automatically,
and the existing PV Power entity keeps its unique ID.

## Local energy controls

The device page adds one work mode selector and five configuration numbers:

| API field        | Entity          | Allowed input                                                                                                                                |
| ---------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `mode`           | Work mode       | Self-consumption, emergency charge, forced charge/discharge, dynamic EV, smart plug, schedule, dynamic tariff, AI, default (codes 0–7 and 9) |
| `chargeLimit`    | Charge limit    | Integer 0–65535 W; the simulator clamps to 2500 W                                                                                            |
| `dischargeLimit` | Discharge limit | Integer 0–65535 W; the device decides the Sink limit                                                                                         |
| `socUpper`       | SOC upper limit | Integer 0–100%                                                                                                                               |
| `socLower`       | SOC lower limit | Integer 0–100%                                                                                                                               |
| `backupSoc`      | Backup SOC      | Integer 0–100%; the device clamps it to the SOC upper limit                                                                                  |

Status and configuration are read every 10 seconds by default. Changing a control sends only its field to
`POST /api/config`; all controls immediately display the device's full `applied` response, including clamping.
For example, requesting a 3000 W charge limit on the simulator shows 2500 W after the write.
Lowering the SOC upper limit can also lower the displayed backup SOC.

`ok:false` reports a failed write after displaying actual readback; it never assumes the requested value took effect.
If the device has just rebooted, retry manually after its sync link is ready. Writes are not automatically retried.
Invalid acknowledgements and communication failures report an error without publishing the requested value.
Failed configuration polls make the coordinated entities unavailable, with recovery on a later successful poll.
Missing or invalid individual parameters remain unknown. Existing local devices must now provide `/api/config`.

The local UI does not expose `backupEn` or `antiReverse`, as specified by the protocol.
Work mode (`mode`) and run status (`runStatus`) are separate fields. The simulator stores configuration without
changing its random status model. This feature is validated with mocked local HTTP responses, not real hardware.
Restart the simulator with the latest code before restarting Home Assistant; existing entries gain the controls
without being removed and re-added.

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

<!--
Uncomment and customize these badges if you want to use them:

[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]
[![Discord][discord-shield]][discord]
-->

**✨ Develop in the cloud:** Want to contribute or customize this integration? Open it directly in GitHub Codespaces - no local setup required!

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/your-org/mova-energy?quickstart=1)

## ✨ Features

- **Easy Setup**: Simple configuration through the UI - no YAML required
- **Air Quality Monitoring**: Track AQI and PM2.5 levels in real-time
- **Filter Management**: Monitor filter life and get replacement alerts
- **Smart Control**: Adjust fan speed, target humidity, and operating modes
- **Child Lock**: Safety feature to prevent accidental changes
- **Diagnostic Info**: View filter life, runtime hours, and device statistics
- **Reconfigurable**: Change credentials anytime without removing the integration
- **Options Flow**: Adjust settings like update interval after setup
- **Custom Services**: Advanced control with built-in service calls

**This integration will set up the following platforms.**

| Platform        | Description                                              |
| --------------- | -------------------------------------------------------- |
| `sensor`        | Air quality index (AQI), PM2.5, filter life, and runtime |
| `binary_sensor` | API connection status and filter replacement alert       |
| `switch`        | Child lock and LED display controls                      |
| `select`        | Fan speed selection (Low/Medium/High/Auto)               |
| `number`        | Target humidity setting (30-80%)                         |
| `button`        | Reset filter timer after replacement                     |
| `fan`           | Air purifier fan control with speed settings             |

> [!TIP]
> **Interactive Demo:** The entities are interconnected for demonstration.
> Press the **Reset Filter Timer** button to see **Filter Life Remaining** update to 100%.
> Changing the **Air Purifier** fan speed syncs the **Fan Speed** select, and vice versa.

## 🚀 Quick Start

### Step 1: Install the Integration

**Prerequisites:** This integration requires [HACS](https://hacs.xyz/) (Home Assistant Community Store) to be installed.

Click the button below to open the integration directly in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jpawlowski&repository=mova-energy&category=integration)

Then:

1. Click "Download" to install the integration
2. **Restart Home Assistant** (required after installation)

> [!NOTE]
> The My Home Assistant redirect will first take you to a landing page. Click the button there to open your Home Assistant instance.

<details>
<summary><strong>Manual Installation (Advanced)</strong></summary>

If you prefer not to use HACS:

1. Download the `custom_components/mova_energy/` folder from this repository
2. Copy it to your Home Assistant's `custom_components/` directory
3. Restart Home Assistant

</details>

### Step 2: Add and Configure the Integration

**Important:** You must have installed the integration first (see Step 1) and restarted Home Assistant!

#### Option 1: One-Click Setup (Quick)

Click the button below to open the configuration dialog:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mova_energy)

Follow the setup wizard:

1. Select **MOVA cloud** or **Local HTTP**.
2. For **Local HTTP**, enter the host and port of the device (the simulator defaults to `localhost:18080`).
3. Home Assistant queries `/api/status` and `/api/config`, then creates the config entry when the device responds.

For **MOVA cloud**, select the environment and sign in with your account and password (currently UAT only).
Then choose a device group by name from the returned list. The integration saves its group ID automatically
and validates device-group access before creating the entry. Your plaintext password is not saved.

#### Option 2: Manual Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for "MOVA Energy"
4. Follow the same setup steps as Option 1

### Step 3: Adjust Settings (Optional)

After setup, you can adjust options:

1. Go to **Settings** → **Devices & Services**
2. Find **MOVA Energy**
3. Click **Configure** to adjust:
   - Update interval (how often to refresh data)
   - Enable debug logging

You can also **Reconfigure** your credentials anytime without removing the integration.

### Step 4: Start Using!

The integration creates several entities for your air purifier:

- **Sensors**: Air quality index, PM2.5 levels, filter life remaining, total runtime
- **Binary Sensors**: API connection status, filter replacement alert
- **Switches**: Child lock, LED display control
- **Select**: Fan speed (Low/Medium/High/Auto)
- **Number**: Target humidity (30-80%)
- **Button**: Reset filter timer
- **Fan**: Air purifier fan control

Find all entities in **Settings** → **Devices & Services** → **MOVA Energy** → click on the device.

## Available Entities

### Sensors

- **Air Quality Index (AQI)**: Real-time air quality measurement (0-500 scale)
  - Includes air quality category (Good/Moderate/Unhealthy/etc.)
  - Health recommendations based on current AQI
- **PM2.5**: Fine particulate matter concentration in µg/m³
- **Filter Life Remaining** (Diagnostic): Shows remaining filter life as percentage
- **Total Runtime** (Diagnostic): Total operating hours of the device

### Binary Sensors

- **API Connection**: Shows whether the connection to the API is active
  - On: Connected and receiving data
  - Off: Connection lost or authentication failed
  - Shows update interval and API endpoint information
- **Filter Replacement Needed**: Alerts when filter needs replacement
  - Shows estimated days remaining
  - Turns on when filter life is low

### Switches

- **Child Lock**: Prevents accidental button presses on the device
  - Icon changes based on state (locked/unlocked)
- **LED Display**: Enable/disable the LED display
  - Disabled by default - enable in entity settings if needed

### Select

- **Fan Speed**: Choose from Low, Medium, High, or Auto
  - Icon changes dynamically based on selected speed
  - Auto mode adjusts speed based on air quality
  - Syncs bidirectionally with the Air Purifier fan entity

### Number

- **Target Humidity**: Set desired humidity level (30-80%)
  - Adjustable in 5% increments
  - Displayed as a slider in the UI

### Button

- **Reset Filter Timer**: Reset the filter life to 100%
  - Press to reset after replacing the filter
  - Instantly updates the Filter Life Remaining sensor

### Fan

- **Air Purifier**: Control the air purifier fan speed and power
  - Three speed levels: Low, Medium, High
  - Syncs bidirectionally with the Fan Speed select entity
  - Turn on/off functionality

## Custom Services

The integration provides services for advanced automation:

### `mova_energy.example_action`

Perform a custom action (customize this for your needs).

**Example:**

```yaml
service: mova_energy.example_action
data:
  # Add your parameters here
```

### `mova_energy.reload_data`

Manually refresh data from the API without waiting for the update interval.

**Example:**

```yaml
service: mova_energy.reload_data
```

Use these services in automations or scripts for more control.

## Configuration Options

### During Setup

| Name        | Required | Description                                            |
| ----------- | -------- | ------------------------------------------------------ |
| Device host | Yes      | Hostname or IP address reachable from Home Assistant   |
| Device port | Yes      | HTTP port exposed by the local device (default: 80)    |

### After Setup (Options)

You can change these anytime by clicking **Configure**:

| Name             | Default | Description                |
| ---------------- | ------- | -------------------------- |
| Update Interval  | 1 hour  | How often to refresh data  |
| Enable Debugging | Off     | Enable extra debug logging |

## Troubleshooting

### Authentication Issues

#### Reauthentication

If your credentials expire or change, Home Assistant will automatically prompt you to reauthenticate:

1. Go to **Settings** → **Devices & Services**
2. Look for **"Action Required"** or **"Configuration Required"** message on the integration
3. Click **"Reconfigure"** or follow the prompt
4. Enter your updated credentials
5. Click Submit

The integration will automatically resume normal operation with the new credentials.

#### Manual Credential Update

You can also update credentials at any time without waiting for an error:

1. Go to **Settings** → **Devices & Services**
2. Find **MOVA Energy**
3. Click the **3 dots menu** → **Reconfigure**
4. Enter new username/password
5. Click Submit

#### Connection Status

Monitor your connection status with the **API Connection** binary sensor:

- **On** (Connected): Integration is receiving data normally
- **Off** (Disconnected): Connection lost or authentication failed
  - Check the binary sensor attributes for diagnostic information
  - Verify credentials if authentication failed
  - Check network connectivity

### Enable Debug Logging

To enable debug logging for this integration, add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.mova_energy: debug
```

### Common Issues

#### Authentication Errors

If you receive authentication errors:

1. Verify your username and password are correct
2. Check that your account has the necessary permissions
3. Wait for the automatic reauthentication prompt, or manually reconfigure
4. Check the API Connection binary sensor for status

#### Device Not Responding

If your device is not responding:

1. Check the **API Connection** binary sensor - it should be "On"
2. Check your network connection
3. Verify the device is powered on
4. Check the integration diagnostics (Settings → Devices & Services → MOVA Energy → 3 dots → Download diagnostics)

## 🤝 Contributing

Contributions are welcome! Please open an issue or pull request if you have suggestions or improvements.

You have two options to set up a development environment — expand below for full details.

<details>
<summary><strong>Development Setup</strong></summary>

Both options provide the same fully-configured environment with Home Assistant, Python 3.14, Node.js LTS, and all necessary tools.

### Option 1: GitHub Codespaces (Recommended) ☁️

Develop directly in your browser without installing anything locally!

1. Click the green **"Code"** button in this repository
2. Switch to the **"Codespaces"** tab
3. Click **"Create codespace on main"**
4. **Wait for setup** (2-3 minutes first time) — everything installs automatically
5. **Review and commit** your changes in the Source Control panel (`Ctrl+Shift+G`)

> [!TIP]
> Codespaces gives you **60 hours/month free** for personal accounts. When you start Home Assistant (`script/develop`), port 8123 forwards automatically.

### Option 2: Local Development with VS Code 💻

#### Prerequisites

You'll need these installed locally:

- **A Docker-compatible container engine** — see options by platform:

  | Option                                                                                                                   | 🍎 macOS | 🐧 Linux | 🪟 Windows | Notes                                                                                                                                                                                                                                     |
  | ------------------------------------------------------------------------------------------------------------------------ | :------: | :------: | :--------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | [Docker Desktop](https://www.docker.com/products/docker-desktop/)                                                        |    ✅    |    ✅    |     ✅     | **Easiest starting point for all platforms.** GUI-based, well-documented, one installer. Uses WSL2 as default backend on Windows (Hyper-V also available). Installation requires admin rights; daily use does not. Free for personal use. |
  | [OrbStack](https://orbstack.dev/) ⭐                                                                                     |    ✅    |    —     |     —      | **Recommended for macOS** once Docker Desktop feels slow. Starts in ~2s, much lighter on RAM/CPU, full Docker API compatibility. Free for personal use.                                                                                   |
  | [Docker CE](https://docs.docker.com/engine/install/) (native) ⭐                                                         |    —     |    ✅    |     —      | **Recommended for Linux.** Install directly via your package manager — no VM, no GUI, no overhead. Free.                                                                                                                                  |
  | [WSL2](https://learn.microsoft.com/windows/wsl/install) + [Docker CE](https://docs.docker.com/engine/install/ubuntu/) ⭐ |    —     |    —     |     ✅     | **Recommended for Windows** once you're comfortable with WSL2. Docker runs natively inside WSL2 — no GUI overhead. Requires one-time WSL2 setup. Free.                                                                                    |
  | [Rancher Desktop](https://rancherdesktop.io/)                                                                            |    ✅    |    ✅    |     ✅     | Open source by SUSE. GUI-based, uses WSL2 on Windows. Good alternative to Docker Desktop. Free.                                                                                                                                           |
  | [Colima](https://github.com/abiosoft/colima)                                                                             |    ✅    |    ✅    |     —      | CLI-only, very lightweight. Good for terminal-focused workflows. Free.                                                                                                                                                                    |

- **VS Code** with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- **Git** — macOS and Linux usually have it already; see below if not, or to get a newer version:
  - **🍎 macOS:** The system Git (`xcode-select --install`) works fine. Recommended: `brew install git` ([Homebrew](https://brew.sh/)) for a current version.
  - **🐧 Linux:** Usually pre-installed. If not: `sudo apt install git` (or your distro's equivalent).
  - **🪟 Windows + WSL2 ⭐:** Install Git _inside WSL2_ with `sudo apt install git`. Git on Windows itself is not needed — VS Code clones and operates entirely within WSL2.
  - **🪟 Windows + Docker Desktop:** Install via `winget install Git.Git` or download [Git for Windows](https://git-scm.com/download/win).
- **Hardware** — the devcontainer runs a full Home Assistant instance including Python tooling:

  |          | Minimum    | Recommended                           |
  | -------- | ---------- | ------------------------------------- |
  | **RAM**  | 8 GB       | 16 GB or more                         |
  | **CPU**  | 4 cores    | 8 cores or more                       |
  | **Disk** | 10 GB free | 20 GB free (SSD strongly recommended) |

> [!TIP]
> **Not sure which Docker option to pick?** Start with [Docker Desktop](https://www.docker.com/products/docker-desktop/) — it works on all platforms, has a GUI, and needs no extra setup. The ⭐ options are faster alternatives once you're comfortable. macOS and Linux offer the best devcontainer experience — containers run with no extra VM layer and file I/O is fast. Windows works well too; this integration uses named container volumes (files live inside WSL2, not on the Windows drive) to keep performance acceptable.

> [!NOTE]
> **New to Dev Containers?** See the [VS Code Dev Containers documentation](https://code.visualstudio.com/docs/devcontainers/containers#_system-requirements) for system requirements and how to install the extension. **Once the extension is installed, you're done** — this repository already ships a complete devcontainer configuration. You don't need to follow the rest of the VS Code guide; the setup steps below are all that's needed.

#### Setup Steps

1. **Clone in a Dev Container:**

   **🍎 macOS / 🐧 Linux:** Clone the repository and open the folder in VS Code → click **"Reopen in Container"** when prompted (or `F1` → **"Dev Containers: Reopen in Container"**).

   **🪟 Windows:** In VS Code, press `F1` → **"Dev Containers: Clone Repository in Named Container Volume..."** and enter the repository URL. This keeps files inside WSL2 for best I/O performance.

2. Wait for the container to build (2-3 minutes first time)

3. **Review and commit** changes in Source Control (`Ctrl+Shift+G`)

4. **Start developing**:

   ```bash
   script/develop  # Home Assistant runs at http://localhost:8123
   ```

> [!NOTE]
> Both Codespaces and local DevContainer provide the exact same experience. The only difference is where the container runs (GitHub's cloud vs. your machine).

</details>

---

## 🤖 AI-Assisted Development

> [!NOTE]
> **Transparency Notice:** This integration was developed with assistance from AI coding agents (GitHub Copilot,
> Claude, and others). AI assistance by itself neither guarantees nor rules out software quality. To make an informed
> installation decision, review the project's stated maturity, known limitations, automated test coverage, real-device
> testing, and the extent of human review. The maintainer should replace the fields below with accurate project-specific
> details rather than implying checks that were not performed. See the blueprint's [`AI_POLICY.md`](AI_POLICY.md) for
> guidance.
>
> - **AI assistance:** limited / substantial / predominant
> - **Human review:** complete / partial / spot-checked / not performed
> - **Automated tests:** [describe or state "not performed"]
> - **Real-device or service testing:** [describe or state "not performed"]
> - **Maturity and known limitations:** [describe]
>
> If you encounter unexpected behavior, please [open an issue](../../issues) on GitHub.
>
> _This section can be removed or modified if AI assistance was not used in your integration's development._

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Made with ❤️ by [@your-org][user_profile]**

---

[commits-shield]: https://img.shields.io/github/commit-activity/y/your-org/mova-energy.svg?style=for-the-badge
[commits]: https://github.com/your-org/mova-energy/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/your-org/mova-energy.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40your-org-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/your-org/mova-energy.svg?style=for-the-badge
[releases]: https://github.com/your-org/mova-energy/releases
[user_profile]: https://github.com/jpawlowski

<!-- Optional badge definitions - uncomment if needed:
[buymecoffee]: https://www.buymeacoffee.com/jpawlowski
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
-->
