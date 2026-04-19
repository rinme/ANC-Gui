from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from dsp import NoiseSuppressor

StatusCallback = Callable[[str], None]
LevelCallback = Callable[[float], None]


class AudioRunner:
    def __init__(
        self,
        cfg: dict,
        status_callback: StatusCallback | None = None,
        level_callback: LevelCallback | None = None,
    ):
        self.cfg = dict(cfg)
        self.status_callback = status_callback
        self.level_callback = level_callback

        sr = int(self.cfg["samplerate"])
        frame_ms = int(self.cfg["frame_ms"])

        self.ns = NoiseSuppressor(
            sr=sr,
            frame_ms=frame_ms,
            beta=float(self.cfg["noise_beta"]),
            noise_floor=float(self.cfg["noise_floor"]),
            ema_alpha=float(self.cfg["ema_alpha"]),
            gain_smooth=float(self.cfg["gain_smooth"]),
            highpass_hz=float(self.cfg["highpass_hz"]),
        )
        self.hop = self.ns.hop
        self._stream: sd.Stream | None = None

    @staticmethod
    def list_devices() -> list[dict]:
        devices = sd.query_devices()
        if isinstance(devices, tuple):
            return [dict(d) for d in devices]
        return [dict(d) for d in devices]

    def _status(self, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(message)

    def _callback(self, indata, outdata, frames, time_info, status) -> None:
        if status:
            self._status(f"Audio status: {status}")

        x = indata[:, 0].copy()
        if len(x) != self.hop:
            x = x[: self.hop] if len(x) > self.hop else np.pad(x, (0, self.hop - len(x)))

        y = self.ns.process(x)
        outdata[:, 0] = y
        if outdata.shape[1] > 1:
            outdata[:, 1] = y

        if self.level_callback is not None:
            rms = float(np.sqrt(np.mean(y**2)))
            self.level_callback(rms)

    def calibrate(self, stop_event: threading.Event | None = None) -> None:
        self._status("Calibrating noise profile...")
        sr = int(self.cfg["samplerate"])
        calib_sec = float(self.cfg["calib_sec"])
        t_end = time.time() + calib_sec

        with sd.InputStream(
            device=self.cfg["device_in"],
            samplerate=sr,
            blocksize=self.hop,
            dtype="float32",
            channels=1,
        ) as stream:
            while time.time() < t_end:
                if stop_event is not None and stop_event.is_set():
                    self._status("Calibration canceled.")
                    return
                inbuf, overflowed = stream.read(self.hop)
                if overflowed:
                    self._status("Input overflow during calibration.")
                self.ns.calibrate_noise(inbuf[:, 0])

        self._status("Calibration complete.")

    def run(self, stop_event: threading.Event) -> None:
        sr = int(self.cfg["samplerate"])
        self._status(
            f"Starting suppression (SR={sr} Hz, frame={self.cfg['frame_ms']} ms, hop={self.hop})."
        )

        with sd.Stream(
            device=(self.cfg["device_in"], self.cfg["device_out"]),
            samplerate=sr,
            blocksize=self.hop,
            dtype="float32",
            channels=1,
            callback=self._callback,
        ) as stream:
            self._stream = stream
            self._status("Running.")
            while not stop_event.is_set():
                time.sleep(0.1)

        self._stream = None
        self._status("Stopped.")

    def run_with_calibration(self, stop_event: threading.Event) -> None:
        self.calibrate(stop_event=stop_event)
        if stop_event.is_set():
            return
        self.run(stop_event=stop_event)
