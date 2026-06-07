import logging
import cv2
from ultralytics import YOLO

logger = logging.getLogger("RTSPDetector")

class YOLODetector:
    def __init__(self, model_name="yolov8n.pt", confidence_threshold=0.5, target_classes=None):
        logger.info(f"Initializing YOLO model: {model_name}...")
        self.model = YOLO(model_name)
        self.confidence_threshold = confidence_threshold
        
        # Default target classes to person, cat, dog if not specified
        if target_classes is None:
            target_classes = ["person", "cat", "dog"]
        self.target_classes = [c.lower() for c in target_classes]
        
        # Map target class names to their IDs in the model
        self.target_class_ids = []
        self._build_class_mapping()

    def _build_class_mapping(self):
        # model.names is a dict of {id: name}
        self.target_class_ids = []
        for class_id, class_name in self.model.names.items():
            if class_name.lower() in self.target_classes:
                self.target_class_ids.append(class_id)
        
        logger.info(f"Target classes: {self.target_classes} mapped to IDs: {self.target_class_ids}")

    def detect(self, frame):
        """
        Runs object detection on the frame.
        Returns:
            list of dicts containing 'class_name', 'confidence', and 'box' (x1, y1, x2, y2)
        """
        if frame is None:
            return []

        # Run inference. We can specify classes to filter at inference level for speed
        results = self.model(frame, verbose=False, conf=self.confidence_threshold, classes=self.target_class_ids)
        
        detections = []
        if len(results) > 0:
            result = results[0]
            boxes = result.boxes
            for box in boxes:
                class_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                
                class_name = self.model.names[class_id]
                
                detections.append({
                    "class_name": class_name,
                    "confidence": confidence,
                    "box": (x1, y1, x2, y2)
                })
                
        return detections

    def draw_detections(self, frame, detections):
        """
        Draws bounding boxes and labels on the frame.
        """
        annotated_frame = frame.copy()
        
        # Color palette for different targets (aesthetic curated colors in BGR format)
        colors = {
            "person": (255, 120, 0),  # Sleek Blue
            "cat": (0, 165, 255),     # Premium Orange
            "dog": (0, 200, 100)      # Neon Green
        }
        default_color = (150, 150, 150)

        for det in detections:
            x1, y1, x2, y2 = det["box"]
            class_name = det["class_name"]
            confidence = det["confidence"]
            
            # Determine color
            color = colors.get(class_name.lower(), default_color)
            
            # Draw premium bounding box (with slightly thicker corners or standard line with overlay)
            # Standard rectangle
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            
            # Label background
            label = f"{class_name.capitalize()} {confidence:.1%}"
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            
            # Draw a solid rectangle background for text
            cv2.rectangle(annotated_frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
            
            # Draw white text over the background
            cv2.putText(annotated_frame, label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            
        return annotated_frame
