from ultralytics import YOLO
from pathlib import Path
import uuid
import cv2
import numpy as np

# --------------------------------------------------
# Load model once when module loads
# --------------------------------------------------

MODEL_PATH = Path(__file__).parent / "yolov10n.pt"
_model = YOLO(str(MODEL_PATH))

# --------------------------------------------------
# Public API
# --------------------------------------------------

def detect(frame):

    required_fields = ["frame_id", "timestamp", "image"]

    for field in required_fields:
        if field not in frame:
            raise ValueError(f"Missing required field: {field}")

    image = frame["image"]

    results = _model(
        image,
        classes=[0],   # person only
        verbose=False
    )

    detections = []

    h, w = image.shape[:2]

    for result in results:

        for box in result.boxes:

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            # Clamp bbox to image bounds
            x1i = max(0, min(w - 1, int(x1)))
            y1i = max(0, min(h - 1, int(y1)))
            x2i = max(0, min(w, int(x2)))
            y2i = max(0, min(h, int(y2)))

            if x2i <= x1i or y2i <= y1i:
                continue  # skip invalid crops

            # -----------------------------
            # Crop person
            # -----------------------------
            crop = image[y1i:y2i, x1i:x2i].copy()

            # -----------------------------
            # OSNet preprocessing
            # -----------------------------

            # BGR → RGB (OpenCV default is BGR)
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

            # Resize to OSNet input (H=256, W=128)
            crop = cv2.resize(crop, (128, 256))

            # Normalize to [0,1]
            crop = crop.astype(np.float32) / 255.0

            detections.append({
                "detection_id": str(uuid.uuid4()),
                "frame_id": frame["frame_id"],
                "timestamp": frame["timestamp"],
                "bbox": [
                    float(x1),
                    float(y1),
                    float(x2),
                    float(y2)
                ],
                "confidence": float(box.conf[0]),
                "image": crop
            })

    return detections