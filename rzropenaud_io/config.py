"""Configuration management and persistence for RZROPENAUD-IO.

Handles persistent settings such as user-configured physical headset serial numbers
stored under ~/.config/rzropenaud/config.json.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "rzropenaud"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> Dict[str, Any]:
    """Load configuration from ~/.config/rzropenaud/config.json.

    Returns:
        Dictionary containing configuration keys, or empty dict if not found/invalid.
    """
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception as e:
        logger.warning("Failed to read config file %s: %s", CONFIG_FILE, e)
        return {}


def save_config(data: Dict[str, Any]) -> None:
    """Save configuration dictionary to ~/.config/rzropenaud/config.json atomically.

    Args:
        data: Dictionary of configuration keys to persist.
    """
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Write to temporary file first, then atomically replace
        tmp_file = CONFIG_DIR / f"config.json.tmp.{os.getpid()}"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        tmp_file.replace(CONFIG_FILE)
    except Exception as e:
        logger.error("Failed to save config to %s: %s", CONFIG_FILE, e)


def get_custom_serial() -> Optional[str]:
    """Retrieve user-configured physical headset serial number if set.

    Returns:
        Configured serial number string or None.
    """
    cfg = load_config()
    sn = cfg.get("serial_number")
    if sn and isinstance(sn, str):
        sn = sn.strip()
        if sn and sn != "00000000":
            return sn
    return None


def set_custom_serial(serial: Optional[str]) -> None:
    """Set or update user-configured physical headset serial number.

    Args:
        serial: Serial number string (e.g. from under left ear cushion),
                or None/empty/'default' to clear.
    """
    cfg = load_config()
    if serial is None or not serial.strip() or serial.strip().lower() == "default":
        cfg.pop("serial_number", None)
    else:
        cfg["serial_number"] = serial.strip()
    save_config(cfg)


def clear_custom_serial() -> None:
    """Remove user-configured serial number from config, restoring hardware default."""
    set_custom_serial(None)


def get_voice_fx_enabled() -> bool:
    """Retrieve whether the microphone voice changer is currently active.

    Returns:
        True if voice changer is enabled in config, False otherwise.
    """
    cfg = load_config()
    return bool(cfg.get("voice_fx_enabled", False))


def set_voice_fx_enabled(enabled: bool) -> None:
    """Set whether the microphone voice changer is enabled.

    Args:
        enabled: Boolean state to persist.
    """
    cfg = load_config()
    cfg["voice_fx_enabled"] = bool(enabled)
    save_config(cfg)


def get_voice_preset() -> str:
    """Retrieve the last selected voice changer preset key.

    Returns:
        Preset identifier (e.g. 'deep', 'robotic', 'female', etc.), default 'deep'.
    """
    cfg = load_config()
    preset = cfg.get("voice_preset", "deep")
    if isinstance(preset, str) and preset.strip():
        return preset.strip().lower()
    return "deep"


def set_voice_preset(preset: str) -> None:
    """Set the last selected voice changer preset key.

    Args:
        preset: Preset identifier string.
    """
    cfg = load_config()
    cfg["voice_preset"] = str(preset).strip().lower()
    save_config(cfg)


def get_voice_monitor_enabled() -> bool:
    """Retrieve whether Voice FX sidetone / monitoring is active.

    Returns:
        True if voice sidetone is enabled, False otherwise.
    """
    cfg = load_config()
    return bool(cfg.get("voice_monitor_enabled", False))


def set_voice_monitor_enabled(enabled: bool) -> None:
    """Set whether Voice FX sidetone / monitoring is enabled.

    Args:
        enabled: Boolean state to persist.
    """
    cfg = load_config()
    cfg["voice_monitor_enabled"] = bool(enabled)
    save_config(cfg)


def get_notifications_enabled() -> bool:
    """Retrieve whether desktop notifications on state changes are enabled.

    Returns:
        True if enabled in config, False otherwise (defaults to False).
    """
    cfg = load_config()
    return bool(cfg.get("notifications_enabled", False))


def set_notifications_enabled(enabled: bool) -> None:
    """Set whether desktop notifications on state changes are enabled.

    Args:
        enabled: Boolean state to persist.
    """
    cfg = load_config()
    cfg["notifications_enabled"] = bool(enabled)
    save_config(cfg)


def get_window_geometry() -> Tuple[int, int, bool]:
    """Retrieve saved window size (width, height) and maximized state.

    Returns:
        Tuple of (width, height, is_maximized). Defaults to (560, 720, False).
    """
    cfg = load_config()
    win_cfg = cfg.get("window", {})
    if isinstance(win_cfg, dict):
        width = int(win_cfg.get("width", 560))
        height = int(win_cfg.get("height", 720))
        is_maximized = bool(win_cfg.get("maximized", False))
        width = max(400, min(3840, width))
        height = max(400, min(2160, height))
        return width, height, is_maximized
    return 560, 720, False


def set_window_geometry(width: int, height: int, is_maximized: bool = False) -> None:
    """Save window size and maximized state to configuration.

    Args:
        width: Window width in pixels.
        height: Window height in pixels.
        is_maximized: Whether window was maximized.
    """
    cfg = load_config()
    cfg["window"] = {
        "width": int(width),
        "height": int(height),
        "maximized": bool(is_maximized),
    }
    save_config(cfg)

