"""Command Line Interface for RZROPENAUD-IO.

Control Razer BlackShark V2 (RZ04-0323 / VID 1532, PID 0529) on Arch Linux (GNOME).
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from rzropenaud_io.config import (
    clear_custom_serial,
    get_voice_preset,
    set_custom_serial,
)
from rzropenaud_io.constants import EQ_BAND_LABELS, EQ_PRESETS
from rzropenaud_io.device import (
    BlackSharkV2,
    RazerDeviceError,
    RazerNotFoundError,
    RazerPermissionError,
)
from rzropenaud_io.easyeffects import VOICE_PRESETS, EasyEffectsBridge
from rzropenaud_io.notify import DesktopNotifier


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(levelname)s: %(message)s" if not verbose else "[%(asctime)s] %(levelname)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rzropenaud-io",
        description="RZROPENAUD-IO: CLI utility for Razer BlackShark V2 (Model RZ04-0323, VID: 1532, PID: 0529).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rzropenaud-io --sidetone 50           # Set sidetone (mic monitoring) to 50%
  rzropenaud-io --sidetone 0            # Disable sidetone
  rzropenaud-io --mic-volume 85         # Set microphone input volume to 85%
  rzropenaud-io --eq game               # Apply 'game' 10-band EQ preset
  rzropenaud-io --eq "3,4,2,0,0,1,3,4,3,2"  # Apply custom 10-band gains in dB
  rzropenaud-io --mic-boost on          # Enable hardware mic boost
  rzropenaud-io --status                # Query device info and settings
  rzropenaud-io --no-notify --sidetone 40  # Update setting without desktop notification
""",
    )

    # Core control flags requested in spec
    parser.add_argument(
        "--mic-volume",
        type=int,
        metavar="0-100",
        help="Set microphone volume level (0 to 100 percent).",
    )
    parser.add_argument(
        "--sidetone",
        type=int,
        metavar="0-100",
        help="Set hardware sidetone (mic monitoring) level (0 disables, 1-100 sets volume).",
    )
    parser.add_argument(
        "--eq",
        type=str,
        metavar="PRESET|BANDS",
        help=f"Set 10-band equalizer. Presets: {', '.join(EQ_PRESETS.keys())} or comma-separated dB values.",
    )

    # Additional audio enhancements supported by headset DSP
    parser.add_argument(
        "--mic-boost",
        choices=["on", "off"],
        help="Enable or disable microphone boost.",
    )
    parser.add_argument(
        "--bass-boost",
        type=int,
        metavar="0-100",
        help="Set bass boost level (0 to 100 percent).",
    )
    parser.add_argument(
        "--voice-clarity",
        type=int,
        metavar="0-100",
        help="Set voice clarity / ambient noise reduction (0 to 100 percent).",
    )
    parser.add_argument(
        "--voice-fx",
        type=str,
        metavar="PRESET",
        choices=["off", "normal", "deep", "female", "child", "robotic", "monster", "radio"],
        help="Apply microphone voice changer preset via EasyEffects (off, deep, female, child, robotic, monster, radio).",
    )
    parser.add_argument(
        "--list-voice-fx",
        action="store_true",
        help="List available microphone voice changer presets.",
    )
    parser.add_argument(
        "--voice-sidetone", "--voice-monitor",
        choices=["on", "off"],
        dest="voice_sidetone",
        help="Enable or disable Voice FX sidetone / monitoring (listen to voice effects in your headset).",
    )

    # Serial Number Configuration
    parser.add_argument(
        "--set-serial",
        type=str,
        metavar="SERIAL",
        help="Configure the physical headset serial number (found under left ear cushion).",
    )
    parser.add_argument(
        "--clear-serial",
        action="store_true",
        help="Clear user-configured headset serial number, reverting to hardware dongle default.",
    )

    # Query & Device Info
    parser.add_argument(
        "-s", "--status", "--info",
        action="store_true",
        dest="status",
        help="Query and print headset status, serial number, and firmware version.",
    )

    # UI / Notification options
    notify_group = parser.add_mutually_exclusive_group()
    notify_group.add_argument(
        "--notify",
        action="store_true",
        default=True,
        help="Send native GNOME desktop notification via notify-send (default).",
    )
    notify_group.add_argument(
        "--no-notify",
        action="store_false",
        dest="notify",
        help="Suppress desktop notifications.",
    )

    # Hardware communication options
    parser.add_argument(
        "--direct",
        action="store_true",
        default=True,
        help="Also write direct DSP memory registers for EQ/Boost (default).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output and raw USB HID hex dumps.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    notifier = DesktopNotifier(enabled=args.notify)

    # If no arguments provided, display help
    has_actions = any([
        args.mic_volume is not None,
        args.sidetone is not None,
        args.eq is not None,
        args.mic_boost is not None,
        args.bass_boost is not None,
        args.voice_clarity is not None,
        args.voice_fx is not None,
        args.voice_sidetone is not None,
        args.list_voice_fx,
        args.set_serial is not None,
        args.clear_serial,
        args.status,
    ])

    if not has_actions:
        parser.print_help()
        return 0

    if args.list_voice_fx:
        print("Available Microphone Voice Changer Presets (EasyEffects):")
        for key, info in VOICE_PRESETS.items():
            print(f"  {key:<10} - {info['title']}: {info['subtitle']}")
        return 0

    # Handle voice preset changes
    if args.voice_fx is not None:
        ee = EasyEffectsBridge()
        enabled = args.voice_fx not in ("off", "normal")
        ee.apply_voice_preset(args.voice_fx, enabled=enabled, sync=True)
        preset_info = VOICE_PRESETS.get(args.voice_fx.lower(), {})
        title = preset_info.get("title", args.voice_fx)
        if enabled:
            print(f"✓ Microphone voice changer set to '{title}' (EasyEffects)")
        else:
            print("✓ Microphone voice changer disabled (Passthrough)")

    # Handle voice sidetone (monitoring)
    if args.voice_sidetone is not None:
        ee = EasyEffectsBridge()
        mon_enabled = args.voice_sidetone == "on"
        ee.set_microphone_monitoring(mon_enabled)
        state_str = "Enabled" if mon_enabled else "Disabled"
        print(f"✓ Voice FX Sidetone (monitoring in headset) {state_str}")

    # Handle serial configuration
    if args.set_serial is not None or args.clear_serial:
        if args.clear_serial or (args.set_serial and args.set_serial.strip().lower() in ("", "default", "none")):
            clear_custom_serial()
            print("✓ Reset headset serial number to hardware default (00000000).")
            notifier.send("Razer BlackShark V2", "Serial number reset to hardware default.")
        else:
            sn = args.set_serial.strip()
            set_custom_serial(sn)
            print(f"✓ Saved headset physical serial number: {sn}")
            notifier.send("Razer BlackShark V2", f"Headset serial set to {sn}")

    # Check if there are other hardware actions to perform
    hw_actions = any([
        args.mic_volume is not None,
        args.sidetone is not None,
        args.eq is not None,
        args.mic_boost is not None,
        args.bass_boost is not None,
        args.voice_clarity is not None,
        args.status,
    ])
    if not hw_actions:
        return 0

    try:
        with BlackSharkV2(verbose=args.verbose) as dev:
            # Query status
            if args.status:
                info = dev.get_device_info()
                print("==================================================")
                print("           RZROPENAUD-IO DEVICE STATUS            ")
                print("==================================================")
                print(f"Device:           {info['model']}")
                print(f"USB ID:           {info['vid']}:{info['pid']}")
                print(f"Interface:        {info['interface_number']}")
                print(f"Firmware:         {info['firmware_version']}")
                print(f"Serial Number:    {info['serial_number']}")
                voice_status = f"{info.get('voice_preset', 'off')} ({'Enabled' if info.get('voice_fx_enabled') else 'Disabled'})"
                print(f"Voice Changer:    {voice_status}")
                voice_mon = "Enabled" if info.get("voice_monitor_enabled") else "Disabled"
                print(f"Voice Sidetone:   {voice_mon}")
                print("==================================================")

            # Apply mic volume
            if args.mic_volume is not None:
                vol = max(0, min(100, args.mic_volume))
                dev.set_mic_volume(vol)
                print(f"✓ Microphone volume set to {vol}%")
                notifier.notify_mic_volume(vol)

            # Apply sidetone
            if args.sidetone is not None:
                st_vol = max(0, min(100, args.sidetone))
                enabled = st_vol > 0
                dev.set_sidetone(st_vol, enabled=enabled)
                status_str = f"{st_vol}%" if enabled else "Disabled (0%)"
                print(f"✓ Sidetone set to {status_str}")
                notifier.notify_sidetone(st_vol, enabled=enabled)

            # Apply equalizer
            if args.eq is not None:
                preset_name, bands = dev.set_equalizer(args.eq, use_direct=args.direct)
                band_desc = ", ".join(f"{lbl}: {g:+d}dB" for lbl, g in zip(EQ_BAND_LABELS, bands))
                print(f"✓ Equalizer profile set to '{preset_name}'")
                print(f"  Bands: [{band_desc}]")
                notifier.notify_eq(preset_name, f"{bands[0]:+d}dB to {bands[-1]:+d}dB")

            # Apply mic boost
            if args.mic_boost is not None:
                boost_enabled = args.mic_boost == "on"
                dev.set_mic_boost(boost_enabled, use_direct=args.direct)
                state_str = "Enabled" if boost_enabled else "Disabled"
                print(f"✓ Microphone boost {state_str}")
                notifier.notify_mic_boost(boost_enabled)

            # Apply bass boost
            if args.bass_boost is not None:
                bb_vol = max(0, min(100, args.bass_boost))
                dev.set_bass_boost(bb_vol)
                print(f"✓ Bass boost set to {bb_vol}%")
                notifier.notify_bass_boost(bb_vol)

            # Apply voice clarity
            if args.voice_clarity is not None:
                vc_vol = max(0, min(100, args.voice_clarity))
                dev.set_voice_clarity(vc_vol)
                print(f"✓ Voice clarity set to {vc_vol}%")

    except RazerPermissionError as e:
        print("\n[!] ERROR: PERMISSION DENIED TO USB HID DEVICE", file=sys.stderr)
        print(f"{e}\n", file=sys.stderr)
        print("To fix permissions without needing root:", file=sys.stderr)
        print("  1. Copy the udev rule:", file=sys.stderr)
        print("     sudo cp 99-razer.rules /etc/udev/rules.d/", file=sys.stderr)
        print("  2. Reload and trigger udev:", file=sys.stderr)
        print("     sudo udevadm control --reload-rules && sudo udevadm trigger", file=sys.stderr)
        print("  3. (Alternative) Temporarily run with sudo.", file=sys.stderr)
        return 2

    except RazerNotFoundError as e:
        print(f"\n[!] ERROR: {e}", file=sys.stderr)
        print("Ensure the Razer BlackShark V2 USB Sound Card is connected.", file=sys.stderr)
        return 1

    except RazerDeviceError as e:
        print(f"\n[!] DEVICE ERROR: {e}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
