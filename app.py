# ═══════════════════════════════════════════════════════════════════════════════
# DUAL-BOT APP — UNIFIED CONTROLLER & LOCAL SERVER (ZERO-DEPENDENCY)
# ═══════════════════════════════════════════════════════════════════════════════

import os, sys, json, threading, asyncio, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from engine.instance_manager import instance_manager, BASE_DIR

WEB_DIR = os.path.join(BASE_DIR, "web")
PORT = int(os.environ.get("PORT", "8080"))

# Background Event Loop for Bot Instances
bot_loop = None

def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(instance_manager.start_all())
    loop.run_forever()

class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default HTTP access logs to keep console clean
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ── API ROUTES ────────────────────────────────────────────────────────
        if path == "/api/status":
            return self.send_json({"ok": True, "bots": instance_manager.get_all_status()})

        elif path == "/api/logs":
            qs = parse_qs(parsed.query)
            bot_id = qs.get("bot_id", [None])[0]
            return self.send_json({"ok": True, "logs": instance_manager.get_logs(bot_id)})

        elif path == "/api/templates":
            return self.send_json({"ok": True, "templates": instance_manager.get_templates()})

        elif path.startswith("/api/bot/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 3:
                bot_id = parts[2]
                sub = parts[3] if len(parts) > 3 else "status"
                bot = instance_manager.get_bot(bot_id)
                if not bot:
                    return self.send_json({"ok": False, "error": f"Bot {bot_id} not found"}, 404)

                if sub == "status":
                    return self.send_json({"ok": True, "status": bot.get_status_data()})
                elif sub == "cookies":
                    return self.send_json({"ok": True, "cookies": bot.get_cookies_data()})
                elif sub == "creds":
                    return self.send_json({"ok": True, "creds": bot.get_creds_data()})
                elif sub == "users":
                    return self.send_json({
                        "ok": True,
                        "users": bot.get_all_users_list(),
                        "admin_id": bot.admin_id
                    })
                elif sub == "env":
                    return self.send_json({
                        "ok": True,
                        "parsed": instance_manager.get_env_parsed(bot_id),
                        "raw": instance_manager.get_env_raw(bot_id)
                    })

        # ── STATIC FILE SERVING ───────────────────────────────────────────────
        if path == "/" or path == "":
            file_path = os.path.join(WEB_DIR, "index.html")
        else:
            rel_path = path.lstrip("/")
            file_path = os.path.join(WEB_DIR, rel_path)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            ctype, _ = mimetypes.guess_type(file_path)
            if not ctype:
                ctype = "application/octet-stream"
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)

        # 404 Fallback
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Read JSON body
        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                raw_body = self.rfile.read(content_length).decode("utf-8")
                body = json.loads(raw_body)
            except Exception:
                body = {}

        # ── TEMPLATES API ─────────────────────────────────────────────────────
        if path == "/api/templates":
            instance_manager.save_templates(body)
            return self.send_json({"ok": True, "message": "Templates saved successfully."})

        # ── BOT CONTROL APIS ──────────────────────────────────────────────────
        if path.startswith("/api/bot/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 4:
                bot_id = parts[2]
                action = parts[3]
                bot = instance_manager.get_bot(bot_id)
                if not bot:
                    return self.send_json({"ok": False, "error": f"Bot {bot_id} not found"}, 404)

                if action == "connect":
                    profile = body.get("profile", "admin")
                    ok, msg = bot.connect_profile(profile)
                    return self.send_json({"ok": ok, "message": msg, "status": bot.get_status_data()})

                elif action == "stop":
                    bot.stop_session_timer()
                    bot.t_log("Engine stopped from Web App.")
                    return self.send_json({"ok": True, "message": "Engine stopped.", "status": bot.get_status_data()})

                elif action == "toggle_debug":
                    new_val = bot.toggle_debug(body.get("debug"))
                    return self.send_json({"ok": True, "debug_mode": new_val})

                elif action == "cookies":
                    slot = body.get("slot")
                    c_name = body.get("cookie_name")
                    c_val = body.get("cookie_value")
                    xsrf = body.get("xsrf_value", "")
                    valid_until = body.get("valid_until", "Unknown")
                    if not slot or not c_name or not c_val:
                        return self.send_json({"ok": False, "error": "Missing cookie slot/name/value"}, 400)
                    bot.save_cookie(slot, c_name, c_val, xsrf, valid_until)
                    return self.send_json({"ok": True, "message": f"Cookie for {slot} saved."})

                elif action == "reset_cookies":
                    bot.reset_cookies()
                    return self.send_json({"ok": True, "message": "All cookies reset."})

                elif action == "creds":
                    slot = body.get("slot")
                    email = body.get("email")
                    password = body.get("password")
                    if not slot or not email or not password:
                        return self.send_json({"ok": False, "error": "Missing creds slot/email/password"}, 400)
                    bot.save_cred(slot, email, password)
                    return self.send_json({"ok": True, "message": f"Credentials for {slot} saved."})

                elif action == "reset_creds":
                    bot.reset_creds()
                    return self.send_json({"ok": True, "message": "All credentials reset."})

                elif action == "users":
                    sub_act = parts[4] if len(parts) > 4 else ""
                    user_id = body.get("user_id")
                    if sub_act == "approve":
                        plan = body.get("plan", "2day")
                        u = bot.approve_user(user_id, plan)
                        return self.send_json({"ok": True, "message": f"User {user_id} approved ({plan}).", "user": u})
                    elif sub_act == "reject":
                        u = bot.reject_user(user_id)
                        return self.send_json({"ok": True, "message": f"User {user_id} rejected.", "user": u})
                    elif sub_act == "remove":
                        ok = bot.remove_user(user_id)
                        return self.send_json({"ok": ok, "message": f"User {user_id} removed."})
                    elif sub_act == "alerts":
                        count = body.get("free_alerts", 5)
                        u = bot.set_user_free_alerts(user_id, count)
                        return self.send_json({"ok": True, "message": f"Alerts set to {count}.", "user": u})

                elif action == "message":
                    user_id = body.get("user_id")
                    text = body.get("text", "")
                    if not user_id or not text:
                        return self.send_json({"ok": False, "error": "Missing user_id or text"}, 400)
                    ok = bot.send_telegram_direct_message(user_id, text)
                    return self.send_json({"ok": ok, "message": "Message dispatched via Telegram."})

                elif action == "broadcast":
                    text = body.get("text", "")
                    if not text:
                        return self.send_json({"ok": False, "error": "Missing broadcast text"}, 400)
                    sent = bot.broadcast_message(text)
                    return self.send_json({"ok": True, "sent_count": sent, "message": f"Broadcast sent to {sent} users."})

                elif action == "env":
                    raw = body.get("raw")
                    kv = body.get("kv")
                    if raw is not None:
                        instance_manager.save_env_raw(bot_id, raw)
                        return self.send_json({"ok": True, "message": "Raw .env saved and applied."})
                    elif kv is not None:
                        instance_manager.save_env_key_values(bot_id, kv)
                        return self.send_json({"ok": True, "message": "Variables updated and applied."})

        self.send_json({"ok": False, "error": "Unknown POST route"}, 404)

def main():
    global bot_loop
    print("=" * 60)
    print(" 🚀 DUAL-BOT CONTROLLER & DASHBOARD STARTING")
    print(f" 🌐 Dashboard Web URL: http://localhost:{PORT}")
    print("=" * 60)

    # Launch background asyncio thread for the bots
    bot_loop = asyncio.new_event_loop()
    t = threading.Thread(target=run_async_loop, args=(bot_loop,), daemon=True)
    t.start()

    # Launch HTTP Server
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AppHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Dual-Bot Controller...")
        server.server_close()
        if bot_loop:
            asyncio.run_coroutine_threadsafe(instance_manager.stop_all(), bot_loop)

if __name__ == "__main__":
    main()
