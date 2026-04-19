from __future__ import annotations

import argparse
import threading

from core import AudioRunner, apply_cli_overrides, load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Real-time Active Noise Cancelling (mic noise suppression)"
    )
    p.add_argument("--gui", action="store_true", help="Launch the PyQt6 GUI")
    p.add_argument(
        "--samplerate", type=int, default=None, help="Sample rate (default from config)"
    )
    p.add_argument("--frame_ms", type=int, default=None, help="Frame length in ms")
    p.add_argument("--calib_sec", type=float, default=None, help="Calibration seconds")
    p.add_argument("--device_in", type=str, default=None, help="Input device index/name")
    p.add_argument("--device_out", type=str, default=None, help="Output device index/name")
    p.add_argument("--highpass", type=float, default=None, help="High-pass cutoff Hz (0 disable)")
    p.add_argument("--config", type=str, default="config.yaml")
    p.add_argument("--list-devices", action="store_true", help="Print devices and exit")
    return p.parse_args(argv)


def _print_status(msg: str) -> None:
    print(f"• {msg}")


def run_cli(args: argparse.Namespace) -> int:
    cfg = apply_cli_overrides(load_config(args.config), args)

    if args.list_devices:
        for index, dev in enumerate(AudioRunner.list_devices()):
            print(f"{index:>2}: {dev['name']}")
        return 0

    runner = AudioRunner(cfg, status_callback=_print_status)
    stop_event = threading.Event()

    try:
        runner.run_with_calibration(stop_event)
    except KeyboardInterrupt:
        stop_event.set()
        _print_status("Stopping...")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.gui:
        from gui.app import run_gui

        initial_cfg = apply_cli_overrides(load_config(args.config), args)
        return run_gui(config_path=args.config, initial_cfg=initial_cfg)

    return run_cli(args)
