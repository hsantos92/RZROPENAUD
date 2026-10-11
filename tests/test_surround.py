"""Unit tests for PipeWire 7.1 Virtual Surround Sound module and integration."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import rzropenaud_io.config as config_mod
import rzropenaud_io.surround as surround_mod
from rzropenaud_io.cli import build_parser, main
from rzropenaud_io.surround import (
    SURROUND_CONF_FILE,
    SURROUND_SERVICE_FILE,
    SURROUND_SINK_NAME,
    disable_surround,
    enable_surround,
    ensure_systemd_service,
    generate_surround_config,
    get_sofa_path,
    get_surround_status,
    is_surround_active,
    is_surround_supported,
    write_surround_config,
)


class TestSurroundSound(unittest.TestCase):
    """Test 7.1 Virtual Surround Sound generation, service configuration, and controls."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_config_dir = config_mod.CONFIG_DIR
        self.orig_config_file = config_mod.CONFIG_FILE
        self.orig_surround_conf = surround_mod.SURROUND_CONF_FILE
        self.orig_service_file = surround_mod.SURROUND_SERVICE_FILE
        self.orig_pid_file = surround_mod.SURROUND_PID_FILE

        config_mod.CONFIG_DIR = Path(self.test_dir)
        config_mod.CONFIG_FILE = config_mod.CONFIG_DIR / "config.json"
        surround_mod.CONFIG_DIR = Path(self.test_dir)
        surround_mod.SURROUND_CONF_FILE = Path(self.test_dir) / "razer-7.1-surround.conf"
        surround_mod.SURROUND_SERVICE_FILE = Path(self.test_dir) / "rzr-surround-7-1.service"
        surround_mod.SURROUND_PID_FILE = Path(self.test_dir) / "surround.pid"

    def tearDown(self):
        config_mod.CONFIG_DIR = self.orig_config_dir
        config_mod.CONFIG_FILE = self.orig_config_file
        surround_mod.CONFIG_DIR = self.orig_config_dir
        surround_mod.SURROUND_CONF_FILE = self.orig_surround_conf
        surround_mod.SURROUND_SERVICE_FILE = self.orig_service_file
        surround_mod.SURROUND_PID_FILE = self.orig_pid_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_sofa_path(self):
        """Test detection of system SOFA HRTF model."""
        path = get_sofa_path()
        # On this system, libmysofa is installed
        if path:
            self.assertTrue(path.exists())
            self.assertTrue(str(path).endswith(".sofa"))

    def test_generate_surround_config(self):
        """Verify the generated PipeWire filter-chain configuration has all 8 channels."""
        cfg = generate_surround_config("/usr/share/libmysofa/default.sofa")

        # Must declare the 8-channel virtual sink
        self.assertIn('node.name        = "effect_input.razer_virtual_surround_7_1"', cfg)
        self.assertIn("media.class      = Audio/Sink", cfg)
        self.assertIn("audio.channels   = 8", cfg)
        self.assertIn("audio.position   = [ FL FR FC LFE RL RR SL SR ]", cfg)

        # Must declare spatializer nodes with SOFA model
        for name in ["spatFL", "spatFR", "spatFC", "spatLFE", "spatRL", "spatRR", "spatSL", "spatSR"]:
            self.assertIn(f"name  = {name}", cfg)

        self.assertIn('filename = "/usr/share/libmysofa/default.sofa"', cfg)
        self.assertIn('type  = sofa', cfg)
        self.assertIn('label = spatializer', cfg)

        # Must declare stereo downmixers
        self.assertIn("name = mixL", cfg)
        self.assertIn("name = mixR", cfg)
        self.assertIn('outputs = [ "mixL:Out" "mixR:Out" ]', cfg)

    def test_write_surround_config(self):
        """Test writing configuration file to disk."""
        target = Path(self.test_dir) / "custom.conf"
        written = write_surround_config(target_file=target, sofa_path="/dummy/test.sofa")
        self.assertEqual(written, target)
        self.assertTrue(target.exists())
        content = target.read_text(encoding="utf-8")
        self.assertIn("/dummy/test.sofa", content)
        self.assertIn("effect_input.razer_virtual_surround_7_1", content)

    def test_ensure_systemd_service(self):
        """Test generation of user systemd unit file."""
        service_path = ensure_systemd_service()
        self.assertTrue(service_path.exists())
        content = service_path.read_text(encoding="utf-8")
        self.assertIn("[Unit]", content)
        self.assertIn("Description=Razer BlackShark V2 7.1 Virtual Surround Sound", content)
        self.assertIn("ExecStart=/usr/bin/pipewire -c", content)
        self.assertIn("Restart=on-failure", content)

    def test_is_surround_supported(self):
        """Test support detection logic."""
        with patch("shutil.which", return_value=None):
            supported, msg = is_surround_supported()
            self.assertFalse(supported)
            self.assertIn("not found", msg)

        with patch("rzropenaud_io.surround.get_sofa_path", return_value=None):
            with patch("shutil.which", return_value="/usr/bin/pipewire"):
                supported, msg = is_surround_supported()
                self.assertFalse(supported)
                self.assertIn("No SOFA HRTF", msg)

    def test_is_surround_active_mock(self):
        """Test detection of active surround sink."""
        # 1. When pw-cli succeeds
        mock_proc = MagicMock(returncode=0, stdout=f"node.name = {SURROUND_SINK_NAME}")
        with patch("subprocess.run", return_value=mock_proc):
            self.assertTrue(is_surround_active())

        # 2. When pw-cli and pactl report missing
        mock_proc_fail = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=mock_proc_fail):
            with patch("rzropenaud_io.surround.is_systemd_user_available", return_value=False):
                self.assertFalse(is_surround_active())

    def test_enable_and_disable_surround(self):
        """Test enable and disable operations."""
        with patch("rzropenaud_io.surround.is_surround_supported", return_value=(True, "Supported")):
            with patch("rzropenaud_io.surround.is_systemd_user_available", return_value=True):
                with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="active")):
                    with patch("rzropenaud_io.surround.is_surround_active", return_value=True):
                        success = enable_surround()
                        self.assertTrue(success)
                        self.assertTrue(config_mod.get_surround_7_1_enabled())

                    with patch("rzropenaud_io.surround.is_surround_active", return_value=False):
                        disabled = disable_surround()
                        self.assertTrue(disabled)
                        self.assertFalse(config_mod.get_surround_7_1_enabled())

    def test_config_persistence(self):
        """Test get_surround_7_1_enabled and set_surround_7_1_enabled."""
        self.assertFalse(config_mod.get_surround_7_1_enabled())
        config_mod.set_surround_7_1_enabled(True)
        self.assertTrue(config_mod.get_surround_7_1_enabled())
        config_mod.set_surround_7_1_enabled(False)
        self.assertFalse(config_mod.get_surround_7_1_enabled())

    def test_cli_surround_options(self):
        """Test CLI --surround-7-1 flag parsing and execution."""
        parser = build_parser()
        args_on = parser.parse_args(["--surround-7-1", "on"])
        self.assertEqual(args_on.surround_7_1, "on")

        args_off = parser.parse_args(["--surround-7-1", "off"])
        self.assertEqual(args_off.surround_7_1, "off")

        with patch("rzropenaud_io.surround.enable_surround", return_value=True) as mock_enable:
            with patch("rzropenaud_io.surround.is_surround_active", return_value=True):
                ret = main(["--surround-7-1", "on", "--no-notify"])
                self.assertEqual(ret, 0)
                mock_enable.assert_called_once()

        with patch("rzropenaud_io.surround.disable_surround", return_value=True) as mock_disable:
            ret = main(["--surround-7-1", "off", "--no-notify"])
            self.assertEqual(ret, 0)
            mock_disable.assert_called_once()

    def test_get_surround_status(self):
        """Test get_surround_status structure."""
        status = get_surround_status()
        self.assertIn("supported", status)
        self.assertIn("active", status)
        self.assertIn("config_enabled", status)
        self.assertIn("channels", status)
        self.assertEqual(status["channels"], 8)
        self.assertEqual(status["sink_name"], SURROUND_SINK_NAME)


if __name__ == "__main__":
    unittest.main()
