import os
import time
import logging
import threading
import requests

logger = logging.getLogger("RTSPDetector")

class WebhookManager:
    def __init__(self, webhook_url, cooldown_seconds=60, enabled=True):
        self.webhook_url = webhook_url
        self.cooldown_seconds = cooldown_seconds
        self.enabled = enabled
        self.last_sent = {}  # maps class_name -> timestamp of last sent notification
        self._lock = threading.Lock()

    def can_trigger(self, class_name):
        if not self.enabled or not self.webhook_url:
            return False
            
        with self._lock:
            now = time.time()
            last_time = self.last_sent.get(class_name, 0)
            if now - last_time >= self.cooldown_seconds:
                return True
            return False

    def update_cooldown(self, class_name):
        with self._lock:
            self.last_sent[class_name] = time.time()

    def send_notification(self, class_name, confidence, frame=None, detector=None, detections=None, save_directory=None, max_usage_bytes=0):
        if not self.can_trigger(class_name):
            return

        # Mark cooldown immediately to prevent duplicate sends during thread startup
        self.update_cooldown(class_name)

        # Send asynchronously in a background thread
        thread = threading.Thread(
            target=self._async_send,
            args=(class_name, confidence, frame, detector, detections, save_directory, max_usage_bytes),
            daemon=True
        )
        thread.start()

    def _async_send(self, class_name, confidence, frame, detector, detections, save_directory, max_usage_bytes):
        try:
            screenshot_path = None
            if frame is not None and detector is not None and detections is not None and save_directory:
                import cv2
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                screenshot_filename = f"det_{class_name}_{timestamp}.jpg"
                os.makedirs(save_directory, exist_ok=True)
                screenshot_path = os.path.join(save_directory, screenshot_filename)
                
                try:
                    # Draw annotated version in the background thread
                    annotated_frame = detector.draw_detections(frame, detections)
                    cv2.imwrite(screenshot_path, annotated_frame)
                    logger.info(f"Background screenshot saved to {screenshot_path}")
                    
                    if max_usage_bytes > 0:
                        self._prune_save_directory(save_directory, max_usage_bytes)
                except Exception as e:
                    logger.error(f"Failed to save background screenshot: {e}")
                    screenshot_path = None

            message = f"🚨 **Detection Alert**\nDetected a **{class_name}** with {confidence:.1%} confidence."
            
            payload = {
                "content": message
            }
            
            files = None
            if screenshot_path and os.path.exists(screenshot_path):
                # We can send the file as an attachment in Discord webhooks
                filename = os.path.basename(screenshot_path)
                files = {
                    "file": (filename, open(screenshot_path, "rb"), "image/jpeg")
                }

            logger.info(f"Sending Discord webhook for '{class_name}'...")
            if files:
                response = requests.post(self.webhook_url, data=payload, files=files, timeout=10)
                # Close the file handle
                files["file"][1].close()
            else:
                response = requests.post(self.webhook_url, json=payload, timeout=10)

            if response.status_code in (200, 204):
                logger.info(f"Webhook notification for '{class_name}' successfully sent.")
            else:
                logger.error(f"Failed to send webhook: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")

    def _prune_save_directory(self, save_directory, max_usage_bytes):
        try:
            if not os.path.exists(save_directory):
                return
                
            files = []
            for entry in os.scandir(save_directory):
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
            if total_size <= max_usage_bytes:
                return
                
            logger.info(f"Storage usage ({total_size / (1024 * 1024):.2f} MB) exceeds limit ({max_usage_bytes / (1024 * 1024):.2f} MB). Pruning oldest files...")
            
            # Sort by mtime (oldest first)
            files.sort(key=lambda x: x["mtime"])
            
            for f in files:
                if total_size <= max_usage_bytes:
                    break
                try:
                    os.remove(f["path"])
                    total_size -= f["size"]
                    logger.info(f"Pruned file: {f['path']} ({f['size'] / 1024:.1f} KB)")
                except Exception as e:
                    logger.error(f"Failed to delete {f['path']}: {e}")
                    
            logger.info(f"Storage pruning complete. Current usage: {total_size / (1024 * 1024):.2f} MB")
        except Exception as e:
            logger.error(f"Error during save directory pruning in background: {e}")

