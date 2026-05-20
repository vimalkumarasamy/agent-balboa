import os
import base64
import math
import requests
import cv2
from dotenv import load_dotenv

load_dotenv()

LEMONADE_BASE = "http://localhost:13305/v1"
VISION_MODEL = "Qwen2.5-VL-7B-Instruct-GGUF"


def _extract_frames(video_path: str, max_frames: int = 4) -> tuple:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    duration_s = total / fps

    n = min(max_frames, max(1, total))
    indices = [int(i * (total - 1) / max(n - 1, 1)) for i in range(n)]

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append((idx, frame))

    cap.release()
    return frames, fps, duration_s


def _frame_to_base64(frame) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode("utf-8")


def _get_pose_description(frame) -> str:
    try:
        import mediapipe as mp

        mp_pose = mp.solutions.pose
        with mp_pose.Pose(static_image_mode=True, model_complexity=1) as pose:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)

            if not results.pose_landmarks:
                return "no pose detected"

            lm = results.pose_landmarks.landmark

            def angle_3pt(a, b, c):
                ax, ay = lm[a].x - lm[b].x, lm[a].y - lm[b].y
                cx, cy = lm[c].x - lm[b].x, lm[c].y - lm[b].y
                dot = ax * cx + ay * cy
                mag = math.sqrt((ax**2 + ay**2) * (cx**2 + cy**2))
                if mag == 0:
                    return 0
                return round(math.degrees(math.acos(max(-1.0, min(1.0, dot / mag)))))

            L_SHO, R_SHO = 11, 12
            L_ELB, R_ELB = 13, 14
            L_WRI, R_WRI = 15, 16
            L_HIP, R_HIP = 23, 24
            L_KNE, R_KNE = 25, 26
            L_ANK, R_ANK = 27, 28

            hip_x = (lm[L_HIP].x + lm[R_HIP].x) / 2
            hip_y = (lm[L_HIP].y + lm[R_HIP].y) / 2
            sho_x = (lm[L_SHO].x + lm[R_SHO].x) / 2
            sho_y = (lm[L_SHO].y + lm[R_SHO].y) / 2
            lean = round(math.degrees(math.atan2(sho_x - hip_x, hip_y - sho_y)))

            return (
                f"L-knee {angle_3pt(L_HIP, L_KNE, L_ANK)}°, "
                f"R-knee {angle_3pt(R_HIP, R_KNE, R_ANK)}°, "
                f"L-hip {angle_3pt(L_SHO, L_HIP, L_KNE)}°, "
                f"R-hip {angle_3pt(R_SHO, R_HIP, R_KNE)}°, "
                f"L-elbow {angle_3pt(L_SHO, L_ELB, L_WRI)}°, "
                f"R-elbow {angle_3pt(R_SHO, R_ELB, R_WRI)}°, "
                f"torso {lean}° from vertical"
            )

    except ImportError:
        return "mediapipe not installed — visual-only analysis"
    except Exception as e:
        return f"pose error: {e}"


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


def analyze_form(video_path: str, activity_type: str = "running") -> str:
    """Analyze running or strength training form from a video file.

    Extracts key frames, measures body pose angles with MediaPipe, then sends
    the frames to a vision model (Qwen2.5-VL locally or Claude) for expert
    biomechanics feedback.

    Args:
        video_path: Path to the video file (MP4, MOV, AVI). Tilde (~) supported.
        activity_type: Type of movement — 'running', 'strength', or 'general'.

    Returns a coach-style critique: key issues, root causes, and correction drills.
    """
    video_path = os.path.expanduser(video_path)

    if not os.path.exists(video_path):
        return f"Video file not found: {video_path}"

    try:
        frames, fps, duration = _extract_frames(video_path, max_frames=4)
    except ValueError as e:
        return str(e)

    if not frames:
        return "Could not extract frames from video."

    content = [
        {
            "type": "text",
            "text": (
                f"You are an expert sports biomechanics coach specialising in {activity_type}. "
                f"I'm sharing {len(frames)} key frames from a {duration:.0f}s video clip.\n\n"
                f"Each frame is accompanied by MediaPipe pose angles (joint angles in degrees).\n\n"
                f"Please provide:\n"
                f"1. The 2–3 most critical form issues (reference the frame number)\n"
                f"2. The likely root cause of each issue\n"
                f"3. A specific drill or coaching cue to fix it\n"
                f"4. One thing they are doing well\n\n"
                f"Be direct and practical. Prioritise injury risk and performance impact."
            ),
        }
    ]

    for i, (frame_idx, frame) in enumerate(frames):
        timestamp = frame_idx / fps
        pose_desc = _get_pose_description(frame)
        img_b64 = _frame_to_base64(frame)

        content.append({
            "type": "text",
            "text": f"\nFrame {i + 1} (t={timestamp:.1f}s) — pose angles: {pose_desc}",
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
        })

    return _call_vision_model(content)
