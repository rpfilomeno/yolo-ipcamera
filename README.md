# YOLO IP Camera RTSP Monitor

A lightweight, modern Windows Python application that streams RTSP video feeds, performs real-time YOLOv8 object detection, saves screenshots of target detections, and dispatches automated notifications via Discord webhooks with built-in cooldowns and intelligent storage management.

Designed with a sleek, dark-themed CustomTkinter UI and system tray integration, the application operates unobtrusively in the background of your system.

---

## 🚀 Key Features

*   **Real-time RTSP Streaming**: Connects to camera streams with automatic reconnection logic if the connection drops.
*   **YOLOv8 Object Detection**: Leverages Ultralytics YOLOv8 (defaulting to the lightweight `yolov8n.pt`) to detect specific target classes (`person`, `cat`, `dog`) or any other YOLO class.
*   **Sleek CustomTkinter UI**: Features a modern, dark-themed dashboard showing the live annotated stream, FPS metrics, and an active connection status indicator (Online/Connecting/Offline).
*   **System Tray Integration**: Easily hide/show the window to/from the system tray (`pystray`). Includes context menu controls to toggle detection or exit the application.
*   **Discord Webhook Notifications**: Sends rich alerts to Discord webhooks containing the class name, confidence rate, and the annotated screenshot as an attachment.
*   **Notification Cooldowns**: Dynamic per-class cooldown timer prevents spamming of notifications.
*   **Storage Pruning**: Monitors local storage usage of screenshots (`save_directory`) and automatically prunes the oldest files when size exceeds the configured threshold (e.g. `max_usage_mb`).

---

## 🛠️ Architecture & File Structure

The project consists of three main modules:

1.  [`app.py`](file:///d:/Github/yolo-ipcamera/app.py): Entry point for the application. Sets up the GUI using CustomTkinter, initiates the RTSP grabber thread, manages system tray operations, handles local folder interactions, and triggers storage pruning.
2.  [`detector.py`](file:///d:/Github/yolo-ipcamera/detector.py): Wraps the YOLO model loader. Performs target class mapping, executes object detection, and renders color-coded aesthetic bounding boxes and confidence overlays onto BGR frames.
3.  [`webhook_manager.py`](file:///d:/Github/yolo-ipcamera/webhook_manager.py): Handles asynchronous Discord notification dispatches, payload assembly, image attachments, and keeps track of per-class cooldown timestamps.

---

## ⚙️ Configuration (`config.json`)

The application is fully configurable via `config.json` in the root directory. If the file does not exist, a default version will be auto-generated upon start:

```json
{
  "rtsp": {
    "url": "rtsp://192.168.1.200:554/live/ch00_1",
    "reconnect_delay_seconds": 5
  },
  "yolo": {
    "model_name": "yolov8n.pt",
    "confidence_threshold": 0.5,
    "target_classes": [
      "person",
      "cat",
      "dog"
    ]
  },
  "notifications": {
    "discord_webhook_url": "https://discord.com/api/webhooks/...",
    "cooldown_seconds": 60,
    "enable_discord": true
  },
  "storage": {
    "save_directory": "./save",
    "max_usage_mb": 100
  },
  "ui": {
    "window_title": "RTSP YOLO Object Detector & Monitor",
    "width": 800,
    "height": 600,
    "start_minimized": false,
    "show_fps": true
  }
}
```

### Config Options Breakdown

*   **`rtsp.url`**: The RTSP connection string for your network IP Camera.
*   **`rtsp.reconnect_delay_seconds`**: Cooldown time before attempting reconnection when a stream is lost.
*   **`yolo.model_name`**: YOLOv8 weights file. Ultralytics automatically downloads standard models (e.g. `yolov8n.pt`, `yolov8s.pt`) if they aren't locally present.
*   **`yolo.confidence_threshold`**: Detections below this probability threshold will be ignored.
*   **`yolo.target_classes`**: List of class names to detect (e.g., `["person", "cat", "dog", "car"]`).
*   **`notifications.discord_webhook_url`**: Discord webhook link used to post detection events.
*   **`notifications.cooldown_seconds`**: Interval (in seconds) that must pass before sending another notification for the *same* class.
*   **`notifications.enable_discord`**: Boolean toggle to switch Discord messaging on or off.
*   **`storage.save_directory`**: Directory where detection screenshots are stored.
*   **`storage.max_usage_mb`**: Maximum storage limit (in megabytes) allocated for screenshot storage. Oldest screenshots are pruned to respect this limit.
*   **`ui.start_minimized`**: If set to `true`, the application will start directly in the system tray.

---

## 📦 Installation & Setup

Ensure you have **Python 3.10+** installed.

### Option 1: Using UV (Recommended)

If you have [uv](https://github.com/astral-sh/uv) installed, running the application is simple. Dependencies will be resolved automatically:

```bash
# Clone the repository
git clone https://github.com/rpfilomeno/yolo-ipcamera.git
cd yolo-ipcamera

# Run the application
uv run app.py
```

### Option 2: Standard Pip installation

```bash
# Clone the repository
git clone https://github.com/rpfilomeno/yolo-ipcamera.git
cd yolo-ipcamera

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Run the app
python app.py
```

---

## 🖥️ Usage

1.  Configure the `config.json` with your RTSP URL and Discord webhook details.
2.  Launch the application.
3.  **UI Controls**:
    *   **Start/Stop Detection**: Toggles YOLO detection. If disabled, the live video is still displayed but no inference or alerts are triggered.
    *   **Hide to Tray**: Minimizes the window to the system tray, freeing up desktop space.
    *   **Open Save Directory**: Opens your saved screenshot folder in Windows Explorer.
    *   **Exit App**: Shuts down the threads and exits.
4.  **System Tray**:
    *   Right-click the camera icon in the Windows taskbar tray to open the menu.
    *   Double-click the tray icon to quickly show or hide the application window.
    *   Toggle YOLO detection directly or exit the application from the menu.

---

## 📝 License

This project is licensed under the [MIT License](file:///d:/Github/yolo-ipcamera/LICENSE) - see the [LICENSE](file:///d:/Github/yolo-ipcamera/LICENSE) file for details.