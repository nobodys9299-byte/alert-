# ═══════════════════════════════════════════════════════════════════════════════
# DUAL-BOT APP — REFACTORED CORE ENGINE (MULTI-INSTANCE & FULL CONTROL SYNC)
# ═══════════════════════════════════════════════════════════════════════════════

import os, sys, re, random, asyncio, logging, warnings, time, json, socket, html
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

try:
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat
    )
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
        ContextTypes, filters
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

PAGE_NAMES = {
    "userDashboard": "Dashboard",
    "my-work": "My Work",
    "userattendance": "Attendance",
    "find-proofreading": "Proofread",
    "all-level-work": "Find Work"
}

def clean_url(u):
    u = (u or "").strip().strip("'\"").strip()
    u = re.sub(r"\s+", "", u)
    if not u: return ""
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    pu = urlparse(u)
    if not pu.netloc or "." not in pu.netloc:
        return ""
    return quote(u, safe=":/?#[]@!$&'()*+,;=%-._~")

def format_uptime(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}h {m:02d}m {s:02d}s"

class BotCore:
    def __init__(self, bot_id, name, config_file, data_dir, templates_file, port=48291):
        self.bot_id = bot_id
        self.name = name
        self.config_file = config_file
        self.data_dir = data_dir
        self.templates_file = templates_file
        self.port = port
        
        os.makedirs(self.data_dir, exist_ok=True)
        self.cookies_file = os.path.join(self.data_dir, "saved_cookies.json")
        self.creds_file   = os.path.join(self.data_dir, "saved_creds.json")
        self.users_file   = os.path.join(self.data_dir, "users.json")
        self.passcode_file = os.path.join(self.data_dir, "saved_passcode.json")
        self.debug_file   = os.path.join(self.data_dir, "debug_mode.json")
        self.state_file   = os.path.join(self.data_dir, "last_state.json")

        # Socket lock
        self.instance_locker = None
        self._acquire_socket_lock()

        # Logs Ring Buffer
        self.logs = []
        self.max_logs = 600

        # Engine state
        self.is_running = False
        self.is_logged_in = False
        self.is_monitoring = False
        self.active_profile_name = ""
        self.session_start_str = "None"
        self.fetch_count = 0
        self.alert_count = 0
        self.reminders_sent = 0
        self.session_errors = set()
        self.total_accumulated_time = 0.0
        self.last_connection_start = None
        self.is_engine_fresh_start = True
        self.last_disconnect_str = "None"
        self.last_disconnect_time = 0.0
        self.next_check_at = None
        self.locked_levels = set()
        self.failed_session_urls = set()
        self.last_state = self._load_json(self.state_file, {})

        # Isolated memory vaults for timers
        self.profile_accumulated = {}
        self.profile_last_disconnect = {}

        # Session & Network
        self.session = requests.Session()

        # Load environment config
        self.env = {}
        self.reload_config()

        # Debug mode
        self.debug_mode = self._load_json(self.debug_file, {}).get("debug", False)

        # Telegram Application & Async loop handle
        self.tg_app = None
        self.loop = None
        self.bg_task = None
        self.check_loop_task = None
        self.user_delay = 60

        self.t_log(f"Initialized {self.name} (Port: {self.port})")

    def _acquire_socket_lock(self):
        try:
            self.instance_locker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.instance_locker.bind(('127.0.0.1', self.port))
        except socket.error:
            self.instance_locker = None

    def _load_json(self, path, default=None):
        if default is None: default = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.t_log(f"Error saving {path}: {e}")

    def reload_config(self):
        self.env = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        self.env[k.strip()] = v.strip().strip("'\"")

        self.bot_token        = self.env.get("BOT_TOKEN", "")
        self.admin_id         = int(self.env.get("ADMIN_ID", "0") or 0)
        self.login_url        = self.env.get("LOGIN_URL", "https://transcribersnet.com/login")
        self.login_submit_url = self.env.get("LOGIN_SUBMIT_URL", "https://transcribersnet.com/admin/login-details-submit")
        self.work_url         = self.env.get("WORK_URL", "https://transcribersnet.com/admin/all-level-work")
        self.quick_login_url  = clean_url(self.env.get("QUICK_LOGIN_URL", "")) or clean_url(self.login_url) or "https://transcribersnet.com/admin/login"
        self.env_email        = self.env.get("WEBSITE_EMAIL", "")
        self.env_password     = self.env.get("WEBSITE_PASSWORD", "")
        self.recovery_key     = self.env.get("RECOVERY_KEY", "250116")
        self.upi_id           = self.env.get("UPI_ID", "your_upi_id@bank")
        self.check_min        = int(self.env.get("CHECK_INTERVAL_MIN", "3"))
        self.check_max        = int(self.env.get("CHECK_INTERVAL_MAX", "10"))
        self.surf_urls        = self.env.get("SURF_URLS", "https://transcribersnet.com/admin/userDashboard,https://transcribersnet.com/admin/my-work,https://transcribersnet.com/admin/userattendance,https://transcribersnet.com/admin/find-proofreading,https://transcribersnet.com/admin/all-level-work")
        self.surf_pages_min   = int(self.env.get("SURF_PAGES_MIN", "0"))
        self.surf_pages_max   = int(self.env.get("SURF_PAGES_MAX", "2"))
        self.surf_delay_min   = float(self.env.get("SURF_DELAY_MIN", "3.0"))
        self.surf_delay_max   = float(self.env.get("SURF_DELAY_MAX", "9.59"))
        self.reminder_freq_sec = int(float(self.env.get("REMINDER_FREQ_MINS", "20")) * 60)

    def get_template(self, key, default=""):
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get(key, {}).get("template", default)
            except Exception:
                pass
        return default

    # ── LOGGING ───────────────────────────────────
    def _ts(self):
        return datetime.now().strftime('%I:%M:%S %p')

    def t_log(self, msg, is_debug=False):
        if is_debug and not self.debug_mode: return
        ts = self._ts()
        entry = {"timestamp": ts, "message": msg, "is_debug": is_debug}
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        try:
            print(f"[{self.bot_id.upper()}] [{ts}] {msg}")
            sys.stdout.flush()
        except Exception:
            pass

    def t_sub(self, msg, is_debug=False):
        self.t_log(f"    {msg}", is_debug)

    def t_head(self, title, is_debug=False):
        self.t_log(f"━━━ {title} ━━━", is_debug)

    def t_step(self, label, msg, is_debug=False):
        self.t_log(f"  {label:<10} {msg}", is_debug)

    def t_item(self, msg, is_debug=False):
        self.t_log(f"      {msg}", is_debug)

    def t_job(self, msg, is_debug=False):
        self.t_log(f"        {msg}", is_debug)

    # ── UPTIME & SESSION TIMERS ──────────────────
    def get_profile_limits(self, profile_name):
        limits = {
            "🔴🍪 Admin": (
                int(float(self.env.get("ADMIN_SHUTDOWN_HOURS", "3")) * 3600),
                int(float(self.env.get("ADMIN_REMINDER_HOURS", "2")) * 3600)
            ),
            "🔵🍪 User 1": (
                int(float(self.env.get("USER1_SHUTDOWN_HOURS", "3")) * 3600),
                int(float(self.env.get("USER1_REMINDER_HOURS", "2")) * 3600)
            ),
            "🟢🍪 User 2": (
                int(float(self.env.get("USER2_SHUTDOWN_HOURS", "4")) * 3600),
                int(float(self.env.get("USER2_REMINDER_HOURS", "3")) * 3600)
            ),
            "🔑 ENV": (
                int(float(self.env.get("ENV_SHUTDOWN_HOURS", "3")) * 3600),
                int(float(self.env.get("ENV_REMINDER_HOURS", "2")) * 3600)
            ),
            "🪪 Login 1": (
                int(float(self.env.get("LOGIN1_SHUTDOWN_HOURS", "3")) * 3600),
                int(float(self.env.get("LOGIN1_REMINDER_HOURS", "2")) * 3600)
            ),
            "🪪 Login 2": (
                int(float(self.env.get("LOGIN2_SHUTDOWN_HOURS", "4")) * 3600),
                int(float(self.env.get("LOGIN2_REMINDER_HOURS", "3")) * 3600)
            )
        }
        return limits.get(profile_name, (10800, 7200))

    def get_current_uptime_seconds(self):
        uptime = self.total_accumulated_time
        if self.is_monitoring and self.last_connection_start:
            uptime += (time.time() - self.last_connection_start)
        return uptime

    def get_uptime_str(self):
        return format_uptime(self.get_current_uptime_seconds())

    def start_session_timer(self):
        prof = self.active_profile_name
        last_disc = self.profile_last_disconnect.get(prof, 0.0)
        saved_acc = self.profile_accumulated.get(prof, 0.0)

        if last_disc > 0 and (time.time() - last_disc) <= 1800:
            self.total_accumulated_time = saved_acc
            self.t_log(f"🧠 Timer resumed: {format_uptime(saved_acc)}", is_debug=True)
        else:
            self.total_accumulated_time = 0.0
            self.t_log("🧠 Timer started fresh: 0h 00m", is_debug=True)

        self.last_connection_start = time.time()
        self.is_monitoring = True
        self.is_engine_fresh_start = True
        self.session_start_str = datetime.now().strftime("%I:%M:%S %p, %d %b %Y")
        self.reminders_sent = 0
        self.fetch_count = 0
        self.alert_count = 0
        self.session_errors.clear()
        self.locked_levels.clear()
        self.failed_session_urls.clear()
        self.t_log("🔧 Engine initialized.")

    def stop_session_timer(self):
        if self.last_connection_start:
            session_duration = time.time() - self.last_connection_start
            self.total_accumulated_time += session_duration
            prof = self.active_profile_name
            self.profile_accumulated[prof] = self.total_accumulated_time
            self.profile_last_disconnect[prof] = time.time()
            self.last_connection_start = None

        self.record_disconnect()
        self.is_monitoring = False
        self.is_logged_in = False
        self.next_check_at = None

    def record_disconnect(self):
        self.last_disconnect_time = time.time()
        self.last_disconnect_str  = datetime.now().strftime("%I:%M:%S %p on %d %b %Y")

    def generate_session_report(self):
        uptime_str = self.get_uptime_str()
        profile_str = self.active_profile_name or "None"
        disc_time = datetime.now().strftime("%I:%M:%S %p, %d %b %Y")
        return (
            f"📋 *Session Summary Report*\n"
            f"Profile: {profile_str}\n"
            f"Start Time: {self.session_start_str}\n"
            f"Stop Time: {disc_time}\n"
            f"Uptime: {uptime_str}\n"
            f"Checks: {self.fetch_count} times\n"
            f"Alerts Sent: {self.alert_count}\n"
        )

    # ── USER MANAGEMENT ───────────────────────────
    def get_users(self):
        return self._load_json(self.users_file, {})

    def save_users(self, data):
        self._save_json(self.users_file, data)

    def get_user(self, user_id):
        return self.get_users().get(str(user_id), {})

    def update_user(self, user_id, data):
        users = self.get_users()
        uid = str(user_id)
        if uid not in users:
            users[uid] = {
                "id": int(user_id),
                "name": "",
                "username": "",
                "status": "pending",
                "free_alerts": 5,
                "expiry": None,
                "created_at": datetime.now().isoformat(),
                "alerts_sent": 0
            }
        users[uid].update(data)
        self.save_users(users)
        return users[uid]

    def is_user_active(self, user_id):
        u = self.get_user(user_id)
        if not u or u.get("status") != "approved":
            return False
        expiry = u.get("expiry")
        if expiry:
            try:
                if datetime.now() <= datetime.fromisoformat(expiry):
                    return True
                else:
                    self.update_user(user_id, {"status": "expired"})
                    return False
            except Exception:
                return False
        return u.get("free_alerts", 0) > 0

    def get_active_users(self):
        return [u for u in self.get_users().values() if self.is_user_active(u.get("id"))]

    def get_all_users_list(self):
        return list(self.get_users().values())

    def approve_user(self, user_id, plan="2day"):
        days = 2 if plan == "2day" else (30 if plan == "30day" else int(plan))
        expiry = (datetime.now() + timedelta(days=days)).isoformat()
        u = self.update_user(user_id, {"status": "approved", "expiry": expiry, "plan": f"{days}day"})
        # Try sending telegram notification
        self.send_telegram_direct_message(user_id, f"✅ *Your subscription is approved for {days} days!*")
        return u

    def reject_user(self, user_id):
        u = self.update_user(user_id, {"status": "rejected"})
        self.send_telegram_direct_message(user_id, "❌ *Your subscription request was rejected.*")
        return u

    def remove_user(self, user_id):
        users = self.get_users()
        uid = str(user_id)
        if uid in users:
            del users[uid]
            self.save_users(users)
            return True
        return False

    def set_user_free_alerts(self, user_id, free_count):
        return self.update_user(user_id, {"free_alerts": int(free_count), "status": "approved"})

    # ── COOKIES & CREDENTIALS ────────────────────
    def get_cookies_data(self):
        return self._load_json(self.cookies_file, {})

    def save_cookie(self, slot, cookie_name, cookie_value, xsrf_value="", valid_until="Unknown"):
        data = self.get_cookies_data()
        data[slot] = {
            "cookie_name": cookie_name,
            "cookie_value": cookie_value,
            "xsrf_value": xsrf_value or "",
            "date": datetime.now().strftime("%d-%b-%Y %I:%M %p"),
            "valid_until": valid_until
        }
        self._save_json(self.cookies_file, data)
        self.t_log(f"Saved cookie for {slot.upper()}")

    def reset_cookies(self):
        if os.path.exists(self.cookies_file):
            try: os.remove(self.cookies_file)
            except: pass
        self.t_log("All cookies reset.")

    def get_creds_data(self):
        return self._load_json(self.creds_file, {})

    def save_cred(self, slot, email, password):
        data = self.get_creds_data()
        data[slot] = {"email": email, "password": password}
        self._save_json(self.creds_file, data)
        self.t_log(f"Saved credentials for {slot.upper()}")

    def reset_creds(self):
        if os.path.exists(self.creds_file):
            try: os.remove(self.creds_file)
            except: pass
        self.t_log("All credentials reset.")

    def toggle_debug(self, val=None):
        if val is None:
            self.debug_mode = not self.debug_mode
        else:
            self.debug_mode = bool(val)
        self._save_json(self.debug_file, {"debug": self.debug_mode})
        self.t_log(f"Debug mode set to: {'ON' if self.debug_mode else 'OFF'}")
        return self.debug_mode

    # ── HTTP & STEALTH ENGINE ────────────────────
    def human_delay(self, a=2, b=4):
        time.sleep(random.uniform(a, b))

    def get_timeout(self):
        return random.uniform(14.2, 16.8)

    def make_session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive"
        })
        return s

    def login_with_cookies(self, cookie_name, cookie_value, xsrf_value, slot_name):
        try:
            self.t_log(f"🔐 Cookie login → {slot_name.upper()}...")
            self.session = self.make_session()
            self.session.cookies.set(cookie_name, cookie_value, domain="transcribersnet.com")
            if xsrf_value and xsrf_value.lower() != "skip":
                self.session.cookies.set("XSRF-TOKEN", xsrf_value, domain="transcribersnet.com")
            self.session.headers.update({"Sec-Fetch-Site": "none"})
            r = self.session.get("https://transcribersnet.com/admin/userDashboard",
                                 timeout=self.get_timeout(), allow_redirects=True)
            self.human_delay(2, 4)
            if "login" not in r.url.lower():
                self.is_logged_in = True
                self.t_sub(f"Landed on: {r.url.replace('https://transcribersnet.com', '')} ({r.status_code})")
                self.t_sub("✔ Login successful")
                return True, "Success"
            else:
                self.is_logged_in = False
                self.t_sub("✖ Token rejected by server")
                return False, "Cookie Expired: Cookies rejected by server."
        except requests.exceptions.RequestException as e:
            self.is_logged_in = False
            self.t_sub(f"✖ Network drop during login: {str(e)[:60]}")
            return False, f"Network Error: {str(e)[:40]}"
        except Exception as e:
            self.is_logged_in = False
            self.t_sub(f"✖ System error during login: {str(e)[:60]}")
            return False, f"System Error: {str(e)[:40]}"

    def login_with_credentials(self, email, password, mapping_slot):
        try:
            self.t_log(f"🔐 Password login → {mapping_slot.upper()}...")
            self.session = self.make_session()
            self.session.headers.update({"Sec-Fetch-Site": "none"})
            page = self.session.get(self.login_url, timeout=self.get_timeout())
            soup = BeautifulSoup(page.text, "html.parser")
            token_input = soup.find("input", {"name": "_token"})
            csrf = token_input.get("value", "") if token_input else ""
            self.human_delay(2, 4)
            self.session.headers.update({
                "Origin": "https://transcribersnet.com",
                "Referer": self.login_url,
                "Sec-Fetch-Site": "same-origin",
                "Content-Type": "application/x-www-form-urlencoded"
            })
            payload = {"email": email, "password": password, "_token": csrf, "remember_me": "1"}
            r = self.session.post(self.login_submit_url, data=payload, timeout=self.get_timeout(), allow_redirects=True)

            if "login" not in r.url.lower():
                self.human_delay(2, 4)
                self.is_logged_in = True
                self.t_sub(f"Landed on: {r.url.replace('https://transcribersnet.com', '')} ({r.status_code})")
                self.t_sub("✔ Login successful")

                xsrf_val    = self.session.cookies.get("XSRF-TOKEN", domain="transcribersnet.com") or ""
                best_name   = None
                best_value  = None
                best_expiry = -1
                best_expiry_str = "Unknown"

                for cookie in self.session.cookies:
                    if cookie.name == "XSRF-TOKEN": continue
                    expiry = cookie.expires if cookie.expires else 0
                    if "remember_web_" in cookie.name:
                        best_name  = cookie.name
                        best_value = cookie.value
                        best_expiry = expiry
                        try: best_expiry_str = datetime.fromtimestamp(expiry).strftime("%d-%b-%Y") if expiry > 0 else "Session"
                        except: best_expiry_str = "Unknown"
                        break
                    if expiry > best_expiry:
                        best_name   = cookie.name
                        best_value  = cookie.value
                        best_expiry = expiry
                        try: best_expiry_str = datetime.fromtimestamp(expiry).strftime("%d-%b-%Y") if expiry > 0 else "Session"
                        except: best_expiry_str = "Unknown"

                if best_name:
                    self.save_cookie(mapping_slot, best_name, best_value, xsrf_val, valid_until=best_expiry_str)
                    self.t_sub(f"✔ remember_web cookie saved: {best_expiry_str}")
                return True, "Success"
            else:
                self.is_logged_in = False
                self.t_sub("✖ Creds dropped. Anti-bot active.")
                return False, "Anti-bot block. Use COOKIE method."
        except requests.exceptions.RequestException as e:
            self.is_logged_in = False
            return False, f"Network Error: {str(e)[:40]}"
        except Exception as e:
            self.is_logged_in = False
            return False, f"System Error: {str(e)[:40]}"

    def connect_profile(self, profile_key):
        """Unified connector for App and Telegram"""
        profile_map = {
            "admin": ("🔴🍪 Admin", "admin", "cookie"),
            "user1": ("🔵🍪 User 1", "user1", "cookie"),
            "user2": ("🟢🍪 User 2", "user2", "cookie"),
            "env":   ("🔑 ENV", "env", "env"),
            "login1": ("🪪 Login 1", "login1", "login"),
            "login2": ("🪪 Login 2", "login2", "login"),
        }
        
        target_info = profile_map.get(profile_key.lower())
        if not target_info:
            return False, f"Unknown profile: {profile_key}"

        target_name, slot, method = target_info

        if self.is_logged_in or self.is_monitoring:
            if self.active_profile_name == target_name:
                return True, f"Already connected via {target_name}."
            self.t_log(f"🔄 Switching {self.active_profile_name} → {target_name}")
            self.stop_session_timer()
            time.sleep(1)

        if method == "env":
            self.active_profile_name = "🔑 ENV"
            ok, reason = self.login_with_credentials(self.env_email, self.env_password, "admin")
        elif method == "login":
            cr = self.get_creds_data().get(slot, {})
            self.active_profile_name = target_name
            map_slot = "user1" if slot == "login1" else "user2"
            if not cr.get("email"):
                return False, f"No saved credentials for {target_name}."
            ok, reason = self.login_with_credentials(cr["email"], cr["password"], map_slot)
        else: # cookie
            self.active_profile_name = target_name
            ck = self.get_cookies_data().get(slot)
            if not ck:
                return False, f"No cookie saved for {target_name}."
            ok, reason = self.login_with_cookies(ck["cookie_name"], ck["cookie_value"], ck.get("xsrf_value", ""), slot)

        if ok:
            self.last_state = {}
            self.next_check_at = None
            self.start_session_timer()
            self.t_log(f"✅ Connected via {self.active_profile_name}!")
            return True, f"Connected via {self.active_profile_name}!"
        else:
            self.t_log(f"❌ Login failed via {self.active_profile_name}: {reason}")
            return False, reason

    # ── WORK SCRAPER & SURFING ────────────────────
    def fetch_work_levels(self, fast_mode=False):
        if not self.is_logged_in: return None
        try:
            urls_pool = [u.strip() for u in self.surf_urls.split(",") if u.strip()]
            landing_page = random.choice(urls_pool) if urls_pool else "https://transcribersnet.com/admin/userDashboard"
            landing_name = PAGE_NAMES.get(landing_page.split('/')[-1], landing_page.split('/')[-1])
            
            self.t_head(f"SCAN #{self.fetch_count + 1} · {self.active_profile_name}")
            self.session.headers.update({"Referer": "https://transcribersnet.com/", "Sec-Fetch-Site": "same-origin"})
            
            try:
                resp_landing = self.session.get(landing_page, timeout=self.get_timeout())
                if "login" in resp_landing.url.lower():
                    self.is_logged_in = False
                    return None
                self.t_step("1 Landing", f"🏠 {landing_name} ✔ OK", is_debug=True)
            except Exception:
                self.t_step("1 Landing", f"🏠 {landing_name} ⏩ skipped", is_debug=True)

            pause = 0.5 if fast_mode else random.uniform(self.surf_delay_min, self.surf_delay_max)
            self.t_item(f"⏳ read {pause:.1f}s", is_debug=True)
            time.sleep(pause)

            self.session.headers.update({"Referer": landing_page})
            resp = self.session.get(self.work_url, timeout=self.get_timeout())
            if "login" in resp.url.lower():
                self.is_logged_in = False
                return None
                
            kb = len(resp.content) // 1024 if resp.content else 0
            self.t_step("2 Work", f"📍 Find Work ✔ {resp.status_code} · {kb}KB", is_debug=True)
            
            soup   = BeautifulSoup(resp.text, "html.parser")
            levels = {}
            for card in soup.find_all("div", class_="level-card"):
                m = next((re.match(r"level-(\d+)$", c) for c in card.get("class", [])
                          if re.match(r"level-(\d+)$", c)), None)
                if not m: continue
                level_num = m.group(1)
                card_text = card.get_text(separator=" ", strip=True)
                av_match  = re.search(r'Available\s*:?\s*(\d+)', card_text, re.IGNORECASE)
                bk_match  = re.search(r'Booked\s*:?\s*(\d+)', card_text, re.IGNORECASE)
                levels[f"LEVEL {level_num}"] = {
                    "available": int(av_match.group(1)) if av_match else 0,
                    "booked":    int(bk_match.group(1)) if bk_match else 0
                }
            self.fetch_count += 1
            
            with_work = sum(1 for v in levels.values() if v["available"] > 0)
            total_av  = sum(v["available"] for v in levels.values())
            self.t_item(f"🟢 {total_av} available · {with_work}/{len(levels)} levels", is_debug=True)
            for k, v in levels.items():
                if v["available"] > 0:
                    self.t_job(f"🎧 L{k.split()[-1]} Avail {v['available']} | Booked {v['booked']}", is_debug=True)
            
            pause2 = 0.5 if fast_mode else random.uniform(self.surf_delay_min, self.surf_delay_max)
            self.t_item(f"⏳ read {pause2:.1f}s", is_debug=True)
            time.sleep(pause2)
            
            return levels
        except requests.exceptions.RequestException:
            return "NETWORK_ERROR"
        except Exception as e:
            self.t_log(f"🛠️ Auto-Fix: parser corrected: {str(e)[:40]}")
            return None

    def fetch_level_languages(self, level_num, fast_mode=False):
        if level_num in self.locked_levels:
            return ["🔒 Locked"]
        level_url = f"https://transcribersnet.com/admin/work/level_work/{level_num}"
        if level_url in self.failed_session_urls:
            return ["🔒 Locked"]

        try:
            self.session.headers.update({"Referer": self.work_url})
            resp = self.session.get(level_url, timeout=self.get_timeout())
            if "login" in resp.url.lower(): return ["Session Lost"]
            
            pause = 0.5 if fast_mode else random.uniform(self.surf_delay_min, self.surf_delay_max)
            time.sleep(pause)
            
            if resp.status_code == 403:
                self.locked_levels.add(level_num)
                self.failed_session_urls.add(level_url)
                return ["🔒 Locked"]
                
            soup = BeautifulSoup(resp.text, "html.parser")
            valid_langs = {"Hindi","English","Tamil","Telugu","Kannada","Malayalam","Bengali",
                           "Marathi","Gujarati","Punjabi","Urdu","Odia","Assamese"}
            lang_abbrev = {
                "Hindi": "Hin", "English": "Eng", "Tamil": "Tam", "Telugu": "Tel",
                "Kannada": "Kan", "Malayalam": "Mal", "Bengali": "Ben", "Marathi": "Mar",
                "Gujarati": "Guj", "Punjabi": "Pun", "Urdu": "Urd", "Odia": "Odi", "Assamese": "Ass"
            }
                     
            job_details = []
            for row in soup.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 7:
                    pay_tot_raw_old = cols[3].get_text(strip=True)
                    job_format_old = " ".join(cols[4].get_text(separator=" ", strip=True).split())
                    due_time_old = " ".join(cols[5].get_text(separator=" ", strip=True).split())
                    language_old = " ".join(cols[6].get_text(separator=" ", strip=True).split())
                    
                    pay_tot_old = re.sub(r'\s+', '', pay_tot_raw_old)
                    lang_emoji_old = f"{language_old} 🐸" if language_old in ["Hindi", "English", "Bengali"] else language_old
                    old_str = f"🗣️ {lang_emoji_old} | 📄 {job_format_old} | ⏳ {due_time_old} | 💰 {pay_tot_old}"
                    
                    pay_min_raw = cols[2].get_text(strip=True)
                    m_min = re.search(r'[\d\.]+', pay_min_raw)
                    pay_min = f"₹{round(float(m_min.group()))}/m" if m_min else re.sub(r'\s+', '', pay_min_raw)
                    m_tot = re.search(r'[\d\.]+', pay_tot_raw_old)
                    pay_tot_new = f"₹{round(float(m_tot.group()))}" if m_tot else pay_tot_old
                    job_format_new = job_format_old.upper().replace("ANALYSIS", "Anlys").replace("TRANSCRIPTION", "Trans")
                    due_time_new = re.sub(r'\bHours?\b', 'H', due_time_old, flags=re.I)
                    due_time_new = re.sub(r'\bMinutes?\b', 'M', due_time_new, flags=re.I)
                    due_time_new = re.sub(r'\s+', '', due_time_new)
                    
                    if language_old in valid_langs:
                        short_lang = lang_abbrev.get(language_old, language_old[:3])
                        lang_emoji_new = f"{short_lang} 🐸" if language_old in ["Hindi", "English", "Bengali"] else short_lang
                        new_str = f"{lang_emoji_new} | 📄 {job_format_new} | ⏳ {due_time_new} | ⚡ {pay_min} | {pay_tot_new}"
                        job_details.append({"old": old_str, "new": new_str})
                            
            return job_details if job_details else ["No Valid Data Found"]
        except Exception:
            return ["Error"]

    def get_lang_map(self, changed, fast_mode=False):
        if not changed: return {}
        result = {}
        for k in changed:
            result[k] = self.fetch_level_languages(k.split()[-1], fast_mode)
        return result

    def human_surf(self):
        urls = [u.strip() for u in self.surf_urls.split(",") if u.strip()]
        if not urls: return
        count = random.randint(self.surf_pages_min, self.surf_pages_max)
        for _ in range(count):
            target = random.choice(urls)
            try:
                self.session.get(target, timeout=self.get_timeout())
                pause = random.uniform(self.surf_delay_min, self.surf_delay_max)
                time.sleep(pause)
            except:
                pass

    # ── CUSTOM TEMPLATES & ALERT BUILDER ─────────
    def build_custom_alert(self, changed, current_levels, lang_map, is_admin=True):
        template_key = "admin_job_alert" if is_admin else "user_job_alert"
        default_tpl = (
            "🎧 <b>{level_name}</b> | <b>Avail: {available}</b> 🍏 | Booked: {booked}\n{languages}\n\n━━━━━━━━━━━━━━━━━━━\n💻 <a href=\"{quick_link}\">Log in quickly!</a>"
            if is_admin else
            "🎧 <b>{level_name}</b> | <b>Avail: {available}</b> 🍏 | Booked: {booked}\n\n━━━━━━━━━━━━━━━━━━━\n💻 <a href=\"{quick_link}\">Log in quickly!</a>"
        )
        template = self.get_template(template_key, default_tpl)

        blocks = []
        for key, data in sorted(changed.items()):
            langs_str = ""
            if is_admin:
                details = lang_map.get(key, [])
                detail_lines = []
                for detail in details:
                    if isinstance(detail, dict):
                        detail_lines.append(html.escape(detail["new"]))
                    else:
                        detail_lines.append(html.escape(str(detail)))
                langs_str = "\n".join(detail_lines)

            block = template.replace("{level_name}", html.escape(key)) \
                            .replace("{available}", str(data["available"])) \
                            .replace("{booked}", str(data["booked"])) \
                            .replace("{languages}", langs_str) \
                            .replace("{quick_link}", html.escape(self.quick_login_url, quote=True))
            blocks.append(block)

        return "\n\n".join(blocks)

    # ── TELEGRAM BOT INTEGRATION ─────────────────
    async def async_send_telegram(self, chat_id, text, parse_mode="HTML", reply_markup=None):
        if not self.tg_app or not self.bot_token: return False
        try:
            await self.tg_app.bot.send_message(
                chat_id=chat_id, text=text, parse_mode=parse_mode,
                reply_markup=reply_markup, disable_web_page_preview=True
            )
            return True
        except Exception as e:
            self.t_log(f"Telegram send error to {chat_id}: {e}", is_debug=True)
            return False

    def send_telegram_direct_message(self, chat_id, text, parse_mode="Markdown"):
        if not self.loop or not self.tg_app: return False
        asyncio.run_coroutine_threadsafe(
            self.async_send_telegram(chat_id, text, parse_mode=parse_mode), self.loop
        )
        return True

    def broadcast_message(self, text):
        users = [u for u in self.get_all_users_list() if u.get("id") != self.admin_id]
        sent = 0
        for u in users:
            if self.is_user_active(u["id"]):
                self.send_telegram_direct_message(u["id"], f"📢 *Broadcast Announcement*\n\n{text}")
                sent += 1
        self.t_log(f"Broadcast sent to {sent} active users.")
        return sent

    # ── BACKGROUND MONITORING CYCLE ──────────────
    async def check_cycle(self):
        while self.is_running:
            if not self.is_monitoring or not self.is_logged_in:
                await asyncio.sleep(2)
                continue

            uptime = self.get_current_uptime_seconds()
            limit_shutdown, limit_reminder = self.get_profile_limits(self.active_profile_name)

            # Auto-reminder check
            if uptime >= limit_reminder:
                expected = int(uptime // self.reminder_freq_sec)
                if expected > self.reminders_sent:
                    self.reminders_sent = expected
                    rem_tpl = self.get_template("session_reminder", "⏳ *Reminder*\nProfile: {profile}\nUptime: {uptime}")
                    msg = rem_tpl.replace("{profile}", self.active_profile_name).replace("{uptime}", format_uptime(uptime))
                    await self.async_send_telegram(self.admin_id, msg, parse_mode="Markdown")

            # Auto-shutdown limit check
            if uptime >= limit_shutdown:
                self.t_log(f"🛑 Time limit reached for {self.active_profile_name}. Disconnecting...")
                report = self.generate_session_report()
                self.stop_session_timer()
                disc_tpl = self.get_template("auto_disconnect", "🛑 *AUTO-DISCONNECT*\nTime limit for {profile}.\n\n{report}")
                msg = disc_tpl.replace("{profile}", self.active_profile_name).replace("{report}", report)
                await self.async_send_telegram(self.admin_id, msg, parse_mode="Markdown")
                await asyncio.sleep(2)
                continue

            # Check next schedule
            if self.next_check_at and datetime.now() < self.next_check_at:
                await asyncio.sleep(2)
                continue

            # Run Scan
            try:
                current = await asyncio.to_thread(self.fetch_work_levels)
                if current is None:
                    self.stop_session_timer()
                    lost_tpl = self.get_template("session_lost", "⚠️ *Session Lost*\n🔴 Engine stopped.\n\n{report}")
                    msg = lost_tpl.replace("{report}", self.generate_session_report())
                    await self.async_send_telegram(self.admin_id, msg, parse_mode="Markdown")
                    continue

                if current == "NETWORK_ERROR":
                    await asyncio.sleep(10)
                    continue

                is_first_scan = self.is_engine_fresh_start and (not bool(self.last_state))
                total_av = sum(v["available"] for v in current.values())

                if not self.is_engine_fresh_start:
                    changed = {k: v for k, v in current.items() if v["available"] > self.last_state.get(k, {}).get("available", 0)}
                else:
                    changed = {k: v for k, v in current.items() if v["available"] > 0}

                if changed:
                    lang_map = await asyncio.to_thread(self.get_lang_map, changed)
                    admin_alert = self.build_custom_alert(changed, current, lang_map, is_admin=True)
                    await self.async_send_telegram(self.admin_id, admin_alert, parse_mode="HTML")

                    # Dispatch to subscribed users
                    if not is_first_scan:
                        user_alert = self.build_custom_alert(changed, current, lang_map, is_admin=False)
                        await asyncio.to_thread(self.human_surf)
                        await asyncio.sleep(self.user_delay)

                        for u in self.get_active_users():
                            uid = u.get("id")
                            if not uid or uid == self.admin_id: continue
                            if not u.get("expiry"):
                                free = u.get("free_alerts", 0)
                                if free <= 0: continue
                                self.update_user(uid, {"free_alerts": free - 1, "alerts_sent": u.get("alerts_sent", 0) + 1})
                                if free - 1 == 1:
                                    last_free_tpl = self.get_template("last_free_alert", "⚠️ *Last Free Alert!*\n\n₹6 — 2 Days\n₹100 — 30 Days\n\n/start")
                                    await self.async_send_telegram(uid, last_free_tpl, parse_mode="Markdown")
                            else:
                                self.update_user(uid, {"alerts_sent": u.get("alerts_sent", 0) + 1})

                            await self.async_send_telegram(uid, user_alert, parse_mode="HTML")
                            self.alert_count += 1
                            await asyncio.sleep(0.1)
                    else:
                        await asyncio.to_thread(self.human_surf)
                else:
                    await asyncio.to_thread(self.human_surf)

                self.is_engine_fresh_start = False
                self.last_state = current
                self._save_json(self.state_file, current)

                delay = random.randint(self.check_min * 60, self.check_max * 60)
                self.next_check_at = datetime.now() + timedelta(seconds=delay)
                rem_m = int((self.next_check_at - datetime.now()).total_seconds() // 60)
                rem_s = int((self.next_check_at - datetime.now()).total_seconds() % 60)
                self.t_step("NEXT", f"💤 {self.next_check_at.strftime('%I:%M:%S %p')} (in {rem_m}m {rem_s}s)")

            except Exception as e:
                self.t_log(f"🛠️ Cycle Recovery: {str(e)[:50]}")
                await asyncio.sleep(10)

    # ── STATUS DATA EXPORTER FOR APP ──────────────
    def get_status_data(self):
        engine_status = "ONLINE" if (self.is_logged_in and self.is_monitoring) else ("OFFLINE" if not self.is_logged_in else "STANDBY")
        limit_shutdown, limit_reminder = self.get_profile_limits(self.active_profile_name)

        rem_seconds = int((self.next_check_at - datetime.now()).total_seconds()) if (self.next_check_at and self.is_monitoring) else 0
        next_check_str = f"{self.next_check_at.strftime('%I:%M:%S %p')} (in {rem_seconds // 60}m {rem_seconds % 60}s)" if rem_seconds > 0 else ("Running..." if self.is_monitoring else "Not scheduled")

        ck_data = self.get_cookies_data()
        cookie_statuses = {}
        for slot in ["admin", "user1", "user2"]:
            ck = ck_data.get(slot)
            cookie_statuses[slot] = {
                "saved": bool(ck),
                "date": ck.get("date", "Unknown") if ck else None,
                "valid_until": ck.get("valid_until", "Unknown") if ck else "Not set"
            }

        cr_data = self.get_creds_data()
        cred_statuses = {
            "login1": bool(cr_data.get("login1", {}).get("email")),
            "login2": bool(cr_data.get("login2", {}).get("email")),
            "env": bool(self.env_email)
        }

        users = self.get_all_users_list()
        non_admin = [u for u in users if u.get("id") != self.admin_id]

        return {
            "bot_id": self.bot_id,
            "name": self.name,
            "engine_status": engine_status,
            "active_profile": self.active_profile_name or "None",
            "session_start": self.session_start_str,
            "uptime": self.get_uptime_str(),
            "auto_shutdown": format_uptime(limit_shutdown),
            "reminder_at": format_uptime(limit_reminder),
            "scan_interval": f"{self.check_min}–{self.check_max} min",
            "page_time": f"{self.surf_delay_min}–{self.surf_delay_max} s",
            "next_check": next_check_str,
            "fetch_count": self.fetch_count,
            "alert_count": self.alert_count,
            "debug_mode": self.debug_mode,
            "last_disconnect": self.last_disconnect_str,
            "cookies": cookie_statuses,
            "credentials": cred_statuses,
            "users_stats": {
                "total": len(non_admin),
                "approved": sum(1 for u in non_admin if u.get('status') == 'approved'),
                "pending": sum(1 for u in non_admin if u.get('status') == 'pending'),
                "rejected": sum(1 for u in non_admin if u.get('status') == 'rejected'),
                "receiving_alerts": len(self.get_active_users())
            }
        }

    # ── LIFECYCLE ────────────────────────────────
    async def start(self):
        self.is_running = True
        self.loop = asyncio.get_running_loop()

        if TELEGRAM_AVAILABLE and self.bot_token:
            try:
                self.tg_app = ApplicationBuilder().token(self.bot_token).build()
                self._setup_telegram_handlers()
                await self.tg_app.initialize()
                await self.tg_app.start()
                await self.tg_app.updater.start_polling(drop_pending_updates=True)
                self.t_log(f"🤖 Telegram Bot polling started.")
            except Exception as e:
                self.t_log(f"⚠️ Telegram init skipped/failed: {e}")

        self.check_loop_task = asyncio.create_task(self.check_cycle())

    async def stop(self):
        self.is_running = False
        self.stop_session_timer()
        if self.check_loop_task:
            self.check_loop_task.cancel()
        if self.tg_app:
            try:
                await self.tg_app.updater.stop()
                await self.tg_app.stop()
                await self.tg_app.shutdown()
            except: pass
        if self.instance_locker:
            try: self.instance_locker.close()
            except: pass
        self.t_log(f"🛑 {self.name} stopped.")

    def _setup_telegram_handlers(self):
        # Admin Keyboard builder
        def admin_kb():
            stop_emoji = "🟢" if (self.is_logged_in and self.is_monitoring) else "🛑"
            return InlineKeyboardMarkup([
                [InlineKeyboardButton("🚂 START BOT ENGINE", callback_data="start_connect"),
                 InlineKeyboardButton(f"{stop_emoji} STOP BOT ENGINE", callback_data="stop_engine")],
                [InlineKeyboardButton("📊 CURRENT BOT STATUS", callback_data="admin_status")],
                [InlineKeyboardButton("🍪 MANAGE SAVED DATA", callback_data="save_details"),
                 InlineKeyboardButton("👥 VIEW ALL REG USERS", callback_data="admin_users")],
                [InlineKeyboardButton("💬 MESSAGE A USER", callback_data="admin_message"),
                 InlineKeyboardButton("📢 BROADCAST MESSAGE", callback_data="admin_broadcast")],
                [InlineKeyboardButton("🗑️ RESET LOGIN IDs", callback_data="confirm_reset_creds"),
                 InlineKeyboardButton("🗑️ RESET ALL COOKIES", callback_data="confirm_reset_cookies")],
            ])

        def connect_kb():
            return InlineKeyboardMarkup([
                [InlineKeyboardButton("🔴🍪 ADMIN", callback_data="auto_connect_admin"),
                 InlineKeyboardButton("🔵🍪 USER 1", callback_data="auto_connect_user1"),
                 InlineKeyboardButton("🟢🍪 USER 2", callback_data="auto_connect_user2")],
                [InlineKeyboardButton("🖥️ LOGIN VIA SYSTEM ENV", callback_data="connect_env")],
                [InlineKeyboardButton("🪪 LOGIN 1", callback_data="auto_connect_login1"),
                 InlineKeyboardButton("🪪 LOGIN 2", callback_data="auto_connect_login2")],
                [InlineKeyboardButton("❌ CANCEL THIS ACTION", callback_data="cancel_action")],
            ])

        async def cmd_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            self.update_user(user.id, {"name": user.full_name, "username": user.username or ""})
            if user.id == self.admin_id:
                await update.message.reply_text(self._format_admin_status_text(), parse_mode="Markdown", reply_markup=admin_kb())
            else:
                u = self.get_user(user.id)
                status_str = "✅ Active" if self.is_user_active(user.id) else "⏳ Pending/Free"
                welcome_tpl = self.get_template("welcome_message", "🎉 *Welcome, {first_name}!* 🎉\n\n🤖 I am your personal Job Alert Bot.\n📡 *Your Status:* {status}\n\n✨ You will automatically receive notifications when new work is available!")
                txt = welcome_tpl.replace("{first_name}", user.first_name).replace("{status}", status_str)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 CHECK MY SUB STATUS", callback_data="user_status"),
                     InlineKeyboardButton("💳 BUY A SUBSCRIPTION", callback_data="user_subscribe")],
                    [InlineKeyboardButton("❓ HELP AND INFORMATION", callback_data="user_help")],
                ])
                await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)

        async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            user_id = query.from_user.id
            try: await query.answer()
            except: pass
            data = query.data

            if user_id == self.admin_id:
                if data == "start_connect":
                    await query.edit_message_text("🔑 *Login Method:*", parse_mode="Markdown", reply_markup=connect_kb())
                elif data.startswith("auto_connect_") or data == "connect_env":
                    raw = "env" if data == "connect_env" else data.split("_")[2]
                    await query.edit_message_text(f"🔄 Connecting via `{raw}`...", parse_mode="Markdown")
                    ok, msg = await asyncio.to_thread(self.connect_profile, raw)
                    await context.bot.send_message(chat_id=user_id, text=f"{'✅' if ok else '❌'} {msg}", reply_markup=admin_kb())
                elif data == "stop_engine":
                    self.stop_session_timer()
                    await query.edit_message_text("🛑 *Engine stopped manually.*", parse_mode="Markdown", reply_markup=admin_kb())
                elif data == "admin_status":
                    await query.edit_message_text(self._format_admin_status_text(), parse_mode="Markdown", reply_markup=admin_kb())
                elif data == "admin_users":
                    users = [u for u in self.get_all_users_list() if u.get("id") != self.admin_id]
                    lines = [f"👥 *USERS ({len(users)})*\n"]
                    btns = []
                    for u in users:
                        uid, name, status = u.get("id"), u.get("name", "?"), u.get("status")
                        lines.append(f"• *{name}* — {status}")
                        if status == "pending":
                            btns.append([InlineKeyboardButton(f"✅ {name[:6]} 2D", callback_data=f"approve_{uid}_2day"),
                                         InlineKeyboardButton(f"✅ {name[:6]} 30D", callback_data=f"approve_{uid}_30day")])
                        else:
                            btns.append([InlineKeyboardButton(f"🗑 REMOVE {name[:6]}", callback_data=f"remove_{uid}")])
                    btns.append([InlineKeyboardButton("🔙 BACK", callback_data="admin_status")])
                    await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))
                elif data.startswith("approve_"):
                    parts = data.split("_")
                    self.approve_user(int(parts[1]), parts[2])
                    await query.edit_message_text("✅ Approved.", reply_markup=admin_kb())
                elif data.startswith("remove_"):
                    self.remove_user(int(data.split("_")[1]))
                    await query.edit_message_text("🗑 Removed.", reply_markup=admin_kb())
                elif data == "confirm_reset_cookies":
                    self.reset_cookies()
                    await query.edit_message_text("🗑️ *All cookies reset.*", parse_mode="Markdown", reply_markup=admin_kb())
                elif data == "confirm_reset_creds":
                    self.reset_creds()
                    await query.edit_message_text("🗑️ *All credentials reset.*", parse_mode="Markdown", reply_markup=admin_kb())
            else: # Regular user callbacks
                if data == "user_status":
                    u = self.get_user(user_id)
                    s = "Active" if self.is_user_active(user_id) else "Inactive/Pending"
                    await query.edit_message_text(f"📋 *Your Status:* {s}\nFree alerts left: {u.get('free_alerts', 0)}", parse_mode="Markdown")
                elif data == "user_subscribe":
                    await query.edit_message_text(f"💳 *Subscription Plans:*\n\n2 Days: ₹6\n30 Days: ₹100\n\nPay via UPI: `{self.upi_id}`\nSend payment screenshot here to activate!", parse_mode="Markdown")

        self.tg_app.add_handler(CommandHandler("start", cmd_start_handler))
        self.tg_app.add_handler(CallbackQueryHandler(callback_handler))

    def _format_admin_status_text(self):
        s = self.get_status_data()
        return (
            "📊 *SYSTEM STATUS*\n"
            "─────────────────────\n"
            f"Engine        : {s['engine_status']}\n"
            f"Profile       : 🪪 {s['active_profile']}\n"
            f"Session Start : {s['session_start']}\n"
            f"Uptime        : {s['uptime']}\n"
            f"Scan Interval : {s['scan_interval']}\n"
            f"Next Check    : {s['next_check']}\n"
            f"Fetch Count   : {s['fetch_count']} times\n"
            f"Debug Mode    : {'🟢 ON' if s['debug_mode'] else '🔴 OFF'}\n"
            "─────────────────────\n"
            f"👥 Users: Total {s['users_stats']['total']} | Receiving Alerts: {s['users_stats']['receiving_alerts']}\n"
        )
