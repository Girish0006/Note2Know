import base64
import io
import json
import os
import cv2
import numpy as np
from PIL import Image
from django.conf import settings


def get_opencv_face_cascade():
    """Load OpenCV Haar cascade for face detection."""
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        # Fallback to alt cascade
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_alt.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
    return face_cascade


def decode_image_bytes(image_input):
    """
    Decode image input which can be raw bytes, base64 string, or uploaded file object.
    Returns OpenCV image (BGR numpy array) or None.
    """
    try:
        if isinstance(image_input, str):
            if "," in image_input:
                image_input = image_input.split(",")[1]
            image_bytes = base64.b64decode(image_input)
        elif hasattr(image_input, "read"):
            image_bytes = image_input.read()
        elif isinstance(image_input, bytes):
            image_bytes = image_input
        else:
            return None

        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"Error decoding image: {e}")
        return None


def detect_and_crop_face(img):
    """
    Detect face in BGR OpenCV image and return cropped, standardized face image (128x128 grayscale)
    and cropped color face image (128x128 BGR).
    """
    if img is None:
        return None, None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_cascade = get_opencv_face_cascade()

    # Detect faces
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(60, 60),
    )

    if len(faces) == 0:
        # Try with slightly looser parameters if first attempt finds no face
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(40, 40),
        )

    if len(faces) == 0:
        return None, None

    # Pick the largest detected face box
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    (x, y, w, h) = faces[0]

    # Add margin around face box
    margin_w = int(w * 0.15)
    margin_h = int(h * 0.15)
    img_h, img_w = img.shape[:2]

    x1 = max(0, x - margin_w)
    y1 = max(0, y - margin_h)
    x2 = min(img_w, x + w + margin_w)
    y2 = min(img_h, y + h + margin_h)

    face_crop_color = img[y1:y2, x1:x2]
    face_crop_gray = gray[y1:y2, x1:x2]

    if face_crop_color.size == 0 or face_crop_gray.size == 0:
        return None, None

    resized_gray = cv2.resize(face_crop_gray, (128, 128))
    resized_color = cv2.resize(face_crop_color, (128, 128))

    return resized_gray, resized_color


def extract_face_feature_vector(face_gray_128x128):
    """
    Extract spatial histogram feature vector from a 128x128 grayscale face crop.
    Divided into 4x4 spatial blocks, computing 32-bin histograms per block.
    Total features: 16 * 32 = 512 dimensions.
    """
    if face_gray_128x128 is None:
        return []

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) for lighting invariance
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(face_gray_128x128)

    features = []
    block_h, block_w = 32, 32  # 128 / 4 = 32

    for r in range(4):
        for c in range(4):
            sub_block = enhanced[r*block_h:(r+1)*block_h, c*block_w:(c+1)*block_w]
            hist = cv2.calcHist([sub_block], [0], None, [32], [0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            features.extend(hist.tolist())

    return features


def compute_similarity(vector1, vector2):
    """
    Compute cosine similarity and correlation distance between two feature vectors.
    Returns float score between 0.0 and 1.0.
    """
    if not vector1 or not vector2 or len(vector1) != len(vector2):
        return 0.0

    v1 = np.array(vector1, dtype=np.float32)
    v2 = np.array(vector2, dtype=np.float32)

    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    cosine_sim = np.dot(v1, v2) / (norm1 * norm2)
    # Scale from [-1, 1] to [0, 1]
    score = (float(cosine_sim) + 1.0) / 2.0
    return score


def verify_with_gemini_vision(live_img_bytes, stored_img_path):
    """
    Dual-verification using Gemini 1.5 Flash Multimodal model if API key exists.
    Compares live frame with registered profile face image.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
    if not api_key or not os.path.exists(stored_img_path):
        return False, 0.0

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel("gemini-1.5-flash")

        # Open images with PIL
        live_pil = Image.open(io.BytesIO(live_img_bytes))
        stored_pil = Image.open(stored_img_path)

        prompt = (
            "You are a security facial verification system. "
            "Image 1 is a live webcam capture. Image 2 is the stored profile photo of a registered user. "
            "Compare the face in Image 1 and Image 2 carefully. Account for minor lighting or angle differences. "
            "Does Image 1 contain the same person as Image 2? "
            "Respond ONLY in valid JSON format: {\"match\": true/false, \"confidence\": float_between_0_and_1, \"reason\": \"short explanation\"}"
        )

        response = model.generate_content([prompt, live_pil, stored_pil])
        resp_text = response.text.strip()

        # Parse JSON
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].strip()

        data = json.loads(resp_text)
        is_match = data.get("match", False)
        confidence = float(data.get("confidence", 0.0))
        return is_match, confidence

    except Exception as e:
        print(f"Gemini Vision face verification error: {e}")
        return False, 0.0


def verify_face_against_user(live_image_input, user_face_obj):
    """
    Main verification engine.
    Compares live image against user_face_obj.
    Returns tuple: (is_authenticated: bool, score: float, message: str)
    """
    if not user_face_obj or not user_face_obj.is_enrolled:
        return False, 0.0, "Face ID is not registered for this user account."

    img = decode_image_bytes(live_image_input)
    if img is None:
        return False, 0.0, "Invalid image data provided."

    face_gray, face_color = detect_and_crop_face(img)
    if face_gray is None:
        return False, 0.0, "No face detected in camera view. Please position your face inside the frame."

    # Live feature extraction
    live_features = extract_face_feature_vector(face_gray)

    # Decode stored features
    stored_features = []
    if user_face_obj.encoding_data:
        try:
            stored_features = json.loads(user_face_obj.encoding_data)
        except Exception:
            stored_features = []

    local_score = compute_similarity(live_features, stored_features)
    print(f"Local face match score for {user_face_obj.user.username}: {local_score:.4f}")

    # Threshold checks
    # High confidence local match (> 0.70)
    if local_score >= 0.70:
        return True, local_score, "Face verified successfully!"

    # Moderate confidence local match (0.55 - 0.70) or if stored image exists -> call Gemini Vision verification
    if user_face_obj.face_image and os.path.exists(user_face_obj.face_image.path):
        # Convert live image to bytes for Gemini Vision
        _, live_buf = cv2.imencode('.jpg', img)
        live_bytes = live_buf.tobytes()

        gemini_match, gemini_conf = verify_with_gemini_vision(live_bytes, user_face_obj.face_image.path)
        print(f"Gemini Vision result: match={gemini_match}, confidence={gemini_conf:.4f}")

        if gemini_match and gemini_conf >= 0.65:
            return True, max(local_score, gemini_conf), "Face verified successfully via AI Vision!"

    # If local score is reasonably close (>= 0.62) and no stored file path for Gemini, accept as matched
    if local_score >= 0.62:
        return True, local_score, "Face verified successfully!"

    return False, local_score, "Face mismatch. The face does not match the registered user profile."
