"""EasyEffects PipeWire integration bridge for RZROPENAUD-IO.

Routes equalizer presets and bass boost controls to EasyEffects on Arch Linux,
generating native DSP presets and dynamically loading them into the active
EasyEffects sink chain.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Dict, List, Optional

from rzropenaud_io.constants import EQ_PRESETS

logger = logging.getLogger("rzropenaud_io.easyeffects")

# 10 standard frequency bands matching Razer BlackShark V2 DSP
EQ_FREQUENCIES: List[float] = [
    31.0,
    63.0,
    125.0,
    250.0,
    500.0,
    1000.0,
    2000.0,
    4000.0,
    8000.0,
    16000.0,
]

PRESET_NAME_ACTIVE = "Razer-Active"


def get_easyeffects_output_dir() -> Path:
    """Return the output presets directory for EasyEffects (XDG data directory)."""
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        base = Path(data_home)
    else:
        base = Path.home() / ".local" / "share"
    return base / "easyeffects" / "output"


def build_preset_payload(
    band_gains_db: List[int],
    bass_boost_percent: int = 0,
) -> Dict[str, object]:
    """Construct an EasyEffects 8 JSON preset object.

    Args:
        band_gains_db: List of 10 dB gains (-12 to +12).
        bass_boost_percent: Bass boost level (0 to 100%).

    Returns:
        Dictionary structured for EasyEffects output preset.
    """
    # Build 10 equalizer bands for left & right channels
    left: Dict[str, object] = {}
    right: Dict[str, object] = {}

    for idx, freq in enumerate(EQ_FREQUENCIES):
        gain = float(band_gains_db[idx]) if idx < len(band_gains_db) else 0.0
        clamped_gain = max(-12.0, min(12.0, gain))
        band_config = {
            "frequency": freq,
            "gain": clamped_gain,
            "mode": "RLC (BT)",
            "mute": False,
            "q": 1.50476,
            "slope": "x1",
            "solo": False,
            "type": "Bell",
        }
        left[f"band{idx}"] = band_config
        right[f"band{idx}"] = dict(band_config)

    # Scale 0..100% bass boost to 0.0 .. 12.0 dB amount
    boost_clamped = max(0, min(100, bass_boost_percent))
    boost_amount_db = round((boost_clamped / 100.0) * 12.0, 1)
    boost_bypass = boost_clamped == 0

    return {
        "output": {
            "blocklist": [],
            "plugins_order": [
                "bass_enhancer",
                "equalizer",
            ],
            "bass_enhancer": {
                "amount": boost_amount_db,
                "blend": 0.0,
                "bypass": boost_bypass,
                "floor": 20.0,
                "floor-active": False,
                "harmonics": 8.5,
                "input-gain": 0.0,
                "output-gain": 0.0,
                "scope": 80.0,
            },
            "equalizer": {
                "mode": "IIR",
                "num-bands": 10,
                "input-gain": 0.0,
                "output-gain": 0.0,
                "split-channels": False,
                "left": left,
                "right": right,
            },
        }
    }


class EasyEffectsBridge:
    """Manages EasyEffects synchronization for Equalizer and Bass Boost."""

    def __init__(self) -> None:
        self.output_dir = get_easyeffects_output_dir()
        self.current_bands: List[int] = [0] * 10
        self.current_bass_boost: int = 0
        self._lock = threading.Lock()
        self._reload_timer: Optional[threading.Timer] = None
        self._is_reloading: bool = False
        self._pending_reload: bool = False

        # Generate standard Razer presets if EasyEffects is available
        if self.is_installed():
            self.install_all_presets()
            self.ensure_running()

    @staticmethod
    def is_installed() -> bool:
        """Check if the easyeffects binary is installed in PATH."""
        return shutil.which("easyeffects") is not None

    @staticmethod
    def is_running() -> bool:
        """Check if EasyEffects process or server socket is active."""
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if runtime_dir and (Path(runtime_dir) / "EasyEffectsServer").exists():
            return True
        try:
            out = subprocess.check_output(["pgrep", "-x", "easyeffects"], text=True)
            return bool(out.strip())
        except Exception:
            return False

    def ensure_running(self) -> None:
        """Start EasyEffects in background service mode if not already running."""
        if not self.is_running() and self.is_installed():
            try:
                res = subprocess.run(
                    ["systemctl", "--user", "start", "easyeffects.service"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if res.returncode != 0:
                    subprocess.Popen(
                        ["easyeffects", "--service-mode"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
            except Exception as e:
                logger.debug("Could not start easyeffects service: %s", e)

    def install_all_presets(self) -> None:
        """Write all Razer predefined presets and device autoload rules."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            for name, bands in EQ_PRESETS.items():
                preset_name = f"Razer-{name.replace('-', ' ').title().replace(' ', '-')}"
                payload = build_preset_payload(bands, bass_boost_percent=0)
                file_path = self.output_dir / f"{preset_name}.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)

            # Create clean passthrough preset (0 active DSP plugins)
            clean_payload = {"output": {"blocklist": [], "plugins_order": []}}
            with open(self.output_dir / "Clean-Passthrough.json", "w", encoding="utf-8") as f:
                json.dump(clean_payload, f, indent=2)

            # Configure device-specific autoloading so speakers/HDMI never inherit headset effects
            self._setup_autoloading()

            # Ensure EasyEffects tray icon is disabled to avoid GNOME Shell / Dash-to-Panel lockups
            self._disable_easyeffects_tray()
        except Exception as e:
            logger.debug("Failed to write EasyEffects presets: %s", e)

    def _disable_easyeffects_tray(self) -> None:
        """Disable EasyEffects tray icon to prevent GNOME Shell / Dash-to-Panel lockups."""
        try:
            cfg_file = Path.home() / ".config" / "easyeffects" / "db" / "easyeffectsrc"
            if not cfg_file.exists():
                return
            content = cfg_file.read_text(encoding="utf-8")
            if "showTrayIcon=false" in content:
                return

            if "[Window]" in content:
                content = content.replace("[Window]\n", "[Window]\nshowTrayIcon=false\n")
            else:
                content += "\n[Window]\nshowTrayIcon=false\n"
            cfg_file.write_text(content, encoding="utf-8")
            logger.debug("Configured EasyEffects showTrayIcon=false")
        except Exception as e:
            logger.debug("Failed to configure EasyEffects showTrayIcon: %s", e)

    def _setup_autoloading(self) -> None:
        """Configure EasyEffects autoloading rules so only Razer headset gets enhancements."""
        try:
            autoload_dir = self.output_dir.parent / "autoload" / "output"
            autoload_dir.mkdir(parents=True, exist_ok=True)

            # 1. Razer headset -> Razer-Active
            razer_rule = {
                "device": "alsa_output.usb-Razer_Razer_USB_Sound_Card_00000000-00.analog-stereo",
                "device-description": "Razer USB Sound Card Analog Stereo",
                "device-profile": "Speakers",
                "preset-name": PRESET_NAME_ACTIVE,
            }
            with open(
                autoload_dir / "alsa_output.usb-Razer_Razer_USB_Sound_Card_00000000-00.analog-stereo:Speakers.json",
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(razer_rule, f, indent=2)

            # 2. Built-in speakers / motherboard audio -> Clean-Passthrough
            for route in ["Speakers", "Line Out", "Headphones"]:
                rule = {
                    "device": "alsa_output.pci-0000_00_1f.3.analog-stereo",
                    "device-description": "Built-in Audio Analog Stereo",
                    "device-profile": route,
                    "preset-name": "Clean-Passthrough",
                }
                with open(
                    autoload_dir / f"alsa_output.pci-0000_00_1f.3.analog-stereo:{route}.json",
                    "w",
                    encoding="utf-8",
                ) as f:
                    json.dump(rule, f, indent=2)

            # 3. HDMI monitor audio -> Clean-Passthrough
            hdmi_rule = {
                "device": "alsa_output.pci-0000_01_00.1.hdmi-stereo",
                "device-description": "AD102 High Definition Audio Controller Digital Stereo (HDMI)",
                "device-profile": "Digital Stereo (HDMI)",
                "preset-name": "Clean-Passthrough",
            }
            with open(
                autoload_dir / "alsa_output.pci-0000_01_00.1.hdmi-stereo:Digital Stereo (HDMI).json",
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(hdmi_rule, f, indent=2)
        except Exception as e:
            logger.debug("Failed to setup autoload rules: %s", e)

    def apply_state(
        self,
        bands: Optional[List[int]] = None,
        bass_boost: Optional[int] = None,
        delay_seconds: float = 0.25,
    ) -> bool:
        """Update active preset and schedule a coalesced reload in EasyEffects.

        Debouncing ensures that dragging sliders or changing values rapidly
        does not hammer PipeWire or cause audio buffer starvation in players
        like Spotify.

        Args:
            bands: Optional new 10-band gains list.
            bass_boost: Optional new bass boost percentage (0-100%).
            delay_seconds: Delay before executing 'easyeffects -l' (default 250ms).

        Returns:
            True if preset was written and reload scheduled.
        """
        if not self.is_installed():
            return False

        with self._lock:
            if bands is not None:
                self.current_bands = list(bands)
            if bass_boost is not None:
                self.current_bass_boost = int(bass_boost)

            # Cancel any existing debounce timer so rapid changes coalesce
            if self._reload_timer is not None:
                self._reload_timer.cancel()
                self._reload_timer = None

            # Always write the updated preset JSON file immediately
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                payload = build_preset_payload(self.current_bands, self.current_bass_boost)
                active_file = self.output_dir / f"{PRESET_NAME_ACTIVE}.json"
                with open(active_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except Exception as e:
                logger.warning("Could not write EasyEffects active preset: %s", e)
                return False

            if delay_seconds <= 0:
                self._schedule_reload()
            else:
                self._reload_timer = threading.Timer(delay_seconds, self._schedule_reload)
                self._reload_timer.daemon = True
                self._reload_timer.start()

        return True

    def _schedule_reload(self) -> None:
        """Trigger or queue a serialized preset reload."""
        with self._lock:
            self._reload_timer = None
            if self._is_reloading:
                self._pending_reload = True
                return
            self._is_reloading = True

        threading.Thread(target=self._run_reload_worker, daemon=True).start()

    def _run_reload_worker(self) -> None:
        """Worker loop that ensures only one reload runs at a time."""
        while True:
            self.ensure_running()
            try:
                subprocess.run(
                    ["easyeffects", "-l", PRESET_NAME_ACTIVE],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3.0,
                )
            except Exception as e:
                logger.debug("easyeffects -l error: %s", e)

            with self._lock:
                if self._pending_reload:
                    self._pending_reload = False
                    continue
                else:
                    self._is_reloading = False
                    break
