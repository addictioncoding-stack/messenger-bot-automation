"""
=====================================================
  Facebook Messenger Bot + Admin Panel
  Vercel Serverless Entry Point
=====================================================
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from functools import wraps
from replies import KEYWORD_REPLIES, DEFAULT_REPLY

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret_key")

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN      = os.environ.get("VERIFY_TOKEN")
ADMIN_PASSWORD    = os.environ.get("ADMIN_PASSWORD", "admin1234")

# Bot state (in-memory — Vercel এ প্রতি request এ reset হতে পারে)
bot_state = {
    "active":          True,
    "total_messages":  0,
    "replied":         0,
}


# ── Auth Decorator ──
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ── Admin Routes ──
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("login.html", error="ভুল পাসওয়ার্ড!")
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
    return redirect(url_for("admin_dashboard", msg=f"Bot {status} করা হয়েছে!"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ── Webhook ──
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


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
                    if not bot_state["active"]:
                        continue
                    if "text" in message:
                        reply_text = get_auto_reply(message["text"])
                        send_message(sender_id, reply_text)
                        bot_state["replied"] += 1
                    elif "attachments" in message:
                        send_message(sender_id, "ধন্যবাদ! কোনো প্রশ্ন থাকলে text এ লিখুন।")
                        bot_state["replied"] += 1
    return "OK", 200


def get_auto_reply(user_message: str) -> str:
    message_lower = user_message.lower().strip()
    for keyword, reply in KEYWORD_REPLIES.items():
        if keyword.lower() in message_lower:
            return reply
    return DEFAULT_REPLY


def send_message(recipient_id: str, message_text: str):
    url     = "https://graph.facebook.com/v21.0/me/messages"
    payload = {
        "recipient":      {"id": recipient_id},
        "message":        {"text": message_text},
        "messaging_type": "RESPONSE",
    }
    try:
        requests.post(url, json=payload, params={"access_token": PAGE_ACCESS_TOKEN})
    except Exception as e:
        print(f"[ERROR] {e}")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "bot":    "Messenger Auto-Reply Bot",
        "active": bot_state["active"],
        "admin":  "/admin",
    })
