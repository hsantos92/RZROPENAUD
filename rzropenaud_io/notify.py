"""Desktop notification wrapper using notify-send for GNOME/Freedesktop environments.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional


class DesktopNotifier:
    """Sends native desktop notifications via notify-send."""

    def __init__(self, app_name: str = "RZROPENAUD-IO", default_icon: str = "audio-headset", enabled: bool = True):
        self.app_name = app_name
        self.default_icon = default_icon
        self.enabled = enabled
        self._notify_send_path: Optional[str] = shutil.which("notify-send")

    def is_available(self) -> bool:
        """Check if notify-send binary is present on the system."""
        return self._notify_send_path is not None

    def send(
        self,
        summary: str,
        body: str = "",
        icon: Optional[str] = None,
        urgency: str = "normal",
        timeout_ms: int = 3000,
    ) -> bool:
        """Send a desktop notification.

        Args:
            summary: Title or main alert text.
            body: Secondary descriptive text.
            icon: Freedesktop icon name.
            urgency: 'low', 'normal', or 'critical'.
            timeout_ms: Duration in milliseconds before disappearing.

        Returns:
            True if notification command exited with code 0, False otherwise.
        """
        if not self.enabled or not self.is_available():
            return False

        icon_name = icon or self.default_icon
        cmd = [
            self._notify_send_path,  # type: ignore[list-item]
            "-a", self.app_name,
            "-i", icon_name,
            "-u", urgency,
            "-t", str(timeout_ms),
            summary,
        ]
        if body:
            cmd.append(body)

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False

    def notify_sidetone(self, volume: int, enabled: bool = True) -> bool:
        """Notification for sidetone change."""
        if not enabled or volume == 0:
            return self.send("Razer BlackShark V2", "Sidetone disabled", icon="audio-volume-muted")
        return self.send("Razer BlackShark V2", f"Sidetone set to {volume}%", icon="audio-input-microphone")

    def notify_mic_volume(self, volume: int) -> bool:
        """Notification for microphone volume change."""
        return self.send("Razer BlackShark V2", f"Microphone Volume set to {volume}%", icon="audio-input-microphone")

    def notify_eq(self, preset_or_custom: str, details: str = "") -> bool:
        """Notification for equalizer preset or band change."""
        body = f"Equalizer profile: {preset_or_custom.capitalize()}"
        if details:
            body += f" ({details})"
        return self.send("Razer BlackShark V2", body, icon="audio-speakers")

    def notify_mic_boost(self, enabled: bool) -> bool:
        """Notification for microphone boost toggle."""
        state = "Enabled" if enabled else "Disabled"
        return self.send("Razer BlackShark V2", f"Mic Boost {state}", icon="audio-input-microphone")

    def notify_bass_boost(self, level: int) -> bool:
        """Notification for bass boost change."""
        return self.send("Razer BlackShark V2", f"Bass Boost set to {level}%", icon="audio-speakers")
