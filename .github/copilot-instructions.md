# Copilot Instructions for ANC-Gui

## Build, test, and lint commands

- This repository currently has **no defined build, lint, or automated test commands** (no test suite/config files are present). Do not invent `pytest`, `ruff`, `mypy`, or CI commands.
- Primary run command:
  - `python main.py`
- Helpful runtime command for device setup/debugging:
  - `python main.py --list-devices`
- **Single-test command:** not available because there is no test suite in this repository yet.

## High-level architecture

- `main.py` is the orchestration layer:
  - Parses CLI args
  - Loads config defaults and optional YAML file
  - Applies CLI overrides on top of config values
  - Owns calibration and real-time stream lifecycle through `sounddevice`
- `dsp.py` contains the DSP engine (`NoiseSuppressor`) and helpers (`hann_sqrt`, `design_highpass`):
  - Frame/hop setup (50% overlap)
  - Noise calibration update path (`calibrate_noise`)
  - Real-time processing path (`process`) with high-pass, spectral subtraction, gain smoothing, and OLA synthesis
- `config.yaml` is optional runtime configuration; values are merged into in-code defaults in `main.py`, then overridden by CLI flags.
- End-to-end flow:
  - Parse args -> merge config -> create `NoiseSuppressor` -> run calibration stream -> run callback-based real-time suppression stream.

## Key conventions in this codebase

- Keep DSP logic in root `dsp.py`; runtime imports use `from dsp import NoiseSuppressor`.
- Preserve config precedence implemented in `main.py`:
  - In-code defaults -> `config.yaml` -> CLI overrides.
- Preserve the stream/block contract:
  - `blocksize` is set to `ns.hop`, and `NoiseSuppressor` assumes hop = frame_len/2.
  - Callback guards against block-size mismatch by trimming/padding to hop length.
- Processing is mono-first:
  - Input reads `indata[:, 0]`
  - Output writes channel 0 and mirrors to channel 1 when present.
- Calibration is a distinct phase before streaming:
  - `ns.calibrate_noise(...)` is called on hop-sized captured chunks for `calib_sec` before entering the real-time callback loop.
