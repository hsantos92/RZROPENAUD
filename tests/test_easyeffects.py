"""Unit tests for EasyEffects integration bridge."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rzropenaud_io.constants import EQ_PRESETS
from rzropenaud_io.easyeffects import (
    VOICE_PRESETS,
    EasyEffectsBridge,
    build_preset_payload,
    build_voice_preset_payload,
)


class TestEasyEffectsBridge(unittest.TestCase):
    """Test suite for EasyEffects preset generation and bridge logic."""

    def test_build_preset_payload_structure(self):
        bands = [0, 2, 4, 3, 1, 0, 1, 2, 3, 4]
        payload = build_preset_payload(bands, bass_boost_percent=50)

        self.assertIn("output", payload)
        output = payload["output"]
        self.assertIn("blocklist", output)
        self.assertIn("plugins_order", output)
        self.assertEqual(output["plugins_order"], ["bass_enhancer", "equalizer"])

        # Check equalizer
        self.assertIn("equalizer", output)
        eq = output["equalizer"]
        self.assertEqual(eq["num-bands"], 10)
        self.assertIn("left", eq)
        self.assertIn("right", eq)
        self.assertEqual(eq["left"]["band2"]["gain"], 4.0)
        self.assertEqual(eq["left"]["band2"]["frequency"], 125.0)

        # Check bass enhancer
        self.assertIn("bass_enhancer", output)
        be = output["bass_enhancer"]
        self.assertFalse(be["bypass"])
        self.assertEqual(be["amount"], 6.0)  # 50% of 12.0 dB = 6.0 dB

    def test_bass_boost_zero_bypass(self):
        payload = build_preset_payload([0] * 10, bass_boost_percent=0)
        be = payload["output"]["bass_enhancer"]
        self.assertTrue(be["bypass"])
        self.assertEqual(be["amount"], 0.0)

    def test_install_all_presets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = EasyEffectsBridge()
            bridge.output_dir = Path(tmpdir)
            bridge.install_all_presets()

            for key in EQ_PRESETS:
                expected_filename = f"Razer-{key.replace('-', ' ').title().replace(' ', '-')}.json"
                file_path = bridge.output_dir / expected_filename
                self.assertTrue(file_path.exists(), f"Preset {expected_filename} was not created")

    def test_build_voice_preset_payload(self):
        for key in ["off", "deep", "female", "child", "robotic", "monster", "radio"]:
            payload = build_voice_preset_payload(key)
            self.assertIn("input", payload)
            input_block = payload["input"]
            self.assertIn("blocklist", input_block)
            self.assertIn("plugins_order", input_block)
            if key == "off":
                self.assertEqual(input_block["plugins_order"], [])
            else:
                self.assertGreater(len(input_block["plugins_order"]), 0)

    def test_install_voice_presets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = EasyEffectsBridge()
            bridge.input_dir = Path(tmpdir)
            bridge.install_voice_presets()

            for key, info in VOICE_PRESETS.items():
                expected_filename = f"{info['preset_name']}.json"
                file_path = bridge.input_dir / expected_filename
                self.assertTrue(file_path.exists(), f"Voice preset {expected_filename} was not created")

    @patch("subprocess.run")
    def test_set_microphone_monitoring(self, mock_run):
        mock_run.return_value.returncode = 0
        bridge = EasyEffectsBridge()
        with patch.object(bridge, "is_installed", return_value=True):
            res = bridge.set_microphone_monitoring(True)
            self.assertTrue(res)
            mock_run.assert_called_with(
                ["easyeffects", "--microphone-monitoring", "1"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            self.assertTrue(bridge.voice_monitor_enabled)

            bridge.set_microphone_monitoring(False)
            mock_run.assert_called_with(
                ["easyeffects", "--microphone-monitoring", "2"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            self.assertFalse(bridge.voice_monitor_enabled)

    def test_disable_easyeffects_tray(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_dir = Path(tmpdir) / ".config" / "easyeffects" / "db"
            cfg_dir.mkdir(parents=True)
            cfg_file = cfg_dir / "easyeffectsrc"
            cfg_file.write_text("[Window]\nheight=1000\n", encoding="utf-8")

            bridge = EasyEffectsBridge()
            # Monkeypatch Home to tempdir for this test
            with unittest.mock.patch("pathlib.Path.home", return_value=Path(tmpdir)):
                bridge._disable_easyeffects_tray()

            updated = cfg_file.read_text(encoding="utf-8")
            self.assertIn("showTrayIcon=false", updated)

    def test_build_voice_preset_payload(self):
        payload = build_voice_preset_payload("monster")
        self.assertIn("pitch", payload["input"])
        pitch_block = payload["input"]["pitch"]
        self.assertEqual(pitch_block["semitones"], -7.5)
        self.assertEqual(pitch_block["tempo-difference"], 0.0)

        payload_child = build_voice_preset_payload("child")
        self.assertIn("pitch", payload_child["input"])
        self.assertEqual(payload_child["input"]["pitch"]["semitones"], 6.8)


if __name__ == "__main__":
    unittest.main()
