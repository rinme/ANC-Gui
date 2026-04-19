from __future__ import annotations

import threading
from collections import Counter
from typing import Any

import sounddevice as sd

from core import AudioRunner, load_config, save_config
from gui.presets import (
    BUILTIN_PRESETS,
    MANUAL_PRESET_NAME,
    PRESET_PARAM_KEYS,
    merged_presets,
    normalized_custom_presets,
)

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtWidgets import (
        QApplication,
        QComboBox,
        QDoubleSpinBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise RuntimeError("PyQt6 is required for GUI mode. Install it via pip.") from exc


def _theme_stylesheet(theme: str) -> str:
    if theme == "dark":
        return """
QWidget { background-color: #1f1f1f; color: #f2f2f2; }
QGroupBox { border: 1px solid #3a3a3a; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton { background-color: #2f2f2f; border: 1px solid #444; padding: 6px; }
QPushButton:hover { background-color: #3a3a3a; }
QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { background-color: #2b2b2b; border: 1px solid #444; }
QProgressBar { border: 1px solid #444; text-align: center; }
QProgressBar::chunk { background-color: #5b9bd5; }
"""
    if theme == "light":
        return """
QGroupBox { border: 1px solid #d6d6d6; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton { padding: 6px; }
"""
    return ""


class AudioWorker(QThread):
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    level_changed = pyqtSignal(float)
    running_changed = pyqtSignal(bool)

    def __init__(self, cfg: dict[str, Any]):
        super().__init__()
        self.cfg = cfg
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self.running_changed.emit(True)
        runner = AudioRunner(
            self.cfg,
            status_callback=self.status_changed.emit,
            level_callback=self.level_changed.emit,
        )
        try:
            runner.run_with_calibration(self._stop_event)
        except (sd.PortAudioError, RuntimeError, ValueError, OSError) as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.running_changed.emit(False)


class MainWindow(QMainWindow):
    def __init__(self, config_path: str, initial_cfg: dict[str, Any]):
        super().__init__()
        self.config_path = config_path
        self.cfg = dict(initial_cfg)
        self.custom_presets = normalized_custom_presets(self.cfg.get("custom_presets", {}))
        self.worker: AudioWorker | None = None

        self.setWindowTitle("ANC-Gui")
        self.resize(820, 700)

        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        audio_group = QGroupBox("Audio Devices")
        audio_form = QFormLayout(audio_group)
        self.device_view_mode_combo = QComboBox()
        self.device_view_mode_combo.addItem("Simple", "simple")
        self.device_view_mode_combo.addItem("Advanced", "advanced")
        self.input_device_combo = QComboBox()
        self.output_device_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh devices")
        audio_form.addRow("Modes", self.device_view_mode_combo)
        audio_form.addRow("Input device", self.input_device_combo)
        audio_form.addRow("Output device", self.output_device_combo)
        audio_form.addRow("", self.refresh_button)
        layout.addWidget(audio_group)

        preset_group = QGroupBox("Presets")
        preset_form = QFormLayout(preset_group)
        self.preset_combo = QComboBox()
        preset_buttons = QHBoxLayout()
        self.save_preset_button = QPushButton("Save current as preset")
        self.delete_preset_button = QPushButton("Delete selected custom preset")
        preset_buttons.addWidget(self.save_preset_button)
        preset_buttons.addWidget(self.delete_preset_button)
        preset_buttons_wrap = QWidget()
        preset_buttons_wrap.setLayout(preset_buttons)
        preset_form.addRow("Profile", self.preset_combo)
        preset_form.addRow("", preset_buttons_wrap)
        layout.addWidget(preset_group)

        processing_group = QGroupBox("Processing")
        processing_form = QFormLayout(processing_group)

        self.samplerate_spin = QSpinBox()
        self.samplerate_spin.setRange(8000, 192000)
        self.samplerate_spin.setSingleStep(1000)
        self.samplerate_spin.setValue(int(self.cfg.get("samplerate", 16000)))

        self.frame_ms_spin = QSpinBox()
        self.frame_ms_spin.setRange(10, 100)
        self.frame_ms_spin.setValue(int(self.cfg.get("frame_ms", 20)))

        self.calib_sec_spin = QDoubleSpinBox()
        self.calib_sec_spin.setRange(0.1, 10.0)
        self.calib_sec_spin.setSingleStep(0.1)
        self.calib_sec_spin.setValue(float(self.cfg.get("calib_sec", 1.0)))

        self.highpass_spin = QDoubleSpinBox()
        self.highpass_spin.setRange(0.0, 500.0)
        self.highpass_spin.setSingleStep(5.0)
        self.highpass_spin.setValue(float(self.cfg.get("highpass_hz", 80.0)))

        self.noise_beta_spin = QDoubleSpinBox()
        self.noise_beta_spin.setRange(0.1, 4.0)
        self.noise_beta_spin.setSingleStep(0.1)
        self.noise_beta_spin.setValue(float(self.cfg.get("noise_beta", 1.0)))

        self.noise_floor_spin = QDoubleSpinBox()
        self.noise_floor_spin.setRange(0.0, 1.0)
        self.noise_floor_spin.setSingleStep(0.01)
        self.noise_floor_spin.setValue(float(self.cfg.get("noise_floor", 0.02)))

        self.ema_alpha_spin = QDoubleSpinBox()
        self.ema_alpha_spin.setRange(0.5, 0.999)
        self.ema_alpha_spin.setSingleStep(0.005)
        self.ema_alpha_spin.setValue(float(self.cfg.get("ema_alpha", 0.96)))

        self.gain_smooth_spin = QDoubleSpinBox()
        self.gain_smooth_spin.setRange(0.0, 0.99)
        self.gain_smooth_spin.setSingleStep(0.01)
        self.gain_smooth_spin.setValue(float(self.cfg.get("gain_smooth", 0.8)))

        processing_form.addRow("Sample rate", self.samplerate_spin)
        processing_form.addRow("Frame (ms)", self.frame_ms_spin)
        processing_form.addRow("Calibration (sec)", self.calib_sec_spin)
        processing_form.addRow("High-pass (Hz)", self.highpass_spin)
        processing_form.addRow("Noise beta", self.noise_beta_spin)
        processing_form.addRow("Noise floor", self.noise_floor_spin)
        processing_form.addRow("EMA alpha", self.ema_alpha_spin)
        processing_form.addRow("Gain smooth", self.gain_smooth_spin)
        layout.addWidget(processing_group)

        appearance_group = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance_group)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("System", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.save_button = QPushButton("Save settings")
        appearance_form.addRow("Theme", self.theme_combo)
        appearance_form.addRow("", self.save_button)
        layout.addWidget(appearance_group)

        runtime_group = QGroupBox("Runtime")
        runtime_layout = QVBoxLayout(runtime_group)
        btn_row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        btn_row.addWidget(self.start_button)
        btn_row.addWidget(self.stop_button)
        runtime_layout.addLayout(btn_row)

        level_form = QFormLayout()
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        level_form.addRow("Output level", self.level_bar)
        runtime_layout.addLayout(level_form)

        self.status_label = QLabel("Idle")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        runtime_layout.addWidget(self.status_label)
        runtime_layout.addWidget(self.log_view)
        layout.addWidget(runtime_group)

        self.refresh_button.clicked.connect(self.refresh_devices)
        self.device_view_mode_combo.currentIndexChanged.connect(self._on_device_mode_changed)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.save_preset_button.clicked.connect(self.save_current_as_preset)
        self.delete_preset_button.clicked.connect(self.delete_selected_custom_preset)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.start_button.clicked.connect(self.start_audio)
        self.stop_button.clicked.connect(self.stop_audio)
        self.save_button.clicked.connect(self.save_settings)

        self._set_combo_by_data(
            self.device_view_mode_combo, self.cfg.get("device_view_mode", "simple")
        )
        self._set_combo_by_data(self.theme_combo, self.cfg.get("theme", "system"))
        self._populate_presets()
        self.refresh_devices()
        self._apply_selected_devices()
        self._set_combo_by_data(self.preset_combo, self.cfg.get("selected_preset", MANUAL_PRESET_NAME))
        self._apply_theme(self.theme_combo.currentData())
        self._append_log("GUI ready.")

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, target: Any) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == target:
                combo.setCurrentIndex(i)
                return

    @staticmethod
    def _restore_selection(combo: QComboBox, target: Any) -> None:
        if target is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == target:
                combo.setCurrentIndex(i)
                return

    def _append_log(self, msg: str) -> None:
        self.log_view.append(msg)
        self.status_label.setText(msg)

    def _preset_snapshot(self) -> dict[str, float]:
        return {
            "calib_sec": float(self.calib_sec_spin.value()),
            "highpass_hz": float(self.highpass_spin.value()),
            "noise_beta": float(self.noise_beta_spin.value()),
            "noise_floor": float(self.noise_floor_spin.value()),
            "ema_alpha": float(self.ema_alpha_spin.value()),
            "gain_smooth": float(self.gain_smooth_spin.value()),
        }

    def _populate_presets(self) -> None:
        selected = self.preset_combo.currentData() or self.cfg.get("selected_preset", MANUAL_PRESET_NAME)
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem(MANUAL_PRESET_NAME, MANUAL_PRESET_NAME)
        for name in BUILTIN_PRESETS:
            self.preset_combo.addItem(f"{name} (Built-in)", name)
        for name in sorted(self.custom_presets.keys()):
            self.preset_combo.addItem(name, name)
        self.preset_combo.blockSignals(False)
        self._set_combo_by_data(self.preset_combo, selected)

    def _apply_preset(self, name: str) -> None:
        if name == MANUAL_PRESET_NAME:
            return
        values = merged_presets(self.custom_presets).get(name)
        if not values:
            return
        if "calib_sec" in values:
            self.calib_sec_spin.setValue(float(values["calib_sec"]))
        if "highpass_hz" in values:
            self.highpass_spin.setValue(float(values["highpass_hz"]))
        if "noise_beta" in values:
            self.noise_beta_spin.setValue(float(values["noise_beta"]))
        if "noise_floor" in values:
            self.noise_floor_spin.setValue(float(values["noise_floor"]))
        if "ema_alpha" in values:
            self.ema_alpha_spin.setValue(float(values["ema_alpha"]))
        if "gain_smooth" in values:
            self.gain_smooth_spin.setValue(float(values["gain_smooth"]))
        self._append_log(f"Applied preset: {name}")

    def _on_preset_changed(self, index: int) -> None:
        del index
        preset_name = self.preset_combo.currentData()
        if not isinstance(preset_name, str):
            return
        if preset_name != MANUAL_PRESET_NAME:
            self._apply_preset(preset_name)

    def save_current_as_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Save preset",
            "Preset name:",
            text="My Preset",
        )
        if not ok:
            return
        preset_name = name.strip()
        if not preset_name:
            QMessageBox.warning(self, "Invalid name", "Preset name cannot be empty.")
            return
        if preset_name == MANUAL_PRESET_NAME or preset_name in BUILTIN_PRESETS:
            QMessageBox.warning(
                self,
                "Reserved name",
                "This name is reserved by a built-in preset. Please choose another name.",
            )
            return
        self.custom_presets[preset_name] = self._preset_snapshot()
        self._populate_presets()
        self._set_combo_by_data(self.preset_combo, preset_name)
        self.save_settings(show_log=False)
        self._append_log(f"Saved custom preset: {preset_name}")

    def delete_selected_custom_preset(self) -> None:
        preset_name = self.preset_combo.currentData()
        if not isinstance(preset_name, str) or preset_name in BUILTIN_PRESETS or preset_name == MANUAL_PRESET_NAME:
            QMessageBox.information(self, "Delete preset", "Select a custom preset to delete.")
            return
        self.custom_presets.pop(preset_name, None)
        self._populate_presets()
        self._set_combo_by_data(self.preset_combo, MANUAL_PRESET_NAME)
        self.save_settings(show_log=False)
        self._append_log(f"Deleted custom preset: {preset_name}")

    def _device_label(
        self,
        index: int,
        dev: dict[str, Any],
        mode: str,
        order: int,
        total: int,
        hostapi_names: dict[int, str],
    ) -> str:
        name = str(dev.get("name", f"Device {index}"))
        if mode == "advanced":
            hostapi_idx = int(dev.get("hostapi", -1))
            host_name = hostapi_names.get(hostapi_idx, f"HostAPI {hostapi_idx}")
            max_in = int(dev.get("max_input_channels", 0))
            max_out = int(dev.get("max_output_channels", 0))
            return f"{index}: {name} | {host_name} | in {max_in} / out {max_out}"
        if total > 1:
            return f"{name} [{order}/{total}]"
        return name

    def _on_device_mode_changed(self, index: int) -> None:
        del index
        self.refresh_devices()

    def refresh_devices(self) -> None:
        try:
            devices = AudioRunner.list_devices()
            hostapis_raw = sd.query_hostapis()
        except (sd.PortAudioError, RuntimeError, ValueError, OSError) as exc:
            QMessageBox.critical(self, "Device Error", str(exc))
            return

        in_prev = self.input_device_combo.currentData()
        out_prev = self.output_device_combo.currentData()
        mode = str(self.device_view_mode_combo.currentData() or "simple")
        hostapi_names = {i: str(info.get("name", f"HostAPI {i}")) for i, info in enumerate(hostapis_raw)}

        self.input_device_combo.clear()
        self.output_device_combo.clear()
        self.input_device_combo.addItem("Default", "default")
        self.output_device_combo.addItem("Default", "default")

        input_candidates = [(idx, dev) for idx, dev in enumerate(devices) if int(dev.get("max_input_channels", 0)) > 0]
        output_candidates = [
            (idx, dev) for idx, dev in enumerate(devices) if int(dev.get("max_output_channels", 0)) > 0
        ]
        input_counts = Counter(str(dev.get("name", "")) for _, dev in input_candidates)
        output_counts = Counter(str(dev.get("name", "")) for _, dev in output_candidates)
        input_seen: Counter[str] = Counter()
        output_seen: Counter[str] = Counter()

        for idx, dev in input_candidates:
            name = str(dev.get("name", ""))
            input_seen[name] += 1
            label = self._device_label(
                idx, dev, mode, input_seen[name], input_counts[name], hostapi_names
            )
            self.input_device_combo.addItem(label, idx)

        for idx, dev in output_candidates:
            name = str(dev.get("name", ""))
            output_seen[name] += 1
            label = self._device_label(
                idx, dev, mode, output_seen[name], output_counts[name], hostapi_names
            )
            self.output_device_combo.addItem(label, idx)

        self._restore_selection(self.input_device_combo, in_prev)
        self._restore_selection(self.output_device_combo, out_prev)
        self._append_log(f"Device list refreshed ({mode} mode).")

    def _apply_selected_devices(self) -> None:
        in_device = self.cfg.get("device_in", "default")
        out_device = self.cfg.get("device_out", "default")
        self._restore_selection(self.input_device_combo, in_device)
        self._restore_selection(self.output_device_combo, out_device)

    def _apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setStyleSheet(_theme_stylesheet(theme))

    def _on_theme_changed(self, index: int) -> None:
        del index
        theme = str(self.theme_combo.currentData() or "system")
        self._apply_theme(theme)
        self._append_log(f"Theme set to {theme}.")

    def _collect_cfg(self) -> dict[str, Any]:
        selected_preset = self.preset_combo.currentData()
        if not isinstance(selected_preset, str):
            selected_preset = MANUAL_PRESET_NAME
        cfg = {
            "samplerate": int(self.samplerate_spin.value()),
            "frame_ms": int(self.frame_ms_spin.value()),
            "calib_sec": float(self.calib_sec_spin.value()),
            "highpass_hz": float(self.highpass_spin.value()),
            "noise_beta": float(self.noise_beta_spin.value()),
            "noise_floor": float(self.noise_floor_spin.value()),
            "ema_alpha": float(self.ema_alpha_spin.value()),
            "gain_smooth": float(self.gain_smooth_spin.value()),
            "device_in": self.input_device_combo.currentData() or "default",
            "device_out": self.output_device_combo.currentData() or "default",
            "selected_preset": selected_preset,
            "custom_presets": {
                name: {key: float(values[key]) for key in PRESET_PARAM_KEYS if key in values}
                for name, values in self.custom_presets.items()
            },
            "device_view_mode": str(self.device_view_mode_combo.currentData() or "simple"),
            "theme": str(self.theme_combo.currentData() or "system"),
        }
        return cfg

    def save_settings(self, show_log: bool = True) -> None:
        cfg = self._collect_cfg()
        save_config(self.config_path, cfg)
        self.cfg = cfg
        if show_log:
            self._append_log(f"Saved settings to {self.config_path}.")

    def start_audio(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        cfg = self._collect_cfg()
        self.worker = AudioWorker(cfg)
        self.worker.status_changed.connect(self._append_log)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.level_changed.connect(self._on_level_changed)
        self.worker.running_changed.connect(self._on_running_changed)
        self.worker.start()

    def stop_audio(self) -> None:
        if self.worker is None:
            return
        self.worker.stop()
        self._append_log("Stopping...")

    def _on_error(self, msg: str) -> None:
        self._append_log(f"Error: {msg}")
        QMessageBox.critical(self, "Audio Error", msg)

    def _on_running_changed(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if not running:
            self.level_bar.setValue(0)

    def _on_level_changed(self, rms: float) -> None:
        level = max(0, min(100, int(rms * 200)))
        self.level_bar.setValue(level)


def run_gui(config_path: str = "config.yaml", initial_cfg: dict[str, Any] | None = None) -> int:
    cfg = initial_cfg if initial_cfg is not None else load_config(config_path)
    app = QApplication([])
    win = MainWindow(config_path=config_path, initial_cfg=cfg)
    win.show()
    return app.exec()
