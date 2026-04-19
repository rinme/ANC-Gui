from __future__ import annotations

from typing import Any

MANUAL_PRESET_NAME = "Manual"
PRESET_PARAM_KEYS = (
    "calib_sec",
    "highpass_hz",
    "noise_beta",
    "noise_floor",
    "ema_alpha",
    "gain_smooth",
)

BUILTIN_PRESETS: dict[str, dict[str, float]] = {
    "Quiet": {
        "calib_sec": 1.0,
        "highpass_hz": 60.0,
        "noise_beta": 0.8,
        "noise_floor": 0.03,
        "ema_alpha": 0.98,
        "gain_smooth": 0.9,
    },
    "Home": {
        "calib_sec": 1.0,
        "highpass_hz": 80.0,
        "noise_beta": 1.0,
        "noise_floor": 0.02,
        "ema_alpha": 0.96,
        "gain_smooth": 0.8,
    },
    "Home + TV Background": {
        "calib_sec": 1.5,
        "highpass_hz": 100.0,
        "noise_beta": 1.3,
        "noise_floor": 0.015,
        "ema_alpha": 0.93,
        "gain_smooth": 0.72,
    },
    "Office": {
        "calib_sec": 1.2,
        "highpass_hz": 90.0,
        "noise_beta": 1.15,
        "noise_floor": 0.02,
        "ema_alpha": 0.95,
        "gain_smooth": 0.8,
    },
    "Noisy Environment": {
        "calib_sec": 1.8,
        "highpass_hz": 120.0,
        "noise_beta": 1.5,
        "noise_floor": 0.01,
        "ema_alpha": 0.9,
        "gain_smooth": 0.65,
    },
}


def normalize_preset_values(values: Any) -> dict[str, float]:
    if not isinstance(values, dict):
        return {}
    normalized: dict[str, float] = {}
    for key in PRESET_PARAM_KEYS:
        if key in values:
            normalized[key] = float(values[key])
    return normalized


def normalized_custom_presets(raw: Any) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        return {}
    custom: dict[str, dict[str, float]] = {}
    for name, values in raw.items():
        if not isinstance(name, str):
            continue
        normalized = normalize_preset_values(values)
        if normalized:
            custom[name] = normalized
    return custom


def merged_presets(custom_presets: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    merged = dict(BUILTIN_PRESETS)
    merged.update(custom_presets)
    return merged
