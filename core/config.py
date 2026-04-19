from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "samplerate": 16000,
    "frame_ms": 20,
    "calib_sec": 1.0,
    "highpass_hz": 80,
    "noise_beta": 1.0,
    "noise_floor": 0.02,
    "ema_alpha": 0.96,
    "gain_smooth": 0.8,
    "device_in": "default",
    "device_out": "default",
    "selected_preset": "Manual",
    "custom_presets": {},
    "device_view_mode": "simple",
    "theme": "system",
}


def load_config(path: str) -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    file_path = Path(path)
    if not file_path.exists():
        return cfg

    with file_path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config at {path} must be a mapping.")

    cfg.update(loaded)
    if not isinstance(cfg.get("custom_presets"), dict):
        cfg["custom_presets"] = {}
    if cfg.get("theme") not in {"system", "light", "dark"}:
        cfg["theme"] = "system"
    if cfg.get("device_view_mode") not in {"simple", "advanced"}:
        cfg["device_view_mode"] = "simple"
    return cfg


def save_config(path: str, cfg: dict[str, Any]) -> None:
    file_path = Path(path)
    serializable = {k: cfg.get(k, v) for k, v in DEFAULT_CONFIG.items()}
    with file_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(serializable, f, sort_keys=False)


def apply_cli_overrides(cfg: dict[str, Any], args: Any) -> dict[str, Any]:
    merged = dict(cfg)

    if getattr(args, "samplerate", None) is not None:
        merged["samplerate"] = args.samplerate
    if getattr(args, "frame_ms", None) is not None:
        merged["frame_ms"] = args.frame_ms
    if getattr(args, "calib_sec", None) is not None:
        merged["calib_sec"] = args.calib_sec
    if getattr(args, "highpass", None) is not None:
        merged["highpass_hz"] = args.highpass
    if getattr(args, "device_in", None) is not None:
        merged["device_in"] = args.device_in
    if getattr(args, "device_out", None) is not None:
        merged["device_out"] = args.device_out

    return merged
