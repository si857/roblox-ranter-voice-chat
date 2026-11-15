# 🎙️ Roblox Ranter Voice Chat [cilck here to get the github source code](https://github.com/roblox-ranter-voice-chat/)
)


A Streamlit chatbot that replies in the **squeaky, fast-talking Roblox story narrator** voice.

1. You type a message.
2. An LLM (**Groq**, **OpenAI** or **Gemini**) writes the reply.
3. **ElevenLabs** speaks it with the **Adam** voice (`pNInz6obpgDQGcFmaJgB`, stability `0.40`, similarity boost `0.75`).
4. **pydub** speeds the audio up by `1.28x` *without pitch correction* (the CapCut speed-up effect), so it comes out fast and high-pitched.
5. The audio autoplays in your browser, and you can download it as an MP3 for your videos.

## Features

- Chat UI with history
- Provider switch (Groq / OpenAI / Gemini) and model picker in the sidebar
- API keys from the sidebar or a `.env` file
- Speed/pitch slider (1.0 to 1.5, default 1.28) that updates all replies instantly, without calling ElevenLabs again
- "Roblox Ranter Mode" toggle for energetic, dramatic, funny storytelling replies
- **Start Agent / Stop Agent** button: while the agent is started, every reply is spoken; while it is stopped, replies are text only (no ElevenLabs credits used)
- Autoplay for each new reply, plus a **Download MP3** button on every message
- Ready to deploy online (Streamlit Community Cloud), so it works from any browser, including your phone

## Setup

### 1. Install FFmpeg (required by pydub)

pydub needs FFmpeg to decode and encode MP3 files.

| OS | Command |
|----|---------|
| Windows | `winget install ffmpeg` (or `choco install ffmpeg`, or download from https://ffmpeg.org/download.html and add the `bin` folder to your PATH) |
| macOS | `brew install ffmpeg` |
| Ubuntu / Debian | `sudo apt update && sudo apt install ffmpeg` |

Verify it works (open a **new** terminal after installing):

```bash
ffmpeg -version
```

### 2. Get the code and create a virtual environment

```bash
git clone <your-repo-url>
cd <your-repo-folder>

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API keys

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env` and fill in:

- `ELEVENLABS_API_KEY` from https://elevenlabs.io (Profile, API Keys)
- One LLM key (pick whichever provider you want to use):
  - `GROQ_API_KEY` from https://console.groq.com/keys
  - `OPENAI_API_KEY` from https://platform.openai.com/api-keys
  - `GEMINI_API_KEY` from https://aistudio.google.com/apikey

You can also skip the `.env` file and paste keys into the sidebar each time.

### 5. Run the app

```bash
streamlit run app.py
```

It opens at http://localhost:8501. Press **Start Agent** to get voiced replies.

## Deploy online (Streamlit Community Cloud)

Run it as a web app anyone can open from a link, with nothing to install on your computer.

1. Push this project to a GitHub repository (never commit `.env`; it's git-ignored).
2. Go to https://share.streamlit.io, sign in with GitHub and click **Create app**.
3. Pick your repository, branch `main`, and main file `app.py`.
4. Open **Advanced settings > Secrets** and paste your keys (see `.streamlit/secrets.toml.example`):

   ```toml
   GEMINI_API_KEY = "your_key"        # or GROQ_API_KEY / OPENAI_API_KEY
   ELEVENLABS_API_KEY = "your_key"
   ```

5. Click **Deploy**.

FFmpeg is installed automatically on Streamlit Cloud because `packages.txt` lists it, so you don't install it there.

**Important: protect your credits.** If you save your keys as secrets and make the app public, anyone with the link can chat and spend your Gemini/OpenAI/ElevenLabs credits. Either set the app to private (App settings > Sharing, then invite specific people), or leave the secrets empty so each visitor pastes their own keys in the sidebar. Saved keys are never shown or sent to the browser, only used on the server.

## How the squeaky effect works

```python
fast = audio._spawn(audio.raw_data,
                    overrides={"frame_rate": int(audio.frame_rate * 1.28)})
fast = fast.set_frame_rate(44100)
```

The first line keeps the same samples but labels them with a 1.28x higher frame rate, so they play faster *and* higher in pitch (no pitch correction, just like CapCut's plain speed-up). The second line resamples back to the standard 44100 Hz so browsers play the file correctly while keeping the new speed and pitch.

## Troubleshooting

- **"Could not process the audio" / `FileNotFoundError: ffmpeg`**: FFmpeg isn't installed or isn't on your PATH. Redo step 1 and restart your terminal.
- **`ModuleNotFoundError: audioop`** on Python 3.13+: run `pip install -r requirements.txt` again; `audioop-lts` is included for this.
- **ElevenLabs 401 / 402 / "paid plan required"**: check your key. ElevenLabs may restrict some library voices on free plans when used through the API; if Adam is blocked for you, you'll need a paid ElevenLabs plan.
- **Audio doesn't autoplay**: some browsers block autoplay until you've interacted with the page. Sending a chat message counts as interaction, but if it still doesn't play, press play once and allow audio for the site in your browser settings.
- **Model not found**: use the "Custom model name" box in the sidebar to enter any model your provider offers.

## Notes

- Keep replies short: ElevenLabs charges credits per character. The app caps each voiced reply at 2,500 characters.
- Never commit your `.env` file. It's already in `.gitignore`.

## Project structure

```
.
├── app.py              # Streamlit app (chat, LLM, ElevenLabs, pydub effect)
├── requirements.txt    # Python dependencies
├── packages.txt        # System packages for deployment (FFmpeg)
├── .env.example        # Template for your API keys (local use)
├── .streamlit/
│   └── secrets.toml.example   # Template for Streamlit Cloud secrets
├── .gitignore
└── README.md
```
