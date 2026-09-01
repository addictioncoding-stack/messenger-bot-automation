"""
=====================================================
  Facebook Messenger Auto-Reply Bot - Main App
  ফেসবুক মেসেঞ্জার অটো-রিপ্লাই বট - মেইন অ্যাপ
=====================================================
"""

import os
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from replies import KEYWORD_REPLIES, DEFAULT_REPLY

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Credentials
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")


# ====================================================
# WEBHOOK VERIFICATION (Facebook এর সাথে connect করতে)
# ====================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Facebook webhook verification"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return challenge, 200
    else:
        print("❌ Webhook verification failed!")
        return "Verification failed", 403


# ====================================================
# RECEIVE MESSAGES (Customer এর মেসেজ receive করা)
# ====================================================
@app.route("/webhook", methods=["POST"])
def receive_message():
    """Receive and process incoming messages"""
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]

                # Text message handling
                if "message" in event:
                    message = event["message"]

                    # Ignore echo messages (bot নিজের মেসেজে reply না করার জন্য)
                    if message.get("is_echo"):
                        continue

                    # Text message
                    if "text" in message:
                        user_text = message["text"]
                        print(f"[MSG] Message received from {sender_id}: {user_text}")

                        # Reply generate করো
                        reply_text = get_auto_reply(user_text)

                        # Reply পাঠাও
                        send_message(sender_id, reply_text)

                    # Sticker / attachment
                    elif "attachments" in message:
                        send_message(sender_id, "ধন্যবাদ আপনার মেসেজের জন্য! কোনো প্রশ্ন থাকলে text এ লিখুন।")

    return "OK", 200


# ====================================================
# AUTO-REPLY LOGIC (কোন মেসেজে কোন উত্তর দেবে)
# ====================================================
def get_auto_reply(user_message: str) -> str:
    """
    User এর মেসেজ দেখে সঠিক reply বের করো।
    Keyword matching করে উত্তর দেয়।
    """
    # Lowercase এ convert করো (case-insensitive matching)
    message_lower = user_message.lower().strip()

    # Keyword check করো
    for keyword, reply in KEYWORD_REPLIES.items():
        if keyword.lower() in message_lower:
            print(f"✅ Keyword matched: '{keyword}'")
            return reply

    # কোনো keyword না মিললে default reply
    print(f"ℹ️ No keyword matched, sending default reply")
    return DEFAULT_REPLY


# ====================================================
# SEND MESSAGE (Facebook API দিয়ে reply পাঠানো)
# ====================================================
def send_message(recipient_id: str, message_text: str):
    """Facebook Messenger API দিয়ে message পাঠাও"""

    url = f"https://graph.facebook.com/v21.0/me/messages"

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE"
    }

    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }

    try:
        response = requests.post(url, headers=headers, json=payload, params=params)
        result = response.json()

        if response.status_code == 200:
            print(f"✅ Message sent to {recipient_id}")
        else:
            print(f"❌ Error sending message: {result}")

    except Exception as e:
        print(f"❌ Exception: {e}")


# ====================================================
# SEND QUICK REPLIES (Button-style replies)
# ====================================================
def send_quick_replies(recipient_id: str, text: str, buttons: list):
    """
    Quick reply buttons পাঠাও।
    Example:
        buttons = ["দাম জানতে", "অর্ডার করতে", "যোগাযোগ"]
    """
    url = f"https://graph.facebook.com/v21.0/me/messages"

    quick_replies = [
        {
            "content_type": "text",
            "title": btn,
            "payload": btn.upper().replace(" ", "_")
        }
        for btn in buttons
    ]

    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": quick_replies
        }
    }

    params = {"access_token": PAGE_ACCESS_TOKEN}

    try:
        response = requests.post(url, json=payload, params=params)
        if response.status_code == 200:
            print(f"✅ Quick replies sent to {recipient_id}")
        else:
            print(f"❌ Error: {response.json()}")
    except Exception as e:
        print(f"❌ Exception: {e}")


# ====================================================
# HOME ROUTE (Server চলছে কিনা দেখার জন্য)
# ====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "bot": "Facebook Messenger Auto-Reply Bot",
        "message": "Bot is active and ready! ✅"
    })


# ====================================================
# START SERVER
# ====================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print("=" * 50)
    print("  [BOT] Messenger Bot Starting...")
    print(f"  [SERVER] http://localhost:{port}")
    print(f"  [WEBHOOK] http://localhost:{port}/webhook")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=True)
