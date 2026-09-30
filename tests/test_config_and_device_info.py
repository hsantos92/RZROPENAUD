"""Unit tests for configuration persistence, firmware detection, and serial number handling."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import rzropenaud_io.config as config_mod
from rzropenaud_io.cli import build_parser, main
from rzropenaud_io.device import BlackSharkV2


class TestConfigAndDeviceInfo(unittest.TestCase):
    """Test persistent config, firmware version formatting, and serial resolution."""

    def setUp(self):
        # Use a temporary directory for config tests
        self.test_dir = tempfile.mkdtemp()
        self.orig_config_dir = config_mod.CONFIG_DIR
        self.orig_config_file = config_mod.CONFIG_FILE
        config_mod.CONFIG_DIR = Path(self.test_dir)
        config_mod.CONFIG_FILE = config_mod.CONFIG_DIR / "config.json"

    def tearDown(self):
        config_mod.CONFIG_DIR = self.orig_config_dir
        config_mod.CONFIG_FILE = self.orig_config_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_and_load_config(self):
        self.assertEqual(config_mod.load_config(), {})
        config_mod.save_config({"test_key": "test_value"})
        self.assertEqual(config_mod.load_config(), {"test_key": "test_value"})

    def test_set_and_get_custom_serial(self):
        self.assertIsNone(config_mod.get_custom_serial())

        config_mod.set_custom_serial("PM2047H1234567")
        self.assertEqual(config_mod.get_custom_serial(), "PM2047H1234567")

        # Clear serial
        config_mod.clear_custom_serial()
        self.assertIsNone(config_mod.get_custom_serial())

    def test_default_or_empty_serial_cleared(self):
        config_mod.set_custom_serial("PM2047H1234567")
        config_mod.set_custom_serial("default")
        self.assertIsNone(config_mod.get_custom_serial())

        config_mod.set_custom_serial("PM2047H1234567")
        config_mod.set_custom_serial("")
        self.assertIsNone(config_mod.get_custom_serial())

        # "00000000" is treated as dongle default, not custom headset serial
        config_mod.save_config({"serial_number": "00000000"})
        self.assertIsNone(config_mod.get_custom_serial())

    def test_device_info_firmware_resolution(self):
        dev = BlackSharkV2()
        dev._dev_info = {
            "vendor_id": 0x1532,
            "product_id": 0x0529,
            "interface_number": 3,
            "release_number": 17,  # 0x0011 -> v0.11
            "serial_number": "00000000",
        }

        # Mock send_and_receive to return blank arguments (simulating sound card dongle)
        mock_report = MagicMock()
        mock_report.arguments = bytearray()
        dev.send_and_receive = MagicMock(return_value=mock_report)

        info = dev.get_device_info()
        self.assertEqual(info["firmware_version"], "v0.11")
        self.assertEqual(info["serial_number"], "00000000 (Hardware Dongle Default)")
        self.assertEqual(info["serial_raw"], "00000000")
        self.assertFalse(info["is_custom_serial"])

    def test_device_info_with_custom_serial(self):
        config_mod.set_custom_serial("PM2047H9999999")

        dev = BlackSharkV2()
        dev._dev_info = {
            "vendor_id": 0x1532,
            "product_id": 0x0529,
            "interface_number": 3,
            "release_number": 17,
            "serial_number": "00000000",
        }
        mock_report = MagicMock()
        mock_report.arguments = bytearray()
        dev.send_and_receive = MagicMock(return_value=mock_report)

        info = dev.get_device_info()
        self.assertEqual(info["firmware_version"], "v0.11")
        self.assertEqual(info["serial_number"], "PM2047H9999999 (Physical Headset)")
        self.assertEqual(info["serial_raw"], "PM2047H9999999")
        self.assertTrue(info["is_custom_serial"])

    def test_cli_set_and_clear_serial(self):
        parser = build_parser()
        args = parser.parse_args(["--set-serial", "PM11223344", "--no-notify"])
        self.assertEqual(args.set_serial, "PM11223344")

        # Test CLI execution for set-serial
        ret = main(["--set-serial", "PM11223344", "--no-notify"])
        self.assertEqual(ret, 0)
        self.assertEqual(config_mod.get_custom_serial(), "PM11223344")

        # Test CLI execution for clear-serial
        ret_clear = main(["--clear-serial", "--no-notify"])
        self.assertEqual(ret_clear, 0)
        self.assertIsNone(config_mod.get_custom_serial())


if __name__ == "__main__":
    unittest.main()
