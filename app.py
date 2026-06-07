import os
import sys
import json
import time
import queue
import logging
import threading
import subprocess
from tkinter import messagebox
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import cv2
import customtkinter as ctk
import pystray
from pystray import MenuItem as item

# Local module imports
from detector import YOLODetector
from webhook_manager import WebhookManager

# Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("RTSPDetector")
logger.setLevel(logging.INFO)

# Config path
CONFIG_PATH = "config.json"

def create_default_icon_image():
    """
    Generates a 64x64 RGBA Image to serve as the system tray icon.
    """
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Outer dark blue camera housing
    draw.rounded_rectangle([6, 14, 58, 50], radius=10, fill=(17, 24, 39, 255), outline=(99, 102, 241, 255), width=3)
    
    # Inner lens ring
    draw.ellipse([20, 20, 44, 44], fill=(31, 41, 55, 255), outline=(99, 102, 241, 255), width=2)
    
    # Lens reflection
    draw.ellipse([25, 25, 31, 31], fill=(255, 255, 255, 220))
    
    # Red recording indicator
    draw.ellipse([46, 18, 52, 24], fill=(239, 68, 68, 255))
    
    return image

class RTSPYoloApp(ctk.CTk):
    def __init__(self, config):
        super().__init__()
        
        self.config = config
        
        # Load Config Values
        ui_cfg = config.get("ui", {})
        self.window_title = ui_cfg.get("window_title", "RTSP YOLO Monitor")
        self.width = ui_cfg.get("width", 800)
        self.height = ui_cfg.get("height", 600)
        self.start_minimized = ui_cfg.get("start_minimized", False)
        self.show_fps_label = ui_cfg.get("show_fps", True)
        
        rtsp_cfg = config.get("rtsp", {})
        self.rtsp_url = rtsp_cfg.get("url", "rtsp://192.168.1.200:554/live/ch00_1")
        self.reconnect_delay = rtsp_cfg.get("reconnect_delay_seconds", 5)
        
        yolo_cfg = config.get("yolo", {})
        self.model_name = yolo_cfg.get("model_name", "yolov8n.pt")
        self.confidence_threshold = yolo_cfg.get("confidence_threshold", 0.5)
        self.target_classes = yolo_cfg.get("target_classes", ["person", "cat", "dog"])
        
        notify_cfg = config.get("notifications", {})
        self.discord_url = notify_cfg.get("discord_webhook_url", "")
        self.cooldown_seconds = notify_cfg.get("cooldown_seconds", 60)
        self.notifications_enabled = notify_cfg.get("enable_discord", True)
        
        storage_cfg = config.get("storage", {})
        self.save_directory = storage_cfg.get("save_directory", "./save")
        self.max_usage_mb = storage_cfg.get("max_usage_mb", 100)
        self.max_usage_bytes = self.max_usage_mb * 1024 * 1024
        
        # Ensure directories exist
        os.makedirs(self.save_directory, exist_ok=True)
        self.prune_save_directory()
        
        # App state variables
        self.running = True
        self.detection_enabled = True
        self.stream_status = "Disconnected"
        self.current_fps = 0.0
        self.window_hidden = False
        
        # Threads & Queues
        self.frame_queue = queue.Queue(maxsize=2)
        
        # Initialize Managers
        self.webhook_manager = WebhookManager(
            webhook_url=self.discord_url,
            cooldown_seconds=self.cooldown_seconds,
            enabled=self.notifications_enabled
        )
        self.detector = YOLODetector(
            model_name=self.model_name,
            confidence_threshold=self.confidence_threshold,
            target_classes=self.target_classes
        )
        
        # Configure Window
        self.title(self.window_title)
        self.geometry(f"{self.width}x{self.height}")
        self.minsize(640, 480)
        
        # CustomTkinter styling
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Handle Close Protocols
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        # Create UI Layout
        self._build_ui()
        
        # Setup System Tray
        self.setup_tray_icon()
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self.capture_loop, name="CaptureThread", daemon=True)
        self.capture_thread.start()
        
        # Start UI Frame Update loop
        self.update_frame_loop()
        
        # If start minimized configuration is active, hide window initially
        if self.start_minimized:
            self.withdraw()
            self.window_hidden = True

    def _build_ui(self):
        # Grid layout (3 rows: Header, Stream Canvas, Controls)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Header
        self.grid_rowconfigure(1, weight=1)  # Video
        self.grid_rowconfigure(2, weight=0)  # Control Panel
        
        # 1. Header Frame
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, height=50)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        self.header_frame.grid_columnconfigure(0, weight=1)
        self.header_frame.grid_columnconfigure(1, weight=0)
        self.header_frame.grid_columnconfigure(2, weight=0)
        
        # Stream Name Label
        self.title_label = ctk.CTkLabel(
            self.header_frame, 
            text="🎥 Live Camera Feed", 
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.grid(row=0, column=0, sticky="w", padx=15, pady=10)
        
        # Status dot and Status label
        self.status_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.status_frame.grid(row=0, column=1, sticky="e", padx=10, pady=10)
        
        self.status_dot = ctk.CTkLabel(
            self.status_frame, 
            text="●", 
            text_color="red", 
            font=ctk.CTkFont(size=14)
        )
        self.status_dot.pack(side="left", padx=(0, 5))
        
        self.status_text = ctk.CTkLabel(
            self.status_frame, 
            text="Disconnected", 
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.status_text.pack(side="left")
        
        # FPS Counter
        self.fps_text = ctk.CTkLabel(
            self.header_frame, 
            text="FPS: 0.0", 
            font=ctk.CTkFont(size=13)
        )
        if self.show_fps_label:
            self.fps_text.grid(row=0, column=2, sticky="e", padx=15, pady=10)
            
        # 2. Main Video Panel Frame
        self.video_frame_container = ctk.CTkFrame(self, corner_radius=10, fg_color="#0a0f1d")
        self.video_frame_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        self.video_frame_container.grid_rowconfigure(0, weight=1)
        self.video_frame_container.grid_columnconfigure(0, weight=1)
        
        # Tkinter Label inside the CTkFrame to render OpenCV images
        self.video_label = tk.Label(self.video_frame_container, bg="#0a0f1d")
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Overlay placeholder text on Video Frame if disconnected
        self.placeholder_label = ctk.CTkLabel(
            self.video_frame_container, 
            text="Waiting for Stream Connection...", 
            font=ctk.CTkFont(size=16)
        )
        self.placeholder_label.grid(row=0, column=0)
        
        # 3. Controls Frame
        self.controls_frame = ctk.CTkFrame(self, corner_radius=10, height=60)
        self.controls_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        # Align controls in grid
        self.controls_frame.grid_columnconfigure(0, weight=1)
        self.controls_frame.grid_columnconfigure(1, weight=1)
        self.controls_frame.grid_columnconfigure(2, weight=1)
        self.controls_frame.grid_columnconfigure(3, weight=1)
        
        # Toggle Detection Button
        self.det_btn = ctk.CTkButton(
            self.controls_frame, 
            text="Stop Detection" if self.detection_enabled else "Start Detection",
            fg_color="#10b981" if self.detection_enabled else "#6b7280",
            hover_color="#059669" if self.detection_enabled else "#4b5563",
            font=ctk.CTkFont(weight="bold"),
            command=self.toggle_detection
        )
        self.det_btn.grid(row=0, column=0, padx=10, pady=15, sticky="ew")
        
        # Hide window button
        self.hide_btn = ctk.CTkButton(
            self.controls_frame, 
            text="Hide to Tray",
            fg_color="#6366f1",
            hover_color="#4f46e5",
            font=ctk.CTkFont(weight="bold"),
            command=self.hide_window
        )
        self.hide_btn.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        
        # Open Save Folder button
        self.folder_btn = ctk.CTkButton(
            self.controls_frame, 
            text="Open Save Directory",
            fg_color="#f59e0b",
            hover_color="#d97706",
            font=ctk.CTkFont(weight="bold"),
            command=self.open_save_directory
        )
        self.folder_btn.grid(row=0, column=2, padx=10, pady=15, sticky="ew")
        
        # Exit application button
        self.exit_btn = ctk.CTkButton(
            self.controls_frame, 
            text="Exit App",
            fg_color="#ef4444",
            hover_color="#dc2626",
            font=ctk.CTkFont(weight="bold"),
            command=self.exit_app
        )
        self.exit_btn.grid(row=0, column=3, padx=10, pady=15, sticky="ew")

    # App Actions
    def toggle_detection(self):
        self.detection_enabled = not self.detection_enabled
        if self.detection_enabled:
            self.det_btn.configure(
                text="Stop Detection", 
                fg_color="#10b981", 
                hover_color="#059669"
            )
            logger.info("YOLO object detection enabled.")
        else:
            self.det_btn.configure(
                text="Start Detection", 
                fg_color="#6b7280", 
                hover_color="#4b5563"
            )
            logger.info("YOLO object detection disabled.")

    def open_save_directory(self):
        try:
            abs_path = os.path.abspath(self.save_directory)
            if not os.path.exists(abs_path):
                os.makedirs(abs_path, exist_ok=True)
            # Opens folder in explorer (Windows-specific)
            os.startfile(abs_path)
            logger.info(f"Opened folder: {abs_path}")
        except Exception as e:
            logger.error(f"Failed to open save directory: {e}")

    def prune_save_directory(self):
        if not hasattr(self, "max_usage_bytes") or self.max_usage_bytes <= 0:
            return
        
        try:
            if not os.path.exists(self.save_directory):
                return
                
            files = []
            for entry in os.scandir(self.save_directory):
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        files.append({
                            "path": entry.path,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime
                        })
                    except OSError:
                        pass
            
            total_size = sum(f["size"] for f in files)
            if total_size <= self.max_usage_bytes:
                return
                
            logger.info(f"Storage usage ({total_size / (1024 * 1024):.2f} MB) exceeds limit ({self.max_usage_bytes / (1024 * 1024):.2f} MB). Pruning oldest files...")
            
            # Sort by mtime (oldest first)
            files.sort(key=lambda x: x["mtime"])
            
            for f in files:
                if total_size <= self.max_usage_bytes:
                    break
                try:
                    os.remove(f["path"])
                    total_size -= f["size"]
                    logger.info(f"Pruned file: {f['path']} ({f['size'] / 1024:.1f} KB)")
                except Exception as e:
                    logger.error(f"Failed to delete {f['path']}: {e}")
                    
            logger.info(f"Storage pruning complete. Current usage: {total_size / (1024 * 1024):.2f} MB")
        except Exception as e:
            logger.error(f"Error during save directory pruning: {e}")

    def hide_window(self):
        self.withdraw()
        self.window_hidden = True
        logger.info("Window hidden to system tray.")

    def show_window(self):
        self.deiconify()
        self.state("normal")
        self.focus_force()
        self.window_hidden = False
        logger.info("Window restored from system tray.")

    def toggle_window_visibility(self):
        if self.window_hidden:
            self.show_window()
        else:
            self.hide_window()

    def exit_app(self):
        logger.info("Initiating shutdown...")
        self.running = False
        
        # Stop System Tray
        if hasattr(self, 'tray_icon') and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception as e:
                logger.error(f"Error stopping tray icon: {e}")
                
        # Destroy GUI
        try:
            self.destroy()
        except Exception as e:
            logger.error(f"Error destroying Tkinter window: {e}")
            
        logger.info("Shutdown completed.")
        sys.exit(0)

    # UI updates from frame queue
    def update_frame_loop(self):
        if not self.running:
            return
            
        try:
            # Poll queue for new processed frame data
            # Using get_nowait to keep UI responsive
            while True:
                data = self.frame_queue.get_nowait()
                
                # Update status indicators
                status = data.get("status", "Disconnected")
                fps = data.get("fps", 0.0)
                
                self.status_text.configure(text=status)
                if status == "Online":
                    self.status_dot.configure(text_color="#10b981")
                elif status == "Connecting...":
                    self.status_dot.configure(text_color="#f59e0b")
                else:
                    self.status_dot.configure(text_color="#ef4444")
                    
                if self.show_fps_label:
                    self.fps_text.configure(text=f"FPS: {fps:.1f}")
                
                # Update frame image
                pil_img = data.get("image")
                if pil_img and not self.window_hidden:
                    # Hide placeholder label
                    self.placeholder_label.grid_remove()
                    
                    # Convert to PhotoImage (must be on main thread)
                    photo = ImageTk.PhotoImage(image=pil_img)
                    
                    # Prevent garbage collection of image
                    self.video_label.photo = photo
                    self.video_label.configure(image=photo)
        except queue.Empty:
            pass
            
        # Schedule next update in ~16ms (approx 60 fps matching)
        self.after(16, self.update_frame_loop)

    def update_status(self, status):
        # Convenience method to push status from threads safely
        def safe_status_update():
            if not self.running:
                return
            self.status_text.configure(text=status)
            if status == "Online":
                self.status_dot.configure(text_color="#10b981")
            elif "Offline" in status or "Retry" in status:
                self.status_dot.configure(text_color="#ef4444")
                self.placeholder_label.grid()  # Show placeholder
                self.placeholder_label.configure(text=f"Stream Offline. {status}")
            else: # Connecting, Reconnecting...
                self.status_dot.configure(text_color="#f59e0b")
                self.placeholder_label.grid()  # Show placeholder
                self.placeholder_label.configure(text=status)
        
        # Schedule on Tkinter thread
        self.after(0, safe_status_update)

    # Core Video capture loop
    def capture_loop(self):
        while self.running:
            logger.info(f"Connecting to RTSP source: {self.rtsp_url}")
            self.update_status("Connecting...")
            
            cap = cv2.VideoCapture(self.rtsp_url)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            
            # Use OpenCV grab / retrieve to prevent frame lag build up on high latency RTSP
            # We also set buffer size if supported by OpenCV backends
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            
            if not cap.isOpened():
                logger.error(f"Failed to open stream. Retrying in {self.reconnect_delay} seconds...")
                self.update_status(f"Offline (Retrying in {self.reconnect_delay}s)")
                cap.release()
                
                for _ in range(self.reconnect_delay * 10):
                    if not self.running:
                        break
                    time.sleep(0.1)
                continue
                
            logger.info("RTSP stream connected.")
            self.update_status("Online")
            
            prev_time = time.time()
            fps_count = 0
            fps_accum = 0.0
            fps = 0.0
            
            while self.running:
                # Capture frame
                ret, frame = cap.read()
                if not ret:
                    logger.warning("Failed to grab frame. Stream disconnected.")
                    self.update_status("Reconnecting...")
                    break
                    
                # Calculate FPS
                now = time.time()
                dt = now - prev_time
                prev_time = now
                fps_count += 1
                fps_accum += dt
                if fps_accum >= 1.0:
                    fps = fps_count / fps_accum
                    fps_count = 0
                    fps_accum = 0.0
                
                detections = []
                display_frame = frame
                
                # Check for detection state
                if self.detection_enabled:
                    detections = self.detector.detect(frame)
                    if len(detections) > 0:
                        self.process_detections(frame, detections)
                    
                    # Draw annotations
                    display_frame = self.detector.draw_detections(frame, detections)
                
                # Render to PIL Image
                rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                
                # Resize keeping aspect ratio to fit the UI canvas elegantly
                h, w = rgb_frame.shape[:2]
                target_w = 780
                target_h = int((h / w) * target_w)
                # Keep height within bound limit
                if target_h > 450:
                    target_h = 450
                    target_w = int((w / h) * target_h)
                
                resized = cv2.resize(rgb_frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                pil_img = Image.fromarray(resized)
                
                # Push into queue
                if self.running:
                    # Clear queue to only hold newest frames
                    while not self.frame_queue.empty():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            break
                    self.frame_queue.put({
                        "image": pil_img,
                        "fps": fps,
                        "status": "Online",
                        "detections": detections
                    })
                
                # Control loop rate slightly (prevents high CPU burn on fast loops)
                time.sleep(0.01)
                
            cap.release()
            logger.info("RTSP connection released.")

    def process_detections(self, frame, detections):
        # Figure out who is eligible for notification
        eligible_classes = []
        highest_conf = {}
        
        for det in detections:
            cname = det["class_name"].lower()
            conf = det["confidence"]
            
            if self.webhook_manager.can_trigger(cname):
                eligible_classes.append(cname)
                if conf > highest_conf.get(cname, 0.0):
                    highest_conf[cname] = conf
                    
        if not eligible_classes:
            return
            
        # We have at least one valid notification to send!
        # Save screenshot
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        class_str = "_".join(eligible_classes)
        screenshot_filename = f"det_{class_str}_{timestamp}.jpg"
        screenshot_path = os.path.join(self.save_directory, screenshot_filename)
        
        try:
            # Save annotated version
            annotated_frame = self.detector.draw_detections(frame, detections)
            cv2.imwrite(screenshot_path, annotated_frame)
            logger.info(f"Screenshot saved to {screenshot_path}")
            self.prune_save_directory()
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            screenshot_path = None
            
        # Dispatch notification webhooks (asynchronously handled in webhook_manager)
        for cname in eligible_classes:
            conf = highest_conf[cname]
            self.webhook_manager.send_notification(cname, conf, screenshot_path)

    # System Tray Integration
    def setup_tray_icon(self):
        # Define Tray Icon Context Menu
        # checked=lambda item: ... ensures checkmarks update dynamically on mouse hover / context menu open.
        self.tray_menu = pystray.Menu(
            item('Show/Hide Player', self.tray_toggle_window, default=True),
            item('Detection Enabled', self.tray_toggle_detection, checked=lambda item: self.detection_enabled),
            pystray.Menu.SEPARATOR,
            item('Exit Application', self.tray_exit_app)
        )
        
        icon_img = create_default_icon_image()
        self.tray_icon = pystray.Icon(
            "RTSPYoloDetector",
            icon_img,
            "YOLO Cam Monitor",
            self.tray_menu
        )
        
        # Run detached (background thread) so it doesn't block the TK main loop
        self.tray_icon.run_detached()
        logger.info("System tray icon initialized and running.")

    # Tray Callbacks (Must schedule on GUI thread safely via .after)
    def tray_toggle_window(self, icon, item):
        self.after(0, self.toggle_window_visibility)

    def tray_toggle_detection(self, icon, item):
        self.after(0, self.toggle_detection)

    def tray_exit_app(self, icon, item):
        self.after(0, self.exit_app)

if __name__ == "__main__":
    # Load configuration
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Error loading {CONFIG_PATH}: {e}")
            
    if not config:
        # Fallback default configuration
        config = {
            "rtsp": {
                "url": "rtsp://192.168.1.200:554/live/ch00_1",
                "reconnect_delay_seconds": 5
            },
            "yolo": {
                "model_name": "yolov8n.pt",
                "confidence_threshold": 0.5,
                "target_classes": ["person", "cat", "dog"]
            },
            "notifications": {
                "discord_webhook_url": "https://discord.com/api/webhooks/1513065582822686832/LLwOPOvxxxxxxxxxxxxx",
                "cooldown_seconds": 60,
                "enable_discord": True
            },
            "storage": {
                "save_directory": "./save",
                "max_usage_mb": 100
            },
            "ui": {
                "window_title": "RTSP YOLO Object Detector & Monitor",
                "width": 800,
                "height": 600,
                "start_minimized": False,
                "show_fps": True
            }
        }
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write default config: {e}")

    # Launch GUI App
    try:
        app = RTSPYoloApp(config)
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Exiting.")
        sys.exit(0)
