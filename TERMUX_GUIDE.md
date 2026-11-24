# 📱 Dual-Bot App — Termux & Mobile Setup Guide

This app allows you to run **both Bot 1 (Alert)** and **Bot 2 (Hybrid)** simultaneously and control every feature through a web dashboard right from your Android phone's browser or PC.

---

### 1. Requirements in Termux

If you haven't already installed the basics in Termux, run:
```bash
pkg update && pkg upgrade -y
pkg install python git -y
pip install requests beautifulsoup4 python-dotenv python-telegram-bot
```

---

### 2. How to Run the App

1. Place the `dual-bot-app` folder on your device.
2. In Termux, navigate to the folder:
   ```bash
   cd dual-bot-app
   ```
3. Run the launch script:
   ```bash
   bash run.sh
   ```
   *(or directly `python app.py`)*

4. Open Chrome or any browser on your phone and visit:
   ```
   http://localhost:8080
   ```
   *(Or if accessing from your PC on the same Wi-Fi, visit `http://<phone-ip>:8080`)*

---

### 3. Add to Home Screen (Progressive Web App)

To make it look and feel like an actual Android App:
1. Open `http://localhost:8080` in Google Chrome on your phone.
2. Tap the **3 dots menu** (top right) in Chrome.
3. Tap **"Add to Home screen"** or **"Install App"**.
4. An icon named **"Dual-Bot Center"** will appear on your phone's home screen! You can now launch it with a single tap just like a native app.

---

### 4. What You Can Control Inside the App

- **🎮 Dual-Bot Controls:** Start or stop Bot 1 and Bot 2 with one tap. Choose your exact login profile (Admin Cookie, User 1 Cookie, User 2 Cookie, System ENV, Login 1, or Login 2).
- **🍪 Cookies & Creds:** View, add, edit, or reset cookies and login passwords without touching JSON files.
- **👥 Users & Subscriptions:** View all registered Telegram users, approve 2-Day or 30-Day plans, reject requests, send direct messages, or broadcast to everyone.
- **💬 Notification Editor:** Edit all Telegram messages (job alerts, reminders, welcome messages, error notices) with custom emojis and live preview!
- **⚙️ .env Editor:** Change any environment setting (intervals, delays, shutdown limits, credentials) on the fly.
- **📟 Live Terminal Logs:** Watch live colored logs for each bot in real time.
