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

    def send_notification(self, class_name, confidence, screenshot_path=None):
        if not self.can_trigger(class_name):
            return

        # Mark cooldown immediately to prevent duplicate sends during thread startup
        self.update_cooldown(class_name)

        # Send asynchronously in a background thread
        thread = threading.Thread(
            target=self._async_send,
            args=(class_name, confidence, screenshot_path),
            daemon=True
        )
        thread.start()

    def _async_send(self, class_name, confidence, screenshot_path):
        try:
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
