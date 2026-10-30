"""Native GNOME graphical user interface for RZROPENAUD-IO using GTK4 and libadwaita.

Provides a sleek, futuristic openSyn Black & Neon Green (#44D62C)
interface for the Razer BlackShark V2 (Model RZ04-0323).
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

import cairo
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
    EQ_BAND_LABELS,
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

logger = logging.getLogger(__name__)


RAZER_CYBER_CSS = """
/* =========================================================================
   RZROPENAUD-IO // FUTURISTIC BLACK & NEON GREEN (#44D62C) openSyn THEME
   ========================================================================= */

@define-color accent_bg_color #44D62C;
@define-color accent_fg_color #0A0A0A;
@define-color accent_color #44D62C;
@define-color window_bg_color #161616;
@define-color window_fg_color #E6E6E6;
@define-color view_bg_color #161616;
@define-color view_fg_color #E6E6E6;
@define-color headerbar_bg_color #0D0D0D;
@define-color headerbar_fg_color #E6E6E6;
@define-color card_bg_color #101010;
@define-color card_fg_color #E6E6E6;
@define-color popover_bg_color #141414;
@define-color popover_fg_color #E6E6E6;
@define-color dialog_bg_color #121212;
@define-color dialog_fg_color #E6E6E6;

window,
.background,
preferencespage,
scrolledwindow,
viewport {
    background-color: #161616;
    color: #E6E6E6;
}

/* --- Top Dark openSyn HeaderBar --- */
headerbar {
    background-color: #0D0D0D;
    color: #E6E6E6;
    border-bottom: 1px solid #222222;
    min-height: 42px;
    padding: 0 8px;
}

headerbar windowtitle title {
    color: #44D62C;
    font-weight: 800;
    letter-spacing: 1.8px;
    font-size: 13px;
}

.opensyn-top-tag {
    color: #44D62C;
    font-weight: 800;
    font-size: 11px;
    letter-spacing: 1.5px;
    padding: 4px 8px;
    border-bottom: 2px solid #44D62C;
}

.opensyn-top-tag-dim {
    color: #888888;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 1.5px;
    padding: 4px 8px;
}

/* --- Vibrant Razer Neon Green Sub-Navigation Bar --- */
.razer-subnav-bar {
    background-color: #44D62C;
    min-height: 38px;
    padding: 0 14px;
    border-bottom: 1px solid #2EA81D;
}

.razer-nav-btn {
    background: transparent;
    color: #0A0A0A;
    border: none;
    border-bottom: 3px solid transparent;
    border-radius: 0;
    padding: 6px 14px;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 1.2px;
    transition: all 150ms ease;
}

.razer-nav-btn:hover {
    background-color: rgba(0, 0, 0, 0.10);
    color: #000000;
}

.razer-nav-btn:checked {
    background-color: rgba(0, 0, 0, 0.16);
    color: #000000;
    border-bottom-color: #0A0A0A;
}

/* --- Hero Device Showcase Panel (Dot-Matrix Carbon Backdrop) --- */
.razer-hero-panel {
    background-color: #181818;
    background-image: radial-gradient(#2B2B2B 1.2px, transparent 1.2px);
    background-size: 18px 18px;
    border: 1px solid #262626;
    border-radius: 4px;
    padding: 16px 20px;
}

.razer-profile-box {
    background-color: #101010;
    border: 1px solid #333333;
    border-radius: 3px;
    padding: 4px 12px;
    color: #D8D8D8;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
}

.razer-profile-label {
    color: #8E8E8E;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.1px;
}

.razer-mode-pill-bar {
    background-color: #0E0E0E;
    border: 1px solid #303030;
    border-radius: 20px;
    padding: 3px;
}

.razer-mode-pill-active {
    background-color: #44D62C;
    color: #0A0A0A;
    border-radius: 16px;
    padding: 4px 16px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
}

.razer-mode-pill-inactive {
    background-color: transparent;
    color: #AAAAAA;
    border-radius: 16px;
    padding: 4px 16px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}

/* --- Status Badges --- */
.status-pill {
    padding: 4px 10px;
    border-radius: 3px;
    font-weight: 800;
    font-size: 11px;
    letter-spacing: 0.6px;
}

.success {
    color: #44D62C;
    background-color: rgba(68, 214, 44, 0.12);
    border: 1px solid rgba(68, 214, 44, 0.45);
}

.error {
    color: #FF4D4D;
    background-color: rgba(255, 77, 77, 0.12);
    border: 1px solid rgba(255, 77, 77, 0.45);
}

/* --- Sleek Recessed Black & Green Cards & Preference Groups --- */
.razer-card,
preferencesgroup > box > boxed-list,
boxed-list {
    background-color: #101010;
    border: 1px solid #242424;
    border-radius: 4px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
}

preferencesgroup > box > box > label.heading {
    color: #44D62C;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 1.4px;
    text-transform: uppercase;
}

preferencesgroup > box > box > label.description {
    color: #888888;
    font-size: 11px;
}

row,
actionrow,
comborow {
    background-color: #101010;
    color: #E6E6E6;
    border-bottom: 1px solid #1C1C1C;
    padding: 6px 8px;
}

row:hover,
actionrow:hover,
comborow:hover {
    background-color: #151815;
}

row title,
actionrow title,
comborow title {
    color: #EAEAEA;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.4px;
}

row subtitle,
actionrow subtitle,
comborow subtitle {
    color: #888888;
    font-size: 11px;
}

row image,
actionrow image,
comborow image {
    color: #44D62C;
}

/* --- Section Card Headers inside Custom Cards --- */
.razer-card-title {
    color: #44D62C;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 1.4px;
}

.razer-sub-pill-on {
    background-color: #44D62C;
    color: #0A0A0A;
    font-weight: 800;
    font-size: 10px;
    letter-spacing: 0.9px;
    padding: 3px 10px;
    border-radius: 2px;
}

.razer-sub-pill-off {
    background-color: #181818;
    color: #888888;
    border: 1px solid #2E2E2E;
    font-weight: 700;
    font-size: 10px;
    letter-spacing: 0.9px;
    padding: 3px 10px;
    border-radius: 2px;
}

/* --- EQ Preset Selector Buttons (Matching Synapse Screenshot 1) --- */
.eq-preset-btn {
    background-color: #141414;
    color: #BBBBBB;
    border: 1px solid #333333;
    border-radius: 2px;
    padding: 6px 10px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.8px;
    transition: all 140ms ease;
}

.eq-preset-btn:hover {
    border-color: #44D62C;
    color: #FFFFFF;
    background-color: #1A2219;
}

.eq-preset-btn:checked {
    background-color: rgba(68, 214, 44, 0.14);
    color: #44D62C;
    border: 1px solid #44D62C;
    box-shadow: inset 0 0 8px rgba(68, 214, 44, 0.22);
}

.eq-reset-btn {
    background: transparent;
    color: #888888;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
}

.eq-reset-btn:hover {
    color: #44D62C;
    border-color: #2E442B;
    background-color: rgba(68, 214, 44, 0.08);
}

/* --- Acoustic Frequency Zone Blocks Below EQ Graph --- */
.eq-zone-chip {
    background-color: #1A1A1A;
    color: #8C8C8C;
    border: 1px solid #242424;
    border-radius: 2px;
    padding: 5px 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.9px;
}

/* --- Neon Green Sliders & Floating Green Value Pill Badges --- */
scale {
    padding: 6px 0;
}

scale trough {
    background-color: #2A2A2A;
    border-radius: 3px;
    min-height: 5px;
}

scale highlight {
    background-color: #44D62C;
    border-radius: 3px;
    min-height: 5px;
    box-shadow: 0 0 6px rgba(68, 214, 44, 0.45);
}

scale slider {
    background-color: #44D62C;
    border: 2px solid #0E0E0E;
    border-radius: 50%;
    min-width: 16px;
    min-height: 16px;
    margin: -6px;
    box-shadow: 0 0 6px rgba(68, 214, 44, 0.7);
    transition: all 120ms ease;
}

scale slider:hover {
    background-color: #5CE644;
    box-shadow: 0 0 10px rgba(68, 214, 44, 0.95);
}

scale value {
    background-color: #44D62C;
    color: #0A0A0A;
    font-weight: 800;
    font-size: 11px;
    border-radius: 3px;
    padding: 2px 7px;
    margin-left: 8px;
}

/* --- Neon Green Toggle Switches (Matching Synapse Screenshot 1 & 2) --- */
switch {
    background-color: #222222;
    border: 1px solid #444444;
    border-radius: 14px;
    min-width: 42px;
    min-height: 22px;
}

switch:checked {
    background-color: rgba(68, 214, 44, 0.22);
    border-color: #44D62C;
}

switch slider {
    background-color: #888888;
    border-radius: 50%;
    min-width: 16px;
    min-height: 16px;
    margin: 2px;
}

switch:checked slider {
    background-color: #44D62C;
    box-shadow: 0 0 6px rgba(68, 214, 44, 0.8);
}

/* --- Voice Changer Cyber Cards --- */
.voice-card-btn {
    background-color: #141414;
    border-radius: 4px;
    padding: 10px 8px;
    transition: all 160ms ease-in-out;
    border: 1px solid #2A2A2A;
    min-width: 95px;
    min-height: 82px;
    color: #CCCCCC;
}

.voice-card-btn:hover {
    background-color: #1A2119;
    border-color: #3A7A30;
    color: #FFFFFF;
}

.voice-card-btn:checked {
    background-color: rgba(68, 214, 44, 0.14);
    border: 1px solid #44D62C;
    color: #44D62C;
    box-shadow: inset 0 0 10px rgba(68, 214, 44, 0.20);
}

/* --- HeaderBar Quick Voice FX Toggle --- */
.suggested-action {
    background-color: #44D62C;
    color: #0A0A0A;
    font-weight: 800;
    border-radius: 3px;
}

/* --- In-Window Alert Banner --- */
banner > revealer > widget {
    background-color: #1B2619;
    color: #E6E6E6;
    border-bottom: 1px solid #44D62C;
}
"""


class RzrOpenAudWindow(Adw.ApplicationWindow):
    """Main GNOME application window using a sleek Black & Green openSyn aesthetic."""

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

        # Equalizer interactive curve state
        self.current_eq_bands: List[int] = list(EQ_PRESETS["flat"])
        self._dragging_eq_band: Optional[int] = None
        self._hovered_eq_band: Optional[int] = None
        self._eq_preset_buttons: Dict[str, Gtk.ToggleButton] = {}
        self._updating_eq_ui: bool = False
        self._custom_eq_timer: Optional[int] = None

        # Sub-navigation tab buttons
        self.nav_buttons: Dict[str, Gtk.ToggleButton] = {}

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
        """Construct the Black & Neon Green openSyn-styled interface."""
        # Force dark mode so black and green palette is always active
        style_mgr = Adw.StyleManager.get_default()
        if style_mgr:
            style_mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        provider = Gtk.CssProvider()
        if hasattr(provider, "load_from_string"):
            provider.load_from_string(RAZER_CYBER_CSS)
        else:
            provider.load_from_data(RAZER_CYBER_CSS.encode("utf-8"))

        disp = Gdk.Display.get_default()
        if disp:
            Gtk.StyleContext.add_provider_for_display(
                disp, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        # ---------------------------------------------------------------------
        # 1. Top Dark openSyn HeaderBar
        # ---------------------------------------------------------------------
        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)

        # Left navigation labels (openSyn | AUDIO) + Refresh button
        hdr_left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr_left_box.set_valign(Gtk.Align.CENTER)

        self.opensyn_lbl = Gtk.Label(label="openSyn")
        self.opensyn_lbl.add_css_class("opensyn-top-tag-dim")
        hdr_left_box.append(self.opensyn_lbl)

        audio_lbl = Gtk.Label(label="AUDIO")
        audio_lbl.add_css_class("opensyn-top-tag")
        hdr_left_box.append(audio_lbl)

        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Refresh device status and re-scan USB bus")
        self.refresh_btn.add_css_class("flat")
        self.refresh_btn.connect("clicked", self._on_refresh_clicked)
        hdr_left_box.append(self.refresh_btn)

        self.header_bar.pack_start(hdr_left_box)

        # Right Quick Voice Changer Toggle
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

        # ---------------------------------------------------------------------
        # 2. Vibrant Razer Neon Green Sub-Navigation Bar (Matching Screenshots)
        # ---------------------------------------------------------------------
        self.subnav_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.subnav_bar.add_css_class("razer-subnav-bar")

        nav_items = [
            ("all", "DASHBOARD"),
            ("sound", "SOUND"),
            ("enhancement", "ENHANCEMENT"),
            ("mic", "MIC"),
            ("voice", "VOICE FX"),
            ("system", "SYSTEM"),
        ]
        first_nav_btn: Optional[Gtk.ToggleButton] = None
        for nav_key, nav_label in nav_items:
            nav_btn = Gtk.ToggleButton(label=nav_label)
            nav_btn.add_css_class("razer-nav-btn")
            if first_nav_btn is None:
                first_nav_btn = nav_btn
                nav_btn.set_active(True)
            else:
                nav_btn.set_group(first_nav_btn)
            nav_btn.connect("toggled", self._on_subnav_toggled, nav_key)
            self.nav_buttons[nav_key] = nav_btn
            self.subnav_bar.append(nav_btn)

        self.toolbar_view.add_top_bar(self.subnav_bar)

        # ---------------------------------------------------------------------
        # 3. In-window Banner for error & permission notices
        # ---------------------------------------------------------------------
        self.banner = Adw.Banner()
        self.banner.connect("button-clicked", self._on_banner_button_clicked)
        self.toolbar_view.add_top_bar(self.banner)

        # ---------------------------------------------------------------------
        # 4. Main PreferencesPage (Scrollable Dashboard)
        # ---------------------------------------------------------------------
        self.pref_page = Adw.PreferencesPage()
        self.toolbar_view.set_content(self.pref_page)

        # =====================================================================
        # SECTION A: HERO HEADSET SHOWCASE (Dot-Matrix Carbon Panel)
        # =====================================================================
        self.hero_group = Adw.PreferencesGroup()
        self.pref_page.add(self.hero_group)

        hero_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        hero_card.add_css_class("razer-hero-panel")

        # Top Profile & Status Strip inside Hero
        hero_top_strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hero_top_strip.set_halign(Gtk.Align.FILL)

        prof_title = Gtk.Label(label="PROFILE")
        prof_title.add_css_class("razer-profile-label")
        hero_top_strip.append(prof_title)

        prof_badge = Gtk.Label(label="WORKSTATION-PC // DEFAULT  ▾")
        prof_badge.add_css_class("razer-profile-box")
        hero_top_strip.append(prof_badge)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        hero_top_strip.append(spacer)

        self.hero_status_indicator = Gtk.Label(label="● USB SOUND CARD")
        self.hero_status_indicator.add_css_class("razer-card-title")
        hero_top_strip.append(self.hero_status_indicator)

        hero_card.append(hero_top_strip)

        # Centerpiece BlackShark V2 Vector Illustration
        hero_img_path = Path(__file__).parent / "assets" / "headset_hero.svg"
        if hero_img_path.exists():
            self.hero_image = Gtk.Image.new_from_file(str(hero_img_path))
        else:
            self.hero_image = Gtk.Image.new_from_icon_name("audio-headset-symbolic")
        self.hero_image.set_pixel_size(165)
        self.hero_image.set_halign(Gtk.Align.CENTER)
        hero_card.append(self.hero_image)

        # Mode Pills under Headset (matching STEREO | THX SPATIAL AUDIO pill bar)
        mode_pill_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mode_pill_bar.add_css_class("razer-mode-pill-bar")
        mode_pill_bar.set_halign(Gtk.Align.CENTER)

        stereo_pill = Gtk.Label(label="24-BIT STEREO DAC")
        stereo_pill.add_css_class("razer-mode-pill-inactive")
        mode_pill_bar.append(stereo_pill)

        dsp_pill = Gtk.Label(label="RAZER AUDIO DSP ENGINE")
        dsp_pill.add_css_class("razer-mode-pill-active")
        mode_pill_bar.append(dsp_pill)

        hero_card.append(mode_pill_bar)
        self.hero_group.add(hero_card)

        # =====================================================================
        # SECTION B: INTERACTIVE 10-BAND AUDIO EQUALIZER GRAPH CARD
        # =====================================================================
        self.eq_visual_group = Adw.PreferencesGroup()
        self.pref_page.add(self.eq_visual_group)

        eq_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        eq_card.add_css_class("razer-card")
        eq_card.set_margin_top(2)
        eq_card.set_margin_bottom(2)
        eq_card.set_margin_start(0)
        eq_card.set_margin_end(0)

        eq_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        eq_inner.set_margin_top(16)
        eq_inner.set_margin_bottom(16)
        eq_inner.set_margin_start(18)
        eq_inner.set_margin_end(18)

        # Card Header Row: AUDIO-EQUALIZER + Mode Badges + Reset Button
        eq_hdr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        eq_title = Gtk.Label(label="AUDIO-EQUALIZER")
        eq_title.add_css_class("razer-card-title")
        eq_hdr_row.append(eq_title)

        std_badge = Gtk.Label(label="STANDARD")
        std_badge.add_css_class("razer-sub-pill-on")
        eq_hdr_row.append(std_badge)

        esp_badge = Gtk.Label(label="E-SPORT")
        esp_badge.add_css_class("razer-sub-pill-off")
        eq_hdr_row.append(esp_badge)

        eq_hdr_spacer = Gtk.Box()
        eq_hdr_spacer.set_hexpand(True)
        eq_hdr_row.append(eq_hdr_spacer)

        self.eq_reset_btn = Gtk.Button(label="↺ RESET")
        self.eq_reset_btn.add_css_class("eq-reset-btn")
        self.eq_reset_btn.set_tooltip_text("Reset 10-band equalizer to Flat (0 dB)")
        self.eq_reset_btn.connect("clicked", self._on_eq_reset_clicked)
        eq_hdr_row.append(self.eq_reset_btn)

        eq_inner.append(eq_hdr_row)

        # Preset Selector Buttons Row (matching SPIEL | FILM | MUSIK | BENUTZERDEFINIERT)
        preset_btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        preset_btn_row.set_homogeneous(True)

        preset_icons = {
            "flat": "─",
            "game": "🎮",
            "movie": "🎬",
            "music": "🎵",
            "voice": "🎙",
            "esports": "⚡",
            "bass-boost": "🔊",
        }
        first_eq_btn: Optional[Gtk.ToggleButton] = None
        for idx, p_key in enumerate(EQ_PRESETS.keys()):
            icon_sym = preset_icons.get(p_key, "•")
            disp_name = p_key.replace("-", " ").upper()
            p_btn = Gtk.ToggleButton(label=f"{icon_sym} {disp_name}")
            p_btn.add_css_class("eq-preset-btn")
            if first_eq_btn is None:
                first_eq_btn = p_btn
                p_btn.set_active(True)
            else:
                p_btn.set_group(first_eq_btn)
            p_btn.connect("toggled", self._on_eq_preset_btn_toggled, idx)
            self._eq_preset_buttons[p_key] = p_btn
            preset_btn_row.append(p_btn)

        eq_inner.append(preset_btn_row)

        # Interactive 10-Band Cairo Curve Graph
        self.eq_drawing_area = Gtk.DrawingArea()
        self.eq_drawing_area.set_content_height(210)
        self.eq_drawing_area.set_hexpand(True)
        self.eq_drawing_area.set_draw_func(self._draw_eq_graph)

        # Mouse click & drag controllers for interactive node adjustment
        drag_ctrl = Gtk.GestureDrag.new()
        drag_ctrl.connect("drag-begin", self._on_eq_drag_begin)
        drag_ctrl.connect("drag-update", self._on_eq_drag_update)
        drag_ctrl.connect("drag-end", self._on_eq_drag_end)
        self.eq_drawing_area.add_controller(drag_ctrl)

        motion_ctrl = Gtk.EventControllerMotion.new()
        motion_ctrl.connect("motion", self._on_eq_motion)
        motion_ctrl.connect("leave", self._on_eq_leave)
        self.eq_drawing_area.add_controller(motion_ctrl)

        eq_inner.append(self.eq_drawing_area)

        # Acoustic Frequency Zone Blocks (SUB-BASS | BASS | LOW MIDS | MID-RANGE | UPPER MIDS | HIGHS)
        zones_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        zones_row.set_homogeneous(True)
        for zone_lbl in ["SUB-BASS", "BASS", "LOW MIDS", "MID-RANGE", "UPPER MIDS", "HIGHS"]:
            z_chip = Gtk.Label(label=zone_lbl)
            z_chip.add_css_class("eq-zone-chip")
            zones_row.append(z_chip)
        eq_inner.append(zones_row)

        eq_card.append(eq_inner)
        self.eq_visual_group.add(eq_card)

        # =====================================================================
        # SECTION C: AUDIO CONTROLS GROUP (Hardware Sidetone, Mic Vol, Boost, EQ)
        # =====================================================================
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
        self.sidetone_scale.set_size_request(210, -1)
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
        self.mic_vol_scale.set_size_request(210, -1)
        self.mic_vol_scale.set_hexpand(True)
        self.mic_vol_scale.connect("value-changed", self._on_mic_volume_value_changed)
        self.mic_vol_row.add_suffix(self.mic_vol_scale)
        self.audio_group.add(self.mic_vol_row)

        # Mic Boost Switch
        self.mic_boost_row = Adw.ActionRow(
            title="Microphone Boost",
            subtitle="Hardware pre-amplifier gain boost (+10dB)",
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
        default_eq_idx = self.preset_keys.index("flat") if "flat" in self.preset_keys else 0
        self.eq_combo_row.set_selected(default_eq_idx)
        self.eq_combo_row.connect("notify::selected", self._on_eq_preset_selected)
        self.audio_group.add(self.eq_combo_row)

        # =====================================================================
        # SECTION D: AUDIO ENHANCEMENTS GROUP (Bass Boost & Voice Clarity)
        # =====================================================================
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
        self.bass_boost_scale.set_size_request(210, -1)
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
        self.voice_clarity_scale.set_size_request(210, -1)
        self.voice_clarity_scale.set_hexpand(True)
        self.voice_clarity_scale.connect("value-changed", self._on_voice_clarity_value_changed)
        self.voice_clarity_row.add_suffix(self.voice_clarity_scale)
        self.enhancements_group.add(self.voice_clarity_row)

        # =====================================================================
        # SECTION E: VOICE CHANGER GROUP (PipeWire / EasyEffects DSP)
        # =====================================================================
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

        # Voice FX Sidetone Switch Row
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

            title_label = Gtk.Label(label=info["title"].upper())
            title_label.add_css_class("caption")
            btn_box.append(title_label)

            btn.set_child(btn_box)
            btn.connect("toggled", self._on_voice_button_toggled, key)
            self.voice_buttons[key] = btn
            self.voice_flowbox.append(btn)

        voice_box.append(self.voice_flowbox)
        self.voice_presets_row.set_child(voice_box)
        self.voice_group.add(self.voice_presets_row)

        # =====================================================================
        # SECTION F: DEVICE STATUS & PREFERENCES GROUPS
        # =====================================================================
        self.info_group = Adw.PreferencesGroup(title="Device Status")
        self.pref_page.add(self.info_group)

        self.model_row = Adw.ActionRow(
            title="Model",
            subtitle=DEVICE_MODEL_NAME,
        )
        self.model_row.add_prefix(Gtk.Image.new_from_icon_name("audio-headset-symbolic"))
        self.info_group.add(self.model_row)

        self.status_badge = Gtk.Label(label="Disconnected")
        self.status_badge.add_css_class("status-pill")
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
    # Sub-Navigation Bar Filtering
    # -------------------------------------------------------------------------

    def _on_subnav_toggled(self, btn: Gtk.ToggleButton, nav_key: str) -> None:
        """Filter visible dashboard sections when clicking green sub-nav tabs."""
        if not btn.get_active():
            return

        show_all = nav_key == "all"
        self.hero_group.set_visible(show_all or nav_key == "sound")
        self.eq_visual_group.set_visible(show_all or nav_key == "sound")
        self.audio_group.set_visible(show_all or nav_key in ("sound", "mic"))
        self.enhancements_group.set_visible(show_all or nav_key == "enhancement")
        self.voice_group.set_visible(show_all or nav_key == "voice")
        self.info_group.set_visible(show_all or nav_key == "system")
        self.settings_group.set_visible(show_all or nav_key == "system")

    # -------------------------------------------------------------------------
    # Interactive 10-Band Equalizer Graph Drawing & Mouse Handling
    # -------------------------------------------------------------------------

    def _get_eq_plot_bounds(self, width: int, height: int) -> tuple[float, float, float, float]:
        """Return (left_pad, top_pad, plot_w, plot_h) for the EQ graph."""
        left_pad = 28.0
        right_pad = 48.0
        top_pad = 24.0
        bottom_pad = 30.0
        plot_w = max(100.0, float(width) - left_pad - right_pad)
        plot_h = max(60.0, float(height) - top_pad - bottom_pad)
        return left_pad, top_pad, plot_w, plot_h

    def _draw_eq_graph(self, _area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int) -> None:
        """Render the Razer Synapse-style 10-band equalizer curve with Cairo."""
        left_pad, top_pad, plot_w, plot_h = self._get_eq_plot_bounds(width, height)
        y_zero = top_pad + plot_h / 2.0

        # 1. Background canvas (#0D0D0D)
        cr.set_source_rgb(0.05, 0.05, 0.05)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # 2. Horizontal dB reference lines (+12dB, 0dB, -12dB) & labels
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(10.5)

        for db_val, label_txt in [(12, "+12dB"), (0, "0dB"), (-12, "-12dB")]:
            y_pos = y_zero - (db_val / 12.0) * (plot_h / 2.0)
            cr.set_source_rgba(0.18, 0.18, 0.18, 0.9 if db_val == 0 else 0.45)
            cr.set_line_width(1.0)
            cr.move_to(left_pad, y_pos)
            cr.line_to(left_pad + plot_w, y_pos)
            cr.stroke()

            cr.set_source_rgba(0.68, 0.68, 0.68, 1.0)
            cr.move_to(left_pad + plot_w + 8, y_pos + 4)
            cr.show_text(label_txt)

        # 3. 10 Vertical frequency tracks, 0dB green center dots, and Hz labels
        num_bands = len(EQ_BAND_LABELS)
        points: List[tuple[float, float]] = []

        for i, hz_label in enumerate(EQ_BAND_LABELS):
            x_pos = left_pad + (i / float(num_bands - 1)) * plot_w

            # Vertical track line
            cr.set_source_rgba(0.16, 0.16, 0.16, 1.0)
            cr.set_line_width(1.2)
            cr.move_to(x_pos, top_pad)
            cr.line_to(x_pos, top_pad + plot_h)
            cr.stroke()

            # Small green 0dB center reference dot (like Synapse screenshot)
            cr.set_source_rgba(0.267, 0.839, 0.173, 0.45)
            cr.arc(x_pos, y_zero, 2.2, 0, 2 * math.pi)
            cr.fill()

            # Frequency label at bottom
            ext = cr.text_extents(hz_label)
            cr.set_source_rgba(0.75, 0.75, 0.75, 1.0)
            cr.move_to(x_pos - ext.width / 2.0, top_pad + plot_h + 18)
            cr.show_text(hz_label)

            # Calculate node Y coordinate from band gain (-12 to +12 dB)
            gain = max(-12, min(12, self.current_eq_bands[i] if i < len(self.current_eq_bands) else 0))
            y_node = y_zero - (gain / 12.0) * (plot_h / 2.0)
            points.append((x_pos, y_node))

        if not points:
            return

        # 4. Soft translucent Razer Green area fill below the curve
        grad = cairo.LinearGradient(0, top_pad, 0, top_pad + plot_h)
        grad.add_color_stop_rgba(0.0, 0.267, 0.839, 0.173, 0.25)
        grad.add_color_stop_rgba(1.0, 0.267, 0.839, 0.173, 0.02)
        cr.set_source(grad)
        cr.move_to(points[0][0], top_pad + plot_h)
        for px, py in points:
            cr.line_to(px, py)
        cr.line_to(points[-1][0], top_pad + plot_h)
        cr.close_path()
        cr.fill()

        # 5. Outer glow stroke along the 10-band curve
        cr.set_source_rgba(0.267, 0.839, 0.173, 0.25)
        cr.set_line_width(5.0)
        cr.move_to(points[0][0], points[0][1])
        for px, py in points[1:]:
            cr.line_to(px, py)
        cr.stroke()

        # 6. Main crisp Razer Neon Green (#44D62C) connecting line
        cr.set_source_rgba(0.267, 0.839, 0.173, 0.95)
        cr.set_line_width(2.0)
        cr.move_to(points[0][0], points[0][1])
        for px, py in points[1:]:
            cr.line_to(px, py)
        cr.stroke()

        # 7. Glowing circular draggable nodes & live dB badges
        for i, (px, py) in enumerate(points):
            is_active = i in (self._dragging_eq_band, self._hovered_eq_band)
            if is_active:
                cr.set_source_rgba(0.267, 0.839, 0.173, 0.32)
                cr.arc(px, py, 11.0, 0, 2 * math.pi)
                cr.fill()

            # Solid green circle node
            cr.set_source_rgb(0.267, 0.839, 0.173)
            cr.arc(px, py, 6.0, 0, 2 * math.pi)
            cr.fill()

            # Value readout above node if non-zero or hovered
            gain_val = self.current_eq_bands[i]
            if is_active or gain_val != 0:
                gain_str = f"{gain_val:+d}" if gain_val != 0 else "0"
                ext = cr.text_extents(gain_str)
                cr.set_source_rgba(0.267, 0.839, 0.173, 1.0 if is_active else 0.85)
                cr.move_to(px - ext.width / 2.0, py - 10)
                cr.show_text(gain_str)

    def _update_eq_band_from_xy(self, x: float, y: float) -> None:
        """Update the closest EQ band gain from mouse (x, y) coordinates."""
        w = self.eq_drawing_area.get_width()
        h = self.eq_drawing_area.get_height()
        left_pad, top_pad, plot_w, plot_h = self._get_eq_plot_bounds(w, h)
        y_zero = top_pad + plot_h / 2.0

        if self._dragging_eq_band is None:
            # Find nearest band column
            rel_x = max(0.0, min(plot_w, x - left_pad))
            band_idx = int(round((rel_x / plot_w) * (len(EQ_BAND_LABELS) - 1)))
            self._dragging_eq_band = max(0, min(len(EQ_BAND_LABELS) - 1, band_idx))

        idx = self._dragging_eq_band
        raw_db = ((y_zero - y) / (plot_h / 2.0)) * 12.0
        clamped_db = int(round(max(-12.0, min(12.0, raw_db))))

        if self.current_eq_bands[idx] != clamped_db:
            self.current_eq_bands[idx] = clamped_db
            self.eq_drawing_area.queue_draw()
            if self._custom_eq_timer:
                GLib.source_remove(self._custom_eq_timer)
            self._custom_eq_timer = GLib.timeout_add(120, self._apply_custom_eq_bands)

    def _on_eq_drag_begin(self, _gesture: Gtk.GestureDrag, start_x: float, start_y: float) -> None:
        self._dragging_eq_band = None
        self._update_eq_band_from_xy(start_x, start_y)

    def _on_eq_drag_update(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float) -> None:
        ok, start_x, start_y = gesture.get_start_point()
        if ok:
            self._update_eq_band_from_xy(start_x + offset_x, start_y + offset_y)

    def _on_eq_drag_end(self, _gesture: Gtk.GestureDrag, _offset_x: float, _offset_y: float) -> None:
        self._dragging_eq_band = None
        self.eq_drawing_area.queue_draw()

    def _on_eq_motion(self, _ctrl: Gtk.EventControllerMotion, x: float, _y: float) -> None:
        w = self.eq_drawing_area.get_width()
        h = self.eq_drawing_area.get_height()
        left_pad, _top_pad, plot_w, _plot_h = self._get_eq_plot_bounds(w, h)
        rel_x = max(0.0, min(plot_w, x - left_pad))
        band_idx = int(round((rel_x / plot_w) * (len(EQ_BAND_LABELS) - 1)))
        if band_idx != self._hovered_eq_band:
            self._hovered_eq_band = band_idx
            self.eq_drawing_area.queue_draw()

    def _on_eq_leave(self, _ctrl: Gtk.EventControllerMotion) -> None:
        self._hovered_eq_band = None
        self.eq_drawing_area.queue_draw()

    def _apply_custom_eq_bands(self) -> bool:
        """Send custom dragged 10-band EQ curve to device & EasyEffects."""
        self._custom_eq_timer = None
        if self.device is not None:
            try:
                bands_str = ",".join(str(b) for b in self.current_eq_bands)
                self.device.set_equalizer(bands_str, use_direct=True)
            except Exception as e:
                print(f"[GUI] Custom EQ error: {e}", file=sys.stderr)
        return GLib.SOURCE_REMOVE

    def _on_eq_preset_btn_toggled(self, btn: Gtk.ToggleButton, preset_idx: int) -> None:
        """Sync visual preset button click with eq_combo_row."""
        if self._updating_eq_ui or not btn.get_active():
            return
        self.eq_combo_row.set_selected(preset_idx)

    def _on_eq_reset_clicked(self, _btn: Gtk.Button) -> None:
        """Reset 10-band equalizer to Flat (0 dB)."""
        flat_idx = self.preset_keys.index("flat") if "flat" in self.preset_keys else 0
        self.eq_combo_row.set_selected(flat_idx)
        self.current_eq_bands = list(EQ_PRESETS["flat"])
        self.eq_drawing_area.queue_draw()

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
            self.status_badge.remove_css_class("error")
            self.status_badge.add_css_class("success")
            self.hero_status_indicator.set_label(f"● CONNECTED // FW {fw}")
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
            self.hero_status_indicator.set_label("▲ PERMISSION DENIED")
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
            self.hero_status_indicator.set_label("○ DISCONNECTED")
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
            self.hero_status_indicator.set_label("▲ DEVICE ERROR")
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
        self.hero_status_indicator.set_label("○ DISCONNECTED")

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
        return False

    def _on_eq_preset_selected(self, row: Adw.ComboRow, _param: Any) -> None:
        """Handle equalizer preset selection and update visual 10-band curve."""
        idx = row.get_selected()
        if 0 <= idx < len(self.preset_keys):
            preset_name = self.preset_keys[idx]
            if preset_name in EQ_PRESETS:
                self.current_eq_bands = list(EQ_PRESETS[preset_name])
                self.eq_drawing_area.queue_draw()

            # Sync top visual preset button
            if preset_name in self._eq_preset_buttons:
                self._updating_eq_ui = True
                try:
                    self._eq_preset_buttons[preset_name].set_active(True)
                finally:
                    self._updating_eq_ui = False

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
