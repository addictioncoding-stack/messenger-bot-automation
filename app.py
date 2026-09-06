"""
=====================================================
  Bella Basket Jewelry — Intelligent AI Messenger Bot
  Full Business Rules + Gemini Context Intelligence
  - AI reads & evaluates context first
  - Sentiment classification (Good / Bad / General)
  - Per 12 pcs Churi -> 4 pcs Ghugur free + Free delivery
  - 6 pcs -> website redirect (bellabasket.store)
  - > 2 dozen -> 200 BDT advance payment
  - Size 24, 26, 28 (in stock); Size 22, 30 (admin approval)
  - Necklace & Payel -> No gift, free delivery only
  - Refusal persuasion ("আজকের জন্যই এই অফার ম্যাডাম/স্যার")
  - Excel Logging of all orders & conversations with sentiment
=====================================================
"""
import os, json, re, uuid, requests
from datetime import datetime
from flask import (Flask, request, jsonify, render_template,
                   redirect, url_for, session)
from functools import wraps
from dotenv import load_dotenv
from order_manager import save_order, get_all_orders, save_conversation_log, get_all_logs
from ai_handler import (analyze_and_reply, get_ai_reply_simple, analyze_product_image,
                        get_keyword_product_image)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "bella_basket_2024")

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "admin1234")
BKASH_NUMBER      = "01937281260"
WEBSITE           = "bellabasket.store"

DATA_DIR      = os.path.join(os.path.dirname(__file__), "data")
REPLIES_FILE  = os.path.join(DATA_DIR, "replies.json")
PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")

# ── States ──
IDLE          = "IDLE"
ASK_SIZE      = "ASK_SIZE"
WAIT_APPROVAL = "WAIT_APPROVAL"
ASK_DOZON     = "ASK_DOZON"
WAIT_ADVANCE  = "WAIT_ADVANCE"   # > 2 dozen advance payment
ASK_NAME      = "ASK_NAME"
ASK_MOBILE    = "ASK_MOBILE"
ASK_ADDRESS   = "ASK_ADDRESS"
ASK_THANA     = "ASK_THANA"
ASK_PAYMENT   = "ASK_PAYMENT"

# ── Runtime ──
bot_state        = {"active": True, "total": 0, "replied": 0}
user_sessions    = {}   # {sender_id: session_dict}
user_product     = {}   # {sender_id: product_name}
pending_approvals= {}   # {approval_id: {...}}
user_no_count    = {}   # persuasion tracking {sender_id: count}


# ====================================================
# PRODUCT RULES BY CATEGORY
# ====================================================
def get_category(product_name):
    pn = str(product_name).lower()
    if any(k in pn for k in ["চুড়ি","বাংলস","কাশ্মীরি","churi"]): return "churi"
    if any(k in pn for k in ["নেকলেস","গলার","necklace","ব্লিস","বাটারফ্লাই","লাভ","সেট"]): return "necklace"
    if any(k in pn for k in ["পায়েল","payal"]): return "payal"
    return "other"


def get_dozon_info(product_name, dozon_str):
    """
    Dozon অনুযায়ী price + ghugur gift info
    চুড়ি: প্রতি ১২ পিসে ৪ পিস ঘুগুর ফ্রি (২৪ পিসে ৮ পিস ঘুগুর ফ্রি)
    """
    try:
        dozon = int(dozon_str)
    except:
        dozon = 1

    cat = get_category(product_name)

    if cat == "churi":
        pieces = dozon * 12
        gift_ghugur = dozon * 4
        
        if dozon == 1:
            price = 650
        else:
            price = dozon * 550  # 1 doz = 650, 2 doz = 1100, 3 doz = 1650

        return {
            "pieces": pieces,
            "price": price,
            "price_str": f"৳{price:,}",
            "gift": gift_ghugur,
            "gift_str": f"🎁 {gift_ghugur} পিস ঘুগুর ফ্রি + ডেলিভারি ফ্রি 🚚"
        }
    else:
        # নেকলেস, পায়েল — No gift, only delivery free
        prices = {"necklace": 650, "payal": 350}
        price = prices.get(cat, 650)
        return {
            "pieces": dozon,
            "price": price,
            "price_str": f"৳{price:,}",
            "gift": 0,
            "gift_str": "ডেলিভারি চার্জ সম্পূর্ণ ফ্রি 🚚"
        }


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
ORDER_WORDS  = ["অর্ডার করব","অর্ডার করবো","নিতে চাই","কিনতে চাই","কিনব","অর্ডার","নেব","বুক","order"]
CANCEL_WORDS = ["বাতিল","cancel","দরকার নেই","না থাক"]
NEGATIVE_WORDS = ["না","নাই","দরকার নাই","interest নেই","পরে","চাই না","কিনব না",
                  "নিব না","থাকুক","ok","ঠিক আছে থাক","দাম বেশি"]

def is_churi(text):   return any(k in text.lower() for k in ["চুড়ি","বাংলস","কাশ্মীরি","churi"])
def is_set(text):     return any(k in text.lower() for k in ["সেট","set","বাটারফ্লাই","লাভ ব্লিস","ব্লিস","নেকলেস"])
def is_payal(text):   return any(k in text.lower() for k in ["পায়েল","payal"])

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
    return any(k in text.lower() for k in CANCEL_WORDS)

def is_negative(text):
    tl = text.lower().strip()
    return any(k in tl for k in NEGATIVE_WORDS) or tl in ["না","na","nah","nope"]

VALID_SIZES   = ["24","26","28"]
UNUSUAL_SIZES = ["22","30"]
SIZE_BN_MAP   = {"২২":"22","২৪":"24","২৬":"26","২৮":"28","৩০":"30"}

def detect_size(text):
    for bn, en in SIZE_BN_MAP.items():
        if bn in text: return en
    m = re.findall(r'\b(22|24|26|28|30)\b', text)
    return m[0] if m else None

def detect_dozon_count(text):
    bn_map = {"এক":1,"একটা":1,"১":1,"দুই":2,"দুইটা":2,"২":2,"তিন":3,"তিনটা":3,"৩":3,
              "চার":4,"৪":4,"পাঁচ":5,"৫":5,"ছয়":6,"৬":6}
    for word, val in bn_map.items():
        if word in text: return val
    m = re.search(r'\b([1-9])\b', text)
    if m: return int(m.group())
    return None

def wants_small_qty(text):
    return any(k in text for k in ["৬","6 পিস","৬ পিস","হাফ ডজন","ছয় পিস"])

def is_valid_mobile(mobile):
    m = re.sub(r'[\s\-\(\)]','', str(mobile))
    return bool(re.match(r'^01[3-9]\d{8}$', m)), m


# ====================================================
# PERSUASION ENGINE
# ====================================================
PERSUASION_MSGS = [
    # Level 1 — urgency & offer reminder
    ("আজকের জন্যই এই অফার ম্যাডাম/স্যার! ⏰\n"
     "আজ চুড়ির সাথে ৪ পিস ঘুগুর ফ্রি + ডেলিভারি চার্জ সম্পূর্ণ ফ্রি + ক্যাশ অন ডেলিভারি!\n"
     "এই সুবর্ণ সুযোগটি মিস করবেন না কিন্তু! 😊"),
    # Level 2 — value proposition
    ("আপু/ভাই, আমরা বেস্ট কোয়ালিটি গ্যারান্টি দিচ্ছি। 💎\n"
     "পণ্য হাতে পেয়ে দেখে চেক করে তারপর টাকা দেবেন — কোনো ঝুঁকি নেই!\n"
     "একবার ট্রাই করে দেখুন, নিশ্চিত ভালো লাগবে! 😊"),
    # Level 3 — suggest other products
    ("ঠিক আছে ম্যাডাম/স্যার! 😊 আমাদের অন্যান্য সেরা জুয়েলারিগুলো দেখতে পারেন:\n\n"
     "💍 বাটারফ্লাই ব্লিস সেট → ৳৬৫০ (ডেলিভারি ফ্রি)\n"
     "🦶 স্নেক গোল্ড পায়েল → ৳৩৫০ (ডেলিভারি ফ্রি)\n"
     "📿 কাশ্মীরি চুড়ি → ৳৬৫০ + ঘুগুর ফ্রি\n\n"
     "কোন পণ্যটি সম্পর্কে জানতে চান লিখুন! 🎁"),
]

def get_persuasion_reply(sender_id):
    count = user_no_count.get(sender_id, 0)
    user_no_count[sender_id] = count + 1
    if count < len(PERSUASION_MSGS):
        return PERSUASION_MSGS[count]
    user_no_count.pop(sender_id, None)
    return None


# ====================================================
# FACEBOOK MESSENGER SEND
# ====================================================
def _fb(payload):
    try:
        r = requests.post("https://graph.facebook.com/v21.0/me/messages",
            json=payload, params={"access_token": PAGE_ACCESS_TOKEN}, timeout=10)
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


# ====================================================
# MAIN PROCESS MESSAGE ENGINE (AI INTEGRATED)
# ====================================================
def process_message(sender_id, text):
    """
    Returns list of actions: [{"type":"text"/"image","content":"..."}]
    Uses Gemini AI to evaluate full context & logs feedback to Excel!
    """
    actions = []
    sd      = user_sessions.get(sender_id, {"state": IDLE})
    state   = sd.get("state", IDLE)

    def txt(msg): actions.append({"type":"text","content":msg})
    def img(url): actions.append({"type":"image","content":url})

    # Track product interest
    prod = detect_product(text)
    if prod: user_product[sender_id] = prod
    current_prod = user_product.get(sender_id, sd.get("product", ""))

    # ── Gemini AI Evaluation ──
    ai_res = analyze_and_reply(text, current_state=state, product_context=current_prod)
    sentiment = ai_res.get("sentiment", "General") if ai_res else "General"
    ai_text   = ai_res.get("reply_text") if ai_res else None

    # AI Detected attributes
    ai_size  = ai_res.get("detected_size") if ai_res else None
    ai_dozen = ai_res.get("detected_dozen") if ai_res else None

    # ── Cancel Check ──
    if is_cancel(text) and state != IDLE:
        user_sessions.pop(sender_id, None)
        reply_msg = "ঠিক আছে, অর্ডার বাতিল করা হয়েছে। আবার কিছু লাগলে জানান! 😊"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ══════════════════════════════════════════
    # ORDER STATE MACHINE
    # ══════════════════════════════════════════

    # ── ASK_SIZE: চুড়ির হাতের সাইজ চাওয়া ──
    if state == ASK_SIZE:
        size = ai_size or detect_size(text)
        if not size:
            reply_msg = "সাইজটি বুঝতে পারিনি স্যার/ম্যাডাম 😊\nআমাদের এভেলেবল সাইজ: ২৪ / ২৬ / ২৮\n\nদয়া করে শুধু সংখ্যায় লিখুন (যেমন: ২৪):"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        if size in VALID_SIZES:
            sd["size"]  = size
            sd["state"] = ASK_DOZON
            user_sessions[sender_id] = sd
            cat = get_category(sd.get("product",""))
            if cat == "churi":
                reply_msg = (f"সাইজ {size} কনফার্ম! ✅\n\nকয় ডজন নিতে চান?\n\n"
                             f"১ ডজন (১২ পিস) → ৳৬৫০ 🎁 ৪ পিস ঘুগুর ফ্রি + ফ্রি ডেলিভারি\n"
                             f"২ ডজন (২৪ পিস) → ৳১,১০০ 🎁 ৮ পিস ঘুগুর ফ্রি + ফ্রি ডেলিভারি\n\n"
                             f"\"১\" অথবা \"২\" লিখুন:")
            else:
                reply_msg = f"সাইজ {size} কনফার্ম! ✅\nকয় ডজন নিতে চান? (\"১\" বা \"২\" লিখুন):"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        elif size in UNUSUAL_SIZES:
            # 22 or 30 size -> Approval Queue
            ap_id = str(uuid.uuid4())[:8]
            sd["size"]        = size
            sd["state"]       = WAIT_APPROVAL
            sd["approval_id"] = ap_id
            user_sessions[sender_id] = sd
            pending_approvals[ap_id] = {
                "sender_id": sender_id, "size": size,
                "product": sd.get("product","কাশ্মীরি চুড়ি"),
                "color": sd.get("color",""),
                "timestamp": datetime.now().strftime("%d/%m %H:%M"),
                "status": "pending",
            }
            reply_msg = f"স্যার/ম্যাডাম চেক করে জানাচ্ছি। একটু অপেক্ষা করুন! 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── WAIT_APPROVAL: অ্যাডমিন এপ্রুভালের জন্য অপেক্ষা ──
    if state == WAIT_APPROVAL:
        reply_msg = "আপনার সাইজটি স্টক চেক করা হচ্ছে স্যার/ম্যাডাম। একটু অপেক্ষা করুন! 😊"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_DOZON: কয় ডজন ──
    if state == ASK_DOZON:
        # ৬ পিস চাইলে ওয়েবসাইট রেফার
        if wants_small_qty(text):
            reply_msg = (f"৬ পিসের জন্য আমাদের ওয়েবসাইট থেকে সহজেই অর্ডার করুন:\n"
                         f"🌐 www.{WEBSITE}\n\nযেকোনো সাহায্য লাগলে জানান! 😊")
            txt(reply_msg)
            user_sessions.pop(sender_id, None)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        dozon_count = ai_dozen or detect_dozon_count(text)

        if dozon_count is None:
            reply_msg = "কয় ডজন নিতে চান স্যার/ম্যাডাম?\n\"১\" (১২ পিস) অথবা \"২\" (২৪ পিস) লিখুন:"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # > ২ ডজন (৩+ ডজন) → ২০০ টাকা অগ্রিম পেমেন্ট
        if dozon_count > 2:
            sd["dozon"] = str(dozon_count)
            sd["state"] = WAIT_ADVANCE
            user_sessions[sender_id] = sd
            info = get_dozon_info(sd.get("product",""), str(dozon_count))
            reply_msg = (f"দারুণ! {dozon_count} ডজন = {info['pieces']} পিস 😊\n\n"
                         f"২ ডজনের বেশি হওয়ায় অর্ডার কনফার্মের জন্য ২০০ টাকা অগ্রিম পেমেন্ট করতে হবে।\n\n"
                         f"💳 বিকাশ (পার্সোনাল): {BKASH_NUMBER}\n"
                         f"পেমেন্ট করে স্ক্রিনশট পাঠালে বাকি অর্ডার কনফার্ম করবো!")
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # Normal 1 or 2 dozen
        sd["dozon"] = str(dozon_count)
        sd["state"] = ASK_NAME
        user_sessions[sender_id] = sd
        info = get_dozon_info(sd.get("product",""), str(dozon_count))
        reply_msg = (f"✅ {info['pieces']} পিস = {info['price_str']} | {info['gift_str']}\n\n"
                     f"অর্ডার কনফার্ম করার জন্য আপনার নামটা বলুন স্যার/ম্যাডাম:")
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── WAIT_ADVANCE ──
    if state == WAIT_ADVANCE:
        reply_msg = ("স্ক্রিনশটটি পেলে আমরা অর্ডার প্রসেস শুরু করবো স্যার/ম্যাডাম! 😊\n"
                     "আপনার নাম ও সম্পূর্ণ ঠিকানাটি লিখে পাঠান।")
        sd["state"] = ASK_NAME
        user_sessions[sender_id] = sd
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_NAME ──
    if state == ASK_NAME:
        name = text.strip()
        if len(name) < 2:
            reply_msg = "স্যার/ম্যাডাম, নামটা দিলে অর্ডারটা কনফার্ম করবো! 😊\nআপনার পুরো নাম লিখুন:"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions
        sd["name"] = name
        sd["state"] = ASK_MOBILE
        user_sessions[sender_id] = sd
        reply_msg = f"ধন্যবাদ {name}! 😊\nস্যার/ম্যাডাম, মোবাইল নম্বরটা (১১ সংখ্যার) দিলে অর্ডারটা কনফার্ম করবো:"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_MOBILE ──
    if state == ASK_MOBILE:
        raw = text.strip()
        valid, clean = is_valid_mobile(raw)
        if not valid:
            reply_msg = "স্যার/ম্যাডাম, সঠিক মোবাইল নম্বরটা (১১ সংখ্যার) দিলে অর্ডারটা কনফার্ম করবো 😊\n(যেমন: 01712345678):"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions
        sd["mobile"] = clean
        sd["state"]  = ASK_ADDRESS
        user_sessions[sender_id] = sd
        reply_msg = "স্যার/ম্যাডাম, সম্পূর্ণ ঠিকানাটা দিলে অর্ডারটা কনফার্ম করবো:\n(গ্রাম / মহল্লা / বাসা নং):"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_ADDRESS ──
    if state == ASK_ADDRESS:
        addr = text.strip()
        if len(addr) < 3:
            reply_msg = "স্যার/ম্যাডাম, ঠিকানাটা দিলে অর্ডারটা কনফার্ম করবো! 😊\n(গ্রাম/এলাকার নাম লিখুন):"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions
        sd["address"] = addr
        sd["state"]   = ASK_THANA
        user_sessions[sender_id] = sd
        reply_msg = "স্যার/ম্যাডাম, থানা/উপজেলার নামটা দিলে অর্ডারটা কনফার্ম করবো:"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_THANA ──
    if state == ASK_THANA:
        thana = text.strip()
        if len(thana) < 2:
            reply_msg = "স্যার/ম্যাডাম, থানা/উপজেলার নামটা দিলে অর্ডারটা কনফার্ম করবো! 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions
        sd["thana"] = thana
        sd["state"] = ASK_PAYMENT
        user_sessions[sender_id] = sd

        dozon = sd.get("dozon","1")
        info  = get_dozon_info(sd.get("product",""), dozon)
        size  = sd.get("size","")
        color = sd.get("color","")

        summary = (
            f"📋 অর্ডার সামারি:\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 নাম: {sd['name']}\n"
            f"📱 মোবাইল: {sd['mobile']}\n"
            f"📍 ঠিকানা: {sd['address']}, {thana}\n"
            f"💍 পণ্য: {sd.get('product','')}"
            + (f" ({color})" if color else "")
            + (f" — সাইজ {size}" if size else "")
            + f"\n📦 পরিমাণ: {info['pieces']} পিস ({dozon} ডজন)\n"
            f"💰 মোট: {info['price_str']} | {info['gift_str']}\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"পেমেন্ট কিভাবে করবেন?\n"
            f"১. বিকাশ\n২. ক্যাশ অন ডেলিভারি\n\n"
            f"\"বিকাশ\" অথবা \"ক্যাশ অন\" লিখুন:"
        )
        txt(summary)
        save_conversation_log(sender_id, text, summary, sentiment, current_prod)
        return actions

    # ── ASK_PAYMENT ──
    if state == ASK_PAYMENT:
        tl = text.lower()
        if "বিকাশ" in tl or "bkash" in tl: payment = "বিকাশ"
        elif "নগদ" in tl:  payment = "নগদ"
        elif "রকেট" in tl: payment = "রকেট"
        else: payment = "ক্যাশ অন ডেলিভারি"

        dozon = sd.get("dozon","1")
        info  = get_dozon_info(sd.get("product",""), dozon)
        size  = sd.get("size","")

        save_order(
            name=sd.get("name",""), mobile=sd.get("mobile",""),
            address=f"{sd.get('address','')} — {sd.get('thana','')}",
            product=sd.get("product",""),
            color_size=f"{sd.get('color','')} সাইজ:{size} {info['pieces']}পিস",
            payment=payment,
        )
        user_sessions.pop(sender_id, None)
        user_no_count.pop(sender_id, None)

        reply = (f"✅ আপনার অর্ডারটি সফলভাবে কনফার্ম হয়েছে!\n\n"
                 f"পণ্য: {sd.get('product','')} {info['pieces']} পিস\n"
                 f"মোট: {info['price_str']} | {info['gift_str']}\n"
                 f"পেমেন্ট মাধ্যম: {payment}\n")
        if payment == "বিকাশ":
            reply += f"\n💳 বিকাশ (পার্সোনাল): {BKASH_NUMBER}\nপেমেন্ট করে স্ক্রিনশট পাঠান! 😊"
        else:
            reply += "\n🚚 পণ্য হাতে পেয়ে দেখে টাকা দেবেন।"
        reply += "\n\nধন্যবাদ! আমরা খুব শীঘ্রই ডেলিভারির ব্যবস্থা করছি। 🎁"
        txt(reply)
        save_conversation_log(sender_id, text, reply, sentiment, current_prod)
        return actions

    # ══════════════════════════════════════════
    # IDLE MODE — AI Context First Flow
    # ══════════════════════════════════════════

    # ── Customer Refusal / Hesitation ──
    if state == IDLE and (sentiment == "Bad" or is_negative(text)):
        p = get_persuasion_reply(sender_id)
        if p:
            txt(p)
            save_conversation_log(sender_id, text, p, "Bad", current_prod)
            return actions

    # ── Order Intent Detection ──
    if state == IDLE and (is_order_intent(text) or (ai_res and ai_res.get("intent") == "ORDER")):
        user_no_count.pop(sender_id, None)
        prod = detect_product(text) or user_product.get(sender_id, "কাশ্মীরি চুড়ি (১ ডজন)")
        
        if is_churi(prod):
            user_sessions[sender_id] = {"state": ASK_SIZE, "product": prod, "color": detect_color(text) or ""}
            reply_msg = "হাতের মাপ কত স্যার/ম্যাডাম? 😊\n\n✅ এভেলেবল সাইজ: ২৪ / ২৬ / ২৮\n\nদয়া করে শুধু সংখ্যায় লিখুন:"
        else:
            user_sessions[sender_id] = {"state": ASK_NAME, "product": prod, "color": detect_color(text) or "", "dozon": "1"}
            reply_msg = "দারুণ! 😊 ডেলিভারি সম্পূর্ণ ফ্রি!\nঅর্ডার কনফার্ম করার জন্য আপনার পুরো নামটা লিখুন স্যার/ম্যাডাম:"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, prod)
        return actions

    # ── Churi Interest ──
    if state == IDLE and is_churi(text):
        user_no_count.pop(sender_id, None)
        color = detect_color(text)
        prod  = detect_product(text) or "কাশ্মীরি চুড়ি (১ ডজন)"
        user_sessions[sender_id] = {"state": ASK_SIZE, "product": prod, "color": color or ""}
        reply_msg = "হাতের মাপ কত স্যার/ম্যাডাম? 😊\n\n✅ এভেলেবল সাইজ: ২৪ / ২৬ / ২৮\n\nদয়া করে শুধু সংখ্যায় লিখুন (যেমন: ২৪):"
        txt(reply_msg)
        img_url = get_keyword_product_image("চুড়ি")
        if img_url: img(img_url)
        save_conversation_log(sender_id, text, reply_msg, sentiment, prod)
        return actions

    # ── Necklace / Set Interest ──
    if state == IDLE and is_set(text):
        user_no_count.pop(sender_id, None)
        prod = detect_product(text) or "বাটারফ্লাই ব্লিস জুয়েলারি সেট"
        user_sessions[sender_id] = {"state": ASK_NAME, "product": prod,
                                    "color": detect_color(text) or "", "dozon": "1"}
        reply_msg = "দারুণ পছন্দ! 😊 অফারে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!\nঅর্ডার নেওয়ার জন্য আপনার পুরো নামটি লিখুন স্যার/ম্যাডাম:"
        txt(reply_msg)
        img_url = get_keyword_product_image("সেট")
        if img_url: img(img_url)
        save_conversation_log(sender_id, text, reply_msg, sentiment, prod)
        return actions

    # ── Payel Interest ──
    if state == IDLE and is_payal(text):
        user_no_count.pop(sender_id, None)
        prod = "স্নেক গোল্ড পায়েল"
        user_sessions[sender_id] = {"state": ASK_NAME, "product": prod,
                                    "color": "গোল্ডেন", "dozon": "1"}
        reply_msg = "দারুণ পছন্দ! 😊 অফারে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!\nঅর্ডার নেওয়ার জন্য আপনার পুরো নামটি লিখুন স্যার/ম্যাডাম:"
        txt(reply_msg)
        img_url = get_keyword_product_image("পায়েল")
        if img_url: img(img_url)
        save_conversation_log(sender_id, text, reply_msg, sentiment, prod)
        return actions

    # ── Intelligent AI Reply (Gemini Context Evaluation) ──
    if ai_text:
        txt(ai_text)
        img_url = get_keyword_product_image(text)
        if img_url: img(img_url)
        save_conversation_log(sender_id, text, ai_text, sentiment, current_prod)
        return actions

    # ── Fallback ──
    fallback_msg = "ধন্যবাদ! 😊 বিস্তারিত জানতে লিখুন:\n\"চুড়ি\" | \"সেট\" | \"পায়েল\" | \"দাম\" | \"অর্ডার\""
    txt(fallback_msg)
    save_conversation_log(sender_id, text, fallback_msg, "General", current_prod)
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
# ADMIN ROUTES
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
    orders  = get_all_orders()
    logs    = get_all_logs()
    pending = {k:v for k,v in pending_approvals.items() if v["status"]=="pending"}
    stats   = {"total":bot_state["total"],"replied":bot_state["replied"],
               "orders":len(orders),"keywords":len(load_replies()),
               "pending":len(pending), "logs": len(logs)}
    return render_template("admin.html", bot_active=bot_state["active"],
                           stats=stats, orders=orders, logs=logs, pending=pending,
                           msg=request.args.get("msg"))

@app.route("/admin/toggle", methods=["POST"])
@login_required
def admin_toggle():
    bot_state["active"] = not bot_state["active"]
    s = "চালু" if bot_state["active"] else "বন্ধ"
    return redirect(url_for("admin_dashboard", msg=f"Bot {s} করা হয়েছে!"))

# ── Approval ──
@app.route("/admin/approval/approve/<ap_id>", methods=["POST"])
@login_required
def approval_approve(ap_id):
    ap = pending_approvals.get(ap_id)
    if ap and ap["status"] == "pending":
        ap["status"] = "approved"
        sid = ap["sender_id"]
        if sid in user_sessions: user_sessions[sid]["state"] = ASK_DOZON
        msg = (f"সুখবর! সাইজ {ap['size']} এর চুড়ি এভেলেবল আছে স্যার/ম্যাডাম! ✅\n\n"
               f"১ ডজন (১২ পিস) → ৳৬৫০ 🎁 ৪ পিস ঘুগুর ফ্রি + ফ্রি ডেলিভারি\n"
               f"২ ডজন (২৪ পিস) → ৳১,১০০ 🎁 ৮ পিস ঘুগুর ফ্রি + ফ্রি ডেলিভারি\n\n\"১\" বা \"২\" লিখুন:")
        send_text(sid, msg)
        save_conversation_log(sid, "System Approved", msg, "Good", ap.get("product",""))
        return redirect(url_for("admin_dashboard", msg="Approved! Customer কে জানানো হয়েছে।"))
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/approval/reject/<ap_id>", methods=["POST"])
@login_required
def approval_reject(ap_id):
    ap = pending_approvals.get(ap_id)
    if ap and ap["status"] == "pending":
        ap["status"] = "rejected"
        sid = ap["sender_id"]
        user_sessions.pop(sid, None)
        msg = (f"এই সাইজের ({ap['size']}) চুড়ি আমাদের কাছে এই মুহূর্তে স্টক আউট স্যার/ম্যাডাম 😔\n"
               f"স্টক আসলে আপনাকে জানানো হবে ইনশাআল্লাহ!\n\n"
               f"আমাদের এভেলেবল সাইজ: ২৪ / ২৬ / ২৮\n"
               f"💍 চুড়ি → ৳৬৫০ (৪ পিস ঘুগুর ফ্রি + ডেলিভারি ফ্রি) 🎁")
        send_text(sid, msg)
        save_conversation_log(sid, "System Rejected", msg, "Bad", ap.get("product",""))
        return redirect(url_for("admin_dashboard", msg="Rejected! Customer কে স্টক আউট মেসেজ পাঠানো হয়েছে।"))
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
    return redirect(url_for("admin_replies", msg="আপডেট হয়েছে!"))

@app.route("/admin/replies/delete", methods=["POST"])
@login_required
def admin_reply_delete():
    d=load_replies(); d.pop(request.form.get("keyword",""),None); save_replies(d)
    return redirect(url_for("admin_replies", msg="মুছে ফেলা হয়েছে!"))

# ── Products ──
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
    products.append({"id":new_id,"name":request.form.get("name",""),
        "category":request.form.get("category",""),
        "price":int(request.form.get("price",0) or 0),
        "package":request.form.get("package",""),
        "free_gift":request.form.get("free_gift","-"),
        "delivery":request.form.get("delivery","ফ্রি"),
        "colors":colors,"description":request.form.get("description",""),
        "image":request.form.get("image_url","").strip()})
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্য যোগ হয়েছে!"))

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
    return redirect(url_for("admin_products", msg="মুছে ফেলা হয়েছে!"))

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
    if msg.startswith("http") and any(e in msg.lower() for e in [".jpg",".jpeg",".png",".webp"]):
        reply = analyze_product_image(msg)
        save_conversation_log("DEMO_ADMIN", "[IMAGE_SENT]", reply, "General", "")
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

                if "attachments" in msg:
                    for att in msg["attachments"]:
                        if att.get("type")=="image":
                            url   = att["payload"].get("url","")
                            reply = analyze_product_image(url, PAGE_ACCESS_TOKEN)
                            send_text(sid, reply)
                            save_conversation_log(sid, "[IMAGE_ATTACHMENT]", reply, "General", "Image Search")
                            if "চুড়ি" in reply or "বাংলস" in reply:
                                send_text(sid, "এটা নিতে চাইলে হাতের মাপ জানান স্যার/ম্যাডাম: ২৪ / ২৬ / ২৮")
                                user_sessions[sid] = {"state":ASK_SIZE,"product":"কাশ্মীরি চুড়ি (১ ডজন)","color":""}
                        else:
                            send_text(sid, "ধন্যবাদ! কিছু জানতে চাইলে text এ লিখুন। 😊")
                    bot_state["replied"] += 1

                elif "text" in msg:
                    text    = msg["text"]
                    actions = process_message(sid, text)
                    for act in actions:
                        if act["type"]=="text": send_text(sid, act["content"])
                        elif act["type"]=="image": send_image(sid, act["content"])
                    bot_state["replied"] += 1

    return "OK",200


@app.route("/")
def home():
    return jsonify({"bot":"Bella Basket Bot","active":bot_state["active"],"admin":"/admin"})

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    print("="*50)
    print("  Bella Basket Bot — Intelligent AI & Excel Logging Active")
    print(f"  Admin: http://localhost:{port}/admin")
    print(f"  Chat:  http://localhost:{port}/admin/chat")
    print("="*50)
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
