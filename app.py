"""
=====================================================
  Facebook Messenger Auto-Reply Bot + Admin Panel
=====================================================
"""

import os
import json
import requests
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from functools import wraps
from dotenv import load_dotenv
from replies import KEYWORD_REPLIES, DEFAULT_REPLY

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_secret_key")

# Credentials
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "admin1234")

# ====================================================
# BOT STATE (On/Off + Stats)
# ====================================================
bot_state = {
    "active": True,       # Bot on/off
    "total_messages": 0,  # মোট মেসেজ
    "replied": 0,         # Auto-reply দেওয়া হয়েছে
}


# ====================================================
# ADMIN AUTH DECORATOR
# ====================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ====================================================
# ADMIN ROUTES
# ====================================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("login.html", error="ভুল পাসওয়ার্ড! আবার চেষ্টা করুন।")
    return render_template("login.html", error=None)


@app.route("/admin")
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    stats = {
        "total":    bot_state["total_messages"],
        "replied":  bot_state["replied"],
        "keywords": len(KEYWORD_REPLIES),
    }
    return render_template(
        "admin.html",
        bot_active=bot_state["active"],
        stats=stats,
        keywords=KEYWORD_REPLIES,
        msg=request.args.get("msg"),
    )


@app.route("/admin/toggle", methods=["POST"])
@login_required
def admin_toggle():
    bot_state["active"] = not bot_state["active"]
    status = "চালু" if bot_state["active"] else "বন্ধ"
    print(f"[ADMIN] Bot toggled: {status}")
    return redirect(url_for("admin_dashboard", msg=f"Bot {status} করা হয়েছে!"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ====================================================
# WEBHOOK VERIFICATION
# ====================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[OK] Webhook verified!")
        return challenge, 200
    return "Verification failed", 403


# ====================================================
# RECEIVE MESSAGES
# ====================================================
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]

                if "message" in event:
                    message = event["message"]
                    if message.get("is_echo"):
                        continue

                    bot_state["total_messages"] += 1

                    # Bot বন্ধ থাকলে reply দেবে না
                    if not bot_state["active"]:
                        print(f"[BOT OFF] Message from {sender_id} ignored.")
                        continue

                    if "text" in message:
                        user_text = message["text"]
                        print(f"[MSG] From {sender_id}: {user_text}")
                        reply_text = get_auto_reply(user_text)
                        send_message(sender_id, reply_text)
                        bot_state["replied"] += 1

                    elif "attachments" in message:
                        send_message(
                            sender_id,
                            "ধন্যবাদ আপনার মেসেজের জন্য! কোনো প্রশ্ন থাকলে text এ লিখুন।"
                        )
                        bot_state["replied"] += 1

    return "OK", 200


# ====================================================
# AUTO-REPLY LOGIC
# ====================================================
def get_auto_reply(user_message: str) -> str:
    message_lower = user_message.lower().strip()
    for keyword, reply in KEYWORD_REPLIES.items():
        if keyword.lower() in message_lower:
            print(f"[MATCH] Keyword: '{keyword}'")
            return reply
    print("[DEFAULT] No keyword matched.")
    return DEFAULT_REPLY


# ====================================================
# SEND MESSAGE
# ====================================================
def send_message(recipient_id: str, message_text: str):
    url     = "https://graph.facebook.com/v21.0/me/messages"
    payload = {
        "recipient":      {"id": recipient_id},
        "message":        {"text": message_text},
        "messaging_type": "RESPONSE",
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    try:
        response = requests.post(url, json=payload, params=params)
        if response.status_code == 200:
            print(f"[OK] Sent to {recipient_id}")
        else:
            print(f"[ERROR] {response.json()}")
    except Exception as e:
        print(f"[ERROR] {e}")


# ====================================================
# HOME
# ====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status":  "running",
        "bot":     "Facebook Messenger Auto-Reply Bot",
        "active":  bot_state["active"],
        "admin":   "/admin",
    })


# ====================================================
# START
# ====================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print("=" * 50)
    print("  [BOT] Messenger Bot + Admin Panel")
    print(f"  [SERVER]  http://localhost:{port}")
    print(f"  [ADMIN]   http://localhost:{port}/admin")
    print(f"  [WEBHOOK] http://localhost:{port}/webhook")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=True)
