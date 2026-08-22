import unittest
import tempfile
import os
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from webhook_manager import WebhookManager
from detector import YOLODetector


class Val:
    """Mimics a torch tensor scalar."""
    def __init__(self, v):
        self._v = v
    def item(self):
        return self._v


class FakeBox:
    def __init__(self, cls_id, conf, xyxy):
        self.cls = [Val(cls_id)]
        self.conf = [Val(conf)]
        self.xyxy = [SimpleNamespace(tolist=lambda: list(xyxy))]


class FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeModel:
    names = {0: "person", 1: "bicycle", 2: "car", 15: "cat", 16: "dog"}
    def __call__(self, frame, **kwargs):
        return [FakeResult([
            FakeBox(15, 0.9, [10.0, 20.0, 110.0, 220.0]),
            FakeBox(16, 0.7, [5.0, 5.0, 60.0, 60.0]),
            FakeBox(2, 0.99, [1.0, 1.0, 9.0, 9.0]),  # car: not targeted, filtered at inference
        ])]


def make_detector():
    det = YOLODetector.__new__(YOLODetector)  # skip __init__ (no model download)
    det.model = FakeModel()
    det.device = "cpu"
    det.confidence_threshold = 0.5
    det.target_classes = ["cat", "dog"]
    det._build_class_mapping()
    return det


class TestClassMapping(unittest.TestCase):
    def test_maps_names_case_insensitive(self):
        det = make_detector()
        self.assertEqual(det.target_class_ids, [15, 16])

    def test_unknown_class_maps_to_nothing(self):
        det = make_detector()
        det.target_classes = ["unicorn"]
        det._build_class_mapping()
        self.assertEqual(det.target_class_ids, [])


class TestDetect(unittest.TestCase):
    def test_returns_parsed_detections(self):
        det = make_detector()
        dets = det.detect(np.zeros((240, 320, 3), dtype=np.uint8))
        self.assertEqual(len(dets), 3)
        cat = dets[0]
        self.assertEqual(cat["class_name"], "cat")
        self.assertAlmostEqual(cat["confidence"], 0.9)
        self.assertEqual(cat["box"], (10, 20, 110, 220))

    def test_none_frame_returns_empty(self):
        det = make_detector()
        self.assertEqual(det.detect(None), [])


class TestDrawDetections(unittest.TestCase):
    def test_preserves_shape(self):
        det = make_detector()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        out = det.draw_detections(frame, [
            {"class_name": "person", "confidence": 0.88, "box": (10, 10, 100, 100)}
        ])
        self.assertEqual(out.shape, frame.shape)
        self.assertFalse(np.array_equal(out, frame))  # something was drawn


class TestWebhookCooldown(unittest.TestCase):
    def make_manager(self, enabled=True, url="http://example/hook", cooldown=60):
        return WebhookManager(webhook_url=url if enabled else "", cooldown_seconds=cooldown, enabled=enabled)

    def test_disabled_never_triggers(self):
        wm = self.make_manager(enabled=False)
        self.assertFalse(wm.can_trigger("person"))

    def test_missing_url_never_triggers(self):
        wm = WebhookManager(webhook_url="", cooldown_seconds=60, enabled=True)
        self.assertFalse(wm.can_trigger("person"))

    def test_first_trigger_allowed_then_cooldown(self):
        wm = self.make_manager()
        self.assertTrue(wm.can_trigger("person"))
        wm.update_cooldown("person")
        self.assertFalse(wm.can_trigger("person"))

    def test_cooldown_expires(self):
        wm = self.make_manager(cooldown=60)
        with patch("webhook_manager.time.time", return_value=1000.0):
            wm.update_cooldown("person")
            self.assertFalse(wm.can_trigger("person"))
            self.assertTrue(wm.can_trigger("dog"))  # per-class isolation
        with patch("webhook_manager.time.time", return_value=1061.0):
            self.assertTrue(wm.can_trigger("person"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
