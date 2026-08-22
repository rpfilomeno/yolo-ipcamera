# AGENTS.md

## Project

Windows desktop app: RTSP IP camera feed + real-time YOLOv8 detection + Discord webhook alerts. Python 3.10+, CustomTkinter GUI, system tray (pystray). Managed with uv (torch/torchvision pinned to cu121 index in pyproject.toml).

## Commands

```bash
uv run app.py                          # run the app
uv run python -m unittest discover -s tests   # run unit tests
uv sync                                # install deps into .venv
```

No linter configured. Tests use stdlib `unittest` with fake model/webhook objects (no GPU, network, or model download needed).

## Structure

- `app.py` — entry point + `RTSPYoloApp` GUI class: RTSP capture thread (`capture_loop`), detection thread (`detection_loop`), UI update loop, tray icon, config loading (auto-generates `config.json` on first run)
- `detector.py` — `YOLODetector`: wraps Ultralytics YOLO model, class filtering, bounding box drawing
- `webhook_manager.py` — `WebhookManager`: per-class cooldowns, async Discord posts with annotated screenshot attachment, storage pruning
- `config.json` — local config (gitignored; see `config.json.example`). All settings under keys: rtsp / yolo / notifications / storage / ui

## Conventions

- Threading: capture and detection run as daemon threads sharing state via `frame_lock` / `detections_lock`; UI updates must be scheduled back to the Tk main thread via `self.after(...)`
- Logging via stdlib `logging`, logger name `"RTSPDetector"`
- Windows-specific bits: `os.startfile`, pystray tray behavior
