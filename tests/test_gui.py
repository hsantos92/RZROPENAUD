"""Unit tests for RZROPENAUD-IO GNOME GUI components."""

import os
import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from rzropenaud_io.gui import RzrOpenAudApp, RzrOpenAudWindow


class TestRzrOpenAudGUI(unittest.TestCase):
    """Test GUI instantiation and component hierarchy."""

    @classmethod
    def setUpClass(cls):
        # Initialize libadwaita
        Adw.init()

    def test_app_instantiation(self):
        app = RzrOpenAudApp()
        self.assertEqual(app.get_application_id(), "io.github.rzropenaud.io")

    def test_window_components(self):
        # Create an app instance and window without calling run()
        app = RzrOpenAudApp()
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

        # Clean up window
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
