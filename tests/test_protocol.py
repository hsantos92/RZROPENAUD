"""Unit tests for RZROPENAUD-IO protocol and report generation."""

import unittest

from rzropenaud_io.constants import (
    CMD_ID_GET_EQUALIZER,
    CMD_ID_GET_FIRMWARE_VERSION,
    CMD_ID_GET_MIC_VOLUME,
    CMD_ID_GET_SERIAL_NUMBER,
    CMD_ID_GET_SIDETONE,
    CMD_ID_SET_BASS_BOOST,
    CMD_ID_SET_EQUALIZER,
    CMD_ID_SET_MIC_BOOST,
    CMD_ID_SET_MIC_VOLUME,
    CMD_ID_SET_SIDETONE,
    CMD_ID_SET_VOICE_CLARITY,
    COMMAND_CLASS_AUDIO,
    COMMAND_CLASS_SYSTEM,
    EQ_PRESETS,
    RAZER_CMD_BUSY,
    RAZER_CMD_NEW,
    RAZER_CMD_SUCCESSFUL,
    RAZER_REPORT_LEN,
)
from rzropenaud_io.direct import (
    DIRECT_ADDR_DSP_TRIGGER,
    DIRECT_ADDR_EQ_BANDS,
    DIRECT_ADDR_MIC_BOOST,
    make_direct_eq_packets,
    make_direct_mic_boost_packet,
    make_direct_request_report,
)
from rzropenaud_io.protocol import (
    RazerReport,
    calculate_razer_crc,
    make_bass_boost_report,
    make_equalizer_report,
    make_get_firmware_version_report,
    make_get_mic_volume_report,
    make_get_serial_number_report,
    make_get_sidetone_report,
    make_mic_boost_report,
    make_mic_volume_report,
    make_sidetone_report,
    make_voice_clarity_report,
)


class TestRazerProtocol(unittest.TestCase):
    """Test standard 90-byte Razer HID transaction protocol."""

    def test_crc_calculation(self):
        buf = bytearray(90)
        # Set bytes 2..87 to known values
        buf[2] = 0xAA
        buf[3] = 0x55
        # CRC is XOR of bytes 2..87: 0xAA ^ 0x55 = 0xFF
        expected = 0xAA ^ 0x55
        self.assertEqual(calculate_razer_crc(buf), expected)

    def test_report_packing_and_length(self):
        report = RazerReport(
            status=RAZER_CMD_NEW,
            transaction_id=0x1F,
            command_class=COMMAND_CLASS_AUDIO,
            command_id=CMD_ID_SET_SIDETONE,
            arguments=bytearray([0x01, 50]),
        )
        packed = report.pack()
        self.assertEqual(len(packed), RAZER_REPORT_LEN)
        self.assertEqual(packed[0], RAZER_CMD_NEW)
        self.assertEqual(packed[1], 0x1F)
        self.assertEqual(packed[6], COMMAND_CLASS_AUDIO)
        self.assertEqual(packed[7], CMD_ID_SET_SIDETONE)
        self.assertEqual(packed[8], 0x01)
        self.assertEqual(packed[9], 50)
        self.assertEqual(packed[88], calculate_razer_crc(packed))
        self.assertEqual(packed[89], 0x00)

    def test_report_unpacking(self):
        report = RazerReport(
            status=RAZER_CMD_SUCCESSFUL,
            transaction_id=0x1F,
            command_class=COMMAND_CLASS_SYSTEM,
            command_id=CMD_ID_GET_FIRMWARE_VERSION,
            arguments=bytearray([0x01, 0x02]),
        )
        packed = report.pack()
        unpacked = RazerReport.unpack(packed)
        self.assertEqual(unpacked.status, RAZER_CMD_SUCCESSFUL)
        self.assertTrue(unpacked.is_successful())
        self.assertEqual(unpacked.command_class, COMMAND_CLASS_SYSTEM)
        self.assertEqual(unpacked.command_id, CMD_ID_GET_FIRMWARE_VERSION)
        self.assertEqual(unpacked.arguments[0], 0x01)
        self.assertEqual(unpacked.arguments[1], 0x02)

    def test_report_unpack_with_report_id_prefix(self):
        # When read from hidraw, report can be 91 bytes with Report ID 0x00 prefix
        report = RazerReport(
            status=RAZER_CMD_SUCCESSFUL,
            command_class=COMMAND_CLASS_AUDIO,
            command_id=CMD_ID_GET_MIC_VOLUME,
            arguments=bytearray([75]),
        )
        packed_91 = b"\x00" + report.pack()
        self.assertEqual(len(packed_91), 91)
        unpacked = RazerReport.unpack(packed_91)
        self.assertEqual(unpacked.status, RAZER_CMD_SUCCESSFUL)
        self.assertEqual(unpacked.arguments[0], 75)

    def test_mic_volume_report(self):
        pkt = make_mic_volume_report(85)
        self.assertEqual(len(pkt), 90)
        unpacked = RazerReport.unpack(pkt)
        self.assertEqual(unpacked.command_class, COMMAND_CLASS_AUDIO)
        self.assertEqual(unpacked.command_id, CMD_ID_SET_MIC_VOLUME)
        self.assertEqual(unpacked.arguments[0], 85)

        # Clamping test
        pkt_clamped = make_mic_volume_report(150)
        self.assertEqual(RazerReport.unpack(pkt_clamped).arguments[0], 100)

    def test_sidetone_report(self):
        pkt = make_sidetone_report(50)
        unpacked = RazerReport.unpack(pkt)
        self.assertEqual(unpacked.command_class, COMMAND_CLASS_AUDIO)
        self.assertEqual(unpacked.command_id, CMD_ID_SET_SIDETONE)
        self.assertEqual(unpacked.arguments[0], 0x01)  # enabled
        self.assertEqual(unpacked.arguments[1], 50)    # volume

        # Disabled sidetone (volume 0)
        pkt_zero = make_sidetone_report(0)
        unpacked_zero = RazerReport.unpack(pkt_zero)
        self.assertEqual(unpacked_zero.arguments[0], 0x00)  # disabled

    def test_equalizer_report(self):
        bands = EQ_PRESETS["game"]
        pkt = make_equalizer_report(1, bands)
        unpacked = RazerReport.unpack(pkt)
        self.assertEqual(unpacked.command_class, COMMAND_CLASS_AUDIO)
        self.assertEqual(unpacked.command_id, CMD_ID_SET_EQUALIZER)
        self.assertEqual(unpacked.arguments[0], 1)  # preset id
        # First band: +3dB
        self.assertEqual(unpacked.arguments[1], 3)

    def test_direct_dsp_packets(self):
        eq_pkts = make_direct_eq_packets([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertGreater(len(eq_pkts), 10)
        for pkt in eq_pkts:
            self.assertEqual(len(pkt), 37)
            self.assertEqual(pkt[0], 0x04)

        boost_pkt = make_direct_mic_boost_packet(True)
        self.assertEqual(len(boost_pkt), 37)
        self.assertEqual(boost_pkt[0], 0x04)
        self.assertEqual(boost_pkt[1], 0x40)  # KRAKEN_DEST_WRITE_RAM
        addr = (boost_pkt[3] << 8) | boost_pkt[4]
        self.assertEqual(addr, DIRECT_ADDR_MIC_BOOST)
        self.assertEqual(boost_pkt[5], 0x2F)  # 0x2F = On


if __name__ == "__main__":
    unittest.main()
