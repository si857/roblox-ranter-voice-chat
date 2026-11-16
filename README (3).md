# 🎙️ Roblox Ranter Voice Chat

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

## Children Mode (ages 7 to 9)

Turn it on with **🧒 Turn ON Children Mode** in the sidebar. While it is on:

- The AI is told to keep everything 100% family-friendly and PG-rated.
- The **AI checks every message** for bad words. If it finds one, it replies
  "I refuse to answer your input due to limitations" and nothing else.
- The API key boxes are **locked**, so keys cannot be changed or removed.
  Add your keys *before* turning it on.
- Turning it off needs a **4-digit PIN**. Five wrong tries lock every attempt
  for 5 minutes.
- Everything is **logged**: entering and leaving the mode, failed PIN tries,
  every message typed, and every refusal. Open **🔐 Grown-ups: scramble PIN /
  read log** and enter the PIN to read or download the log.
- **Scramble PIN** creates a new random PIN (the current PIN is required). The
  new PIN is shown **only once**. Only a salted hash of the PIN is stored.

**Setting the PIN:** put `CHILDREN_MODE_PIN=1234` in your `.env` (or Streamlit
secrets). If you don't, a random PIN is created the first time the app starts
and printed once in the black window (or the app logs on Streamlit Cloud).
The PIN hash and the log are kept in the `children_mode_data/` folder, which is
in `.gitignore`. To reset the PIN, delete `children_mode_data/pin.json`.

**Always-on for a family copy:** set `CHILDREN_MODE_DEFAULT=1` (or
`DEFAULT_CHILDREN_MODE = True` in `app.py`). The app then starts in Children
Mode every time, and refreshing the page or opening a new tab cannot turn it
off. Only the PIN can.

**Please note**
- The log is stored on the server running the app. On a **public** shared app,
  every visitor shares one PIN and one log, so use Children Mode with a private
  copy of the app that you run for your own family.
- On Streamlit Cloud the server's disk is wiped when the app restarts, so a
  scrambled PIN and the log can reset. Set `CHILDREN_MODE_PIN` in the Secrets
  so you always know the starting PIN.
- The check is done by the AI, which is strong but not perfect. An adult should
  still be nearby for young children.

## 🧒 Kid's Guide: How to Play on Phone & Laptop

> **👨‍👩‍👧 Grown-Ups:** Think of this as setting up the batteries before handing over the toy! Please open the sidebar (`>`), enter your API keys, and tap **🧒 Turn ON Children Mode** first. This locks the settings with your secret PIN and keeps every story 100% kid-safe.

---

### 📱 On a Phone or Tablet (Like a Pocket Walkie-Talkie)

1. **Open the toy box**: Ask a grown-up to open the app on your phone or tablet.
2. **Open the secret control panel**: Tap the **`>`** arrow in the top-left corner (it's like opening the battery door on a toy!).
3. **Set up your talking robot**:
   - Turn ON **Roblox Ranter Mode** — this gives your robot super silly, dramatic energy!
   - Slide the **Speed** bar — moving it up is like turning a **chipmunk dial** to make the voice faster and squeakier!
   - Tap **Start Agent** — this is the **ON switch** for the robot's mouth. *(If it is OFF, the robot only writes notes instead of talking out loud).*
4. **Close the control panel**: Tap the **`X`** in the top-left corner to go back to the chat screen.
5. **Send a message & listen**: Type a funny story idea in the bottom box and tap **Send** (like sending a text to your robot friend).
   - *Secret Tip!* Phones sometimes keep the volume asleep at first. If it stays quiet, tap the **Play ▶️** button once to wake up the speaker!
6. **Keep the funny voice**: Tap **Download MP3** to put that voice clip in your pocket (your phone's Downloads folder) so you can replay it anytime!

---

### 💻 On a Laptop or Computer (Like a Mission Control Desk)

1. **Open the screen**: Ask a grown-up to open the app in your web browser.
2. **Check the control panel on the left**:
   - Flip ON **Roblox Ranter Mode** for wild, funny storytelling.
   - Move the **Speed** slider to pick how high and squeaky the chipmunk voice gets.
   - Click **Start Agent** to wake up the voice box so the computer talks out loud.
3. **Type your story**: Click the box at the bottom, type what you want the narrator to say, and press **Enter** (your launch button!).
4. **Listen & save**: Sit back and hear your funny story! Click **Download MP3** if you want to save the sound clip onto your computer.

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

## Children Mode data is stored per device

The PIN (as a salted hash), the wrong-PIN counter and the Children Mode log are
saved in each device's own browser (localStorage), not on the server. Every
device has its own PIN and its own log, and nothing is shared. The code for this
is in the `device_store/` folder, so keep that folder next to `app.py`.

- On a device with no PIN, a grown-up creates one in the sidebar. If the
  `CHILDREN_MODE_PIN` secret/environment variable is set (4 digits), every
  device starts with that PIN instead.
- Clearing the browser's site data deletes that device's PIN and log. Set
  `CHILDREN_MODE_PIN` so the PIN comes back as the same one.
