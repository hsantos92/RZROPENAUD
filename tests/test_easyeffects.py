"""Unit tests for EasyEffects integration bridge."""

from pathlib import Path
import tempfile
import unittest

from rzropenaud_io.constants import EQ_PRESETS
from rzropenaud_io.easyeffects import EasyEffectsBridge, build_preset_payload


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


if __name__ == "__main__":
    unittest.main()
