# ═══════════════════════════════════════
# ALERT BOT — STEALTH, COOKIES & SWITCHER
# ═══════════════════════════════════════

import os, sys, re, random, asyncio, logging, warnings, time, json, socket, html
from urllib.parse import urlparse, quote
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

try:
    instance_locker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    instance_locker.bind(('127.0.0.1', 48291))
except socket.error:
    print("\n❌ [CRITICAL CONFLICT]: Another copy of this bot is ALREADY running in the background/another tab!")
    print("Forcefully close the other tab or type 'pkill -f python' to flush the RAM.\n")
    sys.exit(1)

warnings.filterwarnings("ignore")
logging.getLogger("httpx").setLevel(logging.FATAL)
logging.getLogger("httpcore").setLevel(logging.FATAL)
logging.getLogger("telegram").setLevel(logging.FATAL)
logging.getLogger("apscheduler").setLevel(logging.CRITICAL)

load_dotenv()
BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_ID         = int(os.getenv("ADMIN_ID") or 0)
WORK_URL         = os.getenv("WORK_URL")
LOGIN_URL        = os.getenv("LOGIN_URL")
LOGIN_SUBMIT_URL = os.getenv("LOGIN_SUBMIT_URL")
# Clickable "Log in quickly!" link shown at the bottom of every alert.
# Add this line to your .env :  QUICK_LOGIN_URL=https://transcribersnet.com/admin/login
def _clean_url(u):
    """Telegram silently drops <a> links with an invalid URL, so sanitise it."""
    u = (u or "").strip().strip("'\"").strip()
    u = re.sub(r"\s+", "", u)
    if not u:
        return ""
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    pu = urlparse(u)
    if not pu.netloc or "." not in pu.netloc:
        return ""
    return quote(u, safe=":/?#[]@!$&'()*+,;=%-._~")

_quick_env = _clean_url(os.getenv("QUICK_LOGIN_URL"))
QUICK_LOGIN_URL  = _quick_env or _clean_url(LOGIN_URL) or "https://transcribersnet.com/admin/login"
QUICK_URL_SOURCE = ".env QUICK_LOGIN_URL" if _quick_env else "fallback (QUICK_LOGIN_URL missing/invalid)"
ENV_EMAIL        = os.getenv("WEBSITE_EMAIL", "")
ENV_PASSWORD     = os.getenv("WEBSITE_PASSWORD", "")
RECOVERY_KEY     = os.getenv("RECOVERY_KEY", "your_secret_recovery_key")
CHECK_MIN        = int(os.getenv("CHECK_INTERVAL_MIN", "3"))
CHECK_MAX        = int(os.getenv("CHECK_INTERVAL_MAX", "20"))
UPI_ID           = os.getenv("UPI_ID", "your_upi_id@bank")
SURF_URLS        = os.getenv("SURF_URLS", "https://transcribersnet.com/admin/userDashboard,https://transcribersnet.com/admin/my-work,https://transcribersnet.com/admin/userattendance,https://transcribersnet.com/admin/find-proofreading,https://transcribersnet.com/admin/all-level-work")

SURF_PAGES_MIN   = int(os.getenv("SURF_PAGES_MIN", "0"))
SURF_PAGES_MAX   = int(os.getenv("SURF_PAGES_MAX", "4"))
SURF_DELAY_MIN   = float(os.getenv("SURF_DELAY_MIN", "3.0"))
SURF_DELAY_MAX   = float(os.getenv("SURF_DELAY_MAX", "7.0"))

REMINDER_FREQ_SEC = int(float(os.getenv("REMINDER_FREQ_MINS", "20")) * 60)

COOKIES_FILE  = "saved_cookies.json"
CREDS_FILE    = "saved_creds.json"
USERS_FILE    = "users.json"
PASSCODE_FILE = "saved_passcode.json"
DEBUG_FILE    = "debug_mode.json"
STATE_FILE    = "last_state.json"

PAGE_NAMES = {
    "userDashboard": "Dashboard",
    "my-work": "My Work",
    "userattendance": "Attendance",
    "find-proofreading": "Proofread",
    "all-level-work": "Find Work"
}

failed_session_urls = set()

USER_DELAY  = 60
FREE_ALERTS = 5

debug_mode = False

def load_debug_mode():
    global debug_mode
    if os.path.exists(DEBUG_FILE):
        try:
            with open(DEBUG_FILE) as f:
                debug_mode = json.load(f).get("debug", False)
        except:
            debug_mode = False

def save_debug_mode(val):
    global debug_mode
    debug_mode = val
    try:
        with open(DEBUG_FILE, "w") as f:
            json.dump({"debug": val}, f)
    except:
        pass

load_debug_mode()

# ── Termux log helpers (HybridBot style) ─────
CYAN  = "\033[96m"
RESET = "\033[0m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
GREY   = "\033[90m"

def _ts():
    return datetime.now().strftime('%I:%M:%S %p')

def t_log(msg, is_debug=False):
    """Timestamped main line:  [12:21:23 PM] ✅ Connected"""
    if is_debug and not debug_mode:
        return
    try:
        print(f"[{_ts()}] {msg}")
        sys.stdout.flush()
    except OSError:
        pass
    except Exception:
        pass

def t_sub(msg, is_debug=False):
    """Indented detail line under a main line."""
    if is_debug and not debug_mode:
        return
    try:
        print(f"    {msg}")
        sys.stdout.flush()
    except OSError:
        pass
    except Exception:
        pass

def _out(line, is_debug=False):
    if is_debug and not debug_mode:
        return
    try:
        print(line)
        sys.stdout.flush()
    except OSError:
        pass
    except Exception:
        pass

def t_head(title, is_debug=False, color=CYAN):
    """Blank line + coloured header:  [12:21:29 PM] ━━━ SCAN #1 · Admin ━━━"""
    bar = "━" * max(3, 25 - len(title))
    _out(f"\n[{_ts()}] {color}━━━ {title} {bar}{RESET}", is_debug)

def t_line(is_debug=False):
    """Thin separator line between parts of a cycle."""
    _out(f"  {GREY}{'─' * 38}{RESET}", is_debug)

def t_step(label, msg, is_debug=False):
    """Aligned step line:   1 Landing  🏠 Dashboard OK"""
    _out(f"  {label:<10}{msg}", is_debug)

def t_item(msg, is_debug=False):
    """Detail under a step (6 spaces)."""
    _out(f"      {msg}", is_debug)

def t_job(msg, is_debug=False):
    """Deeper detail (8 spaces): jobs, waits."""
    _out(f"        {msg}", is_debug)

def load_last_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_last_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except:
        pass

# ── Global Engine State ──────────────────────
session              = requests.Session()
is_logged_in         = False
is_monitoring        = False
last_state           = load_last_state()
next_check_at        = None
last_disconnect_str  = "None"
last_disconnect_time = 0.0
locked_levels        = set()

# ── ISOLATED MEMORY VAULTS ───────────────────
profile_accumulated     = {}
profile_last_disconnect = {}

# ── Trackers ────────────────────────────────
active_profile_name    = ""
session_start_str      = "None"
fetch_count            = 0
alert_count            = 0
reminders_sent         = 0
session_errors         = set()
total_accumulated_time = 0.0
last_connection_start  = None
is_engine_fresh_start  = True

def record_disconnect():
    global last_disconnect_str, last_disconnect_time
    last_disconnect_time = time.time()
    last_disconnect_str  = datetime.now().strftime("%I:%M:%S %p on %d %b %Y")

def get_profile_limits(profile_name):
    limits = {
        "🔴🍪 Admin": (
            int(float(os.getenv("ADMIN_SHUTDOWN_HOURS", "3")) * 3600),
            int(float(os.getenv("ADMIN_REMINDER_HOURS", "2")) * 3600)
        ),
        "🔵🍪 User 1": (
            int(float(os.getenv("USER1_SHUTDOWN_HOURS", "3")) * 3600),
            int(float(os.getenv("USER1_REMINDER_HOURS", "2")) * 3600)
        ),
        "🟢🍪 User 2": (
            int(float(os.getenv("USER2_SHUTDOWN_HOURS", "5")) * 3600),
            int(float(os.getenv("USER2_REMINDER_HOURS", "4")) * 3600)
        ),
        "🔑 ENV": (
            int(float(os.getenv("ENV_SHUTDOWN_HOURS", "3")) * 3600),
            int(float(os.getenv("ENV_REMINDER_HOURS", "2")) * 3600)
        ),
        "🪪 Login 1": (
            int(float(os.getenv("LOGIN1_SHUTDOWN_HOURS", "3")) * 3600),
            int(float(os.getenv("LOGIN1_REMINDER_HOURS", "2")) * 3600)
        ),
        "🪪 Login 2": (
            int(float(os.getenv("LOGIN2_SHUTDOWN_HOURS", "5")) * 3600),
            int(float(os.getenv("LOGIN2_REMINDER_HOURS", "4")) * 3600)
        )
    }
    return limits.get(profile_name, (10800, 7200))

def format_uptime(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}h {m:02d}m {s:02d}s"

def get_current_uptime_seconds():
    uptime = total_accumulated_time
    if is_monitoring and last_connection_start:
        uptime += (time.time() - last_connection_start)
    return uptime

def get_uptime_str():
    return format_uptime(get_current_uptime_seconds())

def start_session_timer():
    global total_accumulated_time, last_connection_start, session_start_str
    global is_monitoring, reminders_sent, fetch_count
    global alert_count, session_errors, locked_levels, is_engine_fresh_start, failed_session_urls

    prof      = active_profile_name
    last_disc = profile_last_disconnect.get(prof, 0.0)
    saved_acc = profile_accumulated.get(prof, 0.0)

    if last_disc > 0 and (time.time() - last_disc) <= 1800:
        total_accumulated_time = saved_acc
        t_log(f"🧠 Timer resumed: {format_uptime(saved_acc)}", is_debug=True)
        t_sub("(last session under 30 min ago)", is_debug=True)
    else:
        total_accumulated_time = 0.0
        t_log("🧠 Timer started fresh: 0h 00m", is_debug=True)
        t_sub("(last session over 30 min ago)", is_debug=True)

    last_connection_start = time.time()
    is_monitoring  = True
    is_engine_fresh_start = True
    session_start_str = datetime.now().strftime("%I:%M:%S %p, %d %b %Y")
    reminders_sent = 0
    fetch_count    = 0
    alert_count    = 0
    session_errors.clear()
    locked_levels.clear()
    failed_session_urls.clear()
    t_log("🔧 Engine initialized.")

def stop_session_timer():
    global total_accumulated_time, last_connection_start, is_monitoring, is_logged_in
    if is_monitoring and last_connection_start:
        current_up = get_current_uptime_seconds()
        prof       = active_profile_name
        profile_accumulated[prof]     = current_up
        profile_last_disconnect[prof] = time.time()
        
        total_accumulated_time = current_up
        last_connection_start  = None
        
    is_monitoring = False
    is_logged_in  = False
    record_disconnect()

def generate_session_report():
    err_str = ", ".join(session_errors).replace('*', '').replace('_', '').replace('`', '') if session_errors else "None. Perfectly stable."
    up_str = get_uptime_str()
    prof = active_profile_name if active_profile_name else "Unknown"
    return (
        "━━━━━━━━━━━━━━━━━━━\n"
        "📊 *SESSION SUMMARY*\n"
        f"Method        : {prof}\n"
        f"Total Uptime  : {up_str}\n"
        f"Total Fetches : {fetch_count}\n"
        f"Total Alerts  : {alert_count}\n"
        f"Session Errors: {err_str}"
    )

# ── Data Handlers ──────────────────────────
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE) as f:
                data = json.load(f)
                if not isinstance(data, dict): return {}
                return {k: v for k, v in data.items() if isinstance(v, dict) and "id" in v}
        except: return {}
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w") as f: json.dump(users, f, indent=2)
    except: pass

def get_user(user_id):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "id": int(user_id), "username": "", "name": "", "status": "pending",
            "plan": None, "expiry": None, "free_alerts": FREE_ALERTS,
            "alerts_sent": 0, "joined": datetime.now().isoformat()
        }
        save_users(users)
    return users[uid]

def update_user(user_id, data):
    users = load_users()
    uid = str(user_id)
    if uid in users:
        users[uid].update(data)
    else:
        user = {
            "id": int(user_id), "username": "", "name": "", "status": "pending",
            "plan": None, "expiry": None, "free_alerts": FREE_ALERTS,
            "alerts_sent": 0, "joined": datetime.now().isoformat()
        }
        user.update(data)
        users[uid] = user
    save_users(users)

def is_user_active(user_id):
    if int(user_id) == ADMIN_ID: return True
    user = get_user(user_id)
    if user.get("status") == "approved":
        expiry = user.get("expiry")
        if expiry:
            if datetime.now() < datetime.fromisoformat(expiry): return True
            else:
                update_user(user_id, {"status": "expired"})
                return False
        return True
    return user.get("free_alerts", 0) > 0

def get_active_users():
    return [u for u in load_users().values() if is_user_active(u["id"])]

def get_all_users():
    return list(load_users().values())

def load_cookies_file():
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE) as f:
                data = json.load(f)
                if "cookie_name" in data: return {"admin": data}
                if "user" in data: data["user1"] = data.pop("user")
                return data
        except: return {}
    return {}

def save_cookies_file(slot, c_name, c_value, xsrf_value, date_str=None, valid_until=None):
    data = load_cookies_file()
    if date_str is None:
        date_str = datetime.now().strftime("%d-%b-%Y")
    data[slot] = {
        "cookie_name":  c_name,
        "cookie_value": c_value,
        "xsrf_value":   xsrf_value,
        "date":         date_str,
        "valid_until":  valid_until or "Unknown"
    }
    try:
        with open(COOKIES_FILE, "w") as f: json.dump(data, f, indent=2)
    except: pass

def load_creds_file():
    if os.path.exists(CREDS_FILE):
        try:
            with open(CREDS_FILE) as f:
                data = json.load(f)
                if "email" in data:
                    return {"login1": {"email": data["email"], "password": data["password"]}, "login2": {}}
                return data
        except: return {"login1": {}, "login2": {}}
    return {"login1": {}, "login2": {}}

def save_creds_file(slot, email, password):
    data = load_creds_file()
    data[slot] = {"email": email, "password": password}
    try:
        with open(CREDS_FILE, "w") as f: json.dump(data, f, indent=2)
    except: pass

def load_passcode_file():
    if os.path.exists(PASSCODE_FILE):
        try:
            with open(PASSCODE_FILE) as f: return json.load(f).get("passcode")
        except: return None
    return None

def save_passcode_file(passcode):
    try:
        with open(PASSCODE_FILE, "w") as f: json.dump({"passcode": passcode}, f)
    except: pass

# ── Session & Login ────────────────────────
def human_delay(a=2, b=4): time.sleep(random.uniform(a, b))
def get_timeout(): return random.uniform(14.2, 16.8)

def make_session():
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

def login_with_cookies(cookie_name, cookie_value, xsrf_value, slot_name):
    global is_logged_in, session
    try:
        t_log(f"🔐 Cookie login → {slot_name.upper()}...")
        session = make_session()
        session.cookies.set(cookie_name, cookie_value, domain="transcribersnet.com")
        if xsrf_value and xsrf_value.lower() != "skip":
            session.cookies.set("XSRF-TOKEN", xsrf_value, domain="transcribersnet.com")
        session.headers.update({"Sec-Fetch-Site": "none"})
        r = session.get("https://transcribersnet.com/admin/userDashboard",
                        timeout=get_timeout(), allow_redirects=True)
        human_delay(2, 4)
        if "login" not in r.url.lower():
            is_logged_in = True
            t_sub(f"Landed on: {r.url.replace('https://transcribersnet.com', '')} ({r.status_code})")
            t_sub("✔ Login successful")
            return True, "Success"
        else:
            is_logged_in = False
            t_sub("✖ Token rejected by server")
            return False, "Cookie Expired: Cookies rejected by server."
    except requests.exceptions.RequestException as e:
        is_logged_in = False
        t_sub(f"✖ Network drop during login: {str(e)[:60]}")
        return False, f"Network Error: {str(e)[:40]}"
    except Exception as e:
        is_logged_in = False
        t_sub(f"✖ System error during login: {str(e)[:60]}")
        return False, f"System Error: {str(e)[:40]}"

def login_with_credentials(email, password, mapping_slot):
    global is_logged_in, session
    try:
        t_log(f"🔐 Password login → {mapping_slot.upper()}...")
        session = make_session()
        session.headers.update({"Sec-Fetch-Site": "none"})
        page = session.get(LOGIN_URL, timeout=get_timeout())
        soup = BeautifulSoup(page.text, "html.parser")
        token_input = soup.find("input", {"name": "_token"})
        csrf = token_input.get("value", "") if token_input else ""
        human_delay(2, 4)
        session.headers.update({
            "Origin": "https://transcribersnet.com",
            "Referer": LOGIN_URL,
            "Sec-Fetch-Site": "same-origin",
            "Content-Type": "application/x-www-form-urlencoded"
        })
        payload = {"email": email, "password": password, "_token": csrf, "remember_me": "1"}
        r = session.post(LOGIN_SUBMIT_URL, data=payload, timeout=get_timeout(), allow_redirects=True)

        if "login" not in r.url.lower():
            human_delay(2, 4)
            is_logged_in = True
            t_sub(f"Landed on: {r.url.replace('https://transcribersnet.com', '')} ({r.status_code})")
            t_sub("✔ Login successful")

            xsrf_val    = session.cookies.get("XSRF-TOKEN", domain="transcribersnet.com") or ""
            best_name   = None
            best_value  = None
            best_expiry = -1
            best_expiry_str = "Unknown"
            got_names = []

            for cookie in session.cookies:
                got_names.append(cookie.name)
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

            t_sub(f"Cookies received: {', '.join(got_names) if got_names else 'none'}")

            if best_name:
                save_cookies_file(mapping_slot, best_name, best_value, xsrf_val, valid_until=best_expiry_str)
                if "remember_web_" in best_name:
                    t_sub(f"✔ remember_web cookie saved till: {best_expiry_str}")
                else:
                    t_sub("⚠️ No remember_web cookie from site")
                    t_sub(f"Saving short-lived session cookies instead ({best_expiry_str})")
            return True, "Success"
        else:
            is_logged_in = False
            t_sub("✖ Creds dropped. Anti-bot active.")
            return False, "Anti-bot block. Use COOKIE method."
    except requests.exceptions.RequestException as e:
        is_logged_in = False
        t_sub(f"✖ Login failure: {str(e)[:60]}")
        return False, f"Network Error: {str(e)[:40]}"
    except Exception as e:
        is_logged_in = False
        t_sub(f"✖ Login failure: {str(e)[:60]}")
        return False, f"System Error: {str(e)[:40]}"

def fetch_work_levels(fast_mode=False):
    global is_logged_in, fetch_count, failed_session_urls
    if not is_logged_in: return None
    try:
        urls_pool = [u.strip() for u in SURF_URLS.split(",") if u.strip()]
        landing_page = random.choice(urls_pool) if urls_pool else "https://transcribersnet.com/admin/userDashboard"
        landing_name = PAGE_NAMES.get(landing_page.split('/')[-1], landing_page.split('/')[-1])
        
        t_head(f"SCAN #{fetch_count + 1} · {active_profile_name}")
        
        session.headers.update({"Referer": "https://transcribersnet.com/", "Sec-Fetch-Site": "same-origin"})
        
        try:
            resp_landing = session.get(landing_page, timeout=get_timeout())
            if "login" in resp_landing.url.lower():
                is_logged_in = False
                return None
            t_step("1 Landing", f"🏠 {landing_name} ✔ OK", is_debug=True)
        except Exception:
            t_step("1 Landing", f"🏠 {landing_name} ⏩ skipped", is_debug=True)

        pause = 0.5 if fast_mode else random.uniform(SURF_DELAY_MIN, SURF_DELAY_MAX)
        t_item(f"⏳ read {pause:.1f}s", is_debug=True)
        time.sleep(pause)

        session.headers.update({"Referer": landing_page})
        resp = session.get(WORK_URL, timeout=get_timeout())
        if "login" in resp.url.lower():
            is_logged_in = False
            return None
            
        kb = len(resp.content) // 1024 if resp.content else 0
        t_step("2 Work", f"📍 Find Work ✔ {resp.status_code} · {kb}KB", is_debug=True)
        
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
        fetch_count += 1
        
        with_work = sum(1 for v in levels.values() if v["available"] > 0)
        total_av  = sum(v["available"] for v in levels.values())
        t_item(f"🟢 {total_av} available · {with_work}/{len(levels)} levels", is_debug=True)
        for k, v in levels.items():
            if v["available"] > 0:
                t_job(f"🎧 L{k.split()[-1]}  Avail {v['available']} | Booked {v['booked']}", is_debug=True)
        
        pause2 = 0.5 if fast_mode else random.uniform(SURF_DELAY_MIN, SURF_DELAY_MAX)
        t_item(f"⏳ read {pause2:.1f}s", is_debug=True)
        time.sleep(pause2)
        
        return levels
    except requests.exceptions.RequestException:
        return "NETWORK_ERROR"
    except Exception as e:
        t_log(f"🛠️ Auto-Fix: parser corrected: {str(e)[:40]}")
        return None

def fetch_level_languages(level_num, fast_mode=False):
    global failed_session_urls
    if level_num in locked_levels:
        t_item(f"L{level_num}  🔒 locked (403)", is_debug=True)
        return ["🔒 Locked"]
    
    level_url = f"https://transcribersnet.com/admin/work/level_work/{level_num}"
    if level_url in failed_session_urls:
        t_item(f"L{level_num}  ⏩ skipped (failed before)", is_debug=True)
        return ["🔒 Locked"]

    try:
        session.headers.update({"Referer": WORK_URL})
        resp = session.get(level_url, timeout=get_timeout())
        if "login" in resp.url.lower(): return ["Session Lost"]
        
        kb = len(resp.content) // 1024 if resp.content else 0
        t_item(f"L{level_num}  ✔ {resp.status_code} · {kb}KB", is_debug=True)
        
        pause = 0.5 if fast_mode else random.uniform(SURF_DELAY_MIN, SURF_DELAY_MAX)
        t_job(f"⏳ read {pause:.1f}s", is_debug=True)
        time.sleep(pause)
        
        if resp.status_code == 403:
            locked_levels.add(level_num)
            failed_session_urls.add(level_url) 
            t_job("🔒 locked (403, permanent)", is_debug=True)
            return ["🔒 Locked"]
            
        soup  = BeautifulSoup(resp.text, "html.parser")
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
                    
                    # All available files forcefully appended (no dedup).
                    detail_dict = {"old": old_str, "new": new_str}
                    job_details.append(detail_dict)
                        
        t_job(f"🟢 {len(job_details)} jobs", is_debug=True)
        for jd in job_details:
            t_job(f"🎧 {jd['new']}", is_debug=True)
        return job_details if job_details else ["No Valid Data Found"]
        
    except requests.exceptions.RequestException: 
        failed_session_urls.add(level_url) 
        return ["Network Error"]
    except Exception:
        return ["Error"]

def get_lang_map_sync(changed, fast_mode=False):
    if not changed: return {}
    order_str = " → ".join([k.replace("LEVEL ", "L") for k in changed.keys()])
    t_step("3 Levels", f"📍 {order_str}", is_debug=True)
    
    result = {}
    for k in changed:
        result[k] = fetch_level_languages(k.split()[-1], fast_mode)
    return result

async def async_human_surf():
    global failed_session_urls
    urls_str = SURF_URLS
    if not urls_str: return
        
    urls = [u.strip() for u in urls_str.split(",") if u.strip()]
    if not urls: return
    
    safe_max = min(SURF_PAGES_MAX, len(urls))
    safe_min = min(SURF_PAGES_MIN, safe_max)
    
    num_pages = random.randint(safe_min, safe_max)
    if num_pages == 0:
        return
        
    random.shuffle(urls)
    pages_to_visit = urls[:num_pages]
    
    order_names = [PAGE_NAMES.get(url.split('/')[-1], url.split('/')[-1]) for url in pages_to_visit]
    order_str = " → ".join(order_names)
    t_head(f"🌐 BROWSE · {num_pages} pages", is_debug=True, color=YELLOW)
    t_step("ROUTE", order_str, is_debug=True)
    
    for idx, url in enumerate(pages_to_visit, start=1):
        if url in failed_session_urls:
            continue
            
        page_lbl = PAGE_NAMES.get(url.split('/')[-1], url.split('/')[-1])
        pause = random.uniform(SURF_DELAY_MIN, SURF_DELAY_MAX)
        
        try:
            session.headers.update({"Sec-Fetch-Site": "same-origin", "Referer": WORK_URL})
            resp = await asyncio.to_thread(session.get, url, timeout=get_timeout())
            if resp.status_code in [403, 404, 500]:
                failed_session_urls.add(url) 
                t_item(f"{page_lbl}  🔒 blocked ({resp.status_code})", is_debug=True)
                continue
            
            kb = len(resp.content) // 1024 if resp.content else 0
            t_item(f"{page_lbl}  ✔ {resp.status_code} · {kb}KB", is_debug=True)
            t_job(f"⏳ read {pause:.1f}s", is_debug=True)
            await asyncio.sleep(pause)
            
            if idx < num_pages:
                gap = random.uniform(1.0, 3.5)
                await asyncio.sleep(gap)
                
        except Exception:
            failed_session_urls.add(url)
            t_item(f"{page_lbl}  ✖ failed", is_debug=True)

    t_line(is_debug=True)

def build_alert(changed, current_levels, lang_map, is_admin=True):
    # HTML formatted (parse_mode="HTML") so the link is always clickable
    level_blocks = []
    for key, data in sorted(changed.items()):
        current_block = [f"🎧 <b>{html.escape(key)}</b> | <b>Avail: {data['available']}</b> 🍏 | Booked: {data['booked']}"]
        
        if is_admin:
            details = lang_map.get(key, [])
            for detail in details:
                if isinstance(detail, dict):
                    current_block.append(html.escape(detail["new"]))
                else:
                    current_block.append(html.escape(str(detail)))
            
        level_blocks.append("\n".join(current_block))
            
    alert_body = "\n\n".join(level_blocks) if is_admin else "\n".join(level_blocks)
    link = html.escape(QUICK_LOGIN_URL, quote=True)
    return f'{alert_body}\n\n━━━━━━━━━━━━━━━━━━━\n💻 <a href="{link}">Log in quickly!</a>'

def build_admin_hi_message(levels, fast_mode=False):
    if levels is None or levels == "NETWORK_ERROR":
        return "❌ Could not fetch levels right now."
    available = {k: v for k, v in levels.items() if v["available"] > 0}
    if not available:
        return "❌ No new jobs currently available."
    return build_alert(available, levels, get_lang_map_sync(available, fast_mode), is_admin=True)

def get_next_str():
    if next_check_at and is_monitoring and is_logged_in:
        rem_seconds = int((next_check_at - datetime.now()).total_seconds())
        if rem_seconds > 0:
            return f"{next_check_at.strftime('%I:%M:%S %p')} (in {rem_seconds // 60}m {rem_seconds % 60}s)"
        return "Running..."
    return "Not scheduled"

def build_admin_status():
    engine_line = ("🟢 ONLINE" if is_logged_in and is_monitoring
                   else ("🔴 OFFLINE" if not is_logged_in else "🟡 STANDBY"))
    
    limit_shutdown, limit_reminder = get_profile_limits(active_profile_name)
    shutdown_str = format_uptime(limit_shutdown)
    reminder_str = format_uptime(limit_reminder)
    debug_line    = "🟢 ON" if debug_mode else "🔴 OFF"
    
    ck_data = load_cookies_file()
    expiry_lines = []
    for slot, label in {"admin": "🔴 Admin", "user1": "🔵 User1", "user2": "🟢 User2"}.items():
        ck = ck_data.get(slot)
        if ck:
            expiry_lines.append(f"{label}: Valid Until {ck.get('valid_until','Unknown')}")
        else:
            expiry_lines.append(f"{label}: Valid Until Unknown")
    expiry_block = "\n".join(expiry_lines)
    
    users = get_all_users()
    non_admin = [u for u in users if u.get("id") != ADMIN_ID]
    
    app_count = sum(1 for u in non_admin if u.get('status')=='approved')
    pen_count = sum(1 for u in non_admin if u.get('status')=='pending')
    rej_count = sum(1 for u in non_admin if u.get('status')=='rejected')
    rec_count = len([u for u in non_admin if is_user_active(u.get('id'))])
    
    return (
        "📊 *SYSTEM STATUS*\n"
        "─────────────────────\n"
        f"Engine        : {engine_line}\n"
        f"Profile       : 🪪 {active_profile_name or 'None'}\n"
        f"Session Start : {session_start_str}\n"
        f"Uptime        : {get_uptime_str()}\n"
        f"Auto-Shutdown : {shutdown_str}\n"
        f"Reminder At   : {reminder_str}\n"
        f"Scan Interval : {CHECK_MIN}–{CHECK_MAX} min\n"
        f"Page Time     : {SURF_DELAY_MIN}–{SURF_DELAY_MAX}s\n"
        f"Next Check    : {get_next_str()}\n"
        f"Fetch Count   : {fetch_count} times\n"
        f"Debug Mode    : {debug_line}\n"
        f"Last Disconn  : {last_disconnect_str}\n"
        "─────────────────────\n"
        "🍪 *COOKIE EXPIRY*\n"
        f"{expiry_block}\n"
        "─────────────────────\n"
        "👥 *USER STATISTICS*\n"
        f"Total Registered : {len(non_admin)}\n"
        f"Approved : ✅ {app_count} | Pending : ⏳ {pen_count} | Rejected : ❌ {rej_count}\n"
        f"Receiving Alerts : 🔔 {rec_count}\n"
        "─────────────────────"
    )

# ── Keyboards ───────────────────────────────
def get_3_cookie_row(prefix):
    return [
        InlineKeyboardButton("🔴🍪 ADMIN",  callback_data=f"{prefix}_admin"),
        InlineKeyboardButton("🔵🍪 USER 1", callback_data=f"{prefix}_user1"),
        InlineKeyboardButton("🟢🍪 USER 2", callback_data=f"{prefix}_user2"),
    ]

def admin_keyboard():
    stop_emoji = "🟢" if (is_logged_in and is_monitoring) else "🛑"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚂 START BOT ENGINE",    callback_data="start_connect"),
         InlineKeyboardButton(f"{stop_emoji} STOP BOT ENGINE", callback_data="stop_engine")],
        [InlineKeyboardButton("📊 CURRENT BOT STATUS",  callback_data="admin_status")],
        [InlineKeyboardButton("🍪 MANAGE SAVED DATA",   callback_data="save_details"),
         InlineKeyboardButton("👥 VIEW ALL REG USERS",  callback_data="admin_users")],
        [InlineKeyboardButton("💬 MESSAGE A USER",      callback_data="admin_message"),
         InlineKeyboardButton("📢 BROADCAST MESSAGE",   callback_data="admin_broadcast")],
        [InlineKeyboardButton("🗑️ RESET LOGIN IDs",    callback_data="confirm_reset_creds"),
         InlineKeyboardButton("🗑️ RESET ALL COOKIES",  callback_data="confirm_reset_cookies")],
    ])

def dynamic_connect_keyboard():
    return InlineKeyboardMarkup([
        get_3_cookie_row("auto_connect"),
        [InlineKeyboardButton("🖥️ LOGIN VIA SYSTEM ENV", callback_data="connect_env")],
        [InlineKeyboardButton("🪪 LOGIN 1", callback_data="auto_connect_login1"),
         InlineKeyboardButton("🪪 LOGIN 2", callback_data="auto_connect_login2")],
        [InlineKeyboardButton("❌ CANCEL THIS ACTION",   callback_data="cancel_action")],
    ])

def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ CANCEL THIS ACTION", callback_data="cancel_action")]])

def user_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 CHECK MY SUB STATUS", callback_data="user_status"),
         InlineKeyboardButton("💳 BUY A SUBSCRIPTION",  callback_data="user_subscribe")],
        [InlineKeyboardButton("❓ HELP AND INFORMATION", callback_data="user_help")],
    ])

def approve_keyboard(user_id, plan):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ APPROVE USER SUBSCRIPTION", callback_data=f"approve_{user_id}_{plan}"),
        InlineKeyboardButton("❌ REJECT USER SUBSCRIPTION",  callback_data=f"reject_{user_id}"),
    ]])

# ── Background Alert System ─────────────────
async def check_and_alert(context: ContextTypes.DEFAULT_TYPE):
    global last_state, is_monitoring, is_logged_in, next_check_at, reminders_sent, session_errors, alert_count, is_engine_fresh_start

    if not is_monitoring or not is_logged_in: return

    try:
        uptime = get_current_uptime_seconds()
        limit_shutdown, limit_reminder = get_profile_limits(active_profile_name)

        if uptime >= limit_reminder:
            expected = int(uptime // REMINDER_FREQ_SEC)
            if expected > reminders_sent:
                reminders_sent = expected
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"⏳ *Reminder*\nProfile: {active_profile_name}\nUptime: {format_uptime(uptime)}",
                        parse_mode="Markdown"
                    )
                except: pass

        if uptime >= limit_shutdown:
            t_log("🛑 Uptime limit reached. Shutting down safely.")
            t_sub(f"Profile: {active_profile_name} | Uptime: {format_uptime(uptime)}")
            stop_session_timer()
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🛑 *AUTO-DISCONNECT*\nTime limit for {active_profile_name}.\n\n{generate_session_report()}",
                    parse_mode="Markdown"
                )
                await context.bot.send_message(chat_id=ADMIN_ID, text="⚙️ *Main Menu:*",
                                                parse_mode="Markdown", reply_markup=admin_keyboard())
            except: pass
            return

        if next_check_at and datetime.now() < next_check_at: return

        current = await asyncio.to_thread(fetch_work_levels)

        if current == "NETWORK_ERROR":
            delay = random.randint(CHECK_MIN * 60, CHECK_MAX * 60)
            next_check_at = datetime.now() + timedelta(seconds=delay)
            t_log("⚠️ Network error. Rest position assigned.")
            t_sub(f"Retry at {next_check_at.strftime('%I:%M:%S %p')}")
            session_errors.add("Internet Drop")
            return

        if current is None:
            t_log("🛑 Login token expired or firewall block encountered.")
            session_errors.add("Cookies Expired or Blocked")
            stop_session_timer()
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ *Session Lost*\n🔴 Engine stopped.\n\n{generate_session_report()}",
                    parse_mode="Markdown"
                )
                await context.bot.send_message(chat_id=ADMIN_ID, text="⚙️ *Main Menu:*",
                                                parse_mode="Markdown", reply_markup=admin_keyboard())
            except: pass
            return

        is_first_scan = is_engine_fresh_start and (not bool(last_state))
        
        with_work = sum(1 for v in current.values() if v["available"] > 0)
        total_av  = sum(v["available"] for v in current.values())
        prev_av   = sum(v.get("available", 0) for v in last_state.values()) if last_state else 0
        
        if not is_engine_fresh_start:
            changed = {k: v for k, v in current.items()
                       if v["available"] > last_state.get(k, {}).get("available", 0)}
        else:
            changed = {k: v for k, v in current.items() if v["available"] > 0}

        admin_sent = False
        if changed:
            lang_map        = await asyncio.to_thread(get_lang_map_sync, changed)
            admin_alert_txt = build_alert(changed, current, lang_map, is_admin=True)

            try: 
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert_txt,
                                               parse_mode="HTML", disable_web_page_preview=True)
                admin_sent = True
            except: pass

        # ── RESULT block ──
        t_line()
        new_tag = " 🆕" if changed else ""
        t_step("RESULT", f"🟢 {total_av} available · {with_work} levels (was {prev_av}){new_tag}")
        if changed:
            names = ", ".join(k.replace("LEVEL ", "L") for k in sorted(changed))
            admin_txt = "✅ sent" if admin_sent else "❌ failed"
            user_txt  = "⏸ skipped (1st scan)" if is_first_scan else f"⏳ queued ({USER_DELAY}s)"
            t_step("NEW IN", f"🆕 {names}")
            t_step("ALERTS", f"Admin {admin_txt} | Users {user_txt}")
        else:
            t_step("ALERTS", "none (no new work)")

        if changed:
            if not is_first_scan:
                user_alert_txt  = build_alert(changed, current, lang_map, is_admin=False)
                start_delay = time.time()
                
                await async_human_surf()
                
                elapsed = time.time() - start_delay
                remaining = USER_DELAY - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)

                users_sent = 0
                for user in get_active_users():
                    uid = user.get("id")
                    if not uid or uid == ADMIN_ID: continue
                    try:
                        if not user.get("expiry"):
                            free = user.get("free_alerts", 0)
                            if free <= 0: continue
                            update_user(uid, {"free_alerts": free - 1, "alerts_sent": user.get("alerts_sent", 0) + 1})
                            if free - 1 == 1:
                                await context.bot.send_message(chat_id=uid,
                                    text="⚠️ *Last Free Alert!*\n\n₹6 — 2 Days\n₹100 — 30 Days\n\n/start",
                                    parse_mode="Markdown")
                        else:
                            update_user(uid, {"alerts_sent": user.get("alerts_sent", 0) + 1})
                        await context.bot.send_message(chat_id=uid, text=user_alert_txt,
                                                       parse_mode="HTML", disable_web_page_preview=True)
                        alert_count += 1
                        users_sent += 1
                        await asyncio.sleep(0.1)
                    except: pass
                t_head("📤 USER ALERTS", color=GREEN)
                t_step("SENT", f"📤 {users_sent} users")
            else:
                await async_human_surf()
        else:
            await async_human_surf()

        is_engine_fresh_start = False
        last_state = current
        save_last_state(current)
        
        delay = random.randint(CHECK_MIN * 60, CHECK_MAX * 60)
        next_check_at = datetime.now() + timedelta(seconds=delay)
        
        rem_min = int((next_check_at - datetime.now()).total_seconds() // 60)
        rem_sec = int((next_check_at - datetime.now()).total_seconds() % 60)
        t_line()
        t_step("NEXT", f"💤 {next_check_at.strftime('%I:%M:%S %p')} (in {rem_min}m {rem_sec}s)")
        
    except Exception as e:
        t_log(f"🛠️ Auto-Fix: framework crash recovery: {str(e)[:50]}")

# ── Commands ────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    update_user(user_id, {"name": user.full_name, "username": user.username or ""})
    context.user_data.pop("action", None)
    context.user_data.pop("cookie_slot", None)
    if user_id == ADMIN_ID:
        await update.message.reply_text(build_admin_status(), parse_mode="Markdown", reply_markup=admin_keyboard())
    else:
        u    = get_user(user_id)
        free = u.get("free_alerts", 0)
        if u.get("status") == "approved" and u.get("expiry"):
            s = f"✅ Active — {(datetime.fromisoformat(u['expiry']) - datetime.now()).days} days left"
        elif u.get("status") == "approved":
            s = f"✅ Free — {free} alerts left"
        else:
            s = f"⏳ Pending — {free} free alerts"
        await update.message.reply_text(
            f"🎉 *Welcome, {user.first_name}!* 🎉\n\n"
            f"🤖 I am your personal Job Alert Bot.\n"
            f"📡 *Your Status:* {s}\n\n"
            f"✨ You will automatically receive notifications when new work is available!\n"
            f"👇 Use the menu below to manage your account.",
            parse_mode="Markdown", reply_markup=user_keyboard()
        )

async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data.pop("action", None)
    await update.message.reply_text("🔑 *Login Method:*", parse_mode="Markdown",
                                    reply_markup=dynamic_connect_keyboard())

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("action", None)
    context.user_data.pop("cookie_slot", None)
    kb = admin_keyboard() if update.effective_user.id == ADMIN_ID else user_keyboard()
    await update.message.reply_text("❌ Action cancelled.", reply_markup=kb)

async def cmd_reset_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data["action"] = "recover_passcode"
    await update.message.reply_text("🔐 *PIN Recovery:* Enter your recovery key:",
                                    parse_mode="Markdown", reply_markup=cancel_keyboard())

# ── Helper: send file safely ─────────────────
async def send_file_to_user(bot, user_id, fname):
    work_dir = os.path.expanduser("~")
    fpath    = os.path.join(work_dir, fname)
    if not os.path.exists(fpath) or not os.path.isfile(fpath):
        await bot.send_message(chat_id=user_id, text="❌ File not found.")
        return
    await bot.send_message(chat_id=user_id, text=f"⏳ Extracting `{fname}`...", parse_mode="Markdown")
    send_name = "env_config.txt" if fname == ".env" else (fname + ".txt" if not os.path.splitext(fname)[1] else fname)
    with open(fpath, "rb") as f:
        await bot.send_document(chat_id=user_id, document=f, filename=send_name)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK TO FOLDER", callback_data="view_source")]])
    await bot.send_message(chat_id=user_id,
                           text=f"✅ `{fname}` sent as `{send_name}`",
                           parse_mode="Markdown", reply_markup=kb)

# ── Main Callback Handler ────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring, is_logged_in, last_state, next_check_at, active_profile_name

    query   = update.callback_query
    user_id = query.from_user.id
    try: await query.answer()
    except: pass
    data = query.data

    async def del_msg():
        try: await query.message.delete()
        except: pass

    # ════════════ ADMIN ════════════
    if user_id == ADMIN_ID:

        # Passcode setup on first use
        stored_passcode = load_passcode_file()
        if not stored_passcode:
            if not context.user_data.get("passcode_setup"):
                context.user_data["passcode_setup"] = True
                context.user_data["action"] = "set_passcode"
                await del_msg()
                return await context.bot.send_message(
                    chat_id=user_id,
                    text="🔐 *Security Setup:* Set a 6-digit PIN for restricted areas:",
                    parse_mode="Markdown")
            if context.user_data.get("action") == "confirm_passcode":
                return

        # Restricted area guard
        if data in ["view_saved_details", "confirm_reset_creds", "confirm_reset_cookies"] \
                and not context.user_data.get("restricted_auth"):
            context.user_data["pending_action"] = data
            context.user_data["action"] = "restricted_login"
            await del_msg()
            return await context.bot.send_message(
                chat_id=user_id,
                text="🔐 *Restricted Area:* Enter your 6-digit PIN:",
                parse_mode="Markdown", reply_markup=cancel_keyboard())

        # ── START CONNECT ──────────────────────
        if data == "start_connect":
            context.user_data.pop("action", None)
            context.user_data.pop("cookie_slot", None)
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="🔑 *Login Method:*",
                                           parse_mode="Markdown", reply_markup=dynamic_connect_keyboard())

        # ── ENGINE CONNECT ─────────────────────
        elif data.startswith("auto_connect_") or data == "connect_env":
            context.user_data.pop("action", None)
            if data == "connect_env":
                target_profile, slot = "🔑 ENV", "env"
            else:
                raw_slot = data.split("_")[2]
                profiles = {"admin": "🔴🍪 Admin", "user1": "🔵🍪 User 1", "user2": "🟢🍪 User 2",
                            "login1": "🪪 Login 1", "login2": "🪪 Login 2"}
                target_profile = profiles.get(raw_slot, raw_slot)
                slot = raw_slot
            await del_msg()

            if is_logged_in or is_monitoring:
                if active_profile_name == target_profile:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⚠️ Already connected via {active_profile_name}.",
                        reply_markup=admin_keyboard())
                    return
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🔄 Switching from `{active_profile_name}` to `{target_profile}`...",
                    parse_mode="Markdown")
                t_log(f"🔄 Switching {active_profile_name} → {target_profile}")
                stop_session_timer()
                await asyncio.sleep(1)

            temp = await context.bot.send_message(chat_id=user_id, text=f"🔄 Connecting {target_profile}...")

            if slot == "env":
                active_profile_name = "🔑 ENV"
                ok, reason = await asyncio.to_thread(login_with_credentials, ENV_EMAIL, ENV_PASSWORD, "admin")
            elif "login" in slot:
                cr = load_creds_file().get(slot, {})
                active_profile_name = "🪪 Login 1" if slot == "login1" else "🪪 Login 2"
                map_slot = "user1" if slot == "login1" else "user2"
                if not cr.get("email"):
                    try: await temp.delete()
                    except: pass
                    return await context.bot.send_message(
                        chat_id=user_id,
                        text=f"❌ No saved details for {active_profile_name}.",
                        reply_markup=admin_keyboard())
                ok, reason = await asyncio.to_thread(login_with_credentials, cr["email"], cr["password"], map_slot)
            else:
                active_profile_name = target_profile
                ck = load_cookies_file().get(slot)
                if not ck:
                    try: await temp.delete()
                    except: pass
                    return await context.bot.send_message(
                        chat_id=user_id,
                        text=f"❌ No cookie saved for: {target_profile}",
                        reply_markup=admin_keyboard())
                ok, reason = await asyncio.to_thread(
                    login_with_cookies, ck["cookie_name"], ck["cookie_value"], ck.get("xsrf_value",""), slot)

            try: await temp.delete()
            except: pass

            if ok:
                last_state    = {}   
                next_check_at = None
                start_session_timer()
                t_log(f"✅ Connected via {active_profile_name}!")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ *Connected ({active_profile_name})!*",
                    parse_mode="Markdown", reply_markup=admin_keyboard())
            else:
                t_log(f"❌ Login failed via {active_profile_name}")
                reason_safe = str(reason).replace('<', '&lt;').replace('>', '&gt;')
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ <b>Login Failed</b>\nReason: <code>{reason_safe}</code>",
                    parse_mode="HTML", reply_markup=admin_keyboard())

        # ── STOP ENGINE ────────────────────────
        elif data == "stop_engine":
            t_log("🛑 Engine stopped manually.")
            stop_session_timer()
            await del_msg()
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⏹ *Engine Stopped Manually.*\n\n{generate_session_report()}",
                parse_mode="Markdown")
            await context.bot.send_message(chat_id=ADMIN_ID, text="⚙️ *Main Menu:*",
                                           parse_mode="Markdown", reply_markup=admin_keyboard())

        # ── STATUS ─────────────────────────────
        elif data == "admin_status":
            context.user_data.pop("action", None)
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text=build_admin_status(),
                                           parse_mode="Markdown", reply_markup=admin_keyboard())

        # ── MANAGE SAVED DATA ──────────────────
        elif data == "save_details":
            context.user_data.pop("action", None)
            debug_emoji = "🟢 ON" if debug_mode else "🔴 OFF"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("👀 VIEW ALL SAVED DATA",      callback_data="view_saved_details")],
                get_3_cookie_row("add_cookie"),
                [InlineKeyboardButton("🪪 SET LOGIN 1", callback_data="set_cred_login1"),
                 InlineKeyboardButton("🪪 SET LOGIN 2", callback_data="set_cred_login2")],
                [InlineKeyboardButton(f"🔍 DEBUG MODE: {debug_emoji}", callback_data="toggle_debug")],
                [InlineKeyboardButton("❌ CANCEL THIS ACTION",        callback_data="cancel_action")],
            ])
            await del_msg()
            await context.bot.send_message(chat_id=user_id,
                                           text="🍪 *Manage Saved Details*\n\nSave Details For:",
                                           parse_mode="Markdown", reply_markup=kb)

        # ── VIEW SAVED DETAILS ─────────────────
        elif data == "view_saved_details":
            ck_data = load_cookies_file()
            cr      = load_creds_file()
            ac, u1, u2 = ck_data.get("admin"), ck_data.get("user1"), ck_data.get("user2")
            cr1, cr2   = cr.get("login1", {}), cr.get("login2", {})
            lines = ["💾 *SAVED DETAILS*\n"]
            lines.append(f"🔴 Admin  : ✅ [{ac.get('date','?')}] Valid: {ac.get('valid_until','?')}" if ac else "🔴 Admin  : ❌")
            lines.append(f"🔵 User 1 : ✅ [{u1.get('date','?')}] Valid: {u1.get('valid_until','?')}" if u1 else "🔵 User 1 : ❌")
            lines.append(f"🟢 User 2 : ✅ [{u2.get('date','?')}] Valid: {u2.get('valid_until','?')}" if u2 else "🟢 User 2 : ❌")
            lines.append(f"🪪 Login 1 : ✅ ({cr1.get('email','')})" if cr1.get("email") else "🪪 Login 1 : ❌")
            lines.append(f"🪪 Login 2 : ✅ ({cr2.get('email','')})" if cr2.get("email") else "🪪 Login 2 : ❌")
            lines.append(f"🔑 ENV    : ✅ ({ENV_EMAIL})" if ENV_EMAIL else "🔑 ENV    : ❌")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔴🍪 ADMIN",  callback_data="raw_ck_admin"),
                 InlineKeyboardButton("🔵🍪 USER 1", callback_data="raw_ck_user1"),
                 InlineKeyboardButton("🟢🍪 USER 2", callback_data="raw_ck_user2")],
                [InlineKeyboardButton("🪪 LOGIN 1",  callback_data="raw_cr_login1"),
                 InlineKeyboardButton("🪪 LOGIN 2",  callback_data="raw_cr_login2")],
                [InlineKeyboardButton("🔑 ENV",      callback_data="raw_env")],
                [InlineKeyboardButton("📁 VIEW SOURCE CODE", callback_data="view_source")], 
                [InlineKeyboardButton("🔙 BACK",     callback_data="save_details")],
            ])
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="\n".join(lines),
                                           parse_mode="Markdown", reply_markup=kb)

        # ── RAW VIEW ───────────────────────────
        elif data.startswith("raw_"):
            parts = data.split("_")
            type_, slot = parts[1], (parts[2] if len(parts) > 2 else "")
            await del_msg()
            msg = ""
            if type_ == "ck":
                ck = load_cookies_file().get(slot)
                if ck:
                    label = {"admin":"🔴🍪 Admin","user1":"🔵🍪 User 1","user2":"🟢🍪 User 2"}.get(slot,"")
                    msg = (f"*{label}*\n\n*Name:*\n`{ck.get('cookie_name')}`\n\n"
                           f"*Value:*\n`{ck.get('cookie_value')}`\n\n"
                           f"*XSRF:*\n`{ck.get('xsrf_value','None')}`\n\n"
                           f"Saved: {ck.get('date','?')} | Valid Until: {ck.get('valid_until','?')}")
                else: msg = "❌ Not Set"
            elif type_ == "cr":
                cr = load_creds_file().get(slot, {})
                if cr.get("email"):
                    label = "🪪 Login 1" if slot == "login1" else "🪪 Login 2"
                    msg = f"*{label}*\n\n*Email:*\n`{cr['email']}`\n\n*Password:*\n`{cr['password']}`"
                else: msg = "❌ Not Set"
            elif type_ == "env":
                msg = f"*🔑 ENV*\n\n*Email:*\n`{ENV_EMAIL}`\n\n*Password:*\n`{ENV_PASSWORD}`" if ENV_EMAIL else "❌ Not Set"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="view_saved_details")]])
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown", reply_markup=kb)

        # ── SET CREDENTIALS ────────────────────
        elif data.startswith("set_cred_"):
            slot = data.split("_")[2]
            context.user_data.update({"action": "ask_cred_email", "cred_slot": slot})
            await del_msg()
            await context.bot.send_message(chat_id=user_id,
                                           text=f"📧 Send email for `{slot.upper()}`:",
                                           parse_mode="Markdown", reply_markup=cancel_keyboard())

        # ── ADD COOKIE ─────────────────────────
        elif data.startswith("add_cookie_"):
            slot = data.split("_")[-1]
            context.user_data.update({"action": "ask_cookie_name", "cookie_slot": slot})
            await del_msg()
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🍪 Send cookie *Name* (e.g. remember_web_...) for `{slot.title()}`:",
                parse_mode="Markdown", reply_markup=cancel_keyboard())

        # ── TOGGLE DEBUG ───────────────────────
        elif data == "toggle_debug":
            save_debug_mode(not debug_mode)
            status = "🟢 ON — Debug logs show in Termux" if debug_mode else "🔴 OFF — Debug logs hidden"
            await del_msg()
            await context.bot.send_message(chat_id=user_id,
                                           text=f"🔍 *Debug Mode: {status}*",
                                           parse_mode="Markdown", reply_markup=admin_keyboard())

        # ── VIEW SOURCE CODE ───────────────────
        elif data == "view_source":
            await del_msg()
            work_dir = os.path.expanduser("~")
            IMPORTANT = {".env","debug_mode.json","saved_cookies.json","saved_creds.json",
                         "saved_passcode.json","users.json","last_state.json",
                         "alert.py","trans.py","bot.py","main.py"}
            try:
                all_f   = [f for f in os.listdir(work_dir) if os.path.isfile(os.path.join(work_dir, f))]
                files   = sorted([f for f in all_f if f in IMPORTANT or f.endswith(".py")
                                  or (f.endswith(".json") and not f.startswith("."))])
                folders = sorted([f for f in os.listdir(work_dir)
                                  if os.path.isdir(os.path.join(work_dir, f)) and not f.startswith(".")])
            except:
                files, folders = [], []

            header = f"📁 *File Explorer*\n`{work_dir}`\n\n_Bot-related files only. Click to download._\n"
            if folders:
                header += "\n📂 " + "  📂 ".join(folders[:6])

            btns = []
            for fname in files:
                try:
                    size = os.path.getsize(os.path.join(work_dir, fname))
                    size_str = f"{size//1024}KB" if size > 1024 else f"{size}B"
                except:
                    size_str = "?"
                btns.append([InlineKeyboardButton(f"📄 {fname} ({size_str})", callback_data=f"dl_file_{fname}")])
            btns.append([InlineKeyboardButton("🔙 BACK TO SAVED DATA", callback_data="view_saved_details")])
            await context.bot.send_message(chat_id=user_id, text=header,
                                           parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

        # ── DOWNLOAD FILE ──────────────────────
        elif data.startswith("dl_file_"):
            fname = data[len("dl_file_"):]
            await del_msg()
            try:
                await send_file_to_user(context.bot, user_id, fname)
            except Exception as e:
                await context.bot.send_message(chat_id=user_id,
                                               text=f"❌ Error: {str(e)[:60]}",
                                               reply_markup=admin_keyboard())

        # ── RESET GUARDS ───────────────────────
        elif data == "confirm_reset_creds":
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("YES DELETE", callback_data="reset_creds"),
                InlineKeyboardButton("❌ NO CANCEL",  callback_data="cancel_action"),
            ]])
            await del_msg()
            await context.bot.send_message(chat_id=user_id,
                                           text="⚠️ *Delete all saved Logins?*",
                                           parse_mode="Markdown", reply_markup=kb)

        elif data == "confirm_reset_cookies":
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("YES DELETE", callback_data="reset_cookies"),
                InlineKeyboardButton("❌ NO CANCEL",  callback_data="cancel_action"),
            ]])
            await del_msg()
            await context.bot.send_message(chat_id=user_id,
                                           text="⚠️ *Delete all saved Cookies?*",
                                           parse_mode="Markdown", reply_markup=kb)

        elif data == "reset_cookies":
            if os.path.exists(COOKIES_FILE): os.remove(COOKIES_FILE)
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="🗑 Cookies deleted.",
                                           reply_markup=admin_keyboard())

        elif data == "reset_creds":
            if os.path.exists(CREDS_FILE): os.remove(CREDS_FILE)
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="🗑 Logins deleted.",
                                           reply_markup=admin_keyboard())

        # ── BROADCAST ──────────────────────────
        elif data == "admin_broadcast":
            context.user_data["action"] = "broadcast"
            await del_msg()
            await context.bot.send_message(chat_id=user_id,
                                           text="📢 Type your broadcast message:",
                                           reply_markup=cancel_keyboard())

        # ── MESSAGE USER ───────────────────────
        elif data == "admin_message":
            users = [u for u in get_all_users() if u.get("id") != ADMIN_ID]
            await del_msg()
            if not users:
                return await context.bot.send_message(chat_id=user_id,
                                                      text="👥 No users registered.",
                                                      reply_markup=admin_keyboard())
            btns = []
            for i in range(0, len(users), 2):
                row = [InlineKeyboardButton(
                    f"💬 {users[i].get('name','?')[:8]}", callback_data=f"msguser_{users[i].get('id')}")]
                if i+1 < len(users):
                    row.append(InlineKeyboardButton(
                        f"💬 {users[i+1].get('name','?')[:8]}", callback_data=f"msguser_{users[i+1].get('id')}"))
                btns.append(row)
            btns.append([InlineKeyboardButton("❌ CANCEL", callback_data="cancel_action")])
            await context.bot.send_message(chat_id=user_id, text="💬 *Select user:*",
                                           parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

        elif data.startswith("msguser_"):
            context.user_data.update({"msg_uid": int(data.split("_")[1]), "action": "msg_text"})
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="✏️ Type your message:",
                                           reply_markup=cancel_keyboard())

        # ── CANCEL ─────────────────────────────
        elif data == "cancel_action":
            context.user_data.clear()
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="❌ Action cancelled.",
                                           reply_markup=admin_keyboard())

        # ── USERS LIST ─────────────────────────
        elif data == "admin_users":
            users = [u for u in get_all_users() if u.get("id") != ADMIN_ID]
            await del_msg()
            if not users:
                return await context.bot.send_message(chat_id=user_id,
                                                      text="👥 No users yet.", reply_markup=admin_keyboard())
            lines = [f"👥 *USERS ({len(users)})*\n"]
            btns  = []
            for u in users:
                uid, name, status = u.get("id"), u.get("name","?"), u.get("status")
                expiry, free      = u.get("expiry"), u.get("free_alerts", 0)
                if status == "approved" and expiry:
                    s = f"✅ {(datetime.fromisoformat(expiry)-datetime.now()).days}d"
                elif status == "approved": s = f"✅ Free({free})"
                elif status == "pending":  s = "⏳"
                elif status == "expired":  s = "❌Exp"
                else:                      s = "🔴Rej"
                lines.append(f"• *{name}* — {s}")
                if status == "pending":
                    btns.append([InlineKeyboardButton(f"✅ {name[:5]} 2D", callback_data=f"approve_{uid}_2day"),
                                 InlineKeyboardButton(f"✅ {name[:5]} 30D", callback_data=f"approve_{uid}_30day")])
                    btns.append([InlineKeyboardButton(f"❌ REJECT {name[:5]}", callback_data=f"reject_{uid}")])
                else:
                    btns.append([InlineKeyboardButton(f"🗑 REMOVE {name[:5]}", callback_data=f"remove_{uid}")])
            btns.append([InlineKeyboardButton("🔙 BACK", callback_data="back_admin")])
            await context.bot.send_message(chat_id=user_id, text="\n".join(lines),
                                           parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

        elif data.startswith("approve_"):
            parts = data.split("_")
            uid, plan = int(parts[1]), parts[2]
            days = 2 if plan == "2day" else 30
            update_user(uid, {"status": "approved",
                              "expiry": (datetime.now()+timedelta(days=days)).isoformat(),
                              "plan": plan})
            try: await context.bot.send_message(chat_id=uid,
                                                text=f"✅ *Approved for {days} days!*",
                                                parse_mode="Markdown")
            except: pass
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="✅ Approved.",
                                           reply_markup=admin_keyboard())

        elif data.startswith("reject_"):
            uid = int(data.split("_")[1])
            update_user(uid, {"status": "rejected"})
            try: await context.bot.send_message(chat_id=uid,
                                                text="❌ *Your request was rejected.*",
                                                parse_mode="Markdown")
            except: pass
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="❌ Rejected.",
                                           reply_markup=admin_keyboard())

        elif data.startswith("remove_"):
            uid   = str(data.split("_")[1])
            users = load_users()
            if uid in users: del users[uid]
            save_users(users)
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="🗑 Removed.",
                                           reply_markup=admin_keyboard())

        elif data == "back_admin":
            context.user_data.clear()
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text=build_admin_status(),
                                           parse_mode="Markdown", reply_markup=admin_keyboard())

    # ════════════ USERS ════════════
    else:
        if data == "user_status":
            u = get_user(user_id)
            status, expiry, free, alerts = (u.get("status","pending"), u.get("expiry"),
                                            u.get("free_alerts",0), u.get("alerts_sent",0))
            if status == "approved" and expiry:
                s = f"✅ Active ({(datetime.fromisoformat(expiry)-datetime.now()).days}d left)"
            elif status == "approved": s = f"✅ Free ({free} left)"
            elif status == "expired":  s = "❌ Expired"
            else:                      s = f"⏳ Pending ({free} free)"
            await del_msg()
            await context.bot.send_message(chat_id=user_id,
                                           text=f"👤 *YOUR STATUS*\n\nStatus : {s}\nAlerts Received: {alerts}",
                                           parse_mode="Markdown", reply_markup=user_keyboard())

        elif data == "user_subscribe":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("2 Days (₹6)", callback_data="sub_2day"),
                 InlineKeyboardButton("30 Days (₹100)", callback_data="sub_30day")],
                [InlineKeyboardButton("❌ CANCEL", callback_data="cancel_action")],
            ])
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="💳 *Choose a Plan*",
                                           parse_mode="Markdown", reply_markup=kb)

        elif data.startswith("sub_"):
            plan = data.split("_")[1]
            context.user_data.update({"plan": plan, "action": "wait_for_photo"})
            await del_msg()
            await context.bot.send_message(
                chat_id=user_id,
                text=f"💳 *Plan Selected*\n\nSend payment screenshot.\nUPI: `{UPI_ID}`",
                parse_mode="Markdown", reply_markup=cancel_keyboard())

        elif data == "user_help":
            await del_msg()
            await context.bot.send_message(
                chat_id=user_id,
                text=("❓ *HELP & INFORMATION*\n\n"
                      "🎁 *Free Alerts:* 5 FREE alerts when you start!\n\n"
                      "💳 *Subscriptions:*\n• ₹6 for 2 Days\n• ₹100 for 30 Days\n\n"
                      "_Subscribe via 'Buy a Subscription', upload payment screenshot._"),
                parse_mode="Markdown", reply_markup=user_keyboard())

        elif data == "cancel_action":
            context.user_data.clear()
            await del_msg()
            await context.bot.send_message(chat_id=user_id, text="❌ Cancelled.",
                                           reply_markup=user_keyboard())

# ── Photo Handler ────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("action") == "wait_for_photo":
        plan = context.user_data.pop("plan", "2day")
        context.user_data.clear()
        cap = (f"💳 *Payment Request*\n"
               f"User : {update.effective_user.full_name}\n"
               f"ID   : `{update.effective_user.id}`\n"
               f"Plan : {plan}")
        await context.bot.send_photo(
            chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id,
            caption=cap, parse_mode="Markdown",
            reply_markup=approve_keyboard(update.effective_user.id, plan))
        await update.message.reply_text("✅ Screenshot sent to admin for approval!",
                                        reply_markup=user_keyboard())

# ── Text Handler ─────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_logged_in
    user_id = update.effective_user.id
    text    = update.message.text.strip()
    action  = context.user_data.get("action")

    if user_id == ADMIN_ID:

        if action == "set_passcode":
            if len(text) == 6 and text.isdigit():
                context.user_data.update({"new_passcode": text, "action": "confirm_passcode"})
                await update.message.reply_text("🔐 Re-enter PIN to confirm:")
            else:
                await update.message.reply_text("❌ Must be 6 digits. Try again:")
            return

        elif action == "confirm_passcode":
            if text == context.user_data.get("new_passcode"):
                save_passcode_file(text)
                context.user_data.clear()
                context.user_data["restricted_auth"] = True
                await update.message.reply_text("✅ *PIN Set!*", parse_mode="Markdown")
                await context.bot.send_message(chat_id=user_id, text=build_admin_status(),
                                               parse_mode="Markdown", reply_markup=admin_keyboard())
            else:
                context.user_data.update({"action": "set_passcode"})
                context.user_data.pop("new_passcode", None)
                await update.message.reply_text("❌ PINs don't match. Enter new PIN:")
            return

        elif action == "restricted_login":
            if text == load_passcode_file():
                context.user_data["restricted_auth"] = True
                pending = context.user_data.pop("pending_action", None)
                context.user_data["action"] = None
                await update.message.reply_text("✅ *Access granted.*", parse_mode="Markdown")
                if pending:
                    fake_cb = type("FakeCB", (), {
                        "from_user": type("U", (), {"id": user_id}),
                        "data": pending,
                        "answer": lambda self: None,
                        "message": type("M", (), {"delete": lambda self: None})()
                    })()
                    fake_update = type("FakeUpdate", (), {
                        "callback_query": fake_cb, "update_id": 0, "message": None
                    })()
                    await button_callback(fake_update, context)
            else:
                await update.message.reply_text("❌ Wrong PIN. Try again:")
            return

        elif action == "recover_passcode":
            if text == RECOVERY_KEY:
                context.user_data.clear()
                context.user_data.update({"passcode_setup": True, "action": "set_passcode",
                                          "restricted_auth": True})
                await update.message.reply_text("✅ *Key accepted!* Enter new 6-digit PIN:",
                                                parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Wrong key. Try again:")
            return

        elif action == "broadcast":
            context.user_data.clear()
            sent = 0
            for u in get_active_users():
                if u.get("id") == ADMIN_ID: continue
                try:
                    await context.bot.send_message(chat_id=u["id"],
                                                   text=f"📢 *Broadcast*\n\n{text}",
                                                   parse_mode="Markdown")
                    sent += 1
                    await asyncio.sleep(0.3)
                except: pass
            await update.message.reply_text(f"✅ Sent to {sent} users.",
                                            reply_markup=admin_keyboard())
            return

        elif action == "msg_text":
            uid = context.user_data.pop("msg_uid", None)
            context.user_data.clear()
            if uid:
                try:
                    await context.bot.send_message(chat_id=uid,
                                                   text=f"💬 *Message from Admin*\n\n{text}",
                                                   parse_mode="Markdown")
                    await update.message.reply_text("✅ Message sent!", reply_markup=admin_keyboard())
                except:
                    await update.message.reply_text("❌ Failed.", reply_markup=admin_keyboard())
            return

        elif action == "ask_cookie_name":
            context.user_data.update({"c_name": text, "action": "ask_cookie_value"})
            await update.message.reply_text("🍪 Now send cookie *Value*:",
                                            parse_mode="Markdown", reply_markup=cancel_keyboard())
            return

        elif action == "ask_cookie_value":
            context.user_data.update({"c_value": text, "action": "ask_xsrf_value"})
            await update.message.reply_text("🍪 Now send *XSRF-TOKEN* (or 'skip'):",
                                            parse_mode="Markdown", reply_markup=cancel_keyboard())
            return

        elif action == "ask_xsrf_value":
            c_name = context.user_data.pop("c_name", "")
            c_val  = context.user_data.pop("c_value", "")
            slot   = context.user_data.pop("cookie_slot", "admin")
            context.user_data.clear()
            save_cookies_file(slot, c_name, c_val, text)
            await update.message.reply_text(f"✅ {slot.upper()} Cookies saved!\n\n_Go to 'Start Engine' to use it._",
                                            parse_mode="Markdown", reply_markup=admin_keyboard())
            return

        elif action == "ask_cred_email":
            context.user_data.update({"email": text, "action": "ask_cred_pass"})
            await update.message.reply_text("🔒 Now send your password:",
                                            parse_mode="Markdown", reply_markup=cancel_keyboard())
            return

        elif action == "ask_cred_pass":
            email = context.user_data.pop("email", "")
            slot  = context.user_data.pop("cred_slot", "login1")
            context.user_data.clear()
            save_creds_file(slot, email, text)
            await update.message.reply_text(f"✅ {slot.upper()} credentials saved!\n\n_Go to 'Start Engine' to use it._",
                                            parse_mode="Markdown", reply_markup=admin_keyboard())
            return

        if text.lower() in ["hi", "hello", "hey"]:
            if not is_logged_in:
                return await update.message.reply_text("❌ Bot is offline.", reply_markup=admin_keyboard())
            t_log("👤 Admin manually checked levels.", is_debug=True)
            levels = await asyncio.to_thread(fetch_work_levels, True)
            await update.message.reply_text(
                await asyncio.to_thread(build_admin_hi_message, levels, True),
                parse_mode="HTML", disable_web_page_preview=True)
            return

        await update.message.reply_text("Use the menu buttons.", reply_markup=admin_keyboard())

# ── Startup & Post Init ──────────────────────
async def send_startup_msg(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text="🤖 *ALERT BOT Online!*\n\nPress 🚂 *START BOT ENGINE* to begin.\n\n_(If a huge START button appears, press it first!)_",
            parse_mode="Markdown", reply_markup=admin_keyboard())
    except Exception:
        pass

async def post_init(application):
    await application.bot.set_my_commands([BotCommand("start", "Main Menu")])
    if ADMIN_ID:
        try:
            await application.bot.set_my_commands(
                commands=[BotCommand("start", "Admin Panel"),
                          BotCommand("reset_pin", "Reset your 6-digit PIN")],
                scope=BotCommandScopeChat(chat_id=ADMIN_ID))
        except Exception:
            pass

# ── Main ─────────────────────────────────────
def main():
    t_head("ALERTBOT STARTING")
    t_sub(f"Scan every   : {CHECK_MIN}-{CHECK_MAX} mins")
    t_sub(f"Page wait    : {SURF_DELAY_MIN}-{SURF_DELAY_MAX}s")
    t_sub(f"Extra browse : {SURF_PAGES_MIN}-{SURF_PAGES_MAX} pages/scan")
    t_sub(f"Debug mode   : {'ON' if debug_mode else 'OFF'}")
    t_sub(f"Quick link   : {QUICK_LOGIN_URL}")
    t_sub(f"Link source  : {QUICK_URL_SOURCE}")
    t_log("✅ Online and listening for Telegram")
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("connect",   cmd_connect))
    app.add_handler(CommandHandler("cancel",    cmd_cancel))
    app.add_handler(CommandHandler("reset_pin", cmd_reset_pin))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(check_and_alert, interval=30, first=5)
    app.job_queue.run_once(send_startup_msg, 3)
    try:
        app.run_polling(drop_pending_updates=True, stop_signals=None)
    except KeyboardInterrupt:
        t_log("🛑 Stopped by user.")
    except Exception:
        pass

if __name__ == "__main__":
    main()
