# RZROPENAUD-IO

> Linux CLI utility for the **Razer BlackShark V2** (Model **RZ04-0323**, USB **VID: 1532, PID: 0529**) designed specifically for Arch Linux (GNOME).

`RZROPENAUD-IO` provides direct control over the hardware DSP inside the Razer USB Sound Card without requiring Razer Synapse or Windows. It allows setting microphone volume, hardware sidetone (zero-latency mic monitoring), 10-band equalizer profiles, and hardware boost enhancements directly via USB HID.

---

## Features

- **Hardware Sidetone (Mic Monitoring):** Configure zero-latency hardware sidetone level (`0` to `100%`) or toggle it on/off.
- **Microphone Volume & Boost:** Adjust mic input gain and hardware boost directly on the audio chip.
- **10-Band Equalizer:** Apply built-in tuned presets (`game`, `movie`, `music`, `voice`, `esports`, `flat`, `bass-boost`) or custom dB values across 10 bands (31Hz to 16kHz).
- **Razer Standard 90-Byte HID Protocol:** Full implementation of OpenRazer's 90-byte packet structure with dynamic XOR checksum calculation and status acknowledgement verification.
- **Direct DSP Memory Mapping:** High-fidelity register write fallback (Report ID `0x04`) reverse-engineered from Razer Synapse USB traffic captures.
- **GNOME Desktop Integration:** State changes automatically trigger native desktop notifications via `notify-send`.
- **Rootless Operation:** Includes `99-razer.rules` for `/dev/hidraw*` device node access without `sudo`.

---

## Arch Linux Setup & Installation

### 1. Install System Dependencies

On Arch Linux, install `python-hidapi` (for USB HID communication) and `libnotify` (for GNOME notifications):

```bash
sudo pacman -S python-hidapi libnotify
```

### 2. Configure Udev Rules (Rootless Access)

By default, Linux restricts access to `/dev/hidraw*` character devices to root (`0600`). Install the provided udev rule so your desktop user and audio group can interact with the headset without root privileges:

```bash
# Copy the udev rule to the system directory
sudo cp 99-razer.rules /etc/udev/rules.d/

# Reload udev rules and re-trigger permissions on connected devices
sudo udevadm control --reload-rules
sudo udevadm trigger

# Optionally restart the systemd udev daemon
sudo systemctl restart systemd-udevd.service
```

Verify that your user has access to the device node:
```bash
ls -la /dev/hidraw*
```
You should now see read/write permissions (`crw-rw-rw-` or group `audio`/`uaccess`).

### 3. Install RZROPENAUD-IO

You can install the utility in editable mode or into a Python virtual environment:

#### Option A: Pip install in local virtual environment (Recommended)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### Option B: Run directly via executable script
```bash
./bin/rzropenaud-io --help
```

---

## Usage & CLI Reference

```
usage: rzropenaud-io [-h] [--mic-volume 0-100] [--sidetone 0-100] [--eq PRESET|BANDS]
                     [--mic-boost {on,off}] [--bass-boost 0-100] [--voice-clarity 0-100]
                     [-s] [--notify | --no-notify] [--direct] [-v]
```

### Examples

#### Query Device Information
```bash
rzropenaud-io --status
```
Outputs:
```text
==================================================
           RZROPENAUD-IO DEVICE STATUS            
==================================================
Device:           Razer BlackShark V2 (RZ04-0323)
USB ID:           0x1532:0x0529
Interface:        3
Firmware:         v1.01
Serial Number:    PM2038H0740001
==================================================
```

#### Adjust Hardware Sidetone (Mic Monitoring)
```bash
# Set sidetone volume to 50%
rzropenaud-io --sidetone 50

# Turn off sidetone
rzropenaud-io --sidetone 0
```

#### Set Microphone Volume
```bash
# Set mic volume to 85%
rzropenaud-io --mic-volume 85
```

#### Set 10-Band Equalizer Preset
```bash
# Apply gaming EQ preset
rzropenaud-io --eq game

# Apply flat EQ preset
rzropenaud-io --eq flat

# Apply custom 10-band gains in dB (31Hz, 63Hz, 125Hz, 250Hz, 500Hz, 1kHz, 2kHz, 4kHz, 8kHz, 16kHz)
rzropenaud-io --eq "3,4,2,0,0,1,3,4,3,2"
```

Available presets: `flat`, `game`, `movie`, `music`, `voice`, `esports`, `bass-boost`.

#### Toggle Microphone Boost
```bash
rzropenaud-io --mic-boost on
rzropenaud-io --mic-boost off
```

#### Quiet Mode (Suppress GNOME Notifications)
```bash
rzropenaud-io --sidetone 60 --no-notify
```

#### Debug & Verbose Protocol Inspection
```bash
rzropenaud-io --sidetone 50 --verbose
```

---

## Protocol Specification

### Razer 90-Byte Binary Report

RZROPENAUD-IO constructs packets following the OpenRazer standard 90-byte structure:

| Offset | Field | Type | Description |
|:---|:---|:---|:---|
| `0` | Status | `uint8` | `0x00` (Request / New Command) |
| `1` | Transaction ID | `uint8` | `0x1F` / `0xFF` |
| `2-3` | Remaining Packets | `uint16` (BE) | `0x0000` |
| `4` | Protocol Type | `uint8` | `0x00` |
| `5` | Data Size | `uint8` | Length of parameter payload |
| `6` | Command Class | `uint8` | `0x00` (System) or `0x08` (Audio) |
| `7` | Command ID | `uint8` | Sub-command identifier |
| `8-87` | Arguments | `uint8[80]` | Command payload data |
| `88` | Checksum (CRC) | `uint8` | XOR of bytes `2` through `87` inclusive |
| `89` | Reserved | `uint8` | `0x00` |

### Status Acknowledgement Codes

When reading the response packet:
- `0x01` (`RAZER_CMD_BUSY`): Retries with short backoff.
- `0x02` (`RAZER_CMD_SUCCESSFUL`): Acknowledged and executed by device.
- `0x03` (`RAZER_CMD_FAILURE`): Command rejected.
- `0x04` (`RAZER_CMD_TIMEOUT`): Device timed out.
- `0x05` (`RAZER_CMD_NOT_SUPPORTED`): Command not supported by current firmware.

---

## License

GPL-2.0-or-later. Compatible with OpenRazer and Linux kernel licensing.
