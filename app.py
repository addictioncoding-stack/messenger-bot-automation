"""
=====================================================
  Bella Basket — Complete Hybrid Bot
  Full order flow: size → dozen → name/mobile/address/thana
  Admin approval for unusual sizes
  Category-wise image sending
  Vision support
=====================================================
"""
import os, json, re, uuid, requests
from datetime import datetime
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

# ── States ──
IDLE          = "IDLE"
ASK_SIZE      = "ASK_SIZE"       # হাতের মাপ জিজ্ঞেস
WAIT_APPROVAL = "WAIT_APPROVAL"  # Admin approval pending
ASK_DOZON     = "ASK_DOZON"      # কয় ডজন
ASK_NAME      = "ASK_NAME"
ASK_MOBILE    = "ASK_MOBILE"
ASK_ADDRESS   = "ASK_ADDRESS"
ASK_THANA     = "ASK_THANA"
ASK_PAYMENT   = "ASK_PAYMENT"

# ── Runtime ──
bot_state        = {"active": True, "total": 0, "replied": 0}
user_sessions    = {}   # {sender_id: session_dict}
user_product     = {}   # {sender_id: last_product}
pending_approvals= {}   # {approval_id: {...}}

VALID_SIZES   = ["24", "26", "28"]
UNUSUAL_SIZES = ["22", "30"]
SIZE_BN_MAP   = {"২২":"22","২৪":"24","২৬":"26","২৮":"28","৩০":"30"}


# ====================================================
# DATA HELPERS
# ====================================================
def load_replies():
    try:
        with open(REPLIES_FILE,"r",encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_replies(data):
    with open(REPLIES_FILE,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_products():
    try:
        with open(PRODUCTS_FILE,"r",encoding="utf-8") as f: return json.load(f)
    except: return []

def save_products(data):
    with open(PRODUCTS_FILE,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def products_by_category(cat_kw):
    """category keyword দিয়ে products ফিল্টার"""
    return [p for p in load_products()
            if cat_kw.lower() in p.get("category","").lower()
            or cat_kw.lower() in p.get("name","").lower()]


# ====================================================
# DETECTION HELPERS
# ====================================================
PRODUCT_KW = {
    "কাশ্মীরি চুড়ি (১ ডজন)": ["কাশ্মীরি","চুড়ি","বাংলস","১২","ডজন"],
    "কাশ্মীরি চুড়ি (২ ডজন)": ["২৪ পিস","দুই ডজন"],
    "বাটারফ্লাই ব্লিস জুয়েলারি সেট": ["বাটারফ্লাই","butterfly"],
    "লাভ ব্লিস জুয়েলারি সেট":  ["লাভ ব্লিস","love bliss"],
    "স্নেক গোল্ড পায়েল":       ["পায়েল","গোল্ড পায়েল","স্নেক"],
}
COLORS = ["মিক্সড","ব্ল্যাক","পেল হোয়াইট","রেড","পেস্তা গ্রিন",
          "ব্লু","পার্পল","পিংক","মিন্ট","ডার্ক অ্যাশ",
          "ডার্ক গ্রিন","ডার্ক পিংক","গোল্ডেন"]
ORDER_WORDS = ["অর্ডার করব","নিতে চাই","কিনতে চাই","কিনব","অর্ডার","নেব","বুক"]

def is_churi(text):
    return any(k in text.lower() for k in ["চুড়ি","বাংলস","কাশ্মীরি"])

def is_set(text):
    return any(k in text.lower() for k in ["সেট","set","বাটারফ্লাই","লাভ ব্লিস"])

def is_payal(text):
    return any(k in text.lower() for k in ["পায়েল","payal"])

def detect_product(text):
    tl = text.lower()
    for p, kws in PRODUCT_KW.items():
        if any(k.lower() in tl for k in kws): return p
    return None

def detect_color(text):
    for c in COLORS:
        if c.lower() in text.lower(): return c
    return None

def is_order_intent(text):
    return any(k.lower() in text.lower() for k in ORDER_WORDS)

def is_cancel(text):
    return any(k in text.lower() for k in ["বাতিল","cancel","দরকার নেই"])

def detect_size(text):
    """হাতের সাইজ বের করো (English or Bengali)"""
    # Bengali to English
    for bn, en in SIZE_BN_MAP.items():
        if bn in text: return en
    # English numbers
    m = re.findall(r'\b(22|24|26|28|30)\b', text)
    return m[0] if m else None

def detect_dozon(text):
    """কয় ডজন বের করো"""
    if re.search(r'\b(২|2|দুই|দুইটা)\b', text): return "2"
    if re.search(r'\b(১|1|এক|একটা)\b', text): return "1"
    return None

def is_valid_mobile(mobile):
    m = re.sub(r'[\s\-\(\)]','', mobile)
    return bool(re.match(r'^01[3-9]\d{8}$', m)), m


# ====================================================
# FACEBOOK MESSENGER SEND
# ====================================================
def _fb(payload):
    try:
        r = requests.post(
            "https://graph.facebook.com/v21.0/me/messages",
            json=payload, params={"access_token": PAGE_ACCESS_TOKEN}, timeout=10
        )
        if r.status_code != 200:
            print(f"[FB ERR] {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"[FB ERR] {e}")

def send_text(rid, text):
    _fb({"recipient":{"id":rid},"message":{"text":text},"messaging_type":"RESPONSE"})

def send_image(rid, url):
    _fb({"recipient":{"id":rid},"message":{
        "attachment":{"type":"image","payload":{"url":url,"is_reusable":True}}
    },"messaging_type":"RESPONSE"})

def send_typing(rid):
    _fb({"recipient":{"id":rid},"sender_action":"typing_on"})

def send_category_images(rid, category_kw):
    """Category এর সব product এর ছবি পাঠাও"""
    products = products_by_category(category_kw)
    sent = 0
    for p in products:
        url = p.get("image","").strip()
        if url:
            send_image(rid, url)
            sent += 1
    return sent


# ====================================================
# REPLY ENGINE
# ====================================================
def process_message(sender_id, text):
    """
    Returns list of actions: [{"type":"text"/"image","content":"..."}]
    """
    actions = []
    sd      = user_sessions.get(sender_id, {"state": IDLE})
    state   = sd.get("state", IDLE)

    def txt(msg): actions.append({"type":"text","content":msg})
    def img(url): actions.append({"type":"image","content":url})

    # Track product interest
    prod = detect_product(text)
    if prod: user_product[sender_id] = prod

    # ── Cancel ──
    if is_cancel(text) and state != IDLE:
        user_sessions.pop(sender_id, None)
        txt("ঠিক আছে, অর্ডার বাতিল করা হয়েছে। আর কিছু জানতে চাইলে লিখুন! 😊")
        return actions

    # ══════════════════ ORDER STATES ══════════════════

    # ── ASK_SIZE: হাতের মাপ নিচ্ছি ──
    if state == ASK_SIZE:
        size = detect_size(text)
        if not size:
            txt("সাইজটা বুঝতে পারিনি 😊\nদয়া করে শুধু সংখ্যায় লিখুন: ২৪ / ২৬ / ২৮")
            return actions

        if size in VALID_SIZES:
            sd["size"]  = size
            sd["state"] = ASK_DOZON
            user_sessions[sender_id] = sd
            txt(f"সাইজ {size} নিশ্চিত! ✅\n\nকয় ডজন নিতে চান?\n\n"
                f"১ ডজন (১২ পিস) → ৳৬৫০ 🎁 ৪ পিস গিফট ফ্রি\n"
                f"২ ডজন (২৪ পিস) → ৳১,১০০ 🎁 ৮ পিস গিফট ফ্রি\n\n"
                f"\"১\" অথবা \"২\" লিখুন:")
        elif size in UNUSUAL_SIZES:
            # Admin approval দরকার
            ap_id = str(uuid.uuid4())[:8]
            sd["size"]        = size
            sd["state"]       = WAIT_APPROVAL
            sd["approval_id"] = ap_id
            user_sessions[sender_id] = sd
            pending_approvals[ap_id] = {
                "sender_id": sender_id,
                "size":      size,
                "product":   sd.get("product","কাশ্মীরি চুড়ি"),
                "color":     sd.get("color",""),
                "timestamp": datetime.now().strftime("%d/%m %H:%M"),
                "status":    "pending",
            }
            txt(f"সাইজ {size} — আমরা check করে জানাচ্ছি 😊\n"
                f"একটু অপেক্ষা করুন, শীঘ্রই জানাবো!")
        return actions

    # ── WAIT_APPROVAL: Admin approval এর অপেক্ষা ──
    if state == WAIT_APPROVAL:
        txt("আপনার size টি check করা হচ্ছে। একটু অপেক্ষা করুন 😊")
        return actions

    # ── ASK_DOZON: কয় ডজন ──
    if state == ASK_DOZON:
        dozon = detect_dozon(text)
        if not dozon:
            txt("\"১\" (১ ডজন = ১২ পিস) অথবা \"২\" (২ ডজন = ২৪ পিস) লিখুন:")
            return actions
        price = "৳৬৫০" if dozon == "1" else "৳১,১০০"
        pieces = "১২" if dozon == "1" else "২৪"
        sd["dozon"] = dozon
        sd["state"] = ASK_NAME
        user_sessions[sender_id] = sd
        txt(f"✅ {pieces} পিস ({dozon} ডজন) = {price}\n\n"
            f"এখন অর্ডার ফর্ম পূরণ করি 😊\nআপনার পুরো নামটি লিখুন:")
        return actions

    # ── ASK_NAME ──
    if state == ASK_NAME:
        name = text.strip()
        if len(name) < 2:
            txt("আপু/ভাই, শুধু নামটা দিলেই অর্ডার কনফার্ম করবো! 😊\nআপনার পুরো নাম লিখুন:")
            return actions
        sd["name"] = name; sd["state"] = ASK_MOBILE
        user_sessions[sender_id] = sd
        txt(f"ধন্যবাদ {name}! 😊\nমোবাইল নম্বর দিন (১১ সংখ্যার):")
        return actions

    # ── ASK_MOBILE ──
    if state == ASK_MOBILE:
        raw = text.strip()
        if not raw or len(raw) < 5:
            txt("মোবাইল নম্বরটা দিলেই অর্ডার কনফার্ম করবো! 😊\n(যেমন: 01712345678)")
            return actions
        valid, clean = is_valid_mobile(raw)
        if not valid:
            txt("মোবাইল নম্বরটি সঠিক নয় ❌\nবাংলাদেশের ১১ সংখ্যার নম্বর দিন:\n(যেমন: 01712345678)")
            return actions
        sd["mobile"] = clean; sd["state"] = ASK_ADDRESS
        user_sessions[sender_id] = sd
        txt("ঠিকানা লিখুন:\n(গ্রাম / মহল্লা / এলাকা — বিস্তারিত লিখুন):")
        return actions

    # ── ASK_ADDRESS ──
    if state == ASK_ADDRESS:
        addr = text.strip()
        if len(addr) < 3:
            txt("ঠিকানাটা দিলেই অর্ডার কনফার্ম করবো! 😊\n(গ্রাম/মহল্লা/এলাকার নাম লিখুন):")
            return actions
        sd["address"] = addr; sd["state"] = ASK_THANA
        user_sessions[sender_id] = sd
        txt("থানা / উপজেলার নাম লিখুন:")
        return actions

    # ── ASK_THANA ──
    if state == ASK_THANA:
        thana = text.strip()
        if len(thana) < 2:
            txt("থানার নামটা দিলেই হবে! 😊")
            return actions
        sd["thana"] = thana; sd["state"] = ASK_PAYMENT
        user_sessions[sender_id] = sd

        # Order summary দেখাও
        dozon = sd.get("dozon","1")
        size  = sd.get("size","")
        color = sd.get("color","")
        prod  = sd.get("product","কাশ্মীরি চুড়ি")
        price = "৳৬৫০" if dozon == "1" else "৳১,১০০"
        pieces= "১২" if dozon == "1" else "২৪"

        summary = (
            f"📋 অর্ডার সামারি:\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 নাম: {sd['name']}\n"
            f"📱 মোবাইল: {sd['mobile']}\n"
            f"📍 ঠিকানা: {sd['address']}, {thana}\n"
            f"💍 পণ্য: {prod}"
            + (f" ({color})" if color else "")
            + (f" — সাইজ {size}" if size else "")
            + f"\n📦 পরিমাণ: {pieces} পিস ({dozon} ডজন)\n"
            f"💰 মোট: {price}\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"পেমেন্ট কিভাবে করবেন?\n"
            f"১. বিকাশ\n"
            f"২. ক্যাশ অন ডেলিভারি\n\n"
            f"\"বিকাশ\" অথবা \"ক্যাশ অন\" লিখুন:"
        )
        txt(summary)
        return actions

    # ── ASK_PAYMENT ──
    if state == ASK_PAYMENT:
        tl = text.lower()
        if "বিকাশ" in tl or "bkash" in tl: payment = "বিকাশ"
        elif "নগদ" in tl:  payment = "নগদ"
        elif "রকেট" in tl: payment = "রকেট"
        else: payment = "ক্যাশ অন ডেলিভারি"

        dozon  = sd.get("dozon","1")
        size   = sd.get("size","")
        pieces = "১২" if dozon == "1" else "২৪"
        price  = "৳৬৫০" if dozon == "1" else "৳১,১০০"

        save_order(
            name=sd.get("name",""), mobile=sd.get("mobile",""),
            address=f"{sd.get('address','')} — {sd.get('thana','')}",
            product=sd.get("product",""),
            color_size=f"{sd.get('color','')} সাইজ:{size} {pieces}পিস",
            payment=payment,
        )
        user_sessions.pop(sender_id, None)

        reply = (
            f"✅ অর্ডার কনফার্ম হয়েছে!\n\n"
            f"পণ্য: {sd.get('product','')} {pieces} পিস\n"
            f"মোট: {price}\n"
            f"পেমেন্ট: {payment}\n"
        )
        if payment == "বিকাশ":
            reply += f"\n💳 বিকাশ নম্বর: {BKASH_NUMBER} (পার্সোনাল)\nপেমেন্ট করে screenshot পাঠান! 😊"
        else:
            reply += "\n🚚 পণ্য হাতে পেয়ে টাকা দিন। 😊"
        reply += "\n\nআমরা শীঘ্রই যোগাযোগ করবো! আজ ডেলিভারি ফ্রি! 🎁"
        txt(reply)
        return actions

    # ══════════════════ IDLE MODE ══════════════════

    # চুড়ির ব্যাপারে interest → size ask
    if state == IDLE and (is_churi(text) or is_order_intent(text) and is_churi(user_product.get(sender_id,""))):
        color = detect_color(text)
        prod  = detect_product(text) or user_product.get(sender_id, "কাশ্মীরি চুড়ি")
        user_sessions[sender_id] = {"state": ASK_SIZE, "product": prod, "color": color or ""}
        txt("হাতের মাপ কত? 😊\n\n"
            "✅ সাইজ: ২৪ / ২৬ / ২৮\n\n"
            "শুধু সংখ্যায় লিখুন (যেমন: ২৪):")
        return actions

    # সেট এর অর্ডার → size নেই, সরাসরি order
    if state == IDLE and is_order_intent(text) and is_set(text):
        prod = detect_product(text) or user_product.get(sender_id,"জুয়েলারি সেট")
        user_sessions[sender_id] = {"state": ASK_NAME, "product": prod, "color": detect_color(text) or "", "dozon": "1"}
        txt("দারুণ! অর্ডার নেওয়া হচ্ছে 😊\nআপনার পুরো নামটি লিখুন:")
        return actions

    # পায়েলের অর্ডার
    if state == IDLE and is_order_intent(text) and is_payal(text):
        user_sessions[sender_id] = {"state": ASK_NAME, "product": "স্নেক গোল্ড পায়েল", "color": "গোল্ডেন", "dozon": "1"}
        txt("দারুণ! অর্ডার নেওয়া হচ্ছে 😊\nআপনার পুরো নামটি লিখুন:")
        return actions

    # Generic order
    if state == IDLE and is_order_intent(text):
        prod = detect_product(text) or user_product.get(sender_id,"")
        if is_churi(prod):
            user_sessions[sender_id] = {"state": ASK_SIZE, "product": prod, "color": detect_color(text) or ""}
            txt("হাতের মাপ কত? ✅ ২৪ / ২৬ / ২৮")
        else:
            user_sessions[sender_id] = {"state": ASK_NAME, "product": prod, "color": detect_color(text) or "", "dozon": "1"}
            txt("দারুণ! অর্ডার নেওয়া হচ্ছে 😊\nআপনার পুরো নামটি লিখুন:")
        return actions

    # ── Keyword reply ──
    replies = load_replies()
    tl = text.lower().strip()
    for kw, rep in replies.items():
        if kw.lower() in tl:
            txt(rep)
            img_url = get_keyword_product_image(kw) or get_keyword_product_image(text)
            if img_url: img(img_url)
            return actions

    # ── Gemini AI ──
    ai = get_ai_reply_simple(text)
    if ai:
        txt(ai)
        return actions

    # ── Fallback ──
    txt("আপনার মেসেজের জন্য ধন্যবাদ! 😊\n"
        "জানতে লিখুন: \"চুড়ি\" | \"সেট\" | \"পায়েল\" | \"দাম\" | \"অর্ডার\"")
    return actions


# ====================================================
# AUTH
# ====================================================
def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get("admin"): return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return d


# ====================================================
# ADMIN — Dashboard
# ====================================================
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True; return redirect(url_for("admin_dashboard"))
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
    pending = {k:v for k,v in pending_approvals.items() if v["status"]=="pending"}
    stats  = {"total":bot_state["total"],"replied":bot_state["replied"],
              "orders":len(orders),"keywords":len(load_replies()),
              "pending":len(pending)}
    return render_template("admin.html", bot_active=bot_state["active"],
                           stats=stats, orders=orders,
                           pending=pending, msg=request.args.get("msg"))

@app.route("/admin/toggle", methods=["POST"])
@login_required
def admin_toggle():
    bot_state["active"] = not bot_state["active"]
    s = "চালু" if bot_state["active"] else "বন্ধ"
    return redirect(url_for("admin_dashboard", msg=f"Bot {s} করা হয়েছে!"))


# ── Approval routes ──
@app.route("/admin/approval/approve/<ap_id>", methods=["POST"])
@login_required
def approval_approve(ap_id):
    ap = pending_approvals.get(ap_id)
    if ap and ap["status"] == "pending":
        ap["status"] = "approved"
        sid = ap["sender_id"]
        # Session কে ASK_DOZON এ নিয়ে যাও
        if sid in user_sessions:
            user_sessions[sid]["state"] = ASK_DOZON
        # Customer কে message পাঠাও
        send_text(sid,
            f"সুখবর! সাইজ {ap['size']} এর চুড়ি available আছে! ✅\n\n"
            f"কয় ডজন নিতে চান?\n"
            f"১ ডজন (১২ পিস) → ৳৬৫০ 🎁 ৪ পিস গিফট\n"
            f"২ ডজন (২৪ পিস) → ৳১,১০০ 🎁 ৮ পিস গিফট\n\n"
            f"\"১\" অথবা \"২\" লিখুন:"
        )
        return redirect(url_for("admin_dashboard", msg=f"Approved! Customer কে message পাঠানো হয়েছে।"))
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/approval/reject/<ap_id>", methods=["POST"])
@login_required
def approval_reject(ap_id):
    ap = pending_approvals.get(ap_id)
    if ap and ap["status"] == "pending":
        ap["status"] = "rejected"
        sid = ap["sender_id"]
        user_sessions.pop(sid, None)
        send_text(sid,
            f"দুঃখিত আপু/ভাই 😔\n"
            f"সাইজ {ap['size']} এর চুড়ি এই মুহূর্তে stock-এ নেই।\n"
            f"আসলে আপনাকে জানানো হবে ইনশাআল্লাহ!\n\n"
            f"আমাদের অন্যান্য পণ্য:\n"
            f"• কাশ্মীরি চুড়ি (সাইজ ২৪/২৬/২৮) → ৳৬৫০\n"
            f"• বাটারফ্লাই ব্লিস সেট → ৳৬৫০\n"
            f"• স্নেক গোল্ড পায়েল → ৳৩৫০\n\n"
            f"🎁 আজ গিফট ফ্রি + ডেলিভারি ফ্রি!"
        )
        return redirect(url_for("admin_dashboard", msg="Rejected! Customer কে stock out message পাঠানো হয়েছে।"))
    return redirect(url_for("admin_dashboard"))


# ── Reply Editor ──
@app.route("/admin/replies")
@login_required
def admin_replies():
    return render_template("replies.html", replies=load_replies(), msg=request.args.get("msg"))

@app.route("/admin/replies/add", methods=["POST"])
@login_required
def admin_reply_add():
    kw=request.form.get("keyword","").strip(); rp=request.form.get("reply","").strip()
    if kw and rp: d=load_replies(); d[kw]=rp; save_replies(d)
    return redirect(url_for("admin_replies", msg="Reply যোগ করা হয়েছে!"))

@app.route("/admin/replies/edit", methods=["POST"])
@login_required
def admin_reply_edit():
    old=request.form.get("old_keyword",""); kw=request.form.get("keyword","").strip(); rp=request.form.get("reply","").strip()
    if kw and rp: d=load_replies(); d.pop(old,None); d[kw]=rp; save_replies(d)
    return redirect(url_for("admin_replies", msg="Reply আপডেট হয়েছে!"))

@app.route("/admin/replies/delete", methods=["POST"])
@login_required
def admin_reply_delete():
    d=load_replies(); d.pop(request.form.get("keyword",""),None); save_replies(d)
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
        "id":new_id,"name":request.form.get("name",""),
        "category":request.form.get("category",""),
        "price":int(request.form.get("price",0) or 0),
        "package":request.form.get("package",""),
        "free_gift":request.form.get("free_gift","-"),
        "delivery":request.form.get("delivery","ফ্রি"),
        "colors":colors,"description":request.form.get("description",""),
        "image":request.form.get("image_url","").strip(),
    })
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্য যোগ করা হয়েছে!"))

@app.route("/admin/products/update_image", methods=["POST"])
@login_required
def admin_product_update_image():
    pid=int(request.form.get("id",0)); img_url=request.form.get("image_url","").strip()
    products=load_products()
    for p in products:
        if p["id"]==pid: p["image"]=img_url; break
    save_products(products)
    return redirect(url_for("admin_products", msg="ছবি আপডেট হয়েছে!"))

@app.route("/admin/products/delete", methods=["POST"])
@login_required
def admin_product_delete():
    pid=int(request.form.get("id",0))
    save_products([p for p in load_products() if p["id"]!=pid])
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
    if not msg: return jsonify({"replies":[]})

    # Image URL detection
    if msg.startswith("http") and any(e in msg.lower() for e in [".jpg",".jpeg",".png",".webp"]):
        reply = analyze_product_image(msg)
        return jsonify({"replies":[{"type":"text","content":reply}]})

    actions = process_message("DEMO_ADMIN", msg)
    return jsonify({"replies": actions})


# ====================================================
# WEBHOOK
# ====================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode=request.args.get("hub.mode"); token=request.args.get("hub.verify_token"); ch=request.args.get("hub.challenge")
    if mode=="subscribe" and token==VERIFY_TOKEN: return ch,200
    return "Forbidden",403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    if data.get("object")=="page":
        for entry in data.get("entry",[]):
            for ev in entry.get("messaging",[]):
                sid = ev["sender"]["id"]
                if "message" not in ev: continue
                msg = ev["message"]
                if msg.get("is_echo"): continue

                bot_state["total"] += 1
                if not bot_state["active"]: continue

                send_typing(sid)

                # ── Image attachment ──
                if "attachments" in msg:
                    for att in msg["attachments"]:
                        if att.get("type")=="image":
                            url = att["payload"].get("url","")
                            # Detect what product the image is about
                            reply = analyze_product_image(url, PAGE_ACCESS_TOKEN)
                            send_text(sid, reply)
                            # If it's churi-like → ask size
                            if "চুড়ি" in reply or "বাংলস" in reply:
                                send_text(sid, "এটা নিতে চাইলে হাতের মাপ জানান: ২৪ / ২৬ / ২৮")
                                user_sessions[sid] = {"state": ASK_SIZE, "product": "কাশ্মীরি চুড়ি", "color": ""}
                        else:
                            send_text(sid, "ধন্যবাদ! কোনো প্রশ্ন থাকলে text এ লিখুন। 😊")
                    bot_state["replied"] += 1

                # ── Text ──
                elif "text" in msg:
                    text    = msg["text"]
                    actions = process_message(sid, text)
                    for act in actions:
                        if act["type"] == "text": send_text(sid, act["content"])
                        elif act["type"] == "image": send_image(sid, act["content"])
                    bot_state["replied"] += 1

    return "OK", 200


# ====================================================
# HOME + START
# ====================================================
@app.route("/")
def home():
    return jsonify({"bot":"Bella Basket Bot","active":bot_state["active"],"admin":"/admin"})

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    print("="*52)
    print("  Bella Basket — Full AI Bot")
    print(f"  Admin: http://localhost:{port}/admin")
    print(f"  Chat:  http://localhost:{port}/admin/chat")
    print("="*52)
    app.run(host="0.0.0.0", port=port, debug=True)
