"""Direct DSP / memory report implementation for Razer USB Sound Card.

Reverse-engineered from Synapse USB packet captures on Razer BlackShark V2:
- Report ID 0x04 (Output / Set memory, 37 bytes)
- Report ID 0x05 (Input / Response, 37 bytes)
"""

from __future__ import annotations

import struct
from typing import List

from rzropenaud_io.constants import (
    DIRECT_ADDR_DSP_TRIGGER,
    DIRECT_ADDR_EQ_BANDS,
    DIRECT_ADDR_MIC_BOOST,
    KRAKEN_DEST_DIRECT_REG,
    KRAKEN_DEST_READ_RAM,
    KRAKEN_DEST_WRITE_RAM,
    KRAKEN_REPORT_LEN,
    REPORT_ID_KRAKEN_REQUEST,
)


def make_direct_request_report(
    destination: int,
    address: int,
    data: bytes | bytearray | List[int] = b"",
    report_id: int = REPORT_ID_KRAKEN_REQUEST,
) -> bytes:
    """Build a 37-byte direct memory request packet.

    Format:
    [0]: Report ID (0x04)
    [1]: Destination (e.g. 0x4F, 0x40, 0x00, 0x20)
    [2]: Data length
    [3]: Address High Byte
    [4]: Address Low Byte
    [5..36]: Arguments (32 bytes)
    """
    buf = bytearray(KRAKEN_REPORT_LEN)
    buf[0] = report_id & 0xFF
    buf[1] = destination & 0xFF

    payload = bytearray(data)
    dlen = min(len(payload), 32)
    # In Synapse captures, destination 0x4F/0x0F sets bits 7 & 6 (0xC0 | dlen)
    if destination in (0x4F, 0x0F):
        buf[2] = (0xC0 | dlen) & 0xFF
    else:
        buf[2] = dlen & 0xFF

    buf[3] = (address >> 8) & 0xFF
    buf[4] = address & 0xFF
    buf[5 : 5 + dlen] = payload[:dlen]

    return bytes(buf)


def make_direct_eq_packets(band_gains_db: List[int]) -> List[bytes]:
    """Generate the sequence of direct DSP register packets to set the 10-band EQ.

    Maps 10 frequency bands (-12 to +12 dB) to the BlackShark V2 DSP registers:
    31Hz, 63Hz, 125Hz, 250Hz, 500Hz, 1kHz, 2kHz, 4kHz, 8kHz, 16kHz.
    """
    packets: List[bytes] = []

    # Map dB (-12..+12) to 16-bit DSP gain coefficients
    # In Synapse captures:
    # 0 dB corresponds approximately to 0x0200
    # +12 dB corresponds to 0x07FF
    # -12 dB corresponds to 0x0080
    for idx, addr in enumerate(DIRECT_ADDR_EQ_BANDS):
        gain_db = band_gains_db[idx] if idx < len(band_gains_db) else 0
        clamped_db = max(-12, min(12, int(gain_db)))

        # Linear-in-dB mapping to 16-bit DSP fixed-point coefficient
        # 0dB -> 0x0200 (512). +12dB -> ~0x07D0 (2000). -12dB -> ~0x0080 (128).
        if clamped_db >= 0:
            coeff = int(512 + (clamped_db / 12.0) * (2000 - 512))
        else:
            coeff = int(512 + (clamped_db / 12.0) * (512 - 128))
        coeff = max(0x0080, min(0x07FF, coeff))

        coeff_low = coeff & 0xFF
        coeff_high = (coeff >> 8) & 0xFF

        # Low byte register write
        packets.append(make_direct_request_report(KRAKEN_DEST_DIRECT_REG, addr, [coeff_low]))
        # High byte register write
        packets.append(make_direct_request_report(KRAKEN_DEST_DIRECT_REG, addr + 1, [coeff_high]))
        # Read back / latch verification
        packets.append(make_direct_request_report(0x0F, DIRECT_ADDR_DSP_TRIGGER, [coeff_high]))
        # Commit latch for this band
        packets.append(make_direct_request_report(KRAKEN_DEST_DIRECT_REG, DIRECT_ADDR_DSP_TRIGGER, [0x93]))
        packets.append(make_direct_request_report(0x0F, DIRECT_ADDR_DSP_TRIGGER, [0x93]))

    # Final commit & apply sequence (from Synapse capture packets 145..161)
    packets.append(make_direct_request_report(KRAKEN_DEST_WRITE_RAM, 0x0006, [0x72]))
    packets.append(make_direct_request_report(KRAKEN_DEST_WRITE_RAM, 0x0002, [0x02]))
    # Report ID 0x31
    rep31 = bytearray(17)
    rep31[0] = 0x31
    rep31[1] = 0x06
    packets.append(bytes(rep31))
    packets.append(make_direct_request_report(KRAKEN_DEST_WRITE_RAM, 0x0006, [0xF2]))
    packets.append(make_direct_request_report(KRAKEN_DEST_WRITE_RAM, 0x0002, [0x82]))

    return packets


def make_direct_mic_boost_packet(enabled: bool) -> bytes:
    """Generate packet to set mic boost on/off in DSP register 0x1017."""
    # 0x2F = On, 0x2E = Off (from Synapse capture mic_boost_on_off.pcapng)
    val = 0x2F if enabled else 0x2E
    return make_direct_request_report(KRAKEN_DEST_WRITE_RAM, DIRECT_ADDR_MIC_BOOST, [val])
