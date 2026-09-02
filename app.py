"""
=====================================================
  Bella Basket Jewelry — Hybrid AI Messenger Bot
  Keyword + Gemini AI + Admin Panel + Demo Chat
=====================================================
"""

import os, json, requests
from flask import (Flask, request, jsonify, render_template,
                   redirect, url_for, session)
from functools import wraps
from dotenv import load_dotenv
from order_manager import save_order, get_all_orders
from ai_handler import get_ai_reply_simple

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "bella_basket_2024")

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "admin1234")
BKASH_NUMBER      = "01937281260"

DATA_DIR     = os.path.join(os.path.dirname(__file__), "data")
REPLIES_FILE = os.path.join(DATA_DIR, "replies.json")
PRODUCTS_FILE= os.path.join(DATA_DIR, "products.json")

# ── Runtime State ──
bot_state    = {"active": True, "total": 0, "replied": 0}
user_sessions= {}          # {sender_id: {state, name, mobile, ...}}
user_product = {}          # {sender_id: last product interest}
chat_histories = {}        # {sender_id: [{role, parts}]}

IDLE="IDLE"; ASK_NAME="ASK_NAME"; ASK_MOBILE="ASK_MOBILE"
ASK_ADDRESS="ASK_ADDRESS"; ASK_PAYMENT="ASK_PAYMENT"


# ====================================================
# DATA HELPERS
# ====================================================

def load_replies():
    try:
        with open(REPLIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_replies(data):
    with open(REPLIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_products():
    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_products(data):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ====================================================
# HYBRID REPLY ENGINE
# ====================================================

PRODUCT_KEYWORDS = {
    "কাশ্মীরি চুড়ি (১ ডজন)": ["কাশ্মীরি","চুড়ি","বাংলস","১২","ডজন"],
    "কাশ্মীরি চুড়ি (২ ডজন)": ["২৪","দুই ডজন"],
    "বাটারফ্লাই ব্লিস জুয়েলারি সেট": ["বাটারফ্লাই"],
    "লাভ ব্লিস জুয়েলারি সেট": ["লাভ ব্লিস"],
    "স্নেক গোল্ড পায়েল": ["পায়েল","গোল্ড পায়েল","স্নেক"],
}
COLORS = ["মিক্সড","ব্ল্যাক","পেল হোয়াইট","রেড","পেস্তা গ্রিন",
          "ব্লু","পার্পল","পিংক","মিন্ট","ডার্ক অ্যাশ",
          "ডার্ক গ্রিন","ডার্ক পিংক","গোল্ডেন"]
ORDER_WORDS = ["অর্ডার করব","অর্ডার করতে চাই","নিতে চাই",
               "কিনতে চাই","কিনব","order করব","অর্ডার দিতে চাই","বুক"]

def detect_product(txt):
    tl = txt.lower()
    for p, kws in PRODUCT_KEYWORDS.items():
        if any(k.lower() in tl for k in kws):
            return p
    return None

def detect_color(txt):
    for c in COLORS:
        if c.lower() in txt.lower():
            return c
    return None

def is_order_intent(txt):
    return any(k.lower() in txt.lower() for k in ORDER_WORDS)

def is_cancel(txt):
    return any(k in txt.lower() for k in ["বাতিল","cancel","দরকার নেই","না থাক"])

def keyword_reply(text):
    replies = load_replies()
    tl = text.lower().strip()
    for kw, rep in replies.items():
        if kw.lower() in tl:
            return rep
    return None

def get_reply(sender_id, text):
    """
    Hybrid: keyword → order flow → AI
    """
    sd   = user_sessions.get(sender_id, {"state": IDLE})
    state= sd.get("state", IDLE)

    # Track product interest
    prod = detect_product(text)
    if prod:
        user_product[sender_id] = prod

    # ── Cancel ──
    if is_cancel(text) and state != IDLE:
        user_sessions.pop(sender_id, None)
        return "ঠিক আছে, অর্ডার বাতিল করা হয়েছে। আর কিছু জানতে চাইলে লিখুন! 😊"

    # ── Order Flow (priority over keywords) ──
    if state == ASK_NAME:
        sd["name"]  = text
        sd["state"] = ASK_MOBILE
        user_sessions[sender_id] = sd
        return f"ধন্যবাদ {text}! 😊\nআপনার মোবাইল নম্বরটি লিখুন:"

    if state == ASK_MOBILE:
        sd["mobile"] = text
        sd["state"]  = ASK_ADDRESS
        user_sessions[sender_id] = sd
        return "আপনার সম্পূর্ণ ঠিকানা লিখুন\n(গ্রাম/এলাকা, উপজেলা, জেলা সহ):"

    if state == ASK_ADDRESS:
        sd["address"] = text
        sd["state"]   = ASK_PAYMENT
        user_sessions[sender_id] = sd
        p_line = f"\nপণ্য: {sd.get('product','')}" if sd.get("product") else ""
        return (f"প্রায় শেষ! 🎉{p_line}\n\n"
                f"পেমেন্ট কিভাবে করবেন?\n"
                f"১. বিকাশ\n২. ক্যাশ অন ডেলিভারি\n\n"
                f"\"বিকাশ\" অথবা \"ক্যাশ অন\" লিখুন:")

    if state == ASK_PAYMENT:
        tl = text.lower()
        if "বিকাশ" in tl or "bkash" in tl:
            payment = "বিকাশ"
        elif "নগদ" in tl:
            payment = "নগদ"
        elif "রকেট" in tl:
            payment = "রকেট"
        else:
            payment = "ক্যাশ অন ডেলিভারি"

        save_order(
            name=sd.get("name",""), mobile=sd.get("mobile",""),
            address=sd.get("address",""), product=sd.get("product",""),
            color_size=sd.get("color",""), payment=payment
        )
        user_sessions.pop(sender_id, None)

        name    = sd.get("name","")
        product = sd.get("product","আমাদের পণ্য")
        color   = sd.get("color","")
        reply   = (f"✅ অর্ডার কনফার্ম!\n\n"
                   f"নাম: {name}\nপণ্য: {product}"
                   + (f" ({color})" if color else "")
                   + f"\nপেমেন্ট: {payment}\n")
        if payment == "বিকাশ":
            reply += f"\nবিকাশ নম্বর: {BKASH_NUMBER} (পার্সোনাল)\nপেমেন্ট করে স্ক্রিনশট পাঠান! 😊"
        elif payment in ("নগদ","রকেট"):
            reply += f"\nযোগাযোগ করুন: {BKASH_NUMBER}"
        else:
            reply += "\nপণ্য হাতে পেয়ে টাকা দিন। 😊"
        reply += "\n\nআমরা শীঘ্রই যোগাযোগ করবো! আজ ডেলিভারি ফ্রি!"
        return reply

    # ── IDLE: Order intent ──
    if state == IDLE and is_order_intent(text):
        product = detect_product(text) or user_product.get(sender_id,"")
        user_sessions[sender_id] = {
            "state": ASK_NAME,
            "product": product,
            "color": detect_color(text) or "",
        }
        return "দারুণ! অর্ডার নেওয়া হচ্ছে 😊\n\nআপনার পুরো নামটি লিখুন:"

    # ── Keyword match ──
    kr = keyword_reply(text)
    if kr:
        return kr

    # ── Gemini AI ──
    history = chat_histories.get(sender_id, [])
    ai_reply = get_ai_reply_simple(text)
    if ai_reply:
        # History update
        history.append({"role":"user",  "parts":[text]})
        history.append({"role":"model", "parts":[ai_reply]})
        chat_histories[sender_id] = history[-20:]  # last 10 turns
        return ai_reply

    # ── Ultimate fallback ──
    return ("আপনার মেসেজের জন্য ধন্যবাদ! 😊\n"
            "আমাদের টিম শীঘ্রই যোগাযোগ করবে।\n"
            "জানতে লিখুন: \"দাম\" | \"চুড়ি\" | \"অর্ডার\" | \"ডেলিভারি\"")


# ====================================================
# AUTH
# ====================================================

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return d


# ====================================================
# ADMIN — Dashboard
# ====================================================

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("login.html", error="ভুল পাসওয়ার্ড!")
    return render_template("login.html", error=None)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    orders = get_all_orders()
    stats  = {"total": bot_state["total"], "replied": bot_state["replied"],
              "orders": len(orders), "keywords": len(load_replies())}
    return render_template("admin.html", bot_active=bot_state["active"],
                           stats=stats, orders=orders, msg=request.args.get("msg"))

@app.route("/admin/toggle", methods=["POST"])
@login_required
def admin_toggle():
    bot_state["active"] = not bot_state["active"]
    s = "চালু" if bot_state["active"] else "বন্ধ"
    return redirect(url_for("admin_dashboard", msg=f"Bot {s} করা হয়েছে!"))


# ====================================================
# ADMIN — Reply Editor
# ====================================================

@app.route("/admin/replies")
@login_required
def admin_replies():
    return render_template("replies.html", replies=load_replies(),
                           msg=request.args.get("msg"))

@app.route("/admin/replies/add", methods=["POST"])
@login_required
def admin_reply_add():
    keyword = request.form.get("keyword","").strip()
    reply   = request.form.get("reply","").strip()
    if keyword and reply:
        data = load_replies()
        data[keyword] = reply
        save_replies(data)
    return redirect(url_for("admin_replies", msg="Reply যোগ করা হয়েছে!"))

@app.route("/admin/replies/edit", methods=["POST"])
@login_required
def admin_reply_edit():
    old_kw  = request.form.get("old_keyword","")
    new_kw  = request.form.get("keyword","").strip()
    reply   = request.form.get("reply","").strip()
    if new_kw and reply:
        data = load_replies()
        if old_kw in data:
            del data[old_kw]
        data[new_kw] = reply
        save_replies(data)
    return redirect(url_for("admin_replies", msg="Reply আপডেট হয়েছে!"))

@app.route("/admin/replies/delete", methods=["POST"])
@login_required
def admin_reply_delete():
    kw   = request.form.get("keyword","")
    data = load_replies()
    data.pop(kw, None)
    save_replies(data)
    return redirect(url_for("admin_replies", msg="Reply মুছে ফেলা হয়েছে!"))


# ====================================================
# ADMIN — Product Manager
# ====================================================

@app.route("/admin/products")
@login_required
def admin_products():
    return render_template("products.html", products=load_products(),
                           msg=request.args.get("msg"))

@app.route("/admin/products/add", methods=["POST"])
@login_required
def admin_product_add():
    products = load_products()
    new_id   = max((p["id"] for p in products), default=0) + 1
    colors_raw = request.form.get("colors","")
    colors = [c.strip() for c in colors_raw.split(",") if c.strip()]
    products.append({
        "id": new_id,
        "name":        request.form.get("name",""),
        "category":    request.form.get("category",""),
        "price":       int(request.form.get("price",0) or 0),
        "package":     request.form.get("package",""),
        "free_gift":   request.form.get("free_gift","-"),
        "delivery":    request.form.get("delivery","ফ্রি"),
        "colors":      colors,
        "description": request.form.get("description",""),
        "image":       "",
    })
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্য যোগ করা হয়েছে!"))

@app.route("/admin/products/delete", methods=["POST"])
@login_required
def admin_product_delete():
    pid      = int(request.form.get("id",0))
    products = [p for p in load_products() if p["id"] != pid]
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্য মুছে ফেলা হয়েছে!"))


# ====================================================
# ADMIN — Demo Chat
# ====================================================

@app.route("/admin/chat")
@login_required
def admin_chat():
    return render_template("chat.html")

@app.route("/admin/chat/send", methods=["POST"])
@login_required
def admin_chat_send():
    data    = request.get_json()
    message = data.get("message","").strip()
    if not message:
        return jsonify({"reply": ""})
    demo_id = "DEMO_ADMIN_USER"
    reply   = get_reply(demo_id, message)
    return jsonify({"reply": reply})


# ====================================================
# WEBHOOK
# ====================================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token= request.args.get("hub.verify_token")
    challenge= request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry",[]):
            for ev in entry.get("messaging",[]):
                sid = ev["sender"]["id"]
                if "message" in ev:
                    msg = ev["message"]
                    if msg.get("is_echo"):
                        continue
                    bot_state["total"] += 1
                    if not bot_state["active"]:
                        continue
                    if "text" in msg:
                        reply = get_reply(sid, msg["text"])
                        send_msg(sid, reply)
                        bot_state["replied"] += 1
                    elif "attachments" in msg:
                        send_msg(sid, "ধন্যবাদ! কোনো প্রশ্ন থাকলে text এ লিখুন। 😊")
                        bot_state["replied"] += 1
    return "OK", 200

def send_msg(rid, text):
    try:
        requests.post(
            "https://graph.facebook.com/v21.0/me/messages",
            json={"recipient":{"id":rid},"message":{"text":text},"messaging_type":"RESPONSE"},
            params={"access_token": PAGE_ACCESS_TOKEN}
        )
    except Exception as e:
        print(f"[ERR] {e}")


# ====================================================
# HOME
# ====================================================

@app.route("/")
def home():
    return jsonify({"bot":"Bella Basket Bot","active":bot_state["active"],"admin":"/admin"})


# ====================================================
# START
# ====================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    print("="*52)
    print("  Bella Basket Hybrid AI Bot")
    print(f"  Server:   http://localhost:{port}")
    print(f"  Admin:    http://localhost:{port}/admin")
    print(f"  Chat:     http://localhost:{port}/admin/chat")
    print(f"  Replies:  http://localhost:{port}/admin/replies")
    print(f"  Products: http://localhost:{port}/admin/products")
    print("="*52)
    app.run(host="0.0.0.0", port=port, debug=True)
