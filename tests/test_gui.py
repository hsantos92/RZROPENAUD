"""Unit tests for RZROPENAUD-IO GNOME GUI components."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

import rzropenaud_io.config as config_mod
from rzropenaud_io.gui import RzrOpenAudApp, RzrOpenAudWindow


class TestRzrOpenAudGUI(unittest.TestCase):
    """Test GUI instantiation and component hierarchy."""

    @classmethod
    def setUpClass(cls):
        # Initialize libadwaita
        Adw.init()

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_config_dir = config_mod.CONFIG_DIR
        self.orig_config_file = config_mod.CONFIG_FILE
        config_mod.CONFIG_DIR = Path(self.test_dir)
        config_mod.CONFIG_FILE = config_mod.CONFIG_DIR / "config.json"

    def tearDown(self):
        config_mod.CONFIG_DIR = self.orig_config_dir
        config_mod.CONFIG_FILE = self.orig_config_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_app_instantiation(self):
        app = RzrOpenAudApp()
        self.assertEqual(app.get_application_id(), "io.github.rzropenaud.io")

    def test_window_components(self):
        # Create an app instance and window without calling run()
        app = RzrOpenAudApp()
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        win = RzrOpenAudWindow(application=app)

        # Check title and default dimensions
        self.assertEqual(win.get_title(), "RZROPENAUD-IO")
        width, height = win.get_default_size()
        self.assertEqual(width, 560)
        self.assertEqual(height, 720)

        # Check Audio Controls group title and rows
        self.assertEqual(win.audio_group.get_title(), "Audio Controls")
        self.assertIsNotNone(win.sidetone_row)
        self.assertIsNotNone(win.sidetone_scale)
        self.assertIsNotNone(win.mic_vol_row)
        self.assertIsNotNone(win.mic_vol_scale)
        self.assertIsNotNone(win.mic_boost_row)
        self.assertIsNotNone(win.mic_boost_switch)
        self.assertIsNotNone(win.eq_combo_row)

        # Verify slider ranges
        sidetone_adj = win.sidetone_scale.get_adjustment()
        self.assertEqual(sidetone_adj.get_lower(), 0.0)
        self.assertEqual(sidetone_adj.get_upper(), 100.0)

        mic_adj = win.mic_vol_scale.get_adjustment()
        self.assertEqual(mic_adj.get_lower(), 0.0)
        self.assertEqual(mic_adj.get_upper(), 100.0)

        # Verify EQ presets model
        model = win.eq_combo_row.get_model()
        self.assertGreaterEqual(model.get_n_items(), 7)

        # Verify Device Status rows
        self.assertIsNotNone(win.fw_row)
        self.assertIsNotNone(win.sn_row)
        self.assertIsNotNone(win.edit_sn_btn)

        # Verify Voice Changer group and components
        self.assertEqual(win.voice_group.get_title(), "Voice Changer")
        self.assertIsNotNone(win.voice_header_toggle)
        self.assertIsNotNone(win.voice_master_switch)
        self.assertIsNotNone(win.voice_sidetone_row)
        self.assertIsNotNone(win.voice_sidetone_switch)
        self.assertEqual(len(win.voice_buttons), 7)
        for key in ["off", "deep", "female", "child", "robotic", "monster", "radio"]:
            self.assertIn(key, win.voice_buttons)

        # Clean up window
        win.destroy()

    def test_gui_controls_interaction(self):
        """Test user interaction events on all Audio Control components."""
        app = Adw.Application(
            application_id="io.github.rzropenaud.test.interact",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        app.register(None)
        win = RzrOpenAudWindow(application=app)

        # 1. Sidetone scale adjustment
        win.sidetone_scale.set_value(75.0)
        self.assertEqual(win.sidetone_scale.get_value(), 75.0)
        # Directly invoke debounced callback
        win._apply_sidetone(75)

        # 2. Mic volume scale adjustment
        win.mic_vol_scale.set_value(90.0)
        self.assertEqual(win.mic_vol_scale.get_value(), 90.0)
        win._apply_mic_volume(90)

        # 3. Mic boost toggle
        win.mic_boost_switch.set_active(True)
        self.assertTrue(win.mic_boost_switch.get_active())
        win._on_mic_boost_state_set(win.mic_boost_switch, True)

        # 4. EQ combo preset selection
        win.eq_combo_row.set_selected(1)  # Game
        self.assertEqual(win.eq_combo_row.get_selected(), 1)
        win._on_eq_preset_selected(win.eq_combo_row, None)

        # 5. Bass boost and voice clarity
        win.bass_boost_scale.set_value(40.0)
        win._apply_bass_boost(40)
        win.voice_clarity_scale.set_value(30.0)
        win._apply_voice_clarity(30)

        # 6. Banner retry button
        win._on_banner_button_clicked(win.banner)

        # 7. Serial configuration dialog response handling
        win._handle_serial_dialog_response("save", "PM99887766")
        self.assertIn("PM99887766", win.sn_row.get_subtitle())
        win._handle_serial_dialog_response("reset", "")
        self.assertTrue(
            "00000000" in win.sn_row.get_subtitle() or "Not Detected" in win.sn_row.get_subtitle()
        )

        # 8. Voice Changer toggle and preset buttons
        win.voice_header_toggle.set_active(True)
        self.assertTrue(win.voice_master_switch.get_active())

        # Select robotic preset button
        win.voice_buttons["robotic"].set_active(True)
        self.assertEqual(win.current_voice_preset, "robotic")
        self.assertTrue(win.voice_enabled)

        # Toggle master switch off
        win.voice_master_switch.set_active(False)
        self.assertFalse(win.voice_enabled)
        self.assertFalse(win.voice_header_toggle.get_active())

        # Select normal button (bypass)
        win.voice_buttons["off"].set_active(True)
        self.assertFalse(win.voice_enabled)

        # Test Voice FX Sidetone switch
        win.voice_master_switch.set_active(True)
        win.voice_sidetone_switch.set_active(True)
        self.assertTrue(win.voice_monitor_enabled)
        win.voice_sidetone_switch.set_active(False)
        self.assertFalse(win.voice_monitor_enabled)

        # 9. Notification switch toggle and persistence
        win.notify_switch.set_active(True)
        win._on_notify_state_set(win.notify_switch, True)
        from rzropenaud_io.config import get_notifications_enabled
        self.assertTrue(get_notifications_enabled())
        win.notify_switch.set_active(False)
        win._on_notify_state_set(win.notify_switch, False)
        self.assertFalse(get_notifications_enabled())

        win.destroy()

    def test_window_geometry_remembered(self):
        """Test that window size is remembered and loaded from config."""
        config_mod.set_window_geometry(640, 780, is_maximized=False)

        app = Adw.Application(
            application_id="io.github.rzropenaud.test.geom",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        app.register(None)
        win = RzrOpenAudWindow(application=app)

        w, h = win.get_default_size()
        self.assertEqual(w, 640)
        self.assertEqual(h, 780)

        # Trigger save
        win.set_default_size(700, 850)
        win._save_window_geometry()

        saved_w, saved_h, _ = config_mod.get_window_geometry()
        self.assertEqual(saved_w, 700)
        self.assertEqual(saved_h, 850)

        win.destroy()

    def test_connection_monitoring_and_unplug(self):
        """Test that unplugging headset updates UI status badge to Disconnected."""
        from unittest.mock import MagicMock
        app = Adw.Application(
            application_id="io.github.rzropenaud.test.monitor",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        app.register(None)
        win = RzrOpenAudWindow(application=app)

        # Simulate device connected
        mock_dev = MagicMock()
        mock_dev.is_connected.return_value = True
        win.device = mock_dev
        win._device_was_connected = True
        win.status_badge.set_label("Connected (0x1532:0x0529)")
        win.status_badge.add_css_class("success")

        # Verify polling maintains connected state
        res = win._poll_device_connection()
        self.assertTrue(res)
        self.assertEqual(win.status_badge.get_label(), "Connected (0x1532:0x0529)")

        # Simulate device unplug: is_connected returns False
        mock_dev.is_connected.return_value = False
        res = win._poll_device_connection()
        self.assertTrue(res)

        # Status badge must now say Disconnected
        self.assertEqual(win.status_badge.get_label(), "Disconnected")
        self.assertIsNone(win.device)
        self.assertFalse(win._device_was_connected)
        self.assertTrue(win.banner.get_revealed())

        win.destroy()

    def test_desktop_file_exists(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        desktop_path = os.path.join(root, "data", "rzropenaud.desktop")
        self.assertTrue(os.path.exists(desktop_path), "rzropenaud.desktop must exist in data/")

        with open(desktop_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Categories=Settings;HardwareSettings;", content)
        self.assertIn("Exec=", content)
        self.assertIn("Icon=audio-headset", content)


if __name__ == "__main__":
    unittest.main()
