import os
import glob
import base64
import math
import requests
import cv2
from typing import List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

VIDEO_DROP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "videos")
VIDEO_EXTS = ("*.mp4", "*.mov", "*.avi", "*.mkv")
LEMONADE_BASE = "http://localhost:13305/v1"
VISION_MODEL = "Qwen2.5-VL-7B-Instruct-GGUF"

MAX_DURATION_S = 30
MIN_DURATION_S = 3
MAX_FILE_MB = 150

# ---------------------------------------------------------------------------
# Activity registry
# ---------------------------------------------------------------------------

_ACTIVITY_KEYWORDS = {
    "squat":    ["squat", "squats", "backsquat", "frontsquat", "goblet"],
    "deadlift": ["deadlift", "deadlifts", "rdl", "romanian", "sumo", "dl"],
    "running":  ["run", "running", "jog", "jogging", "sprint", "treadmill", "track"],
}

_RUBRICS = {
    "squat": """\
SQUAT FORM RUBRIC — score each checkpoint: ✓ PASS | ✗ FAIL | ? UNCLEAR
1. Depth        — hip crease reaches or passes below the knee at the bottom
2. Knee tracking — knees track over toes, no inward collapse (valgus)
3. Heel contact — heels remain flat on the floor throughout
4. Spine        — neutral spine, no excessive lumbar rounding
5. Torso lean   — controlled forward lean, not collapsing onto thighs
6. Symmetry     — both sides move evenly, no lateral shift or hip wink""",

    "deadlift": """\
DEADLIFT FORM RUBRIC — score each checkpoint: ✓ PASS | ✗ FAIL | ? UNCLEAR
1. Spine        — neutral throughout, no lumbar rounding at any point
2. Bar path     — bar stays close to the body, not swinging away
3. Hip hinge    — hips drive back on the descent, not squatting the weight up
4. Lockout      — full hip and knee extension achieved at the top
5. Head/neck    — neutral gaze, not hyperextended or tucked
6. Shoulders    — scapulae set and stable before the pull, not shrugged""",

    "running": """\
RUNNING FORM RUBRIC — score each checkpoint: ✓ PASS | ✗ FAIL | ? UNCLEAR
1. Foot strike  — mid or forefoot contact, not heavy heel striking
2. Landing      — foot lands roughly under the hip, not far in front (overstriding)
3. Arm swing    — ~90° elbow angle, arms not crossing the body midline
4. Torso        — slight forward lean from the ankles, not hunched at the waist
5. Head         — neutral position, gaze forward not at the ground
6. Cadence      — stride rate looks efficient, no excessive vertical bounce""",
}

# ---------------------------------------------------------------------------
# Pose utilities
# ---------------------------------------------------------------------------

def _pose_angles(lm) -> List[float]:
    """Return [L-knee, R-knee, L-hip, R-hip, L-elbow, R-elbow] angles in degrees."""
    def ang(a, b, c):
        ax, ay = lm[a].x - lm[b].x, lm[a].y - lm[b].y
        cx, cy = lm[c].x - lm[b].x, lm[c].y - lm[b].y
        dot = ax * cx + ay * cy
        mag = math.sqrt((ax**2 + ay**2) * (cx**2 + cy**2))
        return math.degrees(math.acos(max(-1.0, min(1.0, dot / mag)))) if mag else 0.0

    L_SHO, R_SHO = 11, 12
    L_ELB, R_ELB = 13, 14
    L_WRI, R_WRI = 15, 16
    L_HIP, R_HIP = 23, 24
    L_KNE, R_KNE = 25, 26
    L_ANK, R_ANK = 27, 28
    return [
        ang(L_HIP, L_KNE, L_ANK),
        ang(R_HIP, R_KNE, R_ANK),
        ang(L_SHO, L_HIP, L_KNE),
        ang(R_SHO, R_HIP, R_KNE),
        ang(L_SHO, L_ELB, L_WRI),
        ang(R_SHO, R_ELB, R_WRI),
    ]


def _pose_distance(v1: List[float], v2: List[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))


def _pose_description_str(angles: List[float]) -> str:
    labels = ["L-knee", "R-knee", "L-hip", "R-hip", "L-elbow", "R-elbow"]
    return ", ".join(f"{lbl} {round(a)}°" for lbl, a in zip(labels, angles))

# ---------------------------------------------------------------------------
# Frame extraction — pose-driven keyframe selection
# ---------------------------------------------------------------------------

def _frame_to_base64(frame) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode("utf-8")


def _frames_for_duration(duration_s: float) -> int:
    if duration_s <= 10:
        return 3
    elif duration_s <= 20:
        return 4
    return 5


def _pick_keyframes(
    sampled: List[Tuple[int, any, Optional[List[float]]]],
    n: int,
    activity: str,
) -> List[Tuple[int, any, Optional[List[float]]]]:
    """Greedy max-spread selection in pose space. Seeds with deepest frame for strength activities."""
    if len(sampled) <= n:
        return sampled

    with_pose = [i for i, (_, _, v) in enumerate(sampled) if v is not None]

    if len(with_pose) < n:
        # Not enough pose data — evenly spaced fallback
        step = max(1, len(sampled) // n)
        return [sampled[i] for i in range(0, len(sampled), step)][:n]

    selected = []

    if activity in ("squat", "deadlift"):
        # Seed with deepest frame: smallest average knee angle
        seed = min(with_pose, key=lambda i: (sampled[i][2][0] + sampled[i][2][1]) / 2)
    else:
        seed = with_pose[0]
    selected.append(seed)

    while len(selected) < n:
        best_i, best_d = -1, -1.0
        for i in with_pose:
            if i in selected:
                continue
            d = min(_pose_distance(sampled[i][2], sampled[j][2]) for j in selected)
            if d > best_d:
                best_d, best_i = d, i
        if best_i == -1:
            break
        selected.append(best_i)

    selected.sort()
    return [sampled[i] for i in selected]


def _sample_and_pick_frames(
    video_path: str, n: int, activity: str
) -> Tuple[List[Tuple[int, any, Optional[List[float]]]], float, float]:
    """
    Sample video at ~2fps, run MediaPipe on each sample, then pick n keyframes
    with maximum pose diversity. Returns (keyframes, fps, duration_s) where
    each keyframe is (frame_idx, image, pose_angles_or_None).
    """
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    duration_s = total / fps
    step = max(1, int(fps / 2))  # 2fps sampling

    try:
        import mediapipe as mp
        mp_pose = mp.solutions.pose
        use_mp = True
    except ImportError:
        use_mp = False

    sampled: List[Tuple[int, any, Optional[List[float]]]] = []

    if use_mp:
        with mp_pose.Pose(static_image_mode=True, model_complexity=1) as detector:
            for idx in range(0, total, step):
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.process(rgb)
                vec = _pose_angles(result.pose_landmarks.landmark) if result.pose_landmarks else None
                sampled.append((idx, frame, vec))
    else:
        for idx in range(0, total, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                sampled.append((idx, frame, None))

    cap.release()
    return _pick_keyframes(sampled, n, activity), fps, duration_s

# ---------------------------------------------------------------------------
# Activity detection
# ---------------------------------------------------------------------------

def _detect_from_filename(video_path: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(video_path))[0].lower()
    stem = stem.replace("-", "").replace("_", "").replace(" ", "")
    for activity, keywords in _ACTIVITY_KEYWORDS.items():
        if any(kw in stem for kw in keywords):
            return activity
    return None


def _detect_visually(frame) -> Optional[str]:
    """Send one frame to the vision model, ask it to name the activity."""
    known = ", ".join(_ACTIVITY_KEYWORDS.keys())
    img_b64 = _frame_to_base64(frame)
    content = [
        {
            "type": "text",
            "text": (
                f"What physical exercise or sport is shown? "
                f"Reply with exactly one word from: {known}, unknown. No other text."
            ),
        },
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
    ]

    try:
        provider = os.getenv("LLM_PROVIDER", "lemonade")
        if provider == "claude":
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=10,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": content[0]["text"]},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                ]}],
            )
            word = resp.content[0].text.strip().lower()
        else:
            resp = requests.post(
                f"{LEMONADE_BASE}/chat/completions",
                json={"model": VISION_MODEL, "messages": [{"role": "user", "content": content}], "max_tokens": 10},
                timeout=60,
            )
            resp.raise_for_status()
            word = resp.json()["choices"][0]["message"]["content"].strip().lower()

        for activity in _ACTIVITY_KEYWORDS:
            if activity in word:
                return activity
    except Exception:
        pass

    return None

# ---------------------------------------------------------------------------
# Vision model call
# ---------------------------------------------------------------------------

def _call_vision_model(content: list) -> str:
    provider = os.getenv("LLM_PROVIDER", "lemonade")

    if provider == "claude":
        import anthropic
        anthropic_content = []
        for block in content:
            if block["type"] == "text":
                anthropic_content.append({"type": "text", "text": block["text"]})
            elif block["type"] == "image_url":
                b64 = block["image_url"]["url"].split(",")[1]
                anthropic_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                })
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1500,
            messages=[{"role": "user", "content": anthropic_content}],
        )
        return resp.content[0].text
    else:
        resp = requests.post(
            f"{LEMONADE_BASE}/chat/completions",
            json={
                "model": VISION_MODEL,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 1500,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

# ---------------------------------------------------------------------------
# Drop folder
# ---------------------------------------------------------------------------

def _latest_dropped_video() -> Optional[str]:
    drop_dir = os.path.normpath(VIDEO_DROP_DIR)
    candidates = []
    for pattern in VIDEO_EXTS:
        candidates.extend(glob.glob(os.path.join(drop_dir, pattern)))
    return max(candidates, key=os.path.getmtime) if candidates else None

# ---------------------------------------------------------------------------
# Main tool
# ---------------------------------------------------------------------------

def analyze_form(video_path: str = "", activity_type: str = "") -> str:
    """Analyse running or strength training form from a video file.

    Detects the activity automatically from the filename or visually. Selects
    key frames using pose-driven diversity (capturing the deepest squat position,
    full running gait cycle, etc.) and scores form against a structured rubric.

    Supported activities: squat, deadlift, running.
    Video requirements: 3–30 seconds, under 150 MB.

    Args:
        video_path: Path to the video (MP4, MOV, AVI). Leave empty to use the
                    latest file dropped into data/videos/.
        activity_type: Override activity detection — 'squat', 'deadlift', or
                       'running'. Leave empty to auto-detect.
    """
    # 1. Resolve video path
    if not video_path:
        latest = _latest_dropped_video()
        if not latest:
            return (
                "No video found. Drop a video into data/videos/ "
                "or provide a path explicitly."
            )
        video_path = latest

    video_path = os.path.expanduser(video_path)
    if not os.path.exists(video_path):
        return f"Video file not found: {video_path}"

    # 2. Validate file size
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        return f"Video is {size_mb:.0f} MB — max allowed is {MAX_FILE_MB} MB. Please trim it first."

    # 3. Validate duration (quick open just for metadata)
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_check = cap.get(cv2.CAP_PROP_FPS) or 30
    duration_check = total_frames / fps_check
    # Grab a mid-frame for visual activity detection if needed
    mid_frame = None
    if not activity_type:
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, mid_frame = cap.read()
    cap.release()

    if duration_check < MIN_DURATION_S:
        return f"Video is {duration_check:.1f}s — too short (minimum {MIN_DURATION_S}s). Record a longer clip."
    if duration_check > MAX_DURATION_S:
        return (
            f"Video is {duration_check:.0f}s — too long (maximum {MAX_DURATION_S}s). "
            f"Re-record a {MAX_DURATION_S}s clip of one set or one running segment."
        )

    # 4. Detect activity
    activity = activity_type.lower().strip() if activity_type else None
    if not activity:
        activity = _detect_from_filename(video_path)
    if not activity and mid_frame is not None:
        activity = _detect_visually(mid_frame)
    if not activity or activity not in _RUBRICS:
        supported = ", ".join(_RUBRICS.keys())
        detected_str = f" (detected: '{activity}')" if activity else ""
        return (
            f"Could not identify a supported activity{detected_str}. "
            f"Supported: {supported}. "
            f"Rename the file (e.g. squats.mov) or pass activity_type explicitly."
        )

    # 5. Extract pose-driven keyframes
    n_frames = _frames_for_duration(duration_check)
    keyframes, fps, duration = _sample_and_pick_frames(video_path, n_frames, activity)

    if not keyframes:
        return "Could not extract frames from video."

    # 6. Build prompt with rubric + frames
    rubric = _RUBRICS[activity]
    content = [
        {
            "type": "text",
            "text": (
                f"You are an expert sports biomechanics coach.\n\n"
                f"{rubric}\n\n"
                f"I'm sharing {len(keyframes)} key frames from a {duration:.0f}s {activity} video. "
                f"Frames were selected to capture maximum range of motion.\n"
                f"Each frame includes MediaPipe joint angles.\n\n"
                f"Instructions:\n"
                f"- Score every rubric checkpoint (✓ / ✗ / ?)\n"
                f"- For each FAIL: give the root cause and one specific drill or cue\n"
                f"- End with 1–2 things they are doing well\n"
                f"- Be direct. Reference frame numbers when relevant."
            ),
        }
    ]

    for i, (frame_idx, frame, pose_vec) in enumerate(keyframes):
        timestamp = frame_idx / fps
        pose_str = _pose_description_str(pose_vec) if pose_vec else "pose unavailable"
        img_b64 = _frame_to_base64(frame)

        content.append({
            "type": "text",
            "text": f"\nFrame {i + 1} (t={timestamp:.1f}s) — {pose_str}",
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
        })

    return _call_vision_model(content)
