"""Native GNOME graphical user interface for RZROPENAUD-IO using GTK4 and libadwaita.

Provides modern Adw-styled controls for Razer BlackShark V2 (Model RZ04-0323).
"""

from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from rzropenaud_io.config import (
    clear_custom_serial,
    get_custom_serial,
    get_notifications_enabled,
    get_voice_fx_enabled,
    get_voice_monitor_enabled,
    get_voice_preset,
    get_window_geometry,
    set_custom_serial,
    set_notifications_enabled,
    set_voice_fx_enabled,
    set_voice_monitor_enabled,
    set_voice_preset,
    set_window_geometry,
)
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
    is_blackshark_connected,
)
from rzropenaud_io.easyeffects import VOICE_PRESETS, EasyEffectsBridge
from rzropenaud_io.notify import DesktopNotifier


class RzrOpenAudWindow(Adw.ApplicationWindow):
    """Main GNOME application window using libadwaita components."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.set_title("RZROPENAUD-IO")

        # Window geometry persistence
        self._last_saved_w, self._last_saved_h, is_maximized = get_window_geometry()
        self.set_default_size(self._last_saved_w, self._last_saved_h)
        if is_maximized:
            self.maximize()

        self.connect("close-request", self._on_close_request)
        self.connect("destroy", self._on_destroy)

        # Hardware backend state
        self.device: Optional[BlackSharkV2] = None
        self.notifier = DesktopNotifier(app_name="RZROPENAUD-IO", enabled=get_notifications_enabled())
        self.device_info: Dict[str, Any] = {}
        self._device_was_connected: bool = False
        self._permission_denied: bool = False
        self._poll_timer_id: Optional[int] = None

        # Voice changer DSP state
        self.easyeffects = EasyEffectsBridge()
        self.voice_enabled: bool = get_voice_fx_enabled()
        self.voice_monitor_enabled: bool = get_voice_monitor_enabled()
        self.current_voice_preset: str = get_voice_preset()
        self.voice_buttons: Dict[str, Gtk.ToggleButton] = {}
        self._updating_voice_ui: bool = False

        # Debounce timers for sliders to avoid flooding the USB bus while dragging
        self._sidetone_timer: Optional[int] = None
        self._mic_vol_timer: Optional[int] = None
        self._bass_boost_timer: Optional[int] = None
        self._voice_clarity_timer: Optional[int] = None

        # Build UI layout
        self._build_ui()

        # Connect to hardware device
        self._connect_device()

        # Background polling timer to monitor device connection & window geometry
        self._poll_timer_id = GLib.timeout_add_seconds(1, self._poll_device_connection)

    def _build_ui(self) -> None:
        """Construct the libadwaita layout with HeaderBar, Banner, and PreferencesPage."""
        # Load custom CSS for Voice Changer cards and push buttons
        css = """
        .voice-card-btn {
            border-radius: 12px;
            padding: 8px 6px;
            transition: all 180ms ease-in-out;
            border: 2px solid transparent;
            min-width: 95px;
            min-height: 80px;
        }
        .voice-card-btn:checked {
            background-color: alpha(@accent_color, 0.18);
            border-color: @accent_color;
        }
        .voice-card-btn:hover {
            background-color: alpha(@accent_color, 0.08);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        disp = Gdk.Display.get_default()
        if disp:
            Gtk.StyleContext.add_provider_for_display(
                disp, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

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

        # Quick Voice Changer Toggle at the beginning of the GUI
        self.voice_header_toggle = Gtk.ToggleButton()
        self.voice_header_toggle.set_tooltip_text("Toggle Microphone Voice Changer (On/Off)")
        self.voice_header_toggle.add_css_class("flat")
        voice_hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        voice_hdr_icon = Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic")
        self.voice_hdr_label = Gtk.Label(label="Voice FX: Off")
        voice_hdr_box.append(voice_hdr_icon)
        voice_hdr_box.append(self.voice_hdr_label)
        self.voice_header_toggle.set_child(voice_hdr_box)
        self.voice_header_toggle.connect("toggled", self._on_voice_header_toggled)
        self.header_bar.pack_end(self.voice_header_toggle)

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
            title="Firmware Revision",
            subtitle="Unknown",
        )
        self.fw_row.add_prefix(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
        self.info_group.add(self.fw_row)

        self.sn_row = Adw.ActionRow(
            title="Headset Serial Number",
            subtitle="Unknown",
        )
        self.sn_row.add_prefix(Gtk.Image.new_from_icon_name("fingerprint-symbolic"))

        self.edit_sn_btn = Gtk.Button(icon_name="document-edit-symbolic")
        self.edit_sn_btn.set_tooltip_text("Set physical headset serial number (found under left ear cushion)")
        self.edit_sn_btn.set_valign(Gtk.Align.CENTER)
        self.edit_sn_btn.add_css_class("flat")
        self.edit_sn_btn.connect("clicked", self._on_edit_serial_clicked)
        self.sn_row.add_suffix(self.edit_sn_btn)
        self.sn_row.set_activatable_widget(self.edit_sn_btn)
        self.info_group.add(self.sn_row)

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
            subtitle="10-band headphone playback curve (Game, Music, Movie, etc.)",
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
            description="Dynamic DSP audio filters for headphone playback",
        )
        self.pref_page.add(self.enhancements_group)

        # Bass Boost Slider (0 - 100)
        self.bass_boost_row = Adw.ActionRow(
            title="Bass Boost",
            subtitle="Dynamic low-frequency bass enhancement for headphone playback",
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

        # --- Voice Changer Group ---
        self.voice_group = Adw.PreferencesGroup(
            title="Voice Changer",
            description="Real-time microphone transformation via PipeWire and EasyEffects",
        )
        self.pref_page.add(self.voice_group)

        # Master Switch Row
        self.voice_master_row = Adw.ActionRow(
            title="Microphone Voice Changer",
            subtitle="Enable real-time voice modification effects",
        )
        self.voice_master_row.add_prefix(Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic"))

        self.voice_master_switch = Gtk.Switch()
        self.voice_master_switch.set_valign(Gtk.Align.CENTER)
        self.voice_master_switch.connect("state-set", self._on_voice_master_switch_state_set)
        self.voice_master_row.add_suffix(self.voice_master_switch)
        self.voice_master_row.set_activatable_widget(self.voice_master_switch)
        self.voice_group.add(self.voice_master_row)

        # Voice FX Sidetone Switch Row (listen to voice effects in headset)
        self.voice_sidetone_row = Adw.ActionRow(
            title="Voice FX Sidetone",
            subtitle="Listen to transformed voice effects in your headset in real-time",
        )
        self.voice_sidetone_row.add_prefix(Gtk.Image.new_from_icon_name("audio-headphones-symbolic"))

        self.voice_sidetone_switch = Gtk.Switch()
        self.voice_sidetone_switch.set_valign(Gtk.Align.CENTER)
        self.voice_sidetone_switch.connect("state-set", self._on_voice_sidetone_switch_state_set)
        self.voice_sidetone_row.add_suffix(self.voice_sidetone_switch)
        self.voice_sidetone_row.set_activatable_widget(self.voice_sidetone_switch)
        self.voice_group.add(self.voice_sidetone_row)

        # Push Buttons FlowBox Row
        self.voice_presets_row = Adw.PreferencesRow()
        self.voice_presets_row.set_selectable(False)

        voice_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        voice_box.set_margin_top(12)
        voice_box.set_margin_bottom(12)
        voice_box.set_margin_start(12)
        voice_box.set_margin_end(12)

        self.voice_flowbox = Gtk.FlowBox()
        self.voice_flowbox.set_valign(Gtk.Align.CENTER)
        self.voice_flowbox.set_halign(Gtk.Align.FILL)
        self.voice_flowbox.set_max_children_per_line(4)
        self.voice_flowbox.set_min_children_per_line(2)
        self.voice_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.voice_flowbox.set_row_spacing(10)
        self.voice_flowbox.set_column_spacing(10)
        self.voice_flowbox.set_homogeneous(True)

        icons_dir = Path(__file__).parent / "assets" / "icons"
        first_btn: Optional[Gtk.ToggleButton] = None

        for key, info in VOICE_PRESETS.items():
            btn = Gtk.ToggleButton()
            btn.set_tooltip_text(f"{info['title']} - {info['subtitle']}")
            btn.add_css_class("card")
            btn.add_css_class("voice-card-btn")
            btn.set_hexpand(True)

            if first_btn is None:
                first_btn = btn
            else:
                btn.set_group(first_btn)

            btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            btn_box.set_valign(Gtk.Align.CENTER)
            btn_box.set_halign(Gtk.Align.CENTER)

            icon_file = icons_dir / info.get("icon", "")
            if icon_file.exists():
                img = Gtk.Image.new_from_file(str(icon_file))
            else:
                img = Gtk.Image.new_from_icon_name(info.get("symbolic", "audio-input-microphone-symbolic"))
            img.set_pixel_size(36)
            btn_box.append(img)

            title_label = Gtk.Label(label=info["title"])
            title_label.add_css_class("caption")
            btn_box.append(title_label)

            btn.set_child(btn_box)
            btn.connect("toggled", self._on_voice_button_toggled, key)
            self.voice_buttons[key] = btn
            self.voice_flowbox.append(btn)

        voice_box.append(self.voice_flowbox)
        self.voice_presets_row.set_child(voice_box)
        self.voice_group.add(self.voice_presets_row)

        # --- Preferences / Settings Group ---
        self.settings_group = Adw.PreferencesGroup(title="Preferences")
        self.pref_page.add(self.settings_group)

        self.notify_row = Adw.ActionRow(
            title="Desktop Notifications",
            subtitle="Show GNOME desktop alerts via notify-send on state changes",
        )
        self.notify_row.add_prefix(Gtk.Image.new_from_icon_name("user-available-symbolic"))

        self.notify_switch = Gtk.Switch()
        self.notify_switch.set_active(get_notifications_enabled())
        self.notify_switch.set_valign(Gtk.Align.CENTER)
        self.notify_switch.connect("state-set", self._on_notify_state_set)
        self.notify_row.add_suffix(self.notify_switch)
        self.notify_row.set_activatable_widget(self.notify_switch)
        self.settings_group.add(self.notify_row)

        # Synchronize initial voice UI state
        self._sync_voice_ui()

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

            # Notify connection if state changed
            if not self._device_was_connected:
                self.notifier.notify_connected("Razer BlackShark V2")
                self._device_was_connected = True

            # Query hardware details
            self.device_info = dev.get_device_info()
            fw = self.device_info.get("firmware_version", "v0.11")
            sn = self.device_info.get("serial_number", "00000000")

            # Update UI indicators
            self.status_badge.set_label("Connected (0x1532:0x0529)")
            self.status_badge.remove_css_class("dim-label")
            self.status_badge.add_css_class("success")
            self.fw_row.set_subtitle(fw)
            self.sn_row.set_subtitle(sn)

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
            self._permission_denied = True
            if self._device_was_connected:
                self.notifier.notify_disconnected("Razer BlackShark V2")
                self._device_was_connected = False
            self.status_badge.set_label("Permission Denied")
            self.status_badge.remove_css_class("success")
            self.status_badge.add_css_class("error")
            self.fw_row.set_subtitle("Permission Denied")
            self.sn_row.set_subtitle("Permission Denied")

            self.banner.set_title(
                "Permission Denied: Run 'sudo cp 99-razer.rules /etc/udev/rules.d/' "
                "and reload udev rules."
            )
            self.banner.set_button_label("Retry")
            self.banner.set_revealed(True)
            self._set_controls_sensitive(False)

        except RazerNotFoundError:
            self._permission_denied = False
            if self._device_was_connected:
                self.notifier.notify_disconnected("Razer BlackShark V2")
                self._device_was_connected = False
            self.status_badge.set_label("Disconnected")
            self.status_badge.remove_css_class("success")
            self.status_badge.remove_css_class("error")
            self.status_badge.add_css_class("dim-label")
            self.fw_row.set_subtitle("Not Detected")
            custom_sn = get_custom_serial()
            self.sn_row.set_subtitle(f"{custom_sn} (Saved)" if custom_sn else "Not Detected")

            self.banner.set_title("Razer BlackShark V2 USB Sound Card not detected. Please check USB cable.")
            self.banner.set_button_label("Scan Again")
            self.banner.set_revealed(True)
            self._set_controls_sensitive(False)

        except RazerDeviceError as e:
            self._permission_denied = False
            if self._device_was_connected:
                self.notifier.notify_disconnected("Razer BlackShark V2")
                self._device_was_connected = False
            self.status_badge.set_label("Device Error")
            self.status_badge.remove_css_class("success")
            self.status_badge.add_css_class("error")
            self.fw_row.set_subtitle("Device Error")
            self.sn_row.set_subtitle("Device Error")
            self.banner.set_title(f"Hardware communication error: {e}")
            self.banner.set_button_label("Retry")
            self.banner.set_revealed(True)
            self._set_controls_sensitive(False)

    def _on_edit_serial_clicked(self, _btn: Gtk.Button) -> None:
        """Open a dialog to configure or reset the physical headset serial number."""
        current_custom = get_custom_serial()

        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g. PM2047H1234567")
        if current_custom:
            entry.set_text(current_custom)

        body_text = (
            "The Razer USB Sound Card reports default ID '00000000'.\n\n"
            "Enter the physical serial number printed on the sticker "
            "under your headset's left ear cushion:"
        )

        if hasattr(Adw, "AlertDialog"):
            dialog = Adw.AlertDialog.new("Headset Serial Number", body_text)
            dialog.set_extra_child(entry)
            dialog.add_response("cancel", "Cancel")
            if current_custom:
                dialog.add_response("reset", "Reset to Default")
                dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.add_response("save", "Save")
            dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("save")
            dialog.set_close_response("cancel")

            def _on_alert_response(d: Any, result: Any) -> None:
                try:
                    resp = d.choose_finish(result)
                except Exception:
                    return
                self._handle_serial_dialog_response(resp, entry.get_text())

            dialog.choose(self, None, _on_alert_response)
        else:
            dialog = Adw.MessageDialog(heading="Headset Serial Number", body=body_text)
            dialog.set_transient_for(self)
            dialog.set_modal(True)
            dialog.set_extra_child(entry)
            dialog.add_response("cancel", "Cancel")
            if current_custom:
                dialog.add_response("reset", "Reset to Default")
                dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.add_response("save", "Save")
            dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("save")
            dialog.set_close_response("cancel")

            def _on_msg_response(d: Any, resp: str) -> None:
                self._handle_serial_dialog_response(resp, entry.get_text())

            dialog.connect("response", _on_msg_response)
            dialog.present()

    def _handle_serial_dialog_response(self, response: str, text: str) -> None:
        """Handle response from serial configuration dialog."""
        if response == "save":
            val = text.strip()
            if val:
                set_custom_serial(val)
                self.notifier.send("RZROPENAUD-IO", f"Headset serial set to {val}")
            else:
                clear_custom_serial()
            self._refresh_device_info()
        elif response == "reset":
            clear_custom_serial()
            self.notifier.send("RZROPENAUD-IO", "Headset serial reset to hardware default.")
            self._refresh_device_info()

    def _refresh_device_info(self) -> None:
        """Re-query device info and update GUI labels."""
        if self.device is not None:
            try:
                self.device_info = self.device.get_device_info()
                fw = self.device_info.get("firmware_version", "v0.11")
                sn = self.device_info.get("serial_number", "00000000")
                self.fw_row.set_subtitle(fw)
                self.sn_row.set_subtitle(sn)
            except Exception:
                pass
        else:
            custom_sn = get_custom_serial()
            if custom_sn:
                self.sn_row.set_subtitle(f"{custom_sn} (Physical Headset)")
            else:
                self.sn_row.set_subtitle("Not Detected")

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
        self._permission_denied = False
        self._connect_device()

    def _on_refresh_clicked(self, _btn: Gtk.Button) -> None:
        """Manual refresh from HeaderBar button."""
        self._permission_denied = False
        self._connect_device()

    def _handle_disconnect(self) -> None:
        """Handle hardware disconnection (e.g. USB cable unplugged)."""
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

        if self._device_was_connected:
            self.notifier.notify_disconnected("Razer BlackShark V2")
            self._device_was_connected = False

        self.status_badge.set_label("Disconnected")
        self.status_badge.remove_css_class("success")
        self.status_badge.remove_css_class("error")
        self.status_badge.add_css_class("dim-label")

        self.fw_row.set_subtitle("Not Detected")
        custom_sn = get_custom_serial()
        self.sn_row.set_subtitle(f"{custom_sn} (Saved)" if custom_sn else "Not Detected")

        self.banner.set_title("Razer BlackShark V2 USB Sound Card disconnected. Please check USB cable.")
        self.banner.set_button_label("Scan Again")
        self.banner.set_revealed(True)
        self._set_controls_sensitive(False)

    def _poll_device_connection(self) -> bool:
        """Periodically monitor headset physical USB connection state and window geometry."""
        # 1. Check window geometry changes when unmaximized
        if not self.is_maximized():
            cur_w = self.get_width()
            cur_h = self.get_height()
            if cur_w > 0 and cur_h > 0 and (cur_w != self._last_saved_w or cur_h != self._last_saved_h):
                self._save_window_geometry()

        # 2. Monitor physical USB connection state
        if self.device is not None:
            if not self.device.is_connected():
                self._handle_disconnect()
        else:
            if not self._permission_denied and is_blackshark_connected():
                self._connect_device()
            elif not is_blackshark_connected():
                self._permission_denied = False

        return GLib.SOURCE_CONTINUE

    def _save_window_geometry(self) -> None:
        """Persist current window dimensions and state to configuration."""
        try:
            is_maximized = self.is_maximized()
            cur_w = self.get_width()
            cur_h = self.get_height()
            def_w, def_h = self.get_default_size()

            if is_maximized:
                w = self._last_saved_w if self._last_saved_w > 0 else def_w
                h = self._last_saved_h if self._last_saved_h > 0 else def_h
            else:
                w = cur_w if cur_w > 0 else def_w
                h = cur_h if cur_h > 0 else def_h
                self._last_saved_w = w
                self._last_saved_h = h

            set_window_geometry(w, h, is_maximized=is_maximized)
        except Exception as e:
            logger.debug("Failed to save window geometry: %s", e)

    def _on_close_request(self, _win: Gtk.Window) -> bool:
        """Handle window close request: save geometry and clean up."""
        self._save_window_geometry()
        return False

    def _on_destroy(self, _win: Gtk.Window) -> None:
        """Handle window destroy signal."""
        self._save_window_geometry()
        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None
        if self.device is not None:
            self.device.close()
            self.device = None

    def _on_notify_state_set(self, _switch: Gtk.Switch, state: bool) -> bool:
        """Toggle desktop notification preference."""
        self.notifier.enabled = state
        set_notifications_enabled(state)
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
                if self.device is not None and not self.device.is_connected():
                    self._handle_disconnect()
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
                if self.device is not None and not self.device.is_connected():
                    self._handle_disconnect()
        return GLib.SOURCE_REMOVE

    def _on_mic_boost_state_set(self, _switch: Gtk.Switch, state: bool) -> bool:
        """Handle microphone boost toggle."""
        if self.device is not None:
            try:
                self.device.set_mic_boost(state, use_direct=True)
                self.notifier.notify_mic_boost(state)
            except Exception as e:
                print(f"[GUI] Mic boost error: {e}", file=sys.stderr)
                if self.device is not None and not self.device.is_connected():
                    self._handle_disconnect()
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
                    if self.device is not None and not self.device.is_connected():
                        self._handle_disconnect()

    def _on_bass_boost_value_changed(self, scale: Gtk.Scale) -> None:
        """Handle bass boost slider change with 250ms debounce."""
        val = int(scale.get_value())
        if self._bass_boost_timer:
            GLib.source_remove(self._bass_boost_timer)
        self._bass_boost_timer = GLib.timeout_add(250, self._apply_bass_boost, val)

    def _apply_bass_boost(self, val: int) -> bool:
        self._bass_boost_timer = None
        if self.device is not None:
            try:
                self.device.set_bass_boost(val)
                self.notifier.notify_bass_boost(val)
            except Exception as e:
                print(f"[GUI] Bass boost error: {e}", file=sys.stderr)
                if self.device is not None and not self.device.is_connected():
                    self._handle_disconnect()
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
                if self.device is not None and not self.device.is_connected():
                    self._handle_disconnect()
        return GLib.SOURCE_REMOVE

    # -------------------------------------------------------------------------
    # Voice Changer Event Handlers
    # -------------------------------------------------------------------------

    def _sync_voice_ui(self) -> None:
        """Synchronize voice changer UI components with current state."""
        self._updating_voice_ui = True
        try:
            # Sync master switch in Voice Changer group
            self.voice_master_switch.set_active(self.voice_enabled)

            # Sync quick toggle button in HeaderBar
            self.voice_header_toggle.set_active(self.voice_enabled)
            preset_info = VOICE_PRESETS.get(self.current_voice_preset, {})
            title = preset_info.get("title", self.current_voice_preset.title())
            if self.voice_enabled and self.current_voice_preset != "off":
                self.voice_hdr_label.set_label(f"Voice FX: {title}")
                self.voice_header_toggle.add_css_class("suggested-action")
            else:
                self.voice_hdr_label.set_label("Voice FX: Off")
                self.voice_header_toggle.remove_css_class("suggested-action")

            # Sync active push button
            active_key = self.current_voice_preset if self.voice_enabled else "off"
            if active_key in self.voice_buttons:
                self.voice_buttons[active_key].set_active(True)

            # Sync Voice FX sidetone switch
            self.voice_sidetone_switch.set_active(self.voice_monitor_enabled and self.voice_enabled)
            self.voice_sidetone_row.set_sensitive(self.voice_enabled)

            # Enable/disable push buttons depending on whether master switch is on
            self.voice_flowbox.set_sensitive(self.voice_enabled)

        finally:
            self._updating_voice_ui = False

    def _on_voice_header_toggled(self, btn: Gtk.ToggleButton) -> None:
        """Handle toggle of HeaderBar quick voice changer button."""
        if self._updating_voice_ui:
            return
        is_active = btn.get_active()
        self.voice_master_switch.set_active(is_active)

    def _on_voice_master_switch_state_set(self, _switch: Gtk.Switch, state: bool) -> bool:
        """Handle toggle of Voice Changer master switch."""
        if self._updating_voice_ui:
            return False

        self.voice_enabled = state
        set_voice_fx_enabled(state)

        # Default to 'deep' voice if turning on from off
        if self.voice_enabled and self.current_voice_preset == "off":
            self.current_voice_preset = "deep"
            set_voice_preset("deep")

        # Apply to EasyEffects input pipeline
        preset_to_load = self.current_voice_preset if self.voice_enabled else "off"
        self._apply_voice_preset(preset_to_load, enabled=self.voice_enabled)

        # Update microphone monitoring sidetone
        self.easyeffects.set_microphone_monitoring(self.voice_enabled and self.voice_monitor_enabled)

        self._sync_voice_ui()
        return False

    def _on_voice_sidetone_switch_state_set(self, _switch: Gtk.Switch, state: bool) -> bool:
        """Handle toggle of Voice FX Sidetone (monitoring in headset)."""
        if self._updating_voice_ui:
            return False

        self.voice_monitor_enabled = state
        set_voice_monitor_enabled(state)
        self.easyeffects.set_microphone_monitoring(state and self.voice_enabled)
        return False

    def _on_voice_button_toggled(self, btn: Gtk.ToggleButton, preset_key: str) -> None:
        """Handle selection of a voice preset push button."""
        if self._updating_voice_ui or not btn.get_active():
            return

        if preset_key in ("off", "normal"):
            self.voice_enabled = False
            self.current_voice_preset = "off"
            set_voice_fx_enabled(False)
            set_voice_preset("off")
            self._apply_voice_preset("off", enabled=False)
        else:
            self.voice_enabled = True
            self.current_voice_preset = preset_key
            set_voice_fx_enabled(True)
            set_voice_preset(preset_key)
            self._apply_voice_preset(preset_key, enabled=True)

        self._sync_voice_ui()

    def _apply_voice_preset(self, preset_key: str, enabled: bool = True) -> None:
        """Apply voice preset via EasyEffectsBridge without distracting alerts."""
        self.easyeffects.apply_voice_preset(preset_key, enabled=enabled, sync=False)

    def do_destroy(self) -> None:
        """Clean up hardware connection, timers, and save geometry on window close."""
        self._save_window_geometry()
        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None
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
