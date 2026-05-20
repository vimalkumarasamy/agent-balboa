"""
Find your Telegram chat ID after creating your bot.

Steps:
1. Open Telegram → search @BotFather → /newbot → follow prompts
2. Copy the token → add to .env as TELEGRAM_BOT_TOKEN=...
3. Send any message to your new bot (e.g. "hi")
4. Run: python scripts/telegram_setup.py
5. Copy the chat_id → add to .env as TELEGRAM_CHAT_ID=...
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tools.notifications.telegram import get_updates

updates = get_updates()
if not updates:
    print("No messages found. Send any message to your bot first, then re-run this script.")
    sys.exit(1)

for u in updates:
    msg = u.get("message") or u.get("channel_post", {})
    chat = msg.get("chat", {})
    print(f"chat_id : {chat.get('id')}")
    print(f"name    : {chat.get('first_name', '')} {chat.get('last_name', '')}".strip())
    print(f"type    : {chat.get('type')}")
    print()
    print("Add to .env:  TELEGRAM_CHAT_ID=" + str(chat.get('id', '')))
    break
