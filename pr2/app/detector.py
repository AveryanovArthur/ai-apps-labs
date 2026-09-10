import time
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from ultralytics import YOLO

WEIGHTS = "yolov8n.pt"
DEFAULT_CONFIDENCE = 0.25

class DetectionError(Exception):
    pass

class InvalidImageError(DetectionError):
    pass

_model = None

def load_model():
    global _model
    if _model is None:
        try:
            _model = YOLO(WEIGHTS)
        except Exception as e:
            raise DetectionError(f"Помилка завантаження моделі: {e}")
    return _model

def detect(image_bytes: bytes, confidence: float = DEFAULT_CONFIDENCE):
    model = load_model()
    
    try:
        image = Image.open(BytesIO(image_bytes))
        image.verify()
        image = Image.open(BytesIO(image_bytes))
    except (UnidentifiedImageError, ValueError):
        raise InvalidImageError("Файл не є валідним зображенням або він порожній")

    start_time = time.perf_counter()
    results = model.predict(image, conf=confidence, verbose=False)
    elapsed_time = time.perf_counter() - start_time

    detected_objects = []
    if results and len(results) > 0:
        result = results[0]
        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = model.names[cls_id]
            conf = float(box.conf[0])
            coords = box.xyxy[0].tolist()
            detected_objects.append({
                "class": cls_name,
                "confidence": round(conf, 2),
                "box": [round(c, 1) for c in coords]
            })

    return {
        "objects": detected_objects,
        "count": len(detected_objects),
        "time_seconds": round(elapsed_time, 3)
    }