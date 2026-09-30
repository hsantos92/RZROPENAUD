"""Direct ALSA kernel mixer control for Razer USB Sound Card (1532:0529).

Interacts directly with /dev/snd/controlC* via libasound.so.2 to configure:
- Sidetone Playback Switch (Enable/Disable hardware sidetone)
- Sidetone Playback Volume (0..42 hardware scale)
- Mic Capture Volume (0..35 hardware scale)
- Mic Capture Switch (Mute/Unmute microphone)
- Auto Gain Control (Hardware mic boost)
"""

from __future__ import annotations

import ctypes
import logging
import re
import shutil
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger("rzropenaud_io.alsa")

try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    # Function prototypes
    _asound.snd_ctl_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_int]
    _asound.snd_ctl_open.restype = ctypes.c_int

    _asound.snd_ctl_close.argtypes = [ctypes.c_void_p]
    _asound.snd_ctl_close.restype = ctypes.c_int

    _asound.snd_ctl_elem_value_malloc.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    _asound.snd_ctl_elem_value_malloc.restype = ctypes.c_int

    _asound.snd_ctl_elem_value_free.argtypes = [ctypes.c_void_p]
    _asound.snd_ctl_elem_value_free.restype = None

    _asound.snd_ctl_elem_value_set_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _asound.snd_ctl_elem_value_set_interface.restype = None

    _asound.snd_ctl_elem_value_set_name.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    _asound.snd_ctl_elem_value_set_name.restype = None

    _asound.snd_ctl_elem_value_set_integer.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_long]
    _asound.snd_ctl_elem_value_set_integer.restype = None

    _asound.snd_ctl_elem_value_get_integer.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _asound.snd_ctl_elem_value_get_integer.restype = ctypes.c_long

    _asound.snd_ctl_elem_read.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _asound.snd_ctl_elem_read.restype = ctypes.c_int

    _asound.snd_ctl_elem_write.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _asound.snd_ctl_elem_write.restype = ctypes.c_int

    _asound.snd_ctl_elem_info_malloc.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    _asound.snd_ctl_elem_info_malloc.restype = ctypes.c_int

    _asound.snd_ctl_elem_info_free.argtypes = [ctypes.c_void_p]
    _asound.snd_ctl_elem_info_free.restype = None

    _asound.snd_ctl_elem_info_set_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _asound.snd_ctl_elem_info_set_interface.restype = None

    _asound.snd_ctl_elem_info_set_name.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    _asound.snd_ctl_elem_info_set_name.restype = None

    _asound.snd_ctl_elem_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _asound.snd_ctl_elem_info.restype = ctypes.c_int

    _asound.snd_ctl_elem_info_get_min.argtypes = [ctypes.c_void_p]
    _asound.snd_ctl_elem_info_get_min.restype = ctypes.c_long

    _asound.snd_ctl_elem_info_get_max.argtypes = [ctypes.c_void_p]
    _asound.snd_ctl_elem_info_get_max.restype = ctypes.c_long

    HAVE_ASOUND = True
except Exception as _e:
    logger.warning("Could not initialize libasound: %s", _e)
    HAVE_ASOUND = False


class AlsaMixerControl:
    """Manages ALSA controls for the Razer USB Sound Card."""

    def __init__(self, card_name: str = "hw:Card"):
        self.card_name = card_name

    def _open_ctl(self) -> Optional[ctypes.c_void_p]:
        if not HAVE_ASOUND:
            return None
        ctl = ctypes.c_void_p()
        ret = _asound.snd_ctl_open(ctypes.byref(ctl), self.card_name.encode("utf-8"), 0)
        if ret != 0:
            logger.debug("Failed to open snd_ctl for %s: %d", self.card_name, ret)
            return None
        return ctl

    def get_control(self, name: str) -> Optional[int]:
        """Read current integer/boolean value of an ALSA mixer control."""
        ctl = self._open_ctl()
        if not ctl:
            return None
        try:
            pval = ctypes.c_void_p()
            _asound.snd_ctl_elem_value_malloc(ctypes.byref(pval))
            _asound.snd_ctl_elem_value_set_interface(pval, 2)  # SND_CTL_ELEM_IFACE_MIXER
            _asound.snd_ctl_elem_value_set_name(pval, name.encode("utf-8"))
            ret = _asound.snd_ctl_elem_read(ctl, pval)
            val = None
            if ret == 0:
                val = int(_asound.snd_ctl_elem_value_get_integer(pval, 0))
            _asound.snd_ctl_elem_value_free(pval)
            return val
        finally:
            _asound.snd_ctl_close(ctl)

    def set_control(self, name: str, val: int) -> bool:
        """Write integer/boolean value to an ALSA mixer control."""
        ctl = self._open_ctl()
        if not ctl:
            return False
        try:
            pval = ctypes.c_void_p()
            _asound.snd_ctl_elem_value_malloc(ctypes.byref(pval))
            _asound.snd_ctl_elem_value_set_interface(pval, 2)
            _asound.snd_ctl_elem_value_set_name(pval, name.encode("utf-8"))
            _asound.snd_ctl_elem_value_set_integer(pval, 0, val)
            ret = _asound.snd_ctl_elem_write(ctl, pval)
            _asound.snd_ctl_elem_value_free(pval)
            return ret == 0
        finally:
            _asound.snd_ctl_close(ctl)

    # -------------------------------------------------------------------------
    # High-level controls mapped to percentage (0 - 100%)
    # -------------------------------------------------------------------------

    def set_sidetone(self, percent: int, enabled: Optional[bool] = None) -> bool:
        """Configure hardware sidetone on Razer USB Sound Card.

        Hardware control:
        - Sidetone Playback Switch: 0 = Muted, 1 = Unmuted
        - Sidetone Playback Volume: range 0..42
        """
        clamped = max(0, min(100, percent))
        is_on = (clamped > 0) if enabled is None else enabled

        # Scale 0..100% to hardware range 0..42
        hw_vol = int((clamped / 100.0) * 42)
        sw_ok = self.set_control("Sidetone Playback Switch", 1 if is_on else 0)
        vol_ok = self.set_control("Sidetone Playback Volume", hw_vol)
        return sw_ok and vol_ok

    def get_sidetone(self) -> Tuple[bool, int]:
        """Read hardware sidetone state and volume percentage."""
        sw = self.get_control("Sidetone Playback Switch") or 0
        vol = self.get_control("Sidetone Playback Volume") or 0
        percent = int((vol / 42.0) * 100)
        return bool(sw), percent

    def set_mic_volume(self, percent: int) -> bool:
        """Set hardware microphone gain and sync with PipeWire.

        Hardware control:
        - Mic Capture Switch: 0 = Muted, 1 = Unmuted
        - Mic Capture Volume: range 0..35
        """
        clamped = max(0, min(100, percent))
        is_muted = clamped == 0

        # Scale 0..100% to hardware range 0..35
        hw_vol = int((clamped / 100.0) * 35)
        self.set_control("Mic Capture Switch", 0 if is_muted else 1)
        self.set_control("Mic Capture Volume", hw_vol)

        # Also sync PipeWire source volume for Razer card if wpctl is present
        self._sync_pipewire_mic(clamped, is_muted)
        return True

    def get_mic_volume(self) -> int:
        """Read microphone volume percentage."""
        vol = self.get_control("Mic Capture Volume") or 0
        return int((vol / 35.0) * 100)

    def set_mic_boost(self, enabled: bool) -> bool:
        """Toggle hardware Auto Gain Control (Mic Boost)."""
        return self.set_control("Auto Gain Control", 1 if enabled else 0)

    def get_mic_boost(self) -> bool:
        """Read Auto Gain Control state."""
        return bool(self.get_control("Auto Gain Control"))

    def _sync_pipewire_mic(self, percent: int, is_muted: bool) -> None:
        """Sync volume with PipeWire/WirePlumber if available."""
        if not shutil.which("wpctl"):
            return

        try:
            # Locate the Razer input source node ID
            out = subprocess.check_output(["wpctl", "status"], text=True)
            in_sources = False
            node_id: Optional[str] = None
            for line in out.splitlines():
                if "Sources:" in line:
                    in_sources = True
                    continue
                if in_sources:
                    if any(marker in line for marker in ["Filters:", "Streams:", "Sinks:", "Devices:"]):
                        break
                    if "Razer USB Sound Card" in line:
                        m = re.search(r"(\d+)\.\s+Razer USB Sound Card", line)
                        if m:
                            node_id = m.group(1)
                            break

            if node_id:
                frac = round(percent / 100.0, 2)
                subprocess.run(["wpctl", "set-volume", node_id, str(frac)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["wpctl", "set-mute", node_id, "1" if is_muted else "0"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.debug("PipeWire sync error: %s", e)
