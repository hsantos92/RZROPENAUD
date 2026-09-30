"""RZROPENAUD-IO: Linux CLI utility for Razer BlackShark V2 (RZ04-0323 / VID 1532, PID 0529)."""

__version__ = "0.1.0"

from rzropenaud_io.constants import BLACKSHARK_V2_PID, RAZER_VENDOR_ID
from rzropenaud_io.device import BlackSharkV2
from rzropenaud_io.protocol import RazerReport

__all__ = ["BlackSharkV2", "RazerReport", "RAZER_VENDOR_ID", "BLACKSHARK_V2_PID"]
