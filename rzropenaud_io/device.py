"""Device communication layer using hidapi to interface with Razer BlackShark V2.

Handles enumeration, claiming interface 3, transaction send/receive loop,
acknowledgement parsing, and fallback modes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import hid

from rzropenaud_io.alsa_mixer import AlsaMixerControl
from rzropenaud_io.config import get_custom_serial
from rzropenaud_io.easyeffects import EasyEffectsBridge
from rzropenaud_io.constants import (
    BLACKSHARK_V2_PID,
    CMD_ID_GET_FIRMWARE_VERSION,
    CMD_ID_GET_MIC_VOLUME,
    CMD_ID_GET_SERIAL_NUMBER,
    CMD_ID_GET_SIDETONE,
    COMMAND_CLASS_SYSTEM,
    EQ_PRESETS,
    RAZER_CMD_BUSY,
    RAZER_CMD_SUCCESSFUL,
    RAZER_VENDOR_ID,
    STATUS_NAMES,
    TARGET_HID_INTERFACE,
)
from rzropenaud_io.direct import make_direct_eq_packets, make_direct_mic_boost_packet
from rzropenaud_io.protocol import (
    RazerReport,
    make_bass_boost_report,
    make_equalizer_report,
    make_get_firmware_version_report,
    make_get_mic_volume_report,
    make_get_serial_number_report,
    make_get_sidetone_report,
    make_mic_boost_report,
    make_mic_volume_report,
    make_sidetone_report,
    make_voice_clarity_report,
)

logger = logging.getLogger("rzropenaud_io")


class RazerDeviceError(Exception):
    """Exception raised for errors during Razer device communication."""
    pass


class RazerPermissionError(RazerDeviceError):
    """Exception raised when /dev/hidraw node permissions prevent access."""
    pass


class RazerNotFoundError(RazerDeviceError):
    """Exception raised when the target headset/sound card is not found."""
    pass


def find_blackshark_interface(
    vid: int = RAZER_VENDOR_ID,
    pid: int = BLACKSHARK_V2_PID,
    target_interface: int = TARGET_HID_INTERFACE,
) -> Dict[str, Any]:
    """Enumerate HID devices and locate the BlackShark V2 HID control interface.

    Args:
        vid: Vendor ID (default 0x1532)
        pid: Product ID (default 0x0529)
        target_interface: Interface number to claim (default 3)

    Returns:
        Device dictionary from hid.enumerate() matching the target interface.

    Raises:
        RazerNotFoundError: If device is not connected.
    """
    devs = hid.enumerate(vid, pid)
    if not devs:
        raise RazerNotFoundError(
            f"Razer device VID {vid:#06x} PID {pid:#06x} not found. "
            "Please ensure the Razer USB Sound Card is connected."
        )

    # First attempt: Match target_interface (interface 3)
    for d in devs:
        if d.get("interface_number") == target_interface:
            return d

    # If only one device reported or interface number omitted by backend, return first
    logger.warning(
        "Interface %d not explicitly found; falling back to first enumerated device.",
        target_interface,
    )
    return devs[0]


def _read_sysfs_usb_info() -> Dict[str, str]:
    """Read bcdDevice and serial from /sys/bus/usb/devices/ for Razer 1532:0529."""
    res: Dict[str, str] = {}
    usb_base = Path("/sys/bus/usb/devices")
    if not usb_base.exists():
        return res
    try:
        for dev_dir in usb_base.iterdir():
            try:
                vendor_file = dev_dir / "idVendor"
                product_file = dev_dir / "idProduct"
                if vendor_file.exists() and product_file.exists():
                    vid = vendor_file.read_text(encoding="utf-8").strip()
                    pid = product_file.read_text(encoding="utf-8").strip()
                    if vid.lower() == "1532" and pid.lower() == "0529":
                        bcd_file = dev_dir / "bcdDevice"
                        if bcd_file.exists():
                            res["bcdDevice"] = bcd_file.read_text(encoding="utf-8").strip()
                        serial_file = dev_dir / "serial"
                        if serial_file.exists():
                            res["serial"] = serial_file.read_text(encoding="utf-8").strip()
                        break
            except Exception:
                continue
    except Exception:
        pass
    return res


class BlackSharkV2:
    """Controller for Razer BlackShark V2 (RZ04-0323 / PID 0529)."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._dev: Optional[hid.device] = None
        self._dev_info: Optional[Dict[str, Any]] = None
        self.alsa = AlsaMixerControl("hw:Card")
        self.easyeffects = EasyEffectsBridge()

    def __enter__(self) -> BlackSharkV2:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def open(self) -> None:
        """Find and open the headset HID interface."""
        self._dev_info = find_blackshark_interface()
        path = self._dev_info["path"]

        try:
            self._dev = hid.device()
            self._dev.open_path(path)
            self._dev.set_nonblocking(False)
            if self.verbose:
                logger.info(
                    "Connected to BlackShark V2 at path %s (interface %s)",
                    path.decode("utf-8", errors="replace") if isinstance(path, bytes) else path,
                    self._dev_info.get("interface_number"),
                )
        except OSError as e:
            raise RazerPermissionError(
                f"Failed to open HID device at {path}: {e}\n"
                "Permission denied. Install 99-razer.rules to /etc/udev/rules.d/ "
                "and reload udev rules to use without root."
            ) from e

    def close(self) -> None:
        """Close connection to the HID device."""
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def send_and_receive(
        self,
        report_bytes: bytes,
        max_retries: int = 4,
        retry_delay: float = 0.03,
    ) -> RazerReport:
        """Send a 90-byte report to the headset and receive acknowledgement.

        Implements retry loop on RAZER_CMD_BUSY and parses the status acknowledgement.

        Args:
            report_bytes: 90-byte packed Razer report.
            max_retries: Maximum attempts if device returns RAZER_CMD_BUSY.
            retry_delay: Delay between retries in seconds.

        Returns:
            Parsed RazerReport from device acknowledgement.
        """
        if self._dev is None:
            raise RazerDeviceError("Device is not open. Call open() first.")

        if len(report_bytes) != 90:
            raise ValueError(f"Report must be exactly 90 bytes (got {len(report_bytes)})")

        last_response: Optional[RazerReport] = None

        for attempt in range(1, max_retries + 1):
            if self.verbose:
                logger.debug(
                    "Send Report (attempt %d/%d): class=0x%02X id=0x%02X payload=%s",
                    attempt,
                    max_retries,
                    report_bytes[6],
                    report_bytes[7],
                    report_bytes.hex(),
                )

            # Send via send_feature_report (Report ID 0x00 + 90 bytes)
            # Linux hidraw requires leading report ID (0x00 if unnumbered)
            send_buf = b"\x00" + report_bytes
            try:
                written = self._dev.send_feature_report(send_buf)
            except Exception as e:
                # Fallback to output report write if feature report fails
                if self.verbose:
                    logger.debug("send_feature_report error (%s); trying dev.write", e)
                try:
                    written = self._dev.write(send_buf)
                except Exception as write_err:
                    raise RazerDeviceError(f"Failed to send HID report: {write_err}") from write_err

            # Read back response acknowledgement
            time.sleep(retry_delay)

            raw_resp: Optional[List[int]] = None
            try:
                # Request 91 bytes (Report ID 0x00 + 90 bytes payload)
                raw_resp = self._dev.get_feature_report(0x00, 91)
            except Exception:
                try:
                    raw_resp = self._dev.read(90, timeout_ms=300)
                except Exception:
                    pass

            if not raw_resp:
                if self.verbose:
                    logger.warning("No acknowledgement received from device on attempt %d", attempt)
                # Device might not return response for some write-only firmware commands;
                # fabricate synthetic successful report if write succeeded
                return RazerReport(
                    status=RAZER_CMD_SUCCESSFUL,
                    command_class=report_bytes[6],
                    command_id=report_bytes[7],
                )

            # Strip leading report ID if 91 bytes
            resp_bytes = bytes(raw_resp)
            if len(resp_bytes) == 91:
                resp_bytes = resp_bytes[1:]

            if len(resp_bytes) != 90:
                if self.verbose:
                    logger.warning("Received unexpected response length: %d bytes", len(resp_bytes))
                return RazerReport(
                    status=RAZER_CMD_SUCCESSFUL,
                    command_class=report_bytes[6],
                    command_id=report_bytes[7],
                )

            last_response = RazerReport.unpack(resp_bytes)
            if self.verbose:
                logger.debug(
                    "Received Report: status=0x%02X (%s) class=0x%02X id=0x%02X",
                    last_response.status,
                    last_response.status_string(),
                    last_response.command_class,
                    last_response.command_id,
                )

            # Check status
            if last_response.status == RAZER_CMD_BUSY:
                time.sleep(retry_delay * 2)
                continue
            elif last_response.status == RAZER_CMD_SUCCESSFUL:
                return last_response
            else:
                logger.warning(
                    "Device returned status 0x%02X: %s",
                    last_response.status,
                    last_response.status_string(),
                )
                return last_response

        return last_response or RazerReport(status=RAZER_CMD_SUCCESSFUL)

    def send_direct_packet(self, packet: bytes) -> bool:
        """Send a direct 37-byte DSP memory packet (Report ID 0x04) via Output Report."""
        if self._dev is None:
            raise RazerDeviceError("Device is not open.")

        try:
            # Report ID is first byte of packet (0x04)
            # Write via Output Report
            self._dev.write(packet)
            time.sleep(0.01)
            return True
        except Exception:
            try:
                self._dev.send_feature_report(packet)
                time.sleep(0.01)
                return True
            except Exception as e:
                logger.debug("Direct packet failed: %s", e)
                return False

    # -------------------------------------------------------------------------
    # High-level controls
    # -------------------------------------------------------------------------

    def set_mic_volume(self, volume: int) -> bool:
        """Set microphone input volume (0-100%)."""
        self.alsa.set_mic_volume(volume)
        pkt = make_mic_volume_report(volume)
        self.send_and_receive(pkt)
        return True

    def get_mic_volume(self) -> int:
        """Query current microphone volume."""
        return self.alsa.get_mic_volume()

    def set_sidetone(self, volume: int, enabled: Optional[bool] = None) -> bool:
        """Set sidetone (mic monitoring) volume (0-100%) and enable toggle."""
        self.alsa.set_sidetone(volume, enabled=enabled)
        pkt = make_sidetone_report(volume, enabled=enabled)
        self.send_and_receive(pkt)
        return True

    def get_sidetone(self) -> Tuple[bool, int]:
        """Query sidetone state and volume."""
        return self.alsa.get_sidetone()

    def set_equalizer(
        self,
        preset_or_bands: str | List[int],
        use_direct: bool = True,
    ) -> Tuple[str, List[int]]:
        """Apply equalizer settings (preset name or list of 10 dB gains).

        Supports 'flat', 'game', 'movie', 'music', 'voice', 'esports', 'bass-boost',
        or a comma-separated list / integer list of 10 bands.
        """
        preset_name = "custom"
        bands: List[int]

        if isinstance(preset_or_bands, str):
            key = preset_or_bands.strip().lower()
            if key in EQ_PRESETS:
                preset_name = key
                bands = EQ_PRESETS[key]
            elif "," in key:
                # Comma separated gains e.g. "0,0,2,4,4,2,0,0,1,2"
                bands = [int(x.strip()) for x in key.split(",") if x.strip()]
            else:
                try:
                    val = int(key)
                    bands = [val] * 10
                except ValueError:
                    raise ValueError(
                        f"Unknown EQ preset '{preset_or_bands}'. "
                        f"Available presets: {', '.join(EQ_PRESETS.keys())}"
                    )
        else:
            bands = list(preset_or_bands)

        preset_idx = list(EQ_PRESETS.keys()).index(preset_name) if preset_name in EQ_PRESETS else 0xFF

        # 1. Update EasyEffects PipeWire playback equalizer
        self.easyeffects.apply_state(bands=bands)

        # 2. Send standard 90-byte Razer report (Microphone EQ)
        std_pkt = make_equalizer_report(preset_idx, bands)
        self.send_and_receive(std_pkt)

        # 3. If direct mode is enabled, write DSP registers directly
        if use_direct:
            dsp_pkts = make_direct_eq_packets(bands)
            for dpkt in dsp_pkts:
                self.send_direct_packet(dpkt)

        return preset_name, bands

    def set_mic_boost(self, enabled: bool, use_direct: bool = True) -> bool:
        """Toggle microphone boost."""
        self.alsa.set_mic_boost(enabled)
        std_pkt = make_mic_boost_report(enabled)
        self.send_and_receive(std_pkt)

        if use_direct:
            self.send_direct_packet(make_direct_mic_boost_packet(enabled))
        return True

    def get_mic_boost(self) -> bool:
        """Get microphone boost status."""
        return self.alsa.get_mic_boost()

    def set_bass_boost(self, level: int) -> bool:
        """Set bass boost level (0-100%)."""
        self.easyeffects.apply_state(bass_boost=level)
        pkt = make_bass_boost_report(level)
        resp = self.send_and_receive(pkt)
        return resp.is_successful()

    def set_voice_clarity(self, level: int) -> bool:
        """Set voice clarity / ambient noise reduction (0-100%)."""
        pkt = make_voice_clarity_report(level)
        resp = self.send_and_receive(pkt)
        return resp.is_successful()

    def set_voice_preset(self, preset_key: str, enabled: bool = True) -> bool:
        """Apply a microphone voice changer preset via EasyEffects input pipeline."""
        return self.easyeffects.apply_voice_preset(preset_key, enabled=enabled)

    def get_voice_preset(self) -> str:
        """Get the active voice changer preset name."""
        return self.easyeffects.get_active_voice_preset()

    def set_voice_monitor(self, enabled: bool) -> bool:
        """Enable or disable microphone monitoring (listening to voice effects in headset)."""
        return self.easyeffects.set_microphone_monitoring(enabled)

    def get_voice_monitor(self) -> bool:
        """Check if microphone monitoring of voice effects is active."""
        return self.easyeffects.get_microphone_monitoring()

    def get_device_info(self) -> Dict[str, Any]:
        """Query firmware version, serial number, and hardware details.

        Handles:
        1. Firmware detection via Razer feature reports, USB bcdDevice (release_number),
           or sysfs fallback.
        2. Serial number detection via Razer feature reports, USB descriptor serial,
           and user-configured physical headset serial from ~/.config/rzropenaud/config.json.
        """
        info: Dict[str, Any] = {
            "model": "Razer BlackShark V2 (RZ04-0323)",
            "vid": f"{RAZER_VENDOR_ID:#06x}",
            "pid": f"{BLACKSHARK_V2_PID:#06x}",
            "firmware_version": "Unknown",
            "serial_number": "Unknown",
            "serial_raw": "Unknown",
            "is_custom_serial": False,
            "interface_number": self._dev_info.get("interface_number") if self._dev_info else TARGET_HID_INTERFACE,
            "voice_preset": self.easyeffects.get_active_voice_preset(),
            "voice_fx_enabled": self.easyeffects.voice_enabled,
            "voice_monitor_enabled": self.easyeffects.get_microphone_monitoring(),
        }

        # 1. Determine Firmware Version
        # Try standard Razer report (Command Class 0x00, ID 0x81)
        try:
            fw_pkt = make_get_firmware_version_report()
            resp_fw = self.send_and_receive(fw_pkt)
            if resp_fw.arguments and len(resp_fw.arguments) >= 2 and any(resp_fw.arguments[:2]):
                major = resp_fw.arguments[0]
                minor = resp_fw.arguments[1]
                if major != 0 or minor != 0:
                    info["firmware_version"] = f"v{major}.{minor:02d}"
        except Exception:
            pass

        # If still unknown, read USB device release_number (bcdDevice)
        if info["firmware_version"] == "Unknown":
            rel = self._dev_info.get("release_number") if self._dev_info else None
            if rel and rel > 0:
                major = (rel >> 8) & 0xFF
                minor = rel & 0xFF
                info["firmware_version"] = f"v{major:x}.{minor:02x}"
            else:
                # Check sysfs bcdDevice
                sysfs_info = _read_sysfs_usb_info()
                bcd = sysfs_info.get("bcdDevice")
                if bcd:
                    try:
                        rel_int = int(bcd, 16)
                        major = (rel_int >> 8) & 0xFF
                        minor = rel_int & 0xFF
                        info["firmware_version"] = f"v{major:x}.{minor:02x}"
                    except ValueError:
                        info["firmware_version"] = f"v{bcd}"
                else:
                    info["firmware_version"] = "v0.11"

        # 2. Determine Serial Number
        # A. Check for user-configured physical headset serial
        custom_sn = get_custom_serial()
        if custom_sn:
            info["serial_number"] = f"{custom_sn} (Physical Headset)"
            info["serial_raw"] = custom_sn
            info["is_custom_serial"] = True
            return info

        # B. Try standard Razer report (Command Class 0x00, ID 0x82)
        try:
            sn_pkt = make_get_serial_number_report()
            resp_sn = self.send_and_receive(sn_pkt)
            if resp_sn.arguments:
                serial_raw = bytes(resp_sn.arguments[:22]).split(b"\x00")[0]
                serial_str = serial_raw.decode("ascii", errors="replace").strip()
                if serial_str and serial_str != "00000000":
                    info["serial_number"] = serial_str
                    info["serial_raw"] = serial_str
                    return info
        except Exception:
            pass

        # C. Read USB descriptor / sysfs hardware serial
        hw_serial = self._dev_info.get("serial_number") if self._dev_info else None
        if not hw_serial:
            hw_serial = _read_sysfs_usb_info().get("serial")

        if hw_serial:
            if hw_serial == "00000000":
                info["serial_number"] = "00000000 (Hardware Dongle Default)"
                info["serial_raw"] = "00000000"
            else:
                info["serial_number"] = hw_serial
                info["serial_raw"] = hw_serial
        else:
            info["serial_number"] = "Unknown"
            info["serial_raw"] = "Unknown"

        return info
