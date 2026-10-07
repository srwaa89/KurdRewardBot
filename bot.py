import os
import time
import json
import sqlite3
import urllib.request
import urllib.parse

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB = "kurdreward.db"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# =========================
# DATABASE
# =========================

db = sqlite3.connect(DB, check_same_thread=False)
db.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    points INTEGER DEFAULT 0,
    referrer INTEGER DEFAULT 0,
    joined_at INTEGER
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    points INTEGER,
    method TEXT,
    account TEXT,
    status TEXT DEFAULT 'pending',
    created_at INTEGER
)
""")

db.commit()


# =========================
# TELEGRAM API
# =========================

def api(method, data=None):
    url = f"{API}/{method}"

    if data is None:
        data = {}

    encoded = urllib.parse.urlencode(data).encode()

    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode())


def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)

    return api("sendMessage", data)


def answer_callback(callback_id):
    return api("answerCallbackQuery", {
        "callback_query_id": callback_id
    })


# =========================
# MENU
# =========================

def main_menu():
    return {
        "keyboard": [
            [
                {"text": "🎯 Tasks"},
                {"text": "👥 Referral"}
            ],
            [
                {"text": "📊 Points"},
                {"text": "💰 Wallet"}
            ],
            [
                {"text": "💵 Withdraw"},
                {"text": "ℹ️ Help"}
            ]
        ],
        "resize_keyboard": True
    }


# =========================
# USER
# =========================

def get_user(user_id):
    return db.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()


def create_user(user, referrer=0):

    existing = get_user(user["id"])

    if existing:
        return existing

    points = 0

    if referrer and referrer != user["id"]:
        points = 20

    db.execute("""
        INSERT INTO users
        (id, username, first_name, points, referrer, joined_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user["id"],
        user.get("username", ""),
        user.get("first_name", ""),
        points,
        referrer,
        int(time.time())
    ))

    # Referral reward
    if referrer and referrer != user["id"]:
        db.execute("""
            UPDATE users
            SET points = points + 50
            WHERE id=?
        """, (referrer,))

    db.commit()

    return get_user(user["id"])


def add_points(user_id, amount):
    db.execute("""
        UPDATE users
        SET points = points + ?
        WHERE id=?
    """, (amount, user_id))

    db.commit()


# =========================
# START
# =========================

def handle_start(message):

    user = message["from"]
    args = message.get("text", "").split()

    referrer = 0

    if len(args) > 1:
        code = args[1]

        if code.startswith("ref_"):
            try:
                referrer = int(code.replace("ref_", ""))
            except:
                referrer = 0

    is_new = get_user(user["id"]) is None

    create_user(user, referrer)

    if is_new:
        text = (
            "🎉 بەخێربێیت بۆ KurdRewardBot!\n\n"
            "لە ڕێگەی Tasks و Referral دەتوانیت خاڵ کۆبکەیتەوە.\n\n"
            "🎁 بۆ دەستپێکردن Menu ـی خوارەوە بەکاربهێنە."
        )
    else:
        text = (
            "👋 بەخێربێیتەوە!\n\n"
            "لە Menu ـەکەوە بەشەکەت هەڵبژێرە."
        )

    send_message(
        message["chat"]["id"],
        text,
        main_menu()
    )


# =========================
# TASKS
# =========================

def show_tasks(chat_id, user_id):

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🎁 Daily Bonus +10",
                    "callback_data": "daily_bonus"
                }
            ]
        ]
    }

    text = (
        "🎯 Tasks\n\n"
        "هەموو ڕۆژێک دەتوانیت Daily Bonus وەربگریت.\n\n"
        "لە داهاتوودا دەتوانین Task ـی ڕاستەقینەی "
        "ڕیکلام و Affiliate ـیش زیاد بکەین."
    )

    send_message(chat_id, text, keyboard)


def daily_bonus(chat_id, user_id):

    row = db.execute(
        "SELECT joined_at FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    # Simple daily limitation using a separate table would be better.
    # For this starter version, reward is controlled through memory.
    today = int(time.time()) // 86400

    key = f"{user_id}_{today}"

    if key in daily_claims:
        send_message(
            chat_id,
            "⏳ ئەمڕۆ Bonus ـەکەت وەرگرتووە."
        )
        return

    daily_claims.add(key)

    add_points(user_id, 10)

    send_message(
        chat_id,
        "🎉 پیرۆزە!\n\n"
        "➕ 10 خاڵ زیادکرا.\n\n"
        "📊 خاڵەکانت لە Points ببینە."
    )


# =========================
# REFERRAL
# =========================

def show_referral(chat_id, user_id):

    me = api("getMe")
    bot_username = me["result"]["username"]

    link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    count = db.execute(
        "SELECT COUNT(*) FROM users WHERE referrer=?",
        (user_id,)
    ).fetchone()[0]

    text = (
        "👥 Referral\n\n"
        f"👤 ژمارەی بانگهێشتکراوەکان: {count}\n"
        "🎁 پاداشتی هەر Referral: 50 خاڵ\n\n"
        "🔗 لینکی تایبەت بە تۆ:\n"
        f"{link}\n\n"
        "لینکەکە بۆ هاوڕێکانت بنێرە."
    )

    send_message(chat_id, text)


# =========================
# POINTS
# =========================

def show_points(chat_id, user_id):

    row = get_user(user_id)
    points = row[3] if row else 0

    send_message(
        chat_id,
        f"📊 خاڵەکانت:\n\n"
        f"⭐ {points} Points"
    )


# =========================
# WALLET
# =========================

def show_wallet(chat_id, user_id):

    row = get_user(user_id)
    points = row[3] if row else 0

    # Example conversion:
    # 1000 points = $1
    dollars = points / 1000

    text = (
        "💰 Wallet\n\n"
        f"⭐ Points: {points}\n"
        f"💵 Estimated value: ${dollars:.2f}\n\n"
        "⚠️ ئەم ژمارەیە تەنها کۆی پاداشتەکانە؛ "
        "پارەدان تەنها کاتێک ئەنجام دەدرێت کە سیستەمەکە "
        "داهاتی ڕاستەقینەی هەبێت."
    )

    send_message(chat_id, text)


# =========================
# WITHDRAW
# =========================

def show_withdraw(chat_id, user_id):

    row = get_user(user_id)
    points = row[3] if row else 0

    minimum = 1000

    if points < minimum:
        send_message(
            chat_id,
            "💵 Withdraw\n\n"
            f"کەمترین سنوور: {minimum} خاڵ\n"
            f"خاڵەکانی تۆ: {points}\n\n"
            f"هێشتا {minimum - points} خاڵت کەمە."
        )
        return

    text = (
        "💵 Withdraw\n\n"
        f"⭐ خاڵەکانت: {points}\n\n"
        "بۆ داواکاری پارەدان:\n"
        "نمونە:\n"
        "/withdraw USDT TRC20 YOUR_ADDRESS"
    )

    send_message(chat_id, text)


def process_withdraw(message):

    user_id = message["from"]["id"]
    parts = message.get("text", "").split()

    if len(parts) < 3:
        send_message(
            message["chat"]["id"],
            "❌ شێوازی دروست:\n\n"
            "/withdraw USDT TRC20 YOUR_ADDRESS"
        )
        return

    row = get_user(user_id)
    points = row[3] if row else 0

    if points < 1000:
        send_message(
            message["chat"]["id"],
            "❌ خاڵەکانت بۆ Withdraw بەس نییە."
        )
        return

    method = parts[1]
    account = parts[2]

    db.execute("""
        INSERT INTO withdrawals
        (user_id, points, method, account, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (
        user_id,
        points,
        method,
        account,
        int(time.time())
    ))

    db.commit()

    send_message(
        message["chat"]["id"],
        "✅ داواکاری Withdraw ـەکەت تۆمارکرا.\n\n"
        "⏳ دۆخ: Pending\n"
        "پاش پشکنینی Admin ئەنجام دەدرێت."
    )

    if ADMIN_ID:
        send_message(
            ADMIN_ID,
            "🔔 NEW WITHDRAWAL\n\n"
            f"User: {user_id}\n"
            f"Points: {points}\n"
            f"Method: {method}\n"
            f"Account: {account}"
        )


# =========================
# HELP
# =========================

def show_help(chat_id):

    send_message(
        chat_id,
        "ℹ️ KurdRewardBot\n\n"
        "🎯 Tasks — کار و Task ـەکان\n"
        "👥 Referral — بانگهێشتکردنی هاوڕێ\n"
        "📊 Points — خاڵەکانت\n"
        "💰 Wallet — ناوچەی دارایی\n"
        "💵 Withdraw — داواکاری پارەدان\n\n"
        "⚠️ هیچ پاداشتێک نابێت بەبێ داهاتی ڕاستەقینە "
        "وەک پارەی دڵنیابکراو پیشان بدرێت."
    )


# =========================
# MESSAGE HANDLER
# =========================

daily_claims = set()


def handle_message(message):

    text = message.get("text", "")
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]

    if text.startswith("/start"):
        handle_start(message)
        return

    if text.startswith("/withdraw"):
        process_withdraw(message)
        return

    create_user(message["from"])

    if text == "🎯 Tasks":
        show_tasks(chat_id, user_id)

    elif text == "👥 Referral":
        show_referral(chat_id, user_id)

    elif text == "📊 Points":
        show_points(chat_id, user_id)

    elif text == "💰 Wallet":
        show_wallet(chat_id, user_id)

    elif text == "💵 Withdraw":
        show_withdraw(chat_id, user_id)

    elif text == "ℹ️ Help":
        show_help(chat_id)

    else:
        send_message(
            chat_id,
            "لە Menu ـەکەوە هەڵبژێرە 👇",
            main_menu()
        )


# =========================
# CALLBACKS
# =========================

def handle_callback(query):

    callback_id = query["id"]
    data = query["data"]
    message = query["message"]

    chat_id = message["chat"]["id"]
    user_id = query["from"]["id"]

    answer_callback(callback_id)

    if data == "daily_bonus":
        daily_bonus(chat_id, user_id)


# =========================
# BOT COMMANDS
# =========================

def setup_bot():

    commands = [
        {"command": "start", "description": "Start KurdRewardBot"},
        {"command": "withdraw", "description": "Request withdrawal"}
    ]

    api("setMyCommands", {
        "commands": json.dumps(commands)
    })


# =========================
# MAIN LOOP
# =========================

def main():

    setup_bot()

    offset = 0

    print("KurdRewardBot is running...")

    while True:

        try:

            result = api("getUpdates", {
                "offset": offset,
                "timeout": 30
            })

            updates = result.get("result", [])

            for update in updates:

                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(update["message"])

                elif "callback_query" in update:
                    handle_callback(update["callback_query"])

        except Exception as e:

            print("ERROR:", e)

            time.sleep(5)


if __name__ == "__main__":
    main()
