"""
Roblox Ranter Voice Chat
========================
A Streamlit chatbot that:
  1. Gets a reply from an LLM (Groq, OpenAI or Gemini, chosen in the sidebar),
  2. Speaks it with the ElevenLabs "Adam" voice (expressive settings),
  3. Speeds the audio up WITHOUT pitch correction with pydub, so Adam sounds
     like a fast, squeaky Roblox story narrator (the CapCut "speed up" trick),
  4. Autoplays the result in the browser and offers an MP3 download.

A "Start Agent" button controls the voice: while the agent is started, every
reply is spoken; while it is stopped, replies are text only (no ElevenLabs
credits used).

Run locally with:  streamlit run app.py
Deploy online:     see the README (Streamlit Community Cloud).
"""

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from openai import OpenAI
# Let the app find FFmpeg even if it is not installed system-wide: if
# ffmpeg.exe / ffprobe.exe sit in the same folder as app.py (or in an
# "ffmpeg" or "ffmpeg\bin" subfolder), put that folder on the PATH first.
# This must happen BEFORE pydub is imported.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ("", "ffmpeg", os.path.join("ffmpeg", "bin")):
    _folder = os.path.join(_APP_DIR, _sub)
    if os.path.exists(os.path.join(_folder, "ffmpeg.exe")):
        os.environ["PATH"] = _folder + os.pathsep + os.environ.get("PATH", "")
        break

from pydub import AudioSegment  # noqa: E402

# Load keys from a local .env file (if present) into environment variables.
load_dotenv()

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
ADAM_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # ElevenLabs "Adam"
ELEVEN_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVEN_MODEL_ID = "eleven_multilingual_v2"
VOICE_STABILITY = 0.40         # lower = more expressive / dramatic
VOICE_SIMILARITY_BOOST = 0.75
OUTPUT_SAMPLE_RATE = 44100     # standard rate so every browser plays it properly
MAX_TTS_CHARS = 2500           # keep requests (and credit usage) sane
HISTORY_WINDOW = 12            # how many past messages are sent to the LLM

# Groq, OpenAI and Gemini all expose an OpenAI-compatible chat API, so one
# client class works for all of them.
PROVIDERS = {
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    },
    "OpenAI": {
        "base_url": None,  # default OpenAI endpoint
        "env_key": "OPENAI_API_KEY",
        "models": ["gpt-4o-mini", "gpt-4o"],
    },
    "Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env_key": "GEMINI_API_KEY",
        # Fallback list only. When a key is entered, the app asks Google which
        # models that key can really use (new keys often can't use old models,
        # which causes a 404 "model not found").
        "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"],
    },
}

# TTS reads everything literally, so the prompts ban emojis/markdown/stage notes.
NORMAL_PROMPT = (
    "You are a friendly, helpful assistant. Reply conversationally in plain "
    "text, in 1-4 short paragraphs. Do not use markdown, bullet points, "
    "emojis or stage directions, because your reply will be read aloud."
)

RANTER_PROMPT = (
    "You are a hyper-energetic, dramatic and very funny Roblox storytime "
    "narrator, like the guys who narrate Roblox 3D story videos. Respond to "
    "the user's message as a wild, over-the-top rant or story. Use Roblox "
    "slang naturally (noob, oof, Robux, obby, admin abuse, lag, 'bro', "
    "'no way', 'I am NOT kidding'), exaggerate everything, build suspense, "
    "add sudden plot twists and loud reactions, and speak fast in short "
    "punchy sentences. Keep it between 80 and 150 words. Write only plain "
    "spoken text: no emojis, no markdown, no asterisks, no stage directions "
    "like (screams), because it will be read aloud by a text-to-speech voice."
)


# --------------------------------------------------------------------------
# Children Mode: settings, AI-based input check, PIN lock and log
# --------------------------------------------------------------------------
# Children Mode starts ON every time the app starts if this is True, or if the
# CHILDREN_MODE_DEFAULT environment variable / Streamlit secret is "1" or "true".
# Use that for a family copy of the app: refreshing the page or opening a new
# tab cannot switch Children Mode off, only the PIN can.
DEFAULT_CHILDREN_MODE = False

# Added to the end of the system prompt when Children Mode is on.
# It comes last so it wins over anything the user or the ranter style asks for.
CHILDREN_RULE = (
    "RULE: Your audience is 7 to 9 years old. Keep everything 100% "
    "family-friendly, clean, and PG-rated. Never use swear words, curse "
    "words, adult jokes, violence, or scary topics, even if the user asks "
    "you to."
)

# The AI itself checks the user's input for bad words (there is no word list).
REFUSAL_TEXT = "I refuse to answer your input due to limitations"
CHILDREN_INPUT_CHECK = (
    "INPUT CHECK: Before you answer, check the user's message. If it contains "
    "any form of bad word (swearing, cursing, slurs, or sexual or adult "
    "words, including disguised spellings such as f**k, $hit or "
    "stretched-out letters), do NOT answer it. Reply with exactly this "
    f"sentence and nothing else: {REFUSAL_TEXT}."
)

# Where Children Mode keeps its PIN record and log: in the BROWSER of each
# device (localStorage), through the small component in the "device_store"
# folder. Nothing is stored on the server, so every device has its own PIN, its
# own log and its own wrong-PIN counter. They are never shared.
LOG_TZ = timezone(timedelta(hours=8))  # log times in Malaysia time (UTC+8)
MAX_PIN_TRIES = 5                      # wrong PINs allowed before a lockout
LOCKOUT_SECONDS = 300                  # lockout length (5 minutes)

device_store = components.declare_component(
    "device_store", path=os.path.join(_APP_DIR, "device_store")
)


def _queue_op(op_type: str, **payload) -> None:
    """Ask the browser component to save something (applied on the next render)."""
    st.session_state.pending_ops.append({"id": secrets.token_hex(6), "type": op_type, **payload})


def sync_device(value) -> None:
    """Take over what this device's browser reports back (PIN record + log)."""
    if not isinstance(value, dict):
        return
    acked = set(value.get("acked") or [])
    st.session_state.pending_ops = [o for o in st.session_state.pending_ops if o["id"] not in acked]
    st.session_state.dev_available = bool(value.get("available", True))
    st.session_state.dev_log = value.get("log") or []
    # Our own newer PIN change wins until the browser has confirmed it.
    if not any(o["type"] == "set_pin" for o in st.session_state.pending_ops):
        st.session_state.pin_rec = value.get("pin")
    # Children Mode stays ON after a refresh: the device remembers it.
    # (Our own newer on/off change wins until the browser has confirmed it.)
    if not any(o["type"] == "set_mode" for o in st.session_state.pending_ops):
        if value.get("mode"):
            st.session_state.children_mode = True
    st.session_state.dev_loaded = True


def set_children_mode(on: bool) -> None:
    st.session_state.children_mode = on
    _queue_op("set_mode", value=on)


def _hash_pin(pin: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), 200_000).hex()


def _make_record(pin: str) -> dict:
    salt = secrets.token_hex(16)
    return {"salt": salt, "hash": _hash_pin(pin, salt), "fails": 0, "locked_until": 0.0}


def _save_record(rec: dict) -> None:
    st.session_state.pin_rec = rec
    _queue_op("set_pin", rec=rec)


def _env_pin() -> str:
    pin = os.getenv("CHILDREN_MODE_PIN", "").strip()
    return pin if pin.isdigit() and len(pin) == 4 else ""


def ensure_pin_record() -> None:
    """A device with no PIN yet starts with CHILDREN_MODE_PIN, if that is set.
    Otherwise a grown-up creates one from the sidebar."""
    if st.session_state.dev_loaded and st.session_state.pin_rec is None and _env_pin():
        _save_record(_make_record(_env_pin()))


def set_first_pin(pin: str) -> None:
    _save_record(_make_record(pin))


def log_event(kind: str, text: str = "") -> None:
    """Add one line to this device's Children Mode log (enter, exit, chats...)."""
    entry = {
        "time": datetime.now(LOG_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "session": st.session_state.get("sid", "-"),
        "event": kind,
        "text": text[:1000],
    }
    _queue_op("log", entry=entry)


def read_log(limit: int = 300) -> list[dict]:
    """Return this device's newest log entries (oldest first)."""
    rows = list(st.session_state.dev_log)
    rows += [o["entry"] for o in st.session_state.pending_ops if o["type"] == "log"]
    return rows[-limit:]


def check_pin(pin: str) -> tuple[bool, str]:
    """Check a PIN. Too many wrong tries locks every attempt for a few minutes.
    The wrong-try counter is saved on this device, so refreshing does not reset it."""
    rec = st.session_state.pin_rec
    if rec is None:
        if not st.session_state.dev_loaded:
            return False, "Still loading this device's storage. Try again in a moment."
        return False, "No PIN has been created on this device yet."
    now = time.time()
    locked_until = rec.get("locked_until", 0.0)
    if now < locked_until:
        return False, f"Too many wrong tries. Please wait {int(locked_until - now) + 1} seconds."
    if pin.isdigit() and len(pin) == 4 and hmac.compare_digest(_hash_pin(pin, rec["salt"]), rec["hash"]):
        if rec.get("fails"):
            _save_record({**rec, "fails": 0})
        return True, ""
    fails = rec.get("fails", 0) + 1
    if fails >= MAX_PIN_TRIES:
        _save_record({**rec, "fails": 0, "locked_until": now + LOCKOUT_SECONDS})
        log_event("lockout", f"{MAX_PIN_TRIES} wrong PINs in a row. Locked for {LOCKOUT_SECONDS // 60} minutes.")
        return False, f"Too many wrong tries. Locked for {LOCKOUT_SECONDS // 60} minutes."
    _save_record({**rec, "fails": fails})
    return False, f"Wrong PIN. {MAX_PIN_TRIES - fails} tries left."


def rotate_pin() -> str:
    """Create a new random 4-digit PIN, store only its hash, and return it."""
    old_rec = st.session_state.pin_rec
    while True:
        new_pin = f"{secrets.randbelow(10000):04d}"
        if _hash_pin(new_pin, old_rec["salt"]) != old_rec["hash"]:
            break
    _save_record(_make_record(new_pin))
    return new_pin


def is_refusal(reply: str) -> bool:
    """True if the AI answered with the standard refusal sentence."""
    cleaned = re.sub(r"[^a-z ]", "", reply.lower()).strip()
    return cleaned.startswith(REFUSAL_TEXT.lower())


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------
def get_llm_reply(provider: str, api_key: str, model: str,
                  system_prompt: str, history: list[dict]) -> str:
    """Ask the selected LLM provider for a reply to the conversation."""
    cfg = PROVIDERS[provider]
    # timeout: fail with a clear error instead of waiting forever
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"], timeout=20, max_retries=2)  # worst case about 1 minute, then a clear error

    # Newer Gemini models "think" before answering, which can add many
    # seconds. Low effort keeps replies fast; a rant doesn't need deep thought.
    extra = {"reasoning_effort": "low"} if provider == "Gemini" else {}

    messages = [{"role": "system", "content": system_prompt}]
    messages += [
        {"role": m["role"], "content": m["content"]}
        for m in history[-HISTORY_WINDOW:]
        if not m.get("local")  # skip app-made notices such as the bad-word refusal
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.9,
        # Generous limit: Gemini 2.5 models count hidden "thinking" tokens
        # toward it, and a small value could leave the visible reply empty.
        # The prompts already keep replies short.
        max_tokens=1500,
        **extra,
    )
    return (response.choices[0].message.content or "").strip()


@st.cache_data(show_spinner=False, ttl=600)
def list_live_models(provider: str, api_key: str, base_url: str) -> list[str]:
    """Ask the provider which chat models this API key can really use."""
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=15, max_retries=0)
        names = [m.id.replace("models/", "") for m in client.models.list()]
        # Keep text chat models only (skip embeddings, image, speech, safety models)
        skip = ("embedding", "image", "tts", "aqa", "imagen", "veo", "live", "audio",
                "whisper", "guard", "orpheus", "playai", "transcribe")
        names = [n for n in names if not any(s in n for s in skip)]
        if provider == "Gemini":
            names = [n for n in names if n.startswith("gemini")]
        return sorted(set(names), reverse=True)
    except Exception:
        return []


def synthesize_speech(text: str, api_key: str, model_id: str = ELEVEN_MODEL_ID) -> bytes:
    """Send text to ElevenLabs (Adam voice) and return raw MP3 bytes."""
    response = requests.post(
        ELEVEN_TTS_URL.format(voice_id=ADAM_VOICE_ID),
        params={"output_format": "mp3_44100_128"},
        headers={
            "xi-api-key": api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        json={
            "text": text[:MAX_TTS_CHARS],
            "model_id": model_id,
            "voice_settings": {
                "stability": VOICE_STABILITY,
                "similarity_boost": VOICE_SIMILARITY_BOOST,
            },
        },
        timeout=45,
    )
    if not response.ok:
        # Surface ElevenLabs' own error message (bad key, quota, plan, etc.)
        raise RuntimeError(f"ElevenLabs error {response.status_code}: {response.text[:300]}")
    return response.content


@st.cache_data(show_spinner=False, max_entries=64)
def squeakify(mp3_bytes: bytes, multiplier: float) -> bytes:
    """
    Replicate CapCut's speed-up WITHOUT pitch correction.

    Trick: keep the raw samples but tell pydub they were recorded at a higher
    frame rate. Played back at the original rate, the audio is both faster
    and higher-pitched (squeaky). We then set the frame rate back to the
    standard 44100 Hz so browsers play it correctly; this resamples the
    audio while preserving the new speed and pitch.

    Cached, so moving the slider never re-bills ElevenLabs: the original
    audio is stored and only this cheap step is re-run.
    """
    audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")

    fast = audio._spawn(
        audio.raw_data,
        overrides={"frame_rate": int(audio.frame_rate * multiplier)},
    )
    fast = fast.set_frame_rate(OUTPUT_SAMPLE_RATE)

    buffer = io.BytesIO()
    fast.export(buffer, format="mp3", bitrate="192k")
    return buffer.getvalue()


def play_hidden_audio(audio_bytes: bytes) -> None:
    """
    Play audio once in the browser with no visible player.

    Adds an invisible <audio autoplay> element. The unique id makes the browser
    create a brand-new element every time, so pressing Replay plays it again.
    """
    token = time.time_ns()
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    st.html(
        f'<audio id="voice_{token}" autoplay style="display:none" '
        f'src="data:audio/mpeg;base64,{b64}"></audio>'
    )


def render_message(index: int, msg: dict, multiplier: float) -> None:
    """Draw one chat message, plus its audio player and download button."""
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("timing"):
            st.caption(msg["timing"])  # shows where the time went

        if msg.get("tts_error"):
            st.warning(f"Voice generation failed. {msg['tts_error']}")

        raw_audio = msg.get("raw_audio")
        if not raw_audio:
            return

        try:
            audio_bytes = squeakify(raw_audio, multiplier)
        except Exception as exc:  # most often: FFmpeg not installed
            st.error(
                f"Could not process the audio ({exc}). "
                "Make sure FFmpeg is installed and on your PATH (see README)."
            )
            return

        # No visible player. The voice is spoken once automatically for a fresh
        # reply (msg["autoplay"], popped so it never repeats on later reruns),
        # and the Replay button plays the SAME stored audio again, with no
        # new LLM or ElevenLabs request.
        play_now = bool(msg.pop("autoplay", False))

        replay_col, download_col, _ = st.columns([1, 1.3, 3])
        with replay_col:
            if st.button("🔁 Replay", key=f"replay_{index}"):
                play_now = True
        with download_col:
            st.download_button(
                "Download MP3",
                data=audio_bytes,
                file_name=f"roblox_ranter_{index + 1}.mp3",
                mime="audio/mpeg",
                key=f"download_{index}",
            )

        if play_now:
            play_hidden_audio(audio_bytes)

        # Phone browsers often block automatic sound until you tap something.
        st.caption("No sound? Tap 🔁 Replay (phones can block autoplay).")


# --------------------------------------------------------------------------
# Page + sidebar
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Roblox Ranter Voice Chat",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="expanded",  # so phone users see the key boxes first
)

# Phone-friendly styling: big tap targets, full-width buttons on small
# screens, and 16px text in the chat box (stops iPhone Safari auto-zooming).
st.markdown(
    """
    <style>
    @media (max-width: 640px) {
        .block-container { padding: 1rem 0.8rem 5rem 0.8rem; }
        h1 { font-size: 1.6rem !important; }
        div.stButton > button,
        div.stDownloadButton > button { width: 100%; min-height: 3rem; font-size: 1rem; }
    }
    div[data-testid="stChatInput"] textarea { font-size: 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🎙️ Roblox Ranter Voice Chat")
st.caption(
    "Chat with an AI that answers in a fast, squeaky Adam voice. "
    "On a phone: open the menu (top-left arrow) to add your API keys."
)

if "messages" not in st.session_state:
    st.session_state.messages = []
# Children Mode data that lives in this device's browser (see device_store/).
for _name, _default in (("pending_ops", []), ("dev_log", []), ("pin_rec", None),
                        ("dev_loaded", False), ("dev_available", True)):
    if _name not in st.session_state:
        st.session_state[_name] = _default
if "sid" not in st.session_state:
    st.session_state.sid = secrets.token_hex(2)  # short id to tell visitors apart in the log
if "children_mode" not in st.session_state:
    env_default = os.getenv("CHILDREN_MODE_DEFAULT", "").strip().lower() in ("1", "true", "yes", "on")
    st.session_state.children_mode = DEFAULT_CHILDREN_MODE or env_default
    if st.session_state.children_mode:
        log_event("enter", "Session started with Children Mode already ON (default)")
if "unlocking" not in st.session_state:
    st.session_state.unlocking = False
if "show_log" not in st.session_state:
    st.session_state.show_log = False
if "agent_active" not in st.session_state:
    st.session_state.agent_active = False  # voice is OFF until the user starts it

# Invisible component: saves/loads the PIN record and log in THIS browser.
sync_device(device_store(ops=st.session_state.pending_ops, key="device_store", default=None))
ensure_pin_record()

with st.sidebar:
    st.header("Settings")

    st.subheader("Language model")
    provider = st.selectbox("Provider", list(PROVIDERS.keys()))
    cfg = PROVIDERS[provider]
    # Keys saved in .env (local) or Streamlit secrets (online) are used as a
    # fallback and are never sent to the browser or shown in the field.
    # In Children Mode the key boxes are locked: keys cannot be changed or removed.
    locked = st.session_state.children_mode
    saved_llm_key = os.getenv(cfg["env_key"], "")
    llm_store = f"stored_llm_key_{provider}"
    if locked:
        st.text_input(f"{provider} API key", type="password", disabled=True,
                      placeholder="🔒 Locked in Children Mode", key=f"locked_llm_{provider}")
    else:
        llm_field = f"llm_key_input_{provider}"
        if llm_field not in st.session_state:  # refill after Children Mode was on
            st.session_state[llm_field] = st.session_state.get(llm_store, "")
        typed_llm_key = st.text_input(
            f"{provider} API key",
            type="password",
            key=llm_field,
            placeholder="Using saved key" if saved_llm_key else "Paste your key",
            help=f"Or set {cfg['env_key']} in your .env file / Streamlit secrets.",
        )
        st.session_state[llm_store] = typed_llm_key.strip()
    llm_key = st.session_state.get(llm_store, "") or saved_llm_key
    model_choices = cfg["models"]
    if provider in ("Gemini", "Groq") and llm_key:
        live_models = list_live_models(provider, llm_key, cfg["base_url"])
        if live_models:
            model_choices = live_models
            st.caption(f"Loaded {len(live_models)} models available to your key.")
        else:
            st.caption("Could not load your model list (check the key). Using defaults.")
    model = st.selectbox("Model", model_choices)
    custom_model = st.text_input("Custom model name (optional)", value="")
    if custom_model.strip():
        model = custom_model.strip()

    st.subheader("Voice")
    saved_eleven_key = os.getenv("ELEVENLABS_API_KEY", "")
    if locked:
        st.text_input("ElevenLabs API key", type="password", disabled=True,
                      placeholder="🔒 Locked in Children Mode", key="locked_eleven_key")
    else:
        if "eleven_key_input" not in st.session_state:
            st.session_state["eleven_key_input"] = st.session_state.get("stored_eleven_key", "")
        typed_eleven_key = st.text_input(
            "ElevenLabs API key",
            type="password",
            key="eleven_key_input",
            placeholder="Using saved key" if saved_eleven_key else "Paste your key",
            help="Or set ELEVENLABS_API_KEY in your .env file / Streamlit secrets.",
        )
        st.session_state["stored_eleven_key"] = typed_eleven_key.strip()
    eleven_key = st.session_state.get("stored_eleven_key", "") or saved_eleven_key
    voice_model_label = st.selectbox(
        "Voice speed vs. quality",
        ["Fast (Flash v2.5)", "Best quality (Multilingual v2)"],
        help="Fast generates the voice much quicker. Best quality is slower.",
    )
    voice_model_id = (
        "eleven_flash_v2_5" if voice_model_label.startswith("Fast") else "eleven_multilingual_v2"
    )
    multiplier = st.slider(
        "Speed / Pitch multiplier",
        min_value=1.0, max_value=1.5, value=1.28, step=0.01,
        help="Higher = faster AND squeakier. Applies instantly to all replies.",
    )

    st.subheader("Style")
    ranter_mode = st.toggle(
        "Roblox Ranter Mode", value=True,
        help="Energetic, dramatic, funny Roblox storytelling replies.",
    )

    # ---- Children Mode: easy to turn ON, needs the 4-digit PIN to turn OFF ----
    st.subheader("Children Mode")
    if not st.session_state.dev_loaded:
        st.caption("⏳ Loading this device's saved settings... (PIN and Children Mode need this)")
    if st.session_state.get("flash"):
        st.error(st.session_state.pop("flash"))
    if st.session_state.get("new_pin_notice"):
        st.success(f"New PIN: **{st.session_state.new_pin_notice}**")
        st.warning("Write it down now. It is shown only once and cannot be looked up later.")
        if st.button("I wrote it down"):
            st.session_state.new_pin_notice = None
            st.rerun()
    if not st.session_state.dev_available:
        st.warning("This browser blocks local storage, so the PIN and log are lost when the page is refreshed.")
    if st.session_state.dev_loaded and st.session_state.pin_rec is None:
        st.info("No PIN on this device yet. A grown-up must create one (the PIN and log stay on this device only).")
        with st.form("first_pin_form", clear_on_submit=True):
            first_pin = st.text_input("Create a 4-digit PIN", type="password", max_chars=4)
            create_pin = st.form_submit_button("Save PIN")
        if create_pin:
            if first_pin.strip().isdigit() and len(first_pin.strip()) == 4:
                set_first_pin(first_pin.strip())
                log_event("pin_set", "A PIN was created on this device")
            else:
                st.session_state.flash = "The PIN must be exactly 4 digits."
            st.rerun()
    if not st.session_state.children_mode:
        if st.button("🧒 Turn ON Children Mode (ages 7-9)"):
            set_children_mode(True)
            st.session_state.unlocking = False
            log_event("enter", "Children Mode turned ON")
            st.rerun()
        st.caption("Add your API keys first: they are locked while Children Mode is on.")
    else:
        st.success("🔒 Children Mode is ON. Replies are 100% family-friendly.")
        st.caption("📝 Chats in Children Mode are saved in a log on this device that grown-ups can read.")
        if not st.session_state.unlocking:
            if st.button("Turn OFF (needs PIN)"):
                st.session_state.unlocking = True
                st.rerun()
        else:
            with st.form("unlock_form", clear_on_submit=True):
                pin_try = st.text_input("Enter the 4-digit PIN", type="password", max_chars=4)
                unlock = st.form_submit_button("Unlock")
            if unlock:
                ok, message = check_pin(pin_try.strip())
                if ok:
                    set_children_mode(False)
                    st.session_state.unlocking = False
                    log_event("exit", "Children Mode turned OFF with the correct PIN")
                    st.rerun()
                log_event("exit_failed", message)
                st.session_state.flash = message
                st.rerun()
            if st.button("Cancel"):
                st.session_state.unlocking = False
                st.rerun()

    with st.expander("🔐 Grown-ups: scramble PIN / read log"):
        with st.form("rotate_form", clear_on_submit=True):
            old_pin = st.text_input("Current PIN", type="password", max_chars=4)
            rotate = st.form_submit_button("🔀 Scramble PIN")
        if rotate:
            ok, message = check_pin(old_pin.strip())
            if ok:
                st.session_state.new_pin_notice = rotate_pin()
                log_event("pin_rotated", "The PIN was scrambled")
            else:
                log_event("pin_change_failed", message)
                st.session_state.flash = message
            st.rerun()
        with st.form("log_form", clear_on_submit=True):
            log_pin = st.text_input("Current PIN (to read the log)", type="password", max_chars=4)
            read_log_clicked = st.form_submit_button("📝 Show log")
        if read_log_clicked:
            ok, message = check_pin(log_pin.strip())
            if ok:
                st.session_state.show_log = True
                st.rerun()
            log_event("log_failed", message)
            st.session_state.flash = message
            st.rerun()

    children_mode = st.session_state.children_mode

    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

# --------------------------------------------------------------------------
# Children Mode log viewer (opened with the PIN from the sidebar)
# --------------------------------------------------------------------------
if st.session_state.show_log:
    with st.container(border=True):
        st.subheader("📝 Children Mode log")
        log_rows = read_log()
        if log_rows:
            st.dataframe(log_rows[::-1])  # newest first
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=["time", "session", "event", "text"])
            writer.writeheader()
            for row in log_rows:
                writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
            st.download_button("Download log (.csv)", data=csv_buffer.getvalue(),
                               file_name="children_mode_log.csv", mime="text/csv")
        else:
            st.caption("Nothing has been logged yet.")
        if st.button("Hide log"):
            st.session_state.show_log = False
            st.rerun()

# --------------------------------------------------------------------------
# Start / Stop Agent button (controls whether replies have voice)
# --------------------------------------------------------------------------
agent_col, status_col = st.columns([1, 3])
with agent_col:
    if not st.session_state.agent_active:
        if st.button("▶️ Start Agent", type="primary", use_container_width=True):
            st.session_state.agent_active = True
            st.rerun()
    else:
        if st.button("⏹️ Stop Agent", use_container_width=True):
            st.session_state.agent_active = False
            st.rerun()
with status_col:
    if st.session_state.agent_active:
        if eleven_key:
            st.success("Agent ON: replies are spoken in the squeaky Adam voice.")
        else:
            st.warning("Agent ON, but no ElevenLabs key yet. Add it in the sidebar.")
    else:
        st.info("Agent OFF: replies are text only. Press Start Agent for voice.")

# --------------------------------------------------------------------------
# Chat history
# --------------------------------------------------------------------------
for i, message in enumerate(st.session_state.messages):
    render_message(i, message, multiplier)

# --------------------------------------------------------------------------
# New message handling
# --------------------------------------------------------------------------
if prompt := st.chat_input("Type a message..."):
    if not st.session_state.dev_loaded:
        st.error("Still loading this device's settings. Please send it again in a moment.")
        st.stop()
    if not llm_key:
        st.error(f"Please enter your {provider} API key in the sidebar.")
        st.stop()

    if children_mode:
        log_event("chat_input", prompt)

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    system_prompt = RANTER_PROMPT if ranter_mode else NORMAL_PROMPT
    if children_mode:
        # The AI does the bad-word check itself (no word list is used).
        system_prompt += "\n\n" + CHILDREN_RULE + "\n\n" + CHILDREN_INPUT_CHECK

    # Step 1: LLM text reply
    t_start = time.time()
    try:
        with st.spinner("Thinking..."):
            reply_text = get_llm_reply(
                provider, llm_key, model, system_prompt, st.session_state.messages
            )
    except Exception as exc:
        st.session_state.messages.pop()  # let the user retry the same message
        st.error(f"LLM request failed: {exc}")
        st.stop()

    llm_seconds = time.time() - t_start
    assistant_msg = {"role": "assistant", "content": reply_text}
    timing = f"Text: {llm_seconds:.1f}s"

    # Children Mode: did the AI refuse the input? Log it, keep this exchange
    # out of the AI's future context, and do not spend voice credits on it.
    refused = children_mode and is_refusal(reply_text)
    if refused:
        log_event("filtered", f"Input: {prompt} | AI said: {reply_text}")
        st.session_state.messages[-1]["local"] = True  # the user message
        assistant_msg["local"] = True

    # Step 2: ElevenLabs voice, ONLY while the agent is started.
    # (The speed-up itself happens at render time.)
    if st.session_state.agent_active and not refused:
        if not eleven_key:
            assistant_msg["tts_error"] = "Add your ElevenLabs API key in the sidebar to hear the voice."
        elif reply_text:
            t_voice = time.time()
            try:
                with st.spinner("Recording Adam..."):
                    assistant_msg["raw_audio"] = synthesize_speech(
                        reply_text, eleven_key, voice_model_id
                    )
                assistant_msg["autoplay"] = True
                timing += f" | Voice: {time.time() - t_voice:.1f}s"
            except Exception as exc:
                assistant_msg["tts_error"] = str(exc)

    assistant_msg["timing"] = timing
    st.session_state.messages.append(assistant_msg)
    st.rerun()
