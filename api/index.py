"""
=====================================================
  Facebook Messenger Auto-Reply Bot
  Vercel Serverless Deployment Entry Point
=====================================================
"""

import os
import sys

# replies.py কে import করার জন্য parent directory add করো
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import requests
from flask import Flask, request, jsonify
from replies import KEYWORD_REPLIES, DEFAULT_REPLY

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")


# ====================================================
# WEBHOOK VERIFICATION
# ====================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[OK] Webhook verified!")
        return challenge, 200
    else:
        print("[ERROR] Webhook verification failed!")
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

                    if "text" in message:
                        user_text = message["text"]
                        print(f"[MSG] From {sender_id}: {user_text}")
                        reply_text = get_auto_reply(user_text)
                        send_message(sender_id, reply_text)

                    elif "attachments" in message:
                        send_message(sender_id, "ধন্যবাদ আপনার মেসেজের জন্য! কোনো প্রশ্ন থাকলে text এ লিখুন।")

    return "OK", 200


# ====================================================
# AUTO-REPLY LOGIC
# ====================================================
def get_auto_reply(user_message: str) -> str:
    message_lower = user_message.lower().strip()
    for keyword, reply in KEYWORD_REPLIES.items():
        if keyword.lower() in message_lower:
            return reply
    return DEFAULT_REPLY


# ====================================================
# SEND MESSAGE
# ====================================================
def send_message(recipient_id: str, message_text: str):
    url = "https://graph.facebook.com/v21.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE"
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    try:
        response = requests.post(url, json=payload, params=params)
        if response.status_code == 200:
            print(f"[OK] Message sent to {recipient_id}")
        else:
            print(f"[ERROR] {response.json()}")
    except Exception as e:
        print(f"[ERROR] {e}")


# ====================================================
# HOME ROUTE
# ====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "bot": "Facebook Messenger Auto-Reply Bot",
        "message": "Bot is active! ✅"
    })
