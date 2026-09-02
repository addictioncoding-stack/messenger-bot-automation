"""
=====================================================
  Bella Basket Jewelry — Hybrid AI Messenger Bot
  Keyword + Gemini AI + Vision + Image Reply
  + Order Flow + Admin Panel + Demo Chat
=====================================================
"""

import os, json, requests
from flask import (Flask, request, jsonify, render_template,
                   redirect, url_for, session)
from functools import wraps
from dotenv import load_dotenv
from order_manager import save_order, get_all_orders
from ai_handler import (get_ai_reply_simple, analyze_product_image,
                        get_keyword_product_image)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "bella_basket_2024")

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "admin1234")
BKASH_NUMBER      = "01937281260"

DATA_DIR      = os.path.join(os.path.dirname(__file__), "data")
REPLIES_FILE  = os.path.join(DATA_DIR, "replies.json")
PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")

# ── Runtime ──
bot_state     = {"active": True, "total": 0, "replied": 0}
user_sessions = {}
user_product  = {}

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
# PRODUCT DETECTION
# ====================================================

PRODUCT_KEYWORDS = {
    "কাশ্মীরি চুড়ি (১ ডজন)":            ["কাশ্মীরি","চুড়ি","বাংলস","১২","ডজন"],
    "কাশ্মীরি চুড়ি (২ ডজন)":            ["২৪","দুই ডজন"],
    "বাটারফ্লাই ব্লিস জুয়েলারি সেট":   ["বাটারফ্লাই"],
    "লাভ ব্লিস জুয়েলারি সেট":           ["লাভ ব্লিস"],
    "স্নেক গোল্ড পায়েল":                ["পায়েল","গোল্ড পায়েল","স্নেক"],
}
COLORS = ["মিক্সড","ব্ল্যাক","পেল হোয়াইট","রেড","পেস্তা গ্রিন",
          "ব্লু","পার্পল","পিংক","মিন্ট","ডার্ক অ্যাশ",
          "ডার্ক গ্রিন","ডার্ক পিংক","গোল্ডেন"]
ORDER_WORDS = ["অর্ডার করব","অর্ডার করতে চাই","নিতে চাই","কিনতে চাই",
               "কিনব","order করব","অর্ডার দিতে চাই","বুক","নেব"]

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
    """keyword match → (reply_text, product_name_for_image)"""
    replies = load_replies()
    tl = text.lower().strip()
    for kw, rep in replies.items():
        if kw.lower() in tl:
            product = detect_product(text) or detect_product(kw)
            return rep, product
    return None, None


# ====================================================
# MESSENGER SEND FUNCTIONS
# ====================================================

def _fb_post(payload):
    try:
        r = requests.post(
            "https://graph.facebook.com/v21.0/me/messages",
            json=payload,
            params={"access_token": PAGE_ACCESS_TOKEN},
            timeout=10
        )
        if r.status_code != 200:
            print(f"[FB ERR] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[FB ERR] {e}")

def send_text(recipient_id, text):
    _fb_post({
        "recipient": {"id": recipient_id},
        "message":   {"text": text},
        "messaging_type": "RESPONSE",
    })
    print(f"[SENT TEXT] -> {recipient_id}")

def send_image(recipient_id, image_url):
    """Product ছবি পাঠাও"""
    _fb_post({
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url,
                    "is_reusable": True,
                }
            }
        },
        "messaging_type": "RESPONSE",
    })
    print(f"[SENT IMAGE] -> {recipient_id}: {image_url[:60]}")

def send_typing(recipient_id):
    """Typing indicator দেখাও"""
    _fb_post({
        "recipient": {"id": recipient_id},
        "sender_action": "typing_on",
    })


# ====================================================
# REPLY ENGINE
# ====================================================

def get_reply(sender_id, text):
    """
    Returns: (reply_text, image_url_or_None)
    Hybrid: keyword → order → AI
    """
    sd    = user_sessions.get(sender_id, {"state": IDLE})
    state = sd.get("state", IDLE)

    # Track product interest
    prod = detect_product(text)
    if prod:
        user_product[sender_id] = prod

    # ── Cancel ──
    if is_cancel(text) and state != IDLE:
        user_sessions.pop(sender_id, None)
        return "ঠিক আছে, অর্ডার বাতিল করা হয়েছে। আর কিছু জানতে চাইলে লিখুন! 😊", None

    # ── Order Flow ──
    if state == ASK_NAME:
        sd["name"] = text; sd["state"] = ASK_MOBILE
        user_sessions[sender_id] = sd
        return f"ধন্যবাদ {text}! 😊\nআপনার মোবাইল নম্বরটি লিখুন:", None

    if state == ASK_MOBILE:
        sd["mobile"] = text; sd["state"] = ASK_ADDRESS
        user_sessions[sender_id] = sd
        return "আপনার সম্পূর্ণ ঠিকানা লিখুন\n(গ্রাম/এলাকা, উপজেলা, জেলা সহ):", None

    if state == ASK_ADDRESS:
        sd["address"] = text; sd["state"] = ASK_PAYMENT
        user_sessions[sender_id] = sd
        p_line = f"\nপণ্য: {sd.get('product','')}" if sd.get("product") else ""
        return (f"প্রায় শেষ! 🎉{p_line}\n\n"
                "পেমেন্ট কিভাবে করবেন?\n"
                "১. বিকাশ\n২. ক্যাশ অন ডেলিভারি\n\n"
                "\"বিকাশ\" অথবা \"ক্যাশ অন\" লিখুন:"), None

    if state == ASK_PAYMENT:
        tl = text.lower()
        if "বিকাশ" in tl or "bkash" in tl: payment = "বিকাশ"
        elif "নগদ" in tl:                   payment = "নগদ"
        elif "রকেট" in tl:                  payment = "রকেট"
        else:                                payment = "ক্যাশ অন ডেলিভারি"

        save_order(name=sd.get("name",""), mobile=sd.get("mobile",""),
                   address=sd.get("address",""), product=sd.get("product",""),
                   color_size=sd.get("color",""), payment=payment)
        user_sessions.pop(sender_id, None)

        name = sd.get("name",""); product = sd.get("product","আমাদের পণ্য")
        color = sd.get("color","")
        reply = (f"✅ অর্ডার কনফার্ম!\n\nনাম: {name}\nপণ্য: {product}"
                 + (f" ({color})" if color else "") + f"\nপেমেন্ট: {payment}\n")
        if payment == "বিকাশ":
            reply += f"\nবিকাশ নম্বর: {BKASH_NUMBER} (পার্সোনাল)\nপেমেন্ট করে স্ক্রিনশট পাঠান! 😊"
        elif payment in ("নগদ","রকেট"):
            reply += f"\nযোগাযোগ: {BKASH_NUMBER}"
        else:
            reply += "\nপণ্য হাতে পেয়ে টাকা দিন। 😊"
        reply += "\n\nআমরা শীঘ্রই যোগাযোগ করবো! আজ ডেলিভারি ফ্রি! 🎁"
        return reply, None

    # ── IDLE: Order intent ──
    if state == IDLE and is_order_intent(text):
        product = detect_product(text) or user_product.get(sender_id,"")
        user_sessions[sender_id] = {
            "state": ASK_NAME, "product": product,
            "color": detect_color(text) or "",
        }
        return "দারুণ! অর্ডার নেওয়া হচ্ছে 😊\n\nআপনার পুরো নামটি লিখুন:", None

    # ── Keyword match ──
    kr, matched_product = keyword_reply(text)
    if kr:
        img_url = get_keyword_product_image(matched_product or text)
        return kr, img_url

    # ── Gemini AI ──
    ai_reply = get_ai_reply_simple(text)
    if ai_reply:
        return ai_reply, None

    # ── Fallback ──
    return ("আপনার মেসেজের জন্য ধন্যবাদ! 😊\n"
            "আমাদের টিম শীঘ্রই যোগাযোগ করবে।\n"
            "জানতে লিখুন: \"দাম\" | \"চুড়ি\" | \"অর্ডার\" | \"ডেলিভারি\""), None


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
# ADMIN ROUTES
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
    session.clear(); return redirect(url_for("admin_login"))

@app.route("/admin")
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    orders = get_all_orders()
    stats  = {"total":bot_state["total"],"replied":bot_state["replied"],
              "orders":len(orders),"keywords":len(load_replies())}
    return render_template("admin.html", bot_active=bot_state["active"],
                           stats=stats, orders=orders, msg=request.args.get("msg"))

@app.route("/admin/toggle", methods=["POST"])
@login_required
def admin_toggle():
    bot_state["active"] = not bot_state["active"]
    s = "চালু" if bot_state["active"] else "বন্ধ"
    return redirect(url_for("admin_dashboard", msg=f"Bot {s} করা হয়েছে!"))

# ── Reply Editor ──
@app.route("/admin/replies")
@login_required
def admin_replies():
    return render_template("replies.html", replies=load_replies(), msg=request.args.get("msg"))

@app.route("/admin/replies/add", methods=["POST"])
@login_required
def admin_reply_add():
    kw = request.form.get("keyword","").strip()
    rp = request.form.get("reply","").strip()
    if kw and rp:
        d = load_replies(); d[kw] = rp; save_replies(d)
    return redirect(url_for("admin_replies", msg="Reply যোগ করা হয়েছে!"))

@app.route("/admin/replies/edit", methods=["POST"])
@login_required
def admin_reply_edit():
    old = request.form.get("old_keyword","")
    kw  = request.form.get("keyword","").strip()
    rp  = request.form.get("reply","").strip()
    if kw and rp:
        d = load_replies()
        d.pop(old, None); d[kw] = rp; save_replies(d)
    return redirect(url_for("admin_replies", msg="Reply আপডেট হয়েছে!"))

@app.route("/admin/replies/delete", methods=["POST"])
@login_required
def admin_reply_delete():
    d = load_replies(); d.pop(request.form.get("keyword",""), None); save_replies(d)
    return redirect(url_for("admin_replies", msg="Reply মুছে ফেলা হয়েছে!"))

# ── Product Manager ──
@app.route("/admin/products")
@login_required
def admin_products():
    return render_template("products.html", products=load_products(), msg=request.args.get("msg"))

@app.route("/admin/products/add", methods=["POST"])
@login_required
def admin_product_add():
    products = load_products()
    new_id   = max((p["id"] for p in products), default=0) + 1
    colors   = [c.strip() for c in request.form.get("colors","").split(",") if c.strip()]
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
        "image":       request.form.get("image_url","").strip(),
    })
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্য যোগ করা হয়েছে!"))

@app.route("/admin/products/update_image", methods=["POST"])
@login_required
def admin_product_update_image():
    pid     = int(request.form.get("id", 0))
    img_url = request.form.get("image_url","").strip()
    products= load_products()
    for p in products:
        if p["id"] == pid:
            p["image"] = img_url
            break
    save_products(products)
    return redirect(url_for("admin_products", msg="ছবি আপডেট হয়েছে!"))

@app.route("/admin/products/delete", methods=["POST"])
@login_required
def admin_product_delete():
    pid      = int(request.form.get("id",0))
    products = [p for p in load_products() if p["id"] != pid]
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্য মুছে ফেলা হয়েছে!"))

# ── Demo Chat ──
@app.route("/admin/chat")
@login_required
def admin_chat():
    return render_template("chat.html")

@app.route("/admin/chat/send", methods=["POST"])
@login_required
def admin_chat_send():
    data = request.get_json()
    msg  = data.get("message","").strip()
    if not msg:
        return jsonify({"reply":"", "image":None})

    # Check if it's an image URL (for demo purposes)
    if msg.startswith("http") and any(ext in msg.lower() for ext in [".jpg",".jpeg",".png",".webp"]):
        reply = analyze_product_image(msg)
        return jsonify({"reply": reply, "image": None})

    reply, img = get_reply("DEMO_ADMIN", msg)
    return jsonify({"reply": reply, "image": img})


# ====================================================
# WEBHOOK
# ====================================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode  = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    ch    = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return ch, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry",[]):
            for ev in entry.get("messaging",[]):
                sid = ev["sender"]["id"]
                if "message" not in ev:
                    continue
                msg = ev["message"]
                if msg.get("is_echo"):
                    continue

                bot_state["total"] += 1
                if not bot_state["active"]:
                    continue

                send_typing(sid)

                # ── Customer ছবি পাঠিয়েছে ──
                if "attachments" in msg:
                    for att in msg["attachments"]:
                        if att.get("type") == "image":
                            img_url = att["payload"].get("url","")
                            if img_url:
                                reply = analyze_product_image(img_url, PAGE_ACCESS_TOKEN)
                                send_text(sid, reply)
                                bot_state["replied"] += 1
                        else:
                            send_text(sid, "ধন্যবাদ! কোনো প্রশ্ন থাকলে text এ লিখুন। 😊")
                            bot_state["replied"] += 1

                # ── Text message ──
                elif "text" in msg:
                    text         = msg["text"]
                    reply, img_url = get_reply(sid, text)
                    send_text(sid, reply)
                    # Product ছবি থাকলে পাঠাও
                    if img_url:
                        send_image(sid, img_url)
                    bot_state["replied"] += 1

    return "OK", 200


# ====================================================
# HOME
# ====================================================

@app.route("/")
def home():
    return jsonify({"bot":"Bella Basket Hybrid AI Bot","active":bot_state["active"],"admin":"/admin"})


# ====================================================
# START
# ====================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print("="*52)
    print("  Bella Basket Hybrid AI Bot (Vision Enabled)")
    print(f"  Server:   http://localhost:{port}")
    print(f"  Admin:    http://localhost:{port}/admin")
    print(f"  Chat:     http://localhost:{port}/admin/chat")
    print(f"  Replies:  http://localhost:{port}/admin/replies")
    print(f"  Products: http://localhost:{port}/admin/products")
    print("="*52)
    app.run(host="0.0.0.0", port=port, debug=True)
