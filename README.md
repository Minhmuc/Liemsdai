# 🍭 LieMSdai

Welcome to **LieMSdai**, the highly sophisticated, 100% totally serious, definitely-not-a-meme tool for *extracting* (read: licking) test questions from your LMS like a pro.  
Made for students, teachers, and anyone who looks at LMS JSON data and thinks:  
> "Yeah… I’d rather eat glass than format this manually."

🌍 Live Demo: [lms.liemsdai.is-best.net](https://lms.liemsdai.is-best.net)

---

## 🥂 Features (a.k.a. Reasons to Use This Instead of Crying)

- **Expert Mode 🧠**  
  📂 Upload JSON/TXT or paste raw JSON.  
  🧼 Automatically cleans and formats questions.  
  📋 One-click copy so you can flex your notes.  
  📄 Export to `.docx` because Word still rules the world.

- **Casual Mode 🐔**  
  📜 Browse server files like you’re in 2005.  
  ⬇️ Download without thinking too hard.  
  🫠 So simple, even your goldfish can use it.

- **Master Mode 🛠️**  
  🔐 Password-protected admin panel with epic "UNLOCKED" animation.  
  📤 Upload files directly to Google Drive via drag-drop.  
  🗑️ Delete files with one click.  
  ☁️ Persistent storage across deployments (no more lost files).

- **Customizable UI**  
  🌞 Light mode for the morning coffee people.  
  🌚 Dark mode for the night goblins (synced across all pages).  
  🖼 Different background images for each page.  
  ⚡ Cyberpunk glitch effects on hover (because aesthetics matter).

---

## 🧪 How to Use (Without Breaking Things)

### Expert Mode 🧠
1. Click **Expert Mode**.
2. Throw in your JSON/TXT file (or paste it like a barbarian).
3. Press **Liếm luôn** (translation: "Lick it NOW").
4. Profit 💰.

### Casual Mode 🐔
1. Click **Casual Mode**.

### Master Mode 🛠️
1. Click **Master Mode**.
2. Enter password (hint: it's "admin123" but you didn't hear that from me).
3. Watch the epic "UNLOCKED" animation.
4. Upload files via drag-drop or button.
5. Delete files you no longer need.
6. Files sync to Google Drive instantly.

---

## 🛠 Tech Stuff

- **Frontend:** HTML, CSS, Vanilla JS (because frameworks are for cowards)  
- **Backend:** Python Flask  
- **Storage:** Google Drive API with OAuth 2.0  
- **Monetization:** Shrinkme API for ad links  
- **Export Magic:** `python-docx`  
- **Font:** Minecraft.ttf (*for peak gamer vibes*)  
- **Effects:** Custom CSS animations (cyberpunk glitch, text morphing, unlock animations)

---

## 🏗 Local Setup (a.k.a. How to Summon This Beast)

```bash
git clone https://github.com/Minhmuc/Liemsdai.git
cd Liemsdai
pip install -r requirements.txt

# Set up Google Drive API (optional, for file storage)
# 1. Create OAuth 2.0 credentials in Google Cloud Console
# 2. Save as credentials.json
# 3. Run: python setup_oauth.py
# 4. Follow browser authentication

# Set environment variables (optional)
# USE_GOOGLE_DRIVE=true
# DRIVE_FOLDER_ID=your_folder_id
# ADMIN_PASSWORD=your_password
# SHRINKME_API_KEY=your_api_key

python fromminhmoi.py
