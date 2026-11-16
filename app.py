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
import io
import os
import time

import requests
import streamlit as st
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
    "emojis or stage directions, because your reply will be read aloud and STRICT RULE: Your audience is 7 to 9 years old. Keep everything 100% family-friendly, clean, and PG-rated. Never use swear words, curse words, adult jokes, violence, or scary topics, even if the user asks you to. ."
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


# --------------------------------------------------------------------------
# Page + sidebar
# --------------------------------------------------------------------------
st.set_page_config(page_title="Roblox Ranter Voice Chat", page_icon="🎙️")
st.title("🎙️ Roblox Ranter Voice Chat")
st.caption("Chat with an AI that answers in a fast, squeaky Adam voice.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_active" not in st.session_state:
    st.session_state.agent_active = False  # voice is OFF until the user starts it

with st.sidebar:
    st.header("Settings")

    st.subheader("Language model")
    provider = st.selectbox("Provider", list(PROVIDERS.keys()))
    cfg = PROVIDERS[provider]
    # Keys saved in .env (local) or Streamlit secrets (online) are used as a
    # fallback and are never sent to the browser or shown in the field.
    saved_llm_key = os.getenv(cfg["env_key"], "")
    typed_llm_key = st.text_input(
        f"{provider} API key",
        value="",
        type="password",
        placeholder="Using saved key" if saved_llm_key else "Paste your key",
        help=f"Or set {cfg['env_key']} in your .env file / Streamlit secrets.",
    )
    llm_key = typed_llm_key.strip() or saved_llm_key
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
    typed_eleven_key = st.text_input(
        "ElevenLabs API key",
        value="",
        type="password",
        placeholder="Using saved key" if saved_eleven_key else "Paste your key",
        help="Or set ELEVENLABS_API_KEY in your .env file / Streamlit secrets.",
    )
    eleven_key = typed_eleven_key.strip() or saved_eleven_key
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

    if st.button("Clear chat"):
        st.session_state.messages = []
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
    if not llm_key:
        st.error(f"Please enter your {provider} API key in the sidebar.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    system_prompt = RANTER_PROMPT if ranter_mode else NORMAL_PROMPT

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

    # Step 2: ElevenLabs voice, ONLY while the agent is started.
    # (The speed-up itself happens at render time.)
    if st.session_state.agent_active:
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
