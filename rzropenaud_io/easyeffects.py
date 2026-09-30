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

        # Generate standard Razer presets if EasyEffects is available
        if self.is_installed():
            self.install_all_presets()

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

    def install_all_presets(self) -> None:
        """Write all Razer predefined presets into EasyEffects preset directory."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            for name, bands in EQ_PRESETS.items():
                preset_name = f"Razer-{name.replace('-', ' ').title().replace(' ', '-')}"
                payload = build_preset_payload(bands, bass_boost_percent=0)
                file_path = self.output_dir / f"{preset_name}.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug("Failed to write EasyEffects presets: %s", e)

    def apply_state(
        self,
        bands: Optional[List[int]] = None,
        bass_boost: Optional[int] = None,
        async_load: bool = True,
    ) -> bool:
        """Update active preset and instruct EasyEffects to reload it.

        Args:
            bands: Optional new 10-band gains list.
            bass_boost: Optional new bass boost percentage (0-100%).
            async_load: If True, execute preset load in background thread.

        Returns:
            True if preset was written and load command dispatched.
        """
        if not self.is_installed():
            return False

        with self._lock:
            if bands is not None:
                self.current_bands = list(bands)
            if bass_boost is not None:
                self.current_bass_boost = int(bass_boost)

            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                payload = build_preset_payload(self.current_bands, self.current_bass_boost)
                active_file = self.output_dir / f"{PRESET_NAME_ACTIVE}.json"
                with open(active_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except Exception as e:
                logger.warning("Could not write EasyEffects active preset: %s", e)
                return False

        def _do_load() -> None:
            try:
                subprocess.run(
                    ["easyeffects", "-l", PRESET_NAME_ACTIVE],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                )
            except Exception as e:
                logger.debug("easyeffects -l error: %s", e)

        if async_load:
            threading.Thread(target=_do_load, daemon=True).start()
        else:
            _do_load()

        return True
