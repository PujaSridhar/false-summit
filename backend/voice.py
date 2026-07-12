"""ElevenLabs voice layer.

Voices the rival's taunts (smug) and the investigation report (clinical).
Audio is cached to frontend/audio/<hash>.mp3 and served as /audio/<hash>.mp3.
With no ELEVENLABS_API_KEY, every function returns None and the UI simply
shows text — the game is fully playable silent.
"""
import hashlib
import os
import threading

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
AUDIO_DIR = os.path.join(FRONTEND, "audio")

# Two distinct characters. Defaults are well-known public ElevenLabs voice
# ids; override per-role via env if you want a different cast.
VOICES = {
    "rival": os.environ.get("ELEVENLABS_VOICE_RIVAL", "TxGEqnHWrfWFTfGW9XjX"),   # Josh
    "auditor": os.environ.get("ELEVENLABS_VOICE_AUDITOR", "onwK4e9ZLuTAKqWW03F9"),  # Daniel
}
MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5")

_client = None
_client_tried = False
_lock = threading.Lock()


def enabled():
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def _get_client():
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    if not enabled():
        return None
    try:
        from elevenlabs.client import ElevenLabs
        _client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    except Exception as e:  # pragma: no cover - depends on env
        print(f"[voice] ElevenLabs unavailable, staying silent: {e}")
        _client = None
    return _client


def say(text, role="rival"):
    """Return a URL to cached audio for `text`, or None if voice is disabled."""
    if not text:
        return None
    client = _get_client()
    if client is None:
        return None
    voice_id = VOICES.get(role, VOICES["rival"])
    key = hashlib.sha256(f"{voice_id}:{MODEL}:{text}".encode()).hexdigest()[:16]
    fname = f"{key}.mp3"
    fpath = os.path.join(AUDIO_DIR, fname)
    url = f"/audio/{fname}"
    if os.path.exists(fpath):
        return url
    with _lock:
        if os.path.exists(fpath):
            return url
        try:
            os.makedirs(AUDIO_DIR, exist_ok=True)
            stream = client.text_to_speech.convert(
                voice_id=voice_id, model_id=MODEL, text=text,
                output_format="mp3_44100_128",
            )
            with open(fpath, "wb") as f:
                for chunk in stream:
                    if chunk:
                        f.write(chunk)
        except Exception as e:  # pragma: no cover - network path
            print(f"[voice] synthesis failed: {e}")
            return None
    return url


def report_script(report):
    """Flatten an investigation report into a single narration script."""
    parts = [report["title"], report["subtitle"]]
    for f in report.get("findings", []):
        parts.append(f"{f['segment']}. {f['finding']}")
    parts.append(report.get("verdict", ""))
    parts.append(report.get("closing", ""))
    return " ".join(p for p in parts if p)
