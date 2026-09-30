"""Constants and protocol definitions for RZROPENAUD-IO.

Target Hardware: Razer BlackShark V2 (Model RZ04-0323)
USB VID: 0x1532, USB PID: 0x0529 (Razer USB Sound Card)
"""

# USB Device Identifiers
RAZER_VENDOR_ID: int = 0x1532
BLACKSHARK_V2_PID: int = 0x0529
DEVICE_MODEL_NAME: str = "Razer BlackShark V2 (RZ04-0323)"
DEVICE_NAME_SOUND_CARD: str = "Razer USB Sound Card"

# Target HID Interface on USB Sound Card (Interface 3 is the HID control interface)
TARGET_HID_INTERFACE: int = 3

# Razer Standard 90-byte Protocol Report Parameters
RAZER_REPORT_LEN: int = 90
RAZER_ARGUMENT_LEN: int = 80
DEFAULT_TRANSACTION_ID: int = 0x1F  # or 0xFF

# Status Responses (Byte 0 in acknowledgement report)
RAZER_CMD_NEW: int = 0x00
RAZER_CMD_BUSY: int = 0x01
RAZER_CMD_SUCCESSFUL: int = 0x02
RAZER_CMD_FAILURE: int = 0x03
RAZER_CMD_TIMEOUT: int = 0x04
RAZER_CMD_NOT_SUPPORTED: int = 0x05

STATUS_NAMES = {
    RAZER_CMD_NEW: "New Command / Request",
    RAZER_CMD_BUSY: "Device Busy",
    RAZER_CMD_SUCCESSFUL: "Successful",
    RAZER_CMD_FAILURE: "Command Failed",
    RAZER_CMD_TIMEOUT: "Device Timeout",
    RAZER_CMD_NOT_SUPPORTED: "Command Not Supported",
}

# Razer Protocol Command Classes
COMMAND_CLASS_SYSTEM: int = 0x00       # System, firmware version, serial number
COMMAND_CLASS_CUSTOM: int = 0x01       # Configuration / device profiles
COMMAND_CLASS_DEVICE: int = 0x02       # Device-specific settings
COMMAND_CLASS_AUDIO: int = 0x08        # Audio controls (Mic, Sidetone, EQ, Bass, Clarity)

# System Command IDs (Class 0x00)
CMD_ID_GET_FIRMWARE_VERSION: int = 0x81
CMD_ID_GET_SERIAL_NUMBER: int = 0x82
CMD_ID_SET_DEVICE_MODE: int = 0x04
CMD_ID_GET_DEVICE_MODE: int = 0x84

# Audio Command IDs (Class 0x08)
CMD_ID_SET_MIC_VOLUME: int = 0x01
CMD_ID_GET_MIC_VOLUME: int = 0x81
CMD_ID_SET_SIDETONE: int = 0x02
CMD_ID_GET_SIDETONE: int = 0x82
CMD_ID_SET_EQUALIZER: int = 0x03
CMD_ID_GET_EQUALIZER: int = 0x83
CMD_ID_SET_MIC_BOOST: int = 0x05
CMD_ID_GET_MIC_BOOST: int = 0x85
CMD_ID_SET_VOICE_CLARITY: int = 0x06
CMD_ID_GET_VOICE_CLARITY: int = 0x86
CMD_ID_SET_BASS_BOOST: int = 0x07
CMD_ID_GET_BASS_BOOST: int = 0x87
CMD_ID_SET_SPATIAL_AUDIO: int = 0x08
CMD_ID_GET_SPATIAL_AUDIO: int = 0x88

# 10-Band Equalizer Frequency Labels (Hz)
EQ_BAND_LABELS = [
    "31Hz", "63Hz", "125Hz", "250Hz", "500Hz",
    "1kHz", "2kHz", "4kHz", "8kHz", "16kHz"
]

# Preset 10-Band Equalizer Gains (dB from -12 to +12)
EQ_PRESETS = {
    "flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "game": [3, 4, 2, 0, 0, 1, 3, 4, 3, 2],
    "movie": [4, 5, 3, 0, 0, 2, 3, 3, 4, 4],
    "music": [3, 2, 0, -1, 0, 2, 3, 3, 2, 1],
    "voice": [-4, -2, 0, 2, 4, 4, 3, 1, -1, -3],
    "esports": [-2, -1, 0, 1, 3, 5, 5, 4, 2, 0],
    "bass-boost": [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
}

# Direct DSP / Kraken Memory Protocol (37-byte reports from Wireshark captures)
REPORT_ID_KRAKEN_REQUEST: int = 0x04
REPORT_ID_KRAKEN_RESPONSE: int = 0x05
KRAKEN_REPORT_LEN: int = 37

KRAKEN_DEST_READ_RAM: int = 0x00
KRAKEN_DEST_READ_EEPROM: int = 0x20
KRAKEN_DEST_WRITE_RAM: int = 0x40
KRAKEN_DEST_DIRECT_REG: int = 0x4F

# DSP Direct Memory Addresses for EQ (10 bands)
DIRECT_ADDR_EQ_BANDS = [
    0x1581, 0x1583, 0x1585, 0x1587, 0x1589,
    0x158B, 0x158D, 0x158F, 0x1591, 0x1593
]
DIRECT_ADDR_DSP_TRIGGER: int = 0x1154
DIRECT_ADDR_MIC_BOOST: int = 0x1017
