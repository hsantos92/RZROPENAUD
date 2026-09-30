"""Native GNOME graphical user interface for RZROPENAUD-IO using GTK4 and libadwaita.

Provides modern Adw-styled controls for Razer BlackShark V2 (Model RZ04-0323).
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from rzropenaud_io.constants import (
    BLACKSHARK_V2_PID,
    DEVICE_MODEL_NAME,
    EQ_PRESETS,
    RAZER_VENDOR_ID,
)
from rzropenaud_io.device import (
    BlackSharkV2,
    RazerDeviceError,
    RazerNotFoundError,
    RazerPermissionError,
)
from rzropenaud_io.notify import DesktopNotifier


class RzrOpenAudWindow(Adw.ApplicationWindow):
    """Main GNOME application window using libadwaita components."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.set_title("RZROPENAUD-IO")
        self.set_default_size(560, 720)

        # Hardware backend state
        self.device: Optional[BlackSharkV2] = None
        self.notifier = DesktopNotifier(app_name="RZROPENAUD-IO", enabled=True)
        self.device_info: Dict[str, Any] = {}

        # Debounce timers for sliders to avoid flooding the USB bus while dragging
        self._sidetone_timer: Optional[int] = None
        self._mic_vol_timer: Optional[int] = None
        self._bass_boost_timer: Optional[int] = None
        self._voice_clarity_timer: Optional[int] = None

        # Build UI layout
        self._build_ui()

        # Connect to hardware device
        self._connect_device()

    def _build_ui(self) -> None:
        """Construct the libadwaita layout with HeaderBar, Banner, and PreferencesPage."""
        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        # 1. HeaderBar
        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)

        # Refresh / Rescan button in HeaderBar
        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Refresh device status and re-scan USB bus")
        self.refresh_btn.connect("clicked", self._on_refresh_clicked)
        self.header_bar.pack_start(self.refresh_btn)

        # 2. In-window Banner for error & permission notices
        self.banner = Adw.Banner()
        self.banner.connect("button-clicked", self._on_banner_button_clicked)
        self.toolbar_view.add_top_bar(self.banner)

        # 3. Preferences Page (Scrollable content)
        self.pref_page = Adw.PreferencesPage()
        self.toolbar_view.set_content(self.pref_page)

        # --- Device Info Group ---
        self.info_group = Adw.PreferencesGroup(title="Device Status")
        self.pref_page.add(self.info_group)

        self.model_row = Adw.ActionRow(
            title="Model",
            subtitle=DEVICE_MODEL_NAME,
        )
        self.model_row.add_prefix(Gtk.Image.new_from_icon_name("audio-headset-symbolic"))
        self.info_group.add(self.model_row)

        self.status_badge = Gtk.Label(label="Disconnected")
        self.status_badge.add_css_class("dim-label")
        self.status_badge.set_valign(Gtk.Align.CENTER)
        self.model_row.add_suffix(self.status_badge)

        self.fw_row = Adw.ActionRow(
            title="Firmware and Serial",
            subtitle="Unknown",
        )
        self.fw_row.add_prefix(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
        self.info_group.add(self.fw_row)

        # --- Audio Controls Group ---
        self.audio_group = Adw.PreferencesGroup(
            title="Audio Controls",
            description="Core hardware DSP controls for microphone and monitoring",
        )
        self.pref_page.add(self.audio_group)

        # Sidetone Slider (0 - 100)
        self.sidetone_row = Adw.ActionRow(
            title="Sidetone (Mic Monitoring)",
            subtitle="Zero-latency hardware microphone playback into headset",
        )
        self.sidetone_row.add_prefix(Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic"))

        self.sidetone_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.sidetone_scale.set_value(50)
        self.sidetone_scale.set_draw_value(True)
        self.sidetone_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.sidetone_scale.set_size_request(200, -1)
        self.sidetone_scale.set_hexpand(True)
        self.sidetone_scale.connect("value-changed", self._on_sidetone_value_changed)
        self.sidetone_row.add_suffix(self.sidetone_scale)
        self.audio_group.add(self.sidetone_row)

        # Mic Volume Slider (0 - 100)
        self.mic_vol_row = Adw.ActionRow(
            title="Microphone Volume",
            subtitle="Hardware input gain for the headset microphone",
        )
        self.mic_vol_row.add_prefix(Gtk.Image.new_from_icon_name("audio-volume-high-symbolic"))

        self.mic_vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.mic_vol_scale.set_value(80)
        self.mic_vol_scale.set_draw_value(True)
        self.mic_vol_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.mic_vol_scale.set_size_request(200, -1)
        self.mic_vol_scale.set_hexpand(True)
        self.mic_vol_scale.connect("value-changed", self._on_mic_volume_value_changed)
        self.mic_vol_row.add_suffix(self.mic_vol_scale)
        self.audio_group.add(self.mic_vol_row)

        # Mic Boost Switch
        self.mic_boost_row = Adw.ActionRow(
            title="Microphone Boost",
            subtitle="Hardware pre-amplifier gain boost",
        )
        self.mic_boost_row.add_prefix(Gtk.Image.new_from_icon_name("media-flash-symbolic"))

        self.mic_boost_switch = Gtk.Switch()
        self.mic_boost_switch.set_valign(Gtk.Align.CENTER)
        self.mic_boost_switch.connect("state-set", self._on_mic_boost_state_set)
        self.mic_boost_row.add_suffix(self.mic_boost_switch)
        self.mic_boost_row.set_activatable_widget(self.mic_boost_switch)
        self.audio_group.add(self.mic_boost_row)

        # EQ Presets DropDown / ComboRow
        self.preset_keys: List[str] = list(EQ_PRESETS.keys())
        self.preset_display_names: List[str] = [k.replace("-", " ").title() for k in self.preset_keys]

        string_list = Gtk.StringList.new(self.preset_display_names)
        self.eq_combo_row = Adw.ComboRow(
            title="Equalizer Preset",
            subtitle="10-band curve (Microphone hardware DSP + EasyEffects playback)",
            model=string_list,
        )
        self.eq_combo_row.add_prefix(Gtk.Image.new_from_icon_name("audio-speakers-symbolic"))
        # Default to 'Flat' (index 0) or 'Game' (index 1)
        default_eq_idx = self.preset_keys.index("flat") if "flat" in self.preset_keys else 0
        self.eq_combo_row.set_selected(default_eq_idx)
        self.eq_combo_row.connect("notify::selected", self._on_eq_preset_selected)
        self.audio_group.add(self.eq_combo_row)

        # --- Audio Enhancements Group ---
        self.enhancements_group = Adw.PreferencesGroup(
            title="Audio Enhancements",
            description="Hardware and EasyEffects digital signal processing filters",
        )
        self.pref_page.add(self.enhancements_group)

        # Bass Boost Slider (0 - 100)
        self.bass_boost_row = Adw.ActionRow(
            title="Bass Boost",
            subtitle="Dynamic low-frequency bass enhancement (EasyEffects PipeWire bridge)",
        )
        self.bass_boost_row.add_prefix(Gtk.Image.new_from_icon_name("audio-volume-low-symbolic"))

        self.bass_boost_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.bass_boost_scale.set_value(0)
        self.bass_boost_scale.set_draw_value(True)
        self.bass_boost_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.bass_boost_scale.set_size_request(200, -1)
        self.bass_boost_scale.set_hexpand(True)
        self.bass_boost_scale.connect("value-changed", self._on_bass_boost_value_changed)
        self.bass_boost_row.add_suffix(self.bass_boost_scale)
        self.enhancements_group.add(self.bass_boost_row)

        # Voice Clarity Slider (0 - 100)
        self.voice_clarity_row = Adw.ActionRow(
            title="Voice Clarity",
            subtitle="Vocal frequency isolation and ambient noise suppression",
        )
        self.voice_clarity_row.add_prefix(Gtk.Image.new_from_icon_name("microphone-sensitivity-high-symbolic"))

        self.voice_clarity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.voice_clarity_scale.set_value(0)
        self.voice_clarity_scale.set_draw_value(True)
        self.voice_clarity_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.voice_clarity_scale.set_size_request(200, -1)
        self.voice_clarity_scale.set_hexpand(True)
        self.voice_clarity_scale.connect("value-changed", self._on_voice_clarity_value_changed)
        self.voice_clarity_row.add_suffix(self.voice_clarity_scale)
        self.enhancements_group.add(self.voice_clarity_row)

        # --- Preferences / Settings Group ---
        self.settings_group = Adw.PreferencesGroup(title="Preferences")
        self.pref_page.add(self.settings_group)

        self.notify_row = Adw.ActionRow(
            title="Desktop Notifications",
            subtitle="Show GNOME desktop alerts via notify-send on state changes",
        )
        self.notify_row.add_prefix(Gtk.Image.new_from_icon_name("user-available-symbolic"))

        self.notify_switch = Gtk.Switch()
        self.notify_switch.set_active(True)
        self.notify_switch.set_valign(Gtk.Align.CENTER)
        self.notify_switch.connect("state-set", self._on_notify_state_set)
        self.notify_row.add_suffix(self.notify_switch)
        self.notify_row.set_activatable_widget(self.notify_switch)
        self.settings_group.add(self.notify_row)

    # -------------------------------------------------------------------------
    # Hardware Connection & State Management
    # -------------------------------------------------------------------------

    def _connect_device(self) -> None:
        """Attempt to discover, claim interface, and initialize device."""
        # Close existing connection if any
        if self.device is not None:
            self.device.close()
            self.device = None

        try:
            dev = BlackSharkV2(verbose=False)
            dev.open()
            self.device = dev

            # Query hardware details
            self.device_info = dev.get_device_info()
            fw = self.device_info.get("firmware_version", "v1.00")
            sn = self.device_info.get("serial_number", "Connected")

            # Update UI indicators
            self.status_badge.set_label("Connected (0x1532:0x0529)")
            self.status_badge.remove_css_class("dim-label")
            self.status_badge.add_css_class("success")
            self.fw_row.set_subtitle(f"FW: {fw}  |  S/N: {sn}")

            # Dismiss error banner
            self.banner.set_revealed(False)
            self._set_controls_sensitive(True)

            # Sync initial hardware values into GUI sliders
            try:
                _on, st_vol = dev.get_sidetone()
                self.sidetone_scale.set_value(st_vol)
            except Exception:
                pass

            try:
                mv = dev.get_mic_volume()
                self.mic_vol_scale.set_value(mv)
            except Exception:
                pass

            try:
                mb = dev.get_mic_boost()
                self.mic_boost_switch.set_active(mb)
            except Exception:
                pass

        except RazerPermissionError:
            self.status_badge.set_label("Permission Denied")
            self.status_badge.remove_css_class("success")
            self.status_badge.add_css_class("error")

            self.banner.set_title(
                "Permission Denied: Run 'sudo cp 99-razer.rules /etc/udev/rules.d/' "
                "and reload udev rules."
            )
            self.banner.set_button_label("Retry")
            self.banner.set_revealed(True)
            self._set_controls_sensitive(False)

        except RazerNotFoundError:
            self.status_badge.set_label("Not Found")
            self.status_badge.remove_css_class("success")
            self.status_badge.add_css_class("dim-label")

            self.banner.set_title("Razer BlackShark V2 USB Sound Card not detected. Please check USB cable.")
            self.banner.set_button_label("Scan Again")
            self.banner.set_revealed(True)
            self._set_controls_sensitive(False)

        except RazerDeviceError as e:
            self.status_badge.set_label("Device Error")
            self.banner.set_title(f"Hardware communication error: {e}")
            self.banner.set_button_label("Retry")
            self.banner.set_revealed(True)
            self._set_controls_sensitive(False)

    def _set_controls_sensitive(self, sensitive: bool) -> None:
        """Enable or disable interactive widgets based on hardware connection."""
        self.sidetone_row.set_sensitive(sensitive)
        self.mic_vol_row.set_sensitive(sensitive)
        self.mic_boost_row.set_sensitive(sensitive)
        self.eq_combo_row.set_sensitive(sensitive)
        self.bass_boost_row.set_sensitive(sensitive)
        self.voice_clarity_row.set_sensitive(sensitive)

    def _on_banner_button_clicked(self, _banner: Adw.Banner) -> None:
        """Retry connection when banner action button is pressed."""
        self._connect_device()

    def _on_refresh_clicked(self, _btn: Gtk.Button) -> None:
        """Manual refresh from HeaderBar button."""
        self._connect_device()

    def _on_notify_state_set(self, _switch: Gtk.Switch, state: bool) -> bool:
        """Toggle desktop notification preference."""
        self.notifier.enabled = state
        return False

    # -------------------------------------------------------------------------
    # Audio Control Callbacks (with debouncing for smooth sliding)
    # -------------------------------------------------------------------------

    def _on_sidetone_value_changed(self, scale: Gtk.Scale) -> None:
        """Handle sidetone slider change with 70ms debounce."""
        val = int(scale.get_value())
        if self._sidetone_timer:
            GLib.source_remove(self._sidetone_timer)
        self._sidetone_timer = GLib.timeout_add(70, self._apply_sidetone, val)

    def _apply_sidetone(self, val: int) -> bool:
        self._sidetone_timer = None
        if self.device is not None:
            try:
                enabled = val > 0
                self.device.set_sidetone(val, enabled=enabled)
                self.notifier.notify_sidetone(val, enabled=enabled)
            except Exception as e:
                print(f"[GUI] Sidetone error: {e}", file=sys.stderr)
        return GLib.SOURCE_REMOVE

    def _on_mic_volume_value_changed(self, scale: Gtk.Scale) -> None:
        """Handle microphone volume slider change with 70ms debounce."""
        val = int(scale.get_value())
        if self._mic_vol_timer:
            GLib.source_remove(self._mic_vol_timer)
        self._mic_vol_timer = GLib.timeout_add(70, self._apply_mic_volume, val)

    def _apply_mic_volume(self, val: int) -> bool:
        self._mic_vol_timer = None
        if self.device is not None:
            try:
                self.device.set_mic_volume(val)
                self.notifier.notify_mic_volume(val)
            except Exception as e:
                print(f"[GUI] Mic volume error: {e}", file=sys.stderr)
        return GLib.SOURCE_REMOVE

    def _on_mic_boost_state_set(self, _switch: Gtk.Switch, state: bool) -> bool:
        """Handle microphone boost toggle."""
        if self.device is not None:
            try:
                self.device.set_mic_boost(state, use_direct=True)
                self.notifier.notify_mic_boost(state)
            except Exception as e:
                print(f"[GUI] Mic boost error: {e}", file=sys.stderr)
        return False  # Let default GTK switch handler animate

    def _on_eq_preset_selected(self, row: Adw.ComboRow, _param: Any) -> None:
        """Handle equalizer preset selection."""
        idx = row.get_selected()
        if 0 <= idx < len(self.preset_keys):
            preset_name = self.preset_keys[idx]
            if self.device is not None:
                try:
                    name, bands = self.device.set_equalizer(preset_name, use_direct=True)
                    self.notifier.notify_eq(name, f"{bands[0]:+d}dB to {bands[-1]:+d}dB")
                except Exception as e:
                    print(f"[GUI] EQ error: {e}", file=sys.stderr)

    def _on_bass_boost_value_changed(self, scale: Gtk.Scale) -> None:
        """Handle bass boost slider change with 70ms debounce."""
        val = int(scale.get_value())
        if self._bass_boost_timer:
            GLib.source_remove(self._bass_boost_timer)
        self._bass_boost_timer = GLib.timeout_add(70, self._apply_bass_boost, val)

    def _apply_bass_boost(self, val: int) -> bool:
        self._bass_boost_timer = None
        if self.device is not None:
            try:
                self.device.set_bass_boost(val)
                self.notifier.notify_bass_boost(val)
            except Exception as e:
                print(f"[GUI] Bass boost error: {e}", file=sys.stderr)
        return GLib.SOURCE_REMOVE

    def _on_voice_clarity_value_changed(self, scale: Gtk.Scale) -> None:
        """Handle voice clarity slider change with 70ms debounce."""
        val = int(scale.get_value())
        if self._voice_clarity_timer:
            GLib.source_remove(self._voice_clarity_timer)
        self._voice_clarity_timer = GLib.timeout_add(70, self._apply_voice_clarity, val)

    def _apply_voice_clarity(self, val: int) -> bool:
        self._voice_clarity_timer = None
        if self.device is not None:
            try:
                self.device.set_voice_clarity(val)
            except Exception as e:
                print(f"[GUI] Voice clarity error: {e}", file=sys.stderr)
        return GLib.SOURCE_REMOVE

    def do_destroy(self) -> None:
        """Clean up hardware connection on window close."""
        if self.device is not None:
            self.device.close()
            self.device = None
        super().do_destroy()


class RzrOpenAudApp(Adw.Application):
    """Main Adw.Application subclass for RZROPENAUD-IO."""

    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.rzropenaud.io",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        """Called when application is activated."""
        win = self.props.active_window
        if not win:
            win = RzrOpenAudWindow(application=self)
        win.present()


def main(argv: Optional[List[str]] = None) -> int:
    """GUI Application Entrypoint."""
    app = RzrOpenAudApp()
    return app.run(argv or sys.argv)


if __name__ == "__main__":
    sys.exit(main())
