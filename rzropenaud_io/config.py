"""Configuration management and persistence for RZROPENAUD-IO.

Handles persistent settings such as user-configured physical headset serial numbers
stored under ~/.config/rzropenaud/config.json.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

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
