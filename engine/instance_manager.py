# ═══════════════════════════════════════════════════════════════════════════════
# DUAL-BOT APP — INSTANCE MANAGER & SUPERVISOR
# ═══════════════════════════════════════════════════════════════════════════════

import os, json, asyncio
from engine.bot_core import BotCore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMPLATES_FILE = os.path.join(CONFIG_DIR, "templates.json")

class InstanceManager:
    def __init__(self):
        self.bots = {}
        self.init_instances()

    def init_instances(self):
        bot1_config = os.path.join(CONFIG_DIR, "bot1_env.txt")
        bot1_data   = os.path.join(DATA_DIR, "bot1")
        bot1 = BotCore("bot1", "Bot 1 (Alert Bot)", bot1_config, bot1_data, TEMPLATES_FILE, port=48291)

        bot2_config = os.path.join(CONFIG_DIR, "bot2_env.txt")
        bot2_data   = os.path.join(DATA_DIR, "bot2")
        bot2 = BotCore("bot2", "Bot 2 (Hybrid Bot)", bot2_config, bot2_data, TEMPLATES_FILE, port=48292)

        self.bots = {
            "bot1": bot1,
            "bot2": bot2
        }

    def get_bot(self, bot_id):
        return self.bots.get(bot_id)

    def get_all_status(self):
        return {
            bot_id: bot.get_status_data() for bot_id, bot in self.bots.items()
        }

    def get_logs(self, bot_id=None):
        if bot_id and bot_id in self.bots:
            return {bot_id: self.bots[bot_id].logs}
        return {b_id: b.logs for b_id, b in self.bots.items()}

    def get_env_raw(self, bot_id):
        cfg_file = os.path.join(CONFIG_DIR, f"{bot_id}_env.txt")
        if os.path.exists(cfg_file):
            with open(cfg_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        return ""

    def save_env_raw(self, bot_id, content):
        cfg_file = os.path.join(CONFIG_DIR, f"{bot_id}_env.txt")
        with open(cfg_file, "w", encoding="utf-8") as f:
            f.write(content)
        bot = self.get_bot(bot_id)
        if bot:
            bot.reload_config()
            bot.t_log("Configuration reloaded from .env")
        return True

    def get_env_parsed(self, bot_id):
        bot = self.get_bot(bot_id)
        if bot:
            return bot.env
        return {}

    def save_env_key_values(self, bot_id, kv_dict):
        cfg_file = os.path.join(CONFIG_DIR, f"{bot_id}_env.txt")
        # Read existing file comments and structure if present
        existing_lines = []
        if os.path.exists(cfg_file):
            with open(cfg_file, "r", encoding="utf-8", errors="ignore") as f:
                existing_lines = f.readlines()

        updated_keys = set()
        new_lines = []
        for line in existing_lines:
            raw = line.strip()
            if raw and not raw.startswith("#") and "=" in raw:
                k, _ = raw.split("=", 1)
                k = k.strip()
                if k in kv_dict:
                    new_lines.append(f"{k}={kv_dict[k]}\n")
                    updated_keys.add(k)
                    continue
            new_lines.append(line)

        # Append any brand new keys
        for k, v in kv_dict.items():
            if k not in updated_keys:
                new_lines.append(f"{k}={v}\n")

        with open(cfg_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        bot = self.get_bot(bot_id)
        if bot:
            bot.reload_config()
            bot.t_log("Updated .env variables saved and applied.")
        return True

    def get_templates(self):
        if os.path.exists(TEMPLATES_FILE):
            try:
                with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_templates(self, data):
        with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        for b in self.bots.values():
            b.t_log("Notification templates updated.")
        return True

    async def start_all(self):
        for b in self.bots.values():
            await b.start()

    async def stop_all(self):
        for b in self.bots.values():
            await b.stop()

instance_manager = InstanceManager()
