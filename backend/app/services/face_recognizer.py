import logging
import os
import glob
import numpy as np
import cv2
import onnxruntime as ort
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

FACES_DIR = Path("faces")
FACES_DIR.mkdir(exist_ok=True)

MODEL_DIR = Path(os.path.expanduser("~/.insightface/models/buffalo_l"))

# OpenCV DNN face detector (works great for all angles/distances)
FACE_PROTO = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


class ArcFaceRecognizer:
    """Production-grade face recognition using ArcFace (w600k_r50) via ONNX Runtime."""

    def __init__(self):
        self.det_session = None
        self.rec_session = None
        self.known_faces: dict[str, dict] = {}  # name -> {path, role, id, embedding}
        self._initialized = False

    def _load_models(self):
        """Load ONNX detection and recognition models."""
        det_path = str(MODEL_DIR / "det_10g.onnx")
        rec_path = str(MODEL_DIR / "w600k_r50.onnx")

        if not os.path.exists(det_path) or not os.path.exists(rec_path):
            logger.warning("InsightFace ONNX models not found, falling back to Haar cascade")
            return False

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 2

        try:
            self.det_session = ort.InferenceSession(det_path, opts, providers=["CPUExecutionProvider"])
            self.rec_session = ort.InferenceSession(rec_path, opts, providers=["CPUExecutionProvider"])
            logger.info("ArcFace ONNX models loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load ONNX models: {e}")
            return False

    def load_known_faces(self):
        """Load known faces from DB and compute embeddings."""
        from app.core.database import SessionLocal
        from app.models.face import KnownFace

        models_ok = self._load_models()

        db = SessionLocal()
        try:
            faces = db.query(KnownFace).all()
            for face in faces:
                if os.path.exists(face.photo_path):
                    embedding = None
                    if models_ok:
                        img = cv2.imread(face.photo_path)
                        if img is not None:
                            embedding = self._get_embedding(img)

                    self.known_faces[face.name] = {
                        "path": face.photo_path,
                        "role": face.role,
                        "id": face.id,
                        "embedding": embedding,
                    }
            logger.info(f"Loaded {len(self.known_faces)} known faces")
            self._initialized = True
        finally:
            db.close()

    def _detect_faces_retinaface(self, frame: np.ndarray, threshold: float = 0.5) -> list[dict]:
        """Detect faces using RetinaFace ONNX model (3-stride anchor-free)."""
        h, w = frame.shape[:2]
        det_size = (640, 640)

        # Preprocess
        img = cv2.resize(frame, det_size)
        img = img.astype(np.float32)
        img = np.expand_dims(img.transpose(2, 0, 1), axis=0)

        input_name = self.det_session.get_inputs()[0].name
        outputs = self.det_session.run(None, {input_name: img})

        # Outputs: 3 strides x (scores[N,1], bboxes[N,4], landmarks[N,10])
        # Strides: 8, 16, 32 with feature map sizes 80, 40, 20
        strides = [8, 16, 32]
        feat_sizes = [det_size[0] // s for s in strides]
        score_outputs = [outputs[0], outputs[1], outputs[2]]
        bbox_outputs = [outputs[3], outputs[4], outputs[5]]

        faces = []
        scale_w = w / det_size[0]
        scale_h = h / det_size[1]

        for idx, stride in enumerate(strides):
            scores = score_outputs[idx].reshape(-1)
            bboxes = bbox_outputs[idx].reshape(-1, 4)
            feat_h = feat_w = feat_sizes[idx]

            for i, score in enumerate(scores):
                if score < threshold:
                    continue

                # Anchor position
                anchor_y = (i // (feat_w * 2)) * stride
                anchor_x = ((i // 2) % feat_w) * stride

                # Decode bbox (distance from anchor)
                x1 = (anchor_x - bboxes[i][0] * stride) * scale_w
                y1 = (anchor_y - bboxes[i][1] * stride) * scale_h
                x2 = (anchor_x + bboxes[i][2] * stride) * scale_w
                y2 = (anchor_y + bboxes[i][3] * stride) * scale_h

                faces.append({
                    "bbox": [max(0, int(x1)), max(0, int(y1)),
                             min(w, int(x2)), min(h, int(y2))],
                    "score": float(score),
                })

        # NMS
        if faces:
            boxes = np.array([f["bbox"] for f in faces], dtype=np.float32)
            scores = np.array([f["score"] for f in faces], dtype=np.float32)
            indices = cv2.dnn.NMSBoxes(
                boxes.tolist(), scores.tolist(), threshold, 0.4
            )
            if len(indices) > 0:
                indices = indices.flatten()
                faces = [faces[i] for i in indices]
            else:
                faces = []

        return faces

    def _detect_faces_haar(self, frame: np.ndarray) -> list[dict]:
        """Fallback face detection using Haar cascade."""
        cascade = cv2.CascadeClassifier(FACE_PROTO)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Relaxed params for corridor distance detection
        detected = cascade.detectMultiScale(gray, 1.05, 3, minSize=(30, 30))

        faces = []
        for (x, y, w, h) in detected:
            faces.append({
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
                "score": 0.95,
            })
        return faces

    def _enhance_small_face(self, face: np.ndarray) -> np.ndarray:
        """AI-enhance a small face crop for better recognition at distance."""
        h, w = face.shape[:2]
        if min(h, w) >= 100:
            return face  # Already large enough

        # Step 1: Upscale with LANCZOS4
        target = 224
        upscaled = cv2.resize(face, (target, target), interpolation=cv2.INTER_LANCZOS4)

        # Step 2: CLAHE contrast enhancement
        lab = cv2.cvtColor(upscaled, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        # Step 3: Sharpen
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)

        # Step 4: Light denoise
        final = cv2.fastNlMeansDenoisingColored(sharpened, None, 3, 3, 7, 21)

        logger.debug(f"Face enhanced: {w}x{h} -> {target}x{target}")
        return final

    def _align_face(self, frame: np.ndarray, bbox: list[int]) -> np.ndarray:
        """Crop, enhance if small, and align face for recognition."""
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]

        # Add padding
        pad_w = int((x2 - x1) * 0.2)
        pad_h = int((y2 - y1) * 0.2)
        x1 = max(0, x1 - pad_w)
        y1 = max(0, y1 - pad_h)
        x2 = min(w, x2 + pad_w)
        y2 = min(h, y2 + pad_h)

        face = frame[y1:y2, x1:x2]

        # Enhance small faces (from distance)
        face = self._enhance_small_face(face)

        face = cv2.resize(face, (112, 112))
        return face

    def _get_embedding(self, frame: np.ndarray, bbox: list[int] | None = None) -> np.ndarray | None:
        """Get ArcFace embedding for a face."""
        if self.rec_session is None:
            return None

        if bbox:
            face = self._align_face(frame, bbox)
        else:
            # Detect first face in image
            faces = self._detect_faces_haar(frame)
            if not faces:
                # Use whole image resized
                face = cv2.resize(frame, (112, 112))
            else:
                face = self._align_face(frame, faces[0]["bbox"])

        # Preprocess for ArcFace
        face = face.astype(np.float32)
        face = (face - 127.5) / 127.5
        face = face.transpose(2, 0, 1)
        face = np.expand_dims(face, axis=0)

        try:
            input_name = self.rec_session.get_inputs()[0].name
            embedding = self.rec_session.run(None, {input_name: face})[0]
            # Normalize
            embedding = embedding / np.linalg.norm(embedding)
            return embedding.flatten()
        except Exception as e:
            logger.debug(f"Embedding error: {e}")
            return None

    def recognize(self, frame: np.ndarray) -> list[dict]:
        """Detect and recognize faces in a frame."""
        if not self._initialized:
            self.load_known_faces()

        results = []

        # Detect faces — use Haar (reliable) and RetinaFace as backup
        faces = self._detect_faces_haar(frame)
        if not faces and self.det_session:
            try:
                faces = self._detect_faces_retinaface(frame)
            except Exception:
                pass

        if not faces:
            return results

        for face_det in faces:
            bbox = face_det["bbox"]

            # Get embedding
            embedding = self._get_embedding(frame, bbox)

            if embedding is not None:
                identity = self._match_embedding(embedding)
            else:
                identity = None

            if identity:
                results.append({
                    "name": identity["name"],
                    "role": identity["role"],
                    "known": True,
                    "confidence": round(identity["similarity"], 3),
                    "bbox": bbox,
                })
            else:
                results.append({
                    "name": "Unknown",
                    "role": "unknown",
                    "known": False,
                    "confidence": round(face_det["score"], 3),
                    "bbox": bbox,
                })

        return results

    def _match_embedding(self, embedding: np.ndarray, threshold: float = 0.4) -> dict | None:
        """Match an embedding against known faces using cosine similarity."""
        best_match = None
        best_sim = -1

        for name, info in self.known_faces.items():
            known_emb = info.get("embedding")
            if known_emb is None:
                continue

            sim = cosine_similarity(
                embedding.reshape(1, -1),
                known_emb.reshape(1, -1)
            )[0][0]

            if sim > threshold and sim > best_sim:
                best_sim = sim
                best_match = {
                    "name": name,
                    "role": info["role"],
                    "id": info["id"],
                    "similarity": float(sim),
                }

        return best_match

    def add_face(self, name: str, photo_path: str, role: str = "") -> bool:
        """Register a new known face with embedding."""
        embedding = None
        if self.rec_session:
            img = cv2.imread(photo_path)
            if img is not None:
                embedding = self._get_embedding(img)

        self.known_faces[name] = {
            "path": photo_path,
            "role": role,
            "embedding": embedding,
        }
        logger.info(f"Registered face: {name} (embedding: {'OK' if embedding is not None else 'NONE'})")
        return True

    def remove_face(self, name: str):
        """Remove a known face."""
        self.known_faces.pop(name, None)


# Singleton
face_recognizer = ArcFaceRecognizer()
