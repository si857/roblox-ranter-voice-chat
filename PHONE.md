# 📱 Using Roblox Ranter Voice Chat on a phone

## Option 1: Just open the link (easiest, no setup)

Open your deployed `.streamlit.app` link in Chrome or Safari on your phone.

1. Tap the small arrow at the top left to open the menu.
2. Pick a provider and paste your API keys (Gemini or Groq, and ElevenLabs).
3. Close the menu, tap **Start Agent**, and type a message.
4. If you don't hear the voice, tap **🔁 Replay**. Phone browsers often block
   sound that starts by itself, but a tap always allows it.
5. Tip: use your browser's "Add to Home screen" to get an app-like icon.

Nothing needs to be installed on the phone, and no special permissions are needed.

## Option 2: Run it on the phone itself (Android + Termux, advanced)

This runs the Python app on the phone, so it works without the deployed link.

1. Install **Termux** from F-Droid (the Play Store version is outdated).
2. In Termux, run:
   ```bash
   pkg update && pkg install python ffmpeg git
   termux-setup-storage
   git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
   cd YOUR-REPO
   pip install streamlit openai requests pydub python-dotenv
   streamlit run app.py
   ```
3. Open `http://localhost:8501` in your phone's browser.

If you would rather copy the files from your computer than use git, put the
project folder in your phone's normal storage (Downloads, for example), then in
Termux run `cp -r ~/storage/downloads/roblox-ranter-AI ~/` and `cd ~/roblox-ranter-AI`.

### Is Shizuku needed?
No. Termux can read your normal storage after `termux-setup-storage`, and git
can fetch the files directly. Shizuku is only useful for reaching protected
folders such as `Android/data`, which this app does not need.
