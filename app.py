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
                   redirect, url_for, session, send_from_directory)
from werkzeug.utils import secure_filename
from functools import wraps
from dotenv import load_dotenv
from order_manager import (save_order, get_all_orders, save_conversation_log,
                           get_all_logs, update_conversation_log, delete_conversation_log,
                           find_order_by_id_or_mobile, update_order_status)
from ai_handler import (analyze_and_reply, get_ai_reply_simple, analyze_product_image,
                        analyze_audio_attachment, get_keyword_product_image, get_keyword_product_images_list)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "bella_basket_2024")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100 MB limit (allows 15+ high-res images)

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "admin1234")
BKASH_NUMBER      = "01937281260"
WEBSITE           = "bellabasket.store"

DATA_DIR      = os.path.join(os.path.dirname(__file__), "data")
REPLIES_FILE  = os.path.join(DATA_DIR, "replies.json")
PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")

# ── States ──
IDLE              = "IDLE"
ASK_COLOR_CHOICE  = "ASK_COLOR_CHOICE"  # Product pics shown -> Ask favorite color
ASK_COLOR_SIZE    = "ASK_COLOR_SIZE"
ASK_SIZE          = "ASK_SIZE"
WAIT_APPROVAL = "WAIT_APPROVAL"
ASK_DOZON     = "ASK_DOZON"
ASK_ANYTHING_ELSE = "ASK_ANYTHING_ELSE"
WAIT_ADVANCE  = "WAIT_ADVANCE"   # > 2 dozen advance payment
ASK_CHECKOUT_DETAILS = "ASK_CHECKOUT_DETAILS" # 1-message Name, Mobile, Address checkout
ASK_UPSELL        = "ASK_UPSELL"        # Post-confirmation complementary product recommendation
ASK_NAME      = "ASK_NAME"
ASK_MOBILE    = "ASK_MOBILE"
ASK_ADDRESS   = "ASK_ADDRESS"
ASK_THANA     = "ASK_THANA"
ASK_PAYMENT   = "ASK_PAYMENT"

SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
CHATS_FILE    = os.path.join(DATA_DIR, "chat_history.json")

def load_sessions():
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[SESSION LOAD ERROR] {e}")
    return {}

def save_sessions_to_file():
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(user_sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[SESSION SAVE ERROR] {e}")

# ── Runtime ──
bot_state        = {"active": True, "total": 0, "replied": 0}
user_sessions    = load_sessions()   # Persistent across bot restarts
user_product     = {}   # {sender_id: product_name}
pending_approvals= {}   # {approval_id: {...}}
user_no_count    = {}   # persuasion tracking {sender_id: count}
user_chat_history= {}   # {sender_id: [{"role": "user"|"bot", "text": "...", "time": "..."}]}

def add_chat_history(sender_id, role, text):
    if sender_id not in user_chat_history:
        user_chat_history[sender_id] = []
    user_chat_history[sender_id].append({
        "role": role,
        "text": text,
        "time": datetime.now().strftime("%H:%M:%S")
    })
    if len(user_chat_history[sender_id]) > 20:
        user_chat_history[sender_id] = user_chat_history[sender_id][-20:]
    save_sessions_to_file()

def get_recent_history(sender_id, limit=10):
    msgs = user_chat_history.get(sender_id, [])[-limit:]
    if not msgs:
        return ""
    formatted = []
    for m in msgs:
        prefix = "Customer: " if m["role"] == "user" else "Bella (AI): "
        formatted.append(f"{prefix}{m['text']}")
    return "\n".join(formatted)


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
    "কাশ্মীরি চুড়ি (১ ডজন)": ["কাশ্মীরি","চুড়ি","চুড়ি","বাংলস","১২","ডজন","churi","chury","bangle","bangles"],
    "কাশ্মীরি চুড়ি (২ ডজন)": ["২৪ পিস","দুই ডজন","2 dozon","2 dojon","2 dozen"],
    "বাটারফ্লাই ব্লিস জুয়েলারি সেট": ["বাটারফ্লাই","butterfly"],
    "লাভ ব্লিস জুয়েলারি সেট":  ["লাভ ব্লিস","love bliss"],
    "স্নেক গোল্ড পায়েল":       ["পায়েল","পায়েল","গোল্ড পায়েল","গোল্ড পায়েল","স্নেক","payel","payal","snake payel","নূপুর","nupur"],
}
COLORS = ["মিক্সড","ব্ল্যাক","পেল হোয়াইট","রেড","পেস্তা গ্রিন",
          "ব্লু","পার্পল","পিংক","মিন্ট","ডার্ক অ্যাশ",
          "ডার্ক গ্রিন","ডার্ক পিংক","গোল্ডেন"]

COLOR_MAP = {
    "মিক্সড": ["মিক্সড", "মিক্স", "mix", "mixed", "rainbow", "সব কালার", "সবগুলো"],
    "ব্ল্যাক": ["ব্ল্যাক", "কালো", "black"],
    "পেল হোয়াইট": ["পেল হোয়াইট", "সাদা", "হোয়াইট", "white"],
    "রেড": ["রেড", "লাল", "red"],
    "পেস্তা গ্রিন": ["পেস্তা গ্রিন", "পেস্তা", "pesta", "pistachio"],
    "ব্লু": ["ব্লু", "নীল", "blue", "sky blue"],
    "পার্পল": ["পার্পল", "বেগুনী", "বেগুনি", "purple"],
    "পিংক": ["পিংক", "গোলাপী", "গোলাপি", "pink"],
    "মিন্ট": ["মিন্ট", "mint"],
    "ডার্ক অ্যাশ": ["ডার্ক অ্যাশ", "অ্যাশ", "ash", "grey", "gray"],
    "ডার্ক গ্রিন": ["ডার্ক গ্রিন", "সবুজ", "green", "dark green"],
    "ডার্ক পিংক": ["ডার্ক পিংক", "dark pink", "baby pink"],
    "গোল্ডেন": ["গোল্ডেন", "সোনালী", "সোনালি", "golden", "gold"]
}

def detect_color(text):
    tl = text.lower()
    for standard_col, aliases in COLOR_MAP.items():
        if any(a in tl for a in aliases):
            return standard_col
    for c in COLORS:
        if c.lower() in tl:
            return c
    return None
ORDER_WORDS  = [
    "অর্ডার করব","অর্ডার করবো","নিতে চাই","কিনতে চাই","কিনব","কিনবো","অর্ডার","নেব","নেবো","বুক","বুকিং",
    "order","nite chai","kinte chai","order korbo","order korte chai","kinbo","nebo","lagbe","nibo",
    "order debo","order dibo","nite chassilam","order kora jabe","order confirmation","confirm korte chai"
]
CANCEL_WORDS = ["বাতিল","cancel","দরকার নেই","না থাক","বাদ দাও","দরকার নাই"]
NEGATIVE_WORDS = [
    "না","নাই","দরকার নাই","দরকার নেই","interest নেই","পরে","চাই না","কিনব না","কিনবো না",
    "নিব না","নিবো না","নেব না","নেবো না","লাগবে না","থাকুক","দাম বেশি",
    # Banglish variants
    "nibo na","nebo na","kinbo na","lagbe na","dorkar nai","dorkar nei",
    "chai na","no","nah","nope","not interested","cancel","bad dao"
]

def is_churi(text):
    tl = text.lower()
    return any(k in tl for k in ["চুড়ি","চুড়ি","বাংলস","কাশ্মীরি","churi","chury","bangle","bangles"])

def is_payal(text):
    tl = text.lower()
    return any(k in tl for k in ["পায়েল","পায়েল","payel","payal","pael","নূপুর","nupur","স্নেক","snake"])

def is_set(text):
    tl = text.lower()
    if any(k in tl for k in ["বাটারফ্লাই","butterfly","লাভ ব্লিস","love bliss","নেকলেস","necklace","জুয়েলারি","jewelry","jewellery"]):
        return True
    if any(k in tl for k in ["সেট","set"]):
        if is_churi(text) or is_payal(text):
            return False
        return True
    return False

BN_NUM_MAP = {
    "এক": 1, "১": 1, "one": 1, "1": 1, "একটা": 1, "একটি": 1,
    "দুই": 2, "২": 2, "two": 2, "2": 2, "দুইটা": 2, "দুটি": 2, "দুটো": 2,
    "তিন": 3, "৩": 3, "three": 3, "3": 3, "তিনটা": 3, "তিনটি": 3,
    "চার": 4, "৪": 4, "four": 4, "4": 4, "চারটা": 4, "চারটি": 4,
    "পাঁচ": 5, "৫": 5, "five": 5, "5": 5, "পাঁচটা": 5, "পাঁচটি": 5,
    "ছয়": 6, "৬": 6, "six": 6, "6": 6, "ছয়টা": 6,
}

def extract_quantity_for_product(text, product):
    tl = text.lower()
    unit = product.get("unit_name", "পিস")
    
    unit_synonyms = [unit.lower()]
    if unit == "ডজন":
        unit_synonyms.extend(["dozon", "dozen", "dojon", "ডজন"])
    elif unit == "সেট":
        unit_synonyms.extend(["set", "সেট"])
    elif unit == "জোড়া":
        unit_synonyms.extend(["jora", "pair", "জোড়া", "জোড়া"])
    elif unit == "পিস":
        unit_synonyms.extend(["pcs", "pc", "piece", "পিস", "টা", "টি", "ta", "ti"])
        
    for u in unit_synonyms:
        m = re.search(rf'(\d+)\s*{re.escape(u)}', tl)
        if m:
            try: return int(m.group(1))
            except: pass
            
        for word, val in BN_NUM_MAP.items():
            if f"{word} {u}" in tl or f"{word}{u}" in tl:
                return val
                
    for kw in product.get("keywords", []):
        m = re.search(rf'(\d+)\s*(?:ta|টি|টা)?\s*{re.escape(kw.lower())}', tl)
        if m:
            try: return int(m.group(1))
            except: pass
        for word, val in BN_NUM_MAP.items():
            if f"{word} {kw.lower()}" in tl or f"{word}টা {kw.lower()}" in tl:
                return val
                
    return 1

def detect_products_list(text):
    tl = text.lower()
    products = load_products()
    found = []
    
    for p in products:
        p_name = p["name"]
        keywords = p.get("keywords", [])
        
        matched = False
        for kw in keywords:
            kw_l = kw.lower()
            if kw_l in ["সেট", "set"]:
                if any(c in tl for c in ["চুড়ি", "চুড়ি", "churi", "বাংলস"]):
                    continue
            if kw_l in tl:
                matched = True
                break
                
        if not matched and p_name.lower() in tl:
            matched = True
            
        if matched:
            base_cat = p.get("category", "")
            if base_cat == "চুড়ি":
                has_two_doz = any(k in tl for k in ["২ ডজন", "2 dozen", "2 dozon", "2 dojon", "২৪ পিস", "2 set", "২ সেট", "দুই ডজন"])
                if has_two_doz and "২ ডজন" not in p_name:
                    continue
                if not has_two_doz and "২ ডজন" in p_name:
                    continue
                    
            qty = extract_quantity_for_product(text, p)
            item = dict(p)
            item["qty"] = qty
            item["total_price"] = p["price"] * qty if "চুড়ি" not in base_cat else p["price"]
            found.append(item)
            
    return found

def detect_product(text):
    prods = detect_products_list(text)
    if prods:
        return prods[0]["name"]
    return None

def is_order_intent(text):
    return any(k.lower() in text.lower() for k in ORDER_WORDS)

def is_cancel(text):
    return any(k in text.lower() for k in CANCEL_WORDS)

def is_negative(text):
    tl = text.lower().strip()
    return any(k in tl for k in NEGATIVE_WORDS) or tl in ["না","na","nah","nope","no"]

def is_price_inquiry(text):
    tl = text.lower()
    price_kws = ["দাম", "মূল্য", "কত", "টাকা", "price", "dam", "koto", "rate", "cost", "খরচ"]
    return any(k in tl for k in price_kws)

def is_pic_inquiry(text):
    tl = text.lower()
    pic_kws = ["ছবি", "pic", "photo", "picture", "দেখান", "দেখাও", "দেখতে চাই", "দেখবো", "dekhte chai", "dekhaw", "dekhan", "show", "dekhi", "দেখি", "কালারগুলো", "colors"]
    return any(k in tl for k in pic_kws)

HESITATION_WORDS = [
    "দাম বেশি", "dam beshi", "dam besi", "expensive", "posondo hoy ni",
    "পছন্দ হয়নি", "পছন্দ হয় নাই", "পছন্দ না", "ভালো না", "valo na",
    "bhabtesi", "ভাবছি", "পরে জানাব", "pore janabo", "পরে নিব", "pore nebo"
]

def is_hesitation(text):
    tl = text.lower()
    return any(k in tl for k in HESITATION_WORDS)

QUESTION_WORDS = [
    "কি", "কী", "কবে", "কখন", "কোথায়", "কোথায়", "কয়দিন", "কয়দিন", "কত", "কেমন",
    "কেন", "হবে", "আছেন", "আছে", "দোকান", "ডেলিভারি", "কুরিয়ার", "কুরিয়ার",
    "লোকেশন", "ঠিকানা", "চার্জ", "পেমেন্ট", "বিকাশ", "ক্যাশ", "চেক", "সময়", "সময়",
    "অরিজিনাল", "কোয়ালিটি",
    "ki", "kobe", "kothay", "kivabe", "koto", "ache", "hobe", "dokan",
    "delivery", "courier", "cash on", "advance", "somoy", "location", "address", "quality"
]

def is_question(text):
    tl = text.lower().strip()
    if "?" in text or "？" in text:
        return True
    return any(w in tl for w in QUESTION_WORDS)

user_state_retries = {}

def get_retry_count(sender_id, state):
    rec = user_state_retries.get(sender_id, {})
    if rec.get("state") == state:
        c = rec.get("count", 0) + 1
        user_state_retries[sender_id] = {"state": state, "count": c}
        return c
    else:
        user_state_retries[sender_id] = {"state": state, "count": 1}
        return 1

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

def extract_checkout_info(text):
    """
    একক মেসেজ থেকে নাম, মোবাইল নম্বর এবং সম্পূর্ণ ডেলিভারি ঠিকানা পার্স করে।
    """
    clean_text = text.strip()
    mobile = None
    name = None
    address = None

    # 1. Find mobile (11-digit Bangladesh mobile number starting with 01)
    raw_m = re.search(r'(?:\+?88)?(01[3-9][0-9\s\-]{8,12})\b', clean_text)
    if raw_m:
        digits = re.sub(r'\D', '', raw_m.group(1))
        if len(digits) == 11 and digits.startswith('01'):
            mobile = digits

    text_wo_mobile = re.sub(r'(?:\+?88)?01[3-9][0-9\s\-]{8,12}\b', '', clean_text).strip()

    # 2. Check labelled format (e.g., নাম: ..., ঠিকানা: ...)
    name_m = re.search(r'(?:নাম|name)\s*[:=–-]?\s*([^\n,]+)', clean_text, re.IGNORECASE)
    addr_m = re.search(r'(?:ঠিকানা|address|thana|থানা|জেলা)\s*[:=–-]?\s*(.+)', clean_text, re.IGNORECASE | re.DOTALL)
    if name_m:
        name = name_m.group(1).strip()
    if addr_m:
        addr_val = addr_m.group(1).strip()
        addr_val = re.sub(r'(?:নাম|name|মোবাইল|mobile|phone)\s*[:=–-]?.*', '', addr_val, flags=re.IGNORECASE).strip()
        if addr_val:
            address = addr_val

    # 3. Fallback unlabelled (split by newlines or commas)
    if not name or not address:
        lines = [l.strip() for l in re.split(r'[\n,]+', text_wo_mobile) if l.strip()]
        clean_lines = []
        for l in lines:
            l_sub = re.sub(r'^(?:নাম|name|মোবাইল|mobile|phone|ঠিকানা|address)\s*[:=–-]?\s*', '', l, flags=re.IGNORECASE).strip()
            if l_sub:
                clean_lines.append(l_sub)

        if len(clean_lines) >= 2:
            if not name:
                name = clean_lines[0]
            if not address:
                address = ', '.join(clean_lines[1:])
        elif len(clean_lines) == 1:
            if not name:
                name = clean_lines[0]
            elif not address:
                address = clean_lines[0]

    return {'name': name, 'mobile': mobile, 'address': address}


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
    if url.startswith("/"):
        url = request.host_url.rstrip("/") + url
    _fb({"recipient":{"id":rid},"message":{
        "attachment":{"type":"image","payload":{"url":url,"is_reusable":True}}
    },"messaging_type":"RESPONSE"})

def send_typing(rid):
    _fb({"recipient":{"id":rid},"sender_action":"typing_on"})

user_profile_cache = {}

def get_user_profile(sender_id):
    """
    Facebook Graph API দিয়ে কাস্টমারের প্রোফাইল থেকে আসল ফার্স্ট নেম বা পুরো নাম নিয়ে আসে।
    """
    if not sender_id or sender_id in ["DEMO_ADMIN", "test_user"]:
        return None
    if sender_id in user_profile_cache:
        return user_profile_cache[sender_id]
    try:
        url = f"https://graph.facebook.com/v21.0/{sender_id}"
        r = requests.get(url, params={
            "fields": "first_name,last_name,name",
            "access_token": PAGE_ACCESS_TOKEN
        }, timeout=5)
        if r.status_code == 200:
            data = r.json()
            fname = data.get("first_name") or data.get("name")
            if fname:
                user_profile_cache[sender_id] = fname.strip()
                return fname.strip()
    except Exception as e:
        print(f"[GRAPH API PROFILE ERR] {e}")
    return None


# ====================================================
# CUSTOM REPLIES HELPER (Admin Editor Integration)
# ====================================================
def get_custom_reply(text):
    """
    Checks if text matches an exact keyword configured in /admin/replies.
    Only triggers on exact keyword matches (e.g. 'দাম', 'যোগাযোগ') so the AI agent
    handles all natural conversational sentences and questions freely.
    """
    try:
        replies = load_replies()
        if not replies: return None
        tl = text.strip().lower()
        for k, v in replies.items():
            if k.strip().lower() == tl:
                return v
    except Exception as e:
        print(f"[CUSTOM REPLY ERROR] {e}")
    return None


# ====================================================
# MAIN PROCESS MESSAGE ENGINE (AI INTEGRATED)
# ====================================================
def process_message(sender_id, text):
    """
    Returns list of actions: [{"type":"text"/"image","content":"..."}]
    Supports:
    - Multi-product shopping cart (1, 2, 3, 4+ products) with automated price summation
    - Cross-selling (suggesting Payel/Set when buying Churi, and vice-versa)
    - Alternative product recommendation when customer hesitates or refuses
    - Admin custom reply lookup (from /admin/replies)
    - "পার্সেলটি রিসিভ করে নিবেন" order confirmation
    - Gemini AI evaluation & Excel logging
    """
    actions = []
    sd      = user_sessions.get(sender_id, {"state": IDLE, "cart": []})
    state   = sd.get("state", IDLE)

    def txt(msg):
        actions.append({"type":"text","content":msg})
        add_chat_history(sender_id, "bot", msg)

    def img(url): actions.append({"type":"image","content":url})

    def handle_product_inquiry(inquiry_prods=None):
        prods = inquiry_prods if inquiry_prods is not None else detect_products_list(text)
        if prods:
            all_imgs = []
            prod_details = []
            tot_est = 0
            for p in prods:
                p_name = p["name"]
                p_price = p.get("price", 0)
                p_qty = p.get("qty", 1)
                p_unit = p.get("unit_name", "পিস")
                tot_est += p_price * p_qty
                p_imgs = p.get("images") or get_keyword_product_images_list(p_name) or get_keyword_product_images_list(p.get("category", ""))
                if p_imgs:
                    all_imgs.extend(p_imgs)
                gift_text = f" + {p['free_gift']}" if p.get("free_gift") and p.get("free_gift") != "-" else ""
                prod_details.append(f"✨ {p_name} — ৳{p_price:,} ({p.get('package','')}{gift_text})")

            # Send all images for detected products
            for u in all_imgs:
                img(u)

            details_str = "\n".join(prod_details)
            has_churi_inquiry = any(is_churi(p["name"]) or p.get("category") == "চুড়ি" for p in prods)

            if len(prods) > 1:
                reply_msg = (
                    f"স্যার/ম্যাডাম দেখুন, কোনটি আপনার পছন্দ হয়? 😊\n"
                    f"আমাদের কালেকশনগুলোর ছবি ও বিস্তারিত দেওয়া হলো:\n\n"
                    f"{details_str}\n\n"
                    f"🚚 আজ সারা বাংলাদেশে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!\n"
                )
                if has_churi_inquiry:
                    user_sessions[sender_id] = {
                        "state": ASK_COLOR_CHOICE,
                        "product": "কাশ্মীরি চুড়ি (১ ডজন)",
                        "cart": []
                    }
                    reply_msg += "\nআমাদের চুড়ির কালেকশনের কোন কালারটি আপনার পছন্দ হয়েছে জানাবেন প্লিজ! 💖"
                else:
                    reply_msg += "\nকোনটি কোনটি আপনার পছন্দ হয়েছে জানাবেন প্লিজ! 😊"
            else:
                single_item = prods[0]
                if has_churi_inquiry:
                    user_sessions[sender_id] = {
                        "state": ASK_COLOR_CHOICE,
                        "product": single_item["name"],
                        "cart": []
                    }
                    reply_msg = (
                        "স্যার/ম্যাডাম দেখুন, কোনটি আপনার পছন্দ হয়? 😊 আমাদের এই কালেকশনের কোন কালারটি আপনার পছন্দ হয়েছে জানাবেন প্লিজ!\n\n"
                        f"💰 ১ ডজন মাত্র ৳৬৫০ (🎁 সাথে ৪ পিস ঘুঙুর একদম ফ্রি + ডেলিভারি ফ্রি 🚚)\n"
                        f"💰 ২ ডজন মাত্র ৳১,১০০ (🎁 সাথে ৮ পিস ঘুঙুর ফ্রি + ডেলিভারি ফ্রি 🚚)"
                    )
                else:
                    user_product[sender_id] = single_item["name"]
                    user_sessions[sender_id] = {
                        "state": IDLE,
                        "product": single_item["name"],
                        "cart": []
                    }
                    gift_text = f" (🎁 {single_item['free_gift']})" if single_item.get("free_gift") and single_item.get("free_gift") != "-" else ""
                    delivery_text = f"🚚 ডেলিভারি: {single_item.get('delivery', 'ফ্রি')}"
                    reply_msg = (
                        f"স্যার/ম্যাডাম দেখুন, কোনটি আপনার পছন্দ হয়? 😊\n\n"
                        f"✨ {single_item['name']} ({single_item.get('package','১ পিস')})\n"
                        f"💰 অফার মূল্য: মাত্র ৳{single_item['price']:,}{gift_text}\n"
                        f"{delivery_text}\n\n"
                        f"পণ্যটি কি আপনার পছন্দ হয়েছে? অর্ডার করতে চাইলে জানাবেন প্লিজ! 😊\n"
                        f"(অথবা সাথে আমাদের কাশ্মীরি চুড়িও দেখতে পারেন)"
                    )

            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, ", ".join([p["name"] for p in prods]))
            return actions
        else:
            # Fallback churi visual funnel if customer just says "dam koto" or "pic"
            user_sessions[sender_id] = {
                "state": ASK_COLOR_CHOICE,
                "product": "কাশ্মীরি চুড়ি (১ ডজন)",
                "cart": []
            }
            imgs = get_keyword_product_images_list("চুড়ি")
            if imgs:
                for u in imgs: img(u)
            reply_msg = (
                "স্যার/ম্যাডাম দেখুন, কোনটি আপনার পছন্দ হয়? 😊 আমাদের এই কালেকশনের কোন কালারটি আপনার পছন্দ হয়েছে জানাবেন প্লিজ!\n\n"
                "💰 ১ ডজন মাত্র ৳৬৫০ (🎁 সাথে ৪ পিস ঘুঙুর একদম ফ্রি + ডেলিভারি ফ্রি 🚚)\n"
                "💰 ২ ডজন মাত্র ৳১,১০০ (🎁 সাথে ৮ পিস ঘুঙুর ফ্রি + ডেলিভারি ফ্রি 🚚)"
            )
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, "কাশ্মীরি চুড়ি (১ ডজন)")
            return actions

    # Track product interest
    prod = detect_product(text)
    if prod: user_product[sender_id] = prod
    current_prod = user_product.get(sender_id, sd.get("product", ""))

    # Record user message in memory and get recent 10 messages for AI context
    add_chat_history(sender_id, "user", text)
    chat_hist = get_recent_history(sender_id, limit=10)

    # ── Gemini AI Evaluation (Reads last 10 messages of conversation history) ──
    ai_res = analyze_and_reply(text, current_state=state, product_context=current_prod, chat_history=chat_hist)
    sentiment = ai_res.get("sentiment", "General") if ai_res else "General"
    ai_text   = ai_res.get("reply_text") if ai_res else None

    # AI Detected attributes
    ai_size  = ai_res.get("detected_size") if ai_res else None
    ai_dozen = ai_res.get("detected_dozen") if ai_res else None
    ai_prod  = ai_res.get("detected_product") if ai_res else None
    intent   = ai_res.get("intent", "OTHER") if ai_res else "OTHER"

    # ── Universal Cancel Check ──
    if is_cancel(text):
        user_sessions.pop(sender_id, None)
        user_no_count.pop(sender_id, None)
        reply_msg = "ঠিক আছে, অর্ডার বাতিল করা হয়েছে। আপনার যখন ইচ্ছে আমাদের জানাবেন! 😊"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── Universal Greeting Check ──
    # কাস্টমার যেকোনো অবস্থায় শুধু 'hi', 'hello', 'সালাম' ইত্যাদি বললে
    clean_txt = text.strip().lower()
    is_pure_greeting = clean_txt in ["hi", "hello", "hlw", "hy", "hey", "হাই", "হ্যালো", "সালাম", "assalamualaikum", "salam", "start", "শুরু", "মেনু", "menu"]
    if is_pure_greeting:
        c_name = get_user_profile(sender_id)
        name_part = f" {c_name}" if c_name else ""
        if not sd.get("cart"):
            user_sessions.pop(sender_id, None)
            welcome_msg = (
                f"আসসালামু আলাইকুম{name_part} আপু/ভাইয়া! 💖\n"
                f"আপনাকে আমাদের Bella Basket Jewelry-তে পেয়ে খুব আনন্দিত হলাম। 🌸\n\n"
                f"আপনি আমাদের কোন পণ্যটি দেখতে বা নিতে ইচ্ছুক? (যেমন: কাশ্মীরি চুড়ি, স্নেক গোল্ড পায়েল, নাকি বাটারফ্লাই জুয়েলারি সেট?) 😊"
            )
            txt(welcome_msg)
            save_conversation_log(sender_id, text, welcome_msg, "Good", "Welcome Greeting")
            return actions
        else:
            cart_msg = (
                f"আসসালামু আলাইকুম{name_part} আপু/ভাইয়া! 💖\n"
                f"আপনার কার্টে পণ্য যুক্ত রয়েছে। অর্ডারটি কনফার্ম করতে আপনার ডেলিভারির পুরো নাম, মোবাইল নম্বর ও ঠিকানা জানিয়ে দিন প্লিজ 😊\n"
                f"(অথবা নতুন করে শুরু করতে চাইলে 'বাতিল' লিখুন)"
            )
            txt(cart_msg)
            save_conversation_log(sender_id, text, cart_msg, "Good", current_prod)
            return actions

    # ── Universal Refusal / Alternative Suggestion (breaks loops in ANY state like ASK_COLOR_SIZE) ──
    if state not in (ASK_ANYTHING_ELSE, ASK_UPSELL) and (is_negative(text) or intent == "REFUSAL"):
        user_sessions.pop(sender_id, None)
        no_count = user_no_count.get(sender_id, 0) + 1
        user_no_count[sender_id] = no_count

        if ai_text and any(k in ai_text for k in ["বাটারফ্লাই", "পায়েল", "জুয়েলারি", "অফার", "কোনো সমস্যা নেই", "সমস্যা নেই"]):
            reply_msg = ai_text
        elif no_count == 1:
            reply_msg = (
                "আজকের জন্যই কিন্তু আমাদের এই স্পেশাল অফার এবং ডেলিভারি চার্জ সম্পূর্ণ ফ্রি চলছে স্যার/ম্যাডাম! 😊\n"
                "ক্যাশ অন ডেলিভারিতে চেক করে নেওয়ার সুযোগ আছে। চুড়ি না নিতে চাইলে আমাদের সুন্দর বাটারফ্লাই জুয়েলারি সেট (৳৬৫০) অথবা স্নেক গোল্ড পায়েল (৳৩৫০) দেখতে পারেন।\n\n"
                "কোনোটি দেখতে চান কি?"
            )
        else:
            reply_msg = (
                "কোনো সমস্যা নেই স্যার/ম্যাডাম! 😊\n"
                "আমাদের কাছে জনপ্রিয় অন্য পণ্যগুলো দেখতে পারেন:\n"
                "✨ বাটারফ্লাই ব্লিস জুয়েলারি সেট — ৳৬৫০ (ডেলিভারি ফ্রি)\n"
                "✨ স্নেক গোল্ড পায়েল — মাত্র ৳৩৫০ (ডেলিভারি ফ্রি)\n\n"
                "কোনোটির ছবি বা বিস্তারিত দেখতে চান কি?"
            )
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, "Bad", current_prod)
        return actions

    # ══════════════════════════════════════════
    # ORDER STATE MACHINE
    # ══════════════════════════════════════════

    # ── ASK_COLOR_CHOICE: ছবির পর কাস্টমারের পছন্দের কালার জানা ও চুড়ির দাম বলা ──
    if state == ASK_COLOR_CHOICE:
        matched_prods = detect_products_list(text)
        has_non_churi = any(not is_churi(p["name"]) and p.get("category") != "চুড়ি" for p in matched_prods)
        # কাস্টমার যদি অন্য কোনো পণ্য (যেমন পায়েল, জুয়েলারি সেট) বা পণ্যের ছবি দেখতে চায়
        wants_pics = is_pic_inquiry(text) and not detect_color(text) and not detect_size(text) and not is_order_intent(text)
        if has_non_churi or (wants_pics and matched_prods):
            return handle_product_inquiry(matched_prods)

        # 1. কাস্টমার যদি কালার পছন্দ না করে সরাসরি দাম জানতে চায় ("price ta bolen", "dam koto", "দাম কত")
        if is_price_inquiry(text):
            reply_msg = (
                "আমাদের কাশ্মীরি চুড়ির অফার মূল্য:\n"
                "• ১ ডজন (১২ পিস) — মাত্র ৳৬৫০ (🎁 সাথে ৪ পিস ঘুঙুর একদম ফ্রি!)\n"
                "• ২ ডজন (২৪ পিস) — মাত্র ৳১,১০০ (🎁 সাথে ৮ পিস ঘুঙুর ফ্রি!)\n\n"
                "🚚 আজ সারা বাংলাদেশে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!\n\n"
                "স্যার/ম্যাডাম, আপনার কোন কালারটি এবং হাতের সাইজ (২৪ / ২৬ / ২৮) পছন্দ হয়েছে জানাবেন প্লিজ? 😊"
            )
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # 2. কাস্টমার কালার জানিয়েছে বা সাইজ/ডজন জানিয়েছে -> চুড়ির দাম ও অফার বলা
        color = detect_color(text) or (ai_res.get("detected_color") if ai_res else None)
        size  = ai_size or detect_size(text)
        raw_dozen = ai_dozen or detect_dozon_count(text)

        if color or (size in VALID_SIZES) or raw_dozen:
            if color:
                sd["color"] = color

            # If both size and dozen are provided right away -> Direct to 1-message checkout
            if size in VALID_SIZES and raw_dozen:
                try:
                    dozon_count = int(raw_dozen)
                except (ValueError, TypeError):
                    dozon_count = detect_dozon_count(text)

                if dozon_count:
                    sd["size"] = size
                    sd["dozon"] = str(dozon_count)
                    chosen_color = sd.get("color") or color or "মিক্সড"
                    info = get_dozon_info(sd.get("product","কাশ্মীরি চুড়ি"), str(dozon_count))
                    cart = [{
                        "product": sd.get("product", "কাশ্মীরি চুড়ি"),
                        "color": chosen_color,
                        "size": size,
                        "pieces": info["pieces"],
                        "price": info["price"],
                        "gift": info["gift_str"],
                        "details": f"সাইজ: {size}, রঙ: {chosen_color}, {info['pieces']} পিস"
                    }]
                    sd["cart"] = cart
                    sd["state"] = ASK_CHECKOUT_DETAILS
                    user_sessions[sender_id] = sd
                    curr_tot = info["price"]
                    reply_msg = (
                        f"✅ {sd.get('product','চুড়ি')} ({info['pieces']} পিস) নিশ্চিত করা হয়েছে! 🎁 {info['gift_str']}\n"
                        f"💰 সর্বমোট বিল: ৳{curr_tot:,} (ডেলিভারি চার্জ একদম ফ্রি 🚚)\n\n"
                        f"অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
                        f"• নাম:\n"
                        f"• মোবাইল নম্বর:\n"
                        f"• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
                        f"একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
                    )
                    txt(reply_msg)
                    save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
                    return actions

            sd["state"] = ASK_DOZON if size else ASK_SIZE
            if size:
                sd["size"] = size
            user_sessions[sender_id] = sd

            color_praise = f"{color} কালারটি " if color else "আপনার পছন্দটি "
            reply_msg = (
                f"দারুণ পছন্দ! {color_praise}পরলে হাত সত্যিই অসম্ভব সুন্দর লাগবে। 💖\n\n"
                f"✨ আমাদের কাশ্মীরি চুড়ির অফার মূল্য:\n"
                f"• ১ ডজন (১২ পিস) — মাত্র ৳৬৫০ (🎁 সাথে ৪ পিস ঘুঙুর একদম ফ্রি!)\n"
                f"• ২ ডজন (২৪ পিস) — মাত্র ৳১,১০০ (🎁 সাথে ৮ পিস ঘুঙুর ফ্রি!)\n\n"
                f"🚚 আজ সারা বাংলাদেশে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!\n\n"
            )
            if not size:
                reply_msg += "আপনার হাতের মাপ কত? (২৪ / ২৬ / ২৮)\nএবং কয় ডজন নিতে চান জানাবেন প্লিজ? 😊"
            else:
                reply_msg += f"সাইজ {size} কনফার্ম! ✅ কয় ডজন নিতে চান? (\"১\" বা \"২\" লিখুন):"

            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # 3. কাস্টমার যদি ইতস্তত করে, দাম বেশি বলে বা পছন্দ হচ্ছে না বলে -> পুশ করা (Push)
        if is_hesitation(text) or sentiment == "Bad":
            no_count = user_no_count.get(sender_id, 0) + 1
            user_no_count[sender_id] = no_count
            if no_count == 1:
                reply_msg = (
                    "আজকের জন্যই কিন্তু আমাদের এই বিশেষ ছাড় ও ফ্রি ডেলিভারি অফার আপু/ভাইয়া! ⏰\n\n"
                    "চুড়ির সাথে পাচ্ছেন ৪/৮ পিস ঘুঙুর একদম ফ্রি এবং ক্যাশ অন ডেলিভারি (পণ্য হাতে পেয়ে দেখে নেওয়ার সুযোগ)। কোনো ঝুঁকি নেই!\n"
                    "একবার নিয়ে দেখুন, কালার ও কোয়ালিটি নিশ্চিত পছন্দ হবে। কোন কালারটি দেখতে চান বলুন তো? 😊"
                )
                txt(reply_msg)
                save_conversation_log(sender_id, text, reply_msg, "General", current_prod)
                return actions
            else:
                user_sessions.pop(sender_id, None)
                reply_msg = (
                    "কোনো সমস্যা নেই আপু/ভাইয়া! 😊 চুড়ি পছন্দ না হলে আমাদের অন্যান্য সেরা জুয়েলারিগুলো দেখতে পারেন:\n\n"
                    "💍 বাটারফ্লাই ব্লিস জুয়েলারি সেট — ৳৬৫০ (ডেলিভারি ফ্রি)\n"
                    "🦶 স্নেক গোল্ড পায়েল — মাত্র ৳৩৫০ (ডেলিভারি ফ্রি)\n\n"
                    "কোনটির ছবি বা বিস্তারিত দেখতে চান জানাবেন!"
                )
                txt(reply_msg)
                save_conversation_log(sender_id, text, reply_msg, "Bad", current_prod)
                return actions

        # 4. কাস্টমার যদি কোনো সাধারণ প্রশ্ন করে (যেমন ডেলিভারি, দোকান ইত্যাদি)
        if is_question(text) or intent == "QUERY":
            ans = ai_text or "আমাদের সব পণ্যে ডেলিভারি সম্পূর্ণ ফ্রি এবং ক্যাশ অন ডেলিভারি সুবিধা রয়েছে! 😊"
            if any(k in ans for k in ["কালার", "রং", "সাইজ", "পছন্দ"]):
                reply_msg = ans
            else:
                reply_msg = f"{ans}\n\nআমাদের চুড়ির কোন কালারটি আপনার পছন্দ হয়েছে বলুন তো? 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions
        # 5. কোনো কালার বা তথ্য না থাকলে বিনম্রভাবে জানতে চাওয়া
        reply_msg = (
            "আমাদের কাশ্মীরি চুড়ির ১৩টি চমৎকার কালার রয়েছে আপু/ভাইয়া! 💖\n"
            "কোন কালারটি আপনার সবচেয়ে পছন্দ হয়েছে বলুন তো? অথবা অন্য কোনো জুয়েলারি কালেকশন দেখতে চাইলে জানাতে পারেন 😊"
        )
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions


    # ── ASK_COLOR_SIZE: কালার এবং সাইজ চাওয়া ──
    if state == ASK_COLOR_SIZE:
        size = ai_size or detect_size(text)
        color = detect_color(text) or sd.get("color", "") or (ai_res.get("detected_color") if ai_res else "")
        if color:
            sd["color"] = color

        if not size:
            if is_question(text) or intent == "QUERY":
                ans = ai_text or "আমাদের চুড়ির সব প্যাকেজেই ডেলিভারি সম্পূর্ণ ফ্রি! 😊"
                reply_msg = f"{ans}\n\nঅর্ডারটি কনফার্ম করার জন্য আপনার হাতের মাপটি (২৪ / ২৬ / ২৮) জানিয়ে দিন প্লিজ 😊"
            else:
                r_count = get_retry_count(sender_id, "ASK_COLOR_SIZE")
                if r_count == 1:
                    reply_msg = f"{color + ' কালার ' if color else ''}দারুণ পছন্দ! কিন্তু সাইজটি বুঝতে পারিনি স্যার/ম্যাডাম 😊\nআমাদের এভেলেবল সাইজ: ২৪ / ২৬ / ২৮\nদয়া করে শুধু সংখ্যায় লিখুন (যেমন: ২৪ বা ২৬):"
                elif r_count == 2:
                    reply_msg = "হাতের সাইজটি জানালে একদম পারফেক্ট মাপের চুড়ি পৌঁছে দিতে পারবো আপু/ভাইয়া! 💖\nআপনার হাতের মাপ অনুযায়ী ২৪, ২৬ অথবা ২৮—কোনটি দিতে হবে বলুন তো?"
                else:
                    reply_msg = "সাধারণত মাঝারি মাপের হাতে ২৬ এবং কিছুটা চিকন হাতে ২৪ সাইজ সুন্দরভাবে ফিট হয়। আপনার কোন সাইজটি লাগবে জানিয়ে দিন প্লিজ 😊"

            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        if size in VALID_SIZES:
            sd["size"]  = size
            dozon_count = ai_dozen or detect_dozon_count(text) or 1
            if dozon_count:
                sd["dozon"] = str(dozon_count)
                chosen_color = sd.get("color") or color or "মিক্সড"
                info = get_dozon_info(sd.get("product","কাশ্মীরি চুড়ি"), str(dozon_count))
                cart = [{
                    "product": sd.get("product", "কাশ্মীরি চুড়ি"),
                    "color": chosen_color,
                    "size": size,
                    "pieces": info["pieces"],
                    "price": info["price"],
                    "gift": info["gift_str"],
                    "details": f"সাইজ: {size}, রঙ: {chosen_color}, {info['pieces']} পিস"
                }]
                sd["cart"] = cart
                sd["state"] = ASK_CHECKOUT_DETAILS
                user_sessions[sender_id] = sd
                curr_tot = info["price"]
                reply_msg = (
                    f"✅ {sd.get('product','চুড়ি')} ({info['pieces']} পিস) নিশ্চিত করা হয়েছে! 🎁 {info['gift_str']}\n"
                    f"💰 সর্বমোট বিল: ৳{curr_tot:,} (ডেলিভারি চার্জ একদম ফ্রি 🚚)\n\n"
                    f"অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
                    f"• নাম:\n"
                    f"• মোবাইল নম্বর:\n"
                    f"• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
                    f"একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
                )
                txt(reply_msg)
                save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
                return actions

            sd["state"] = ASK_DOZON
            user_sessions[sender_id] = sd
            cat = get_category(sd.get("product",""))
            if cat == "churi":
                reply_msg = (f"{color + ' কালার, ' if color else ''}সাইজ {size} কনফার্ম! ✅\n\nকয় ডজন নিতে চান?\n\n"
                             f"১ ডজন (১২ পিস) → ৳৬৫০ 🎁 ৪ পিস ঘুগুর ফ্রি + ফ্রি ডেলিভারি\n"
                             f"২ ডজন (২৪ পিস) → ৳১,১০০ 🎁 ৮ পিস ঘুগুর ফ্রি + ফ্রি ডেলিভারি\n\n"
                             f"\"১\" অথবা \"২\" লিখুন:")
            else:
                reply_msg = f"{color + ' কালার, ' if color else ''}সাইজ {size} কনফার্ম! ✅\nকয় ডজন নিতে চান? (\"১\" বা \"২\" লিখুন):"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        elif size in UNUSUAL_SIZES:
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

    # ── ASK_SIZE: চুড়ির হাতের সাইজ চাওয়া ──
    if state == ASK_SIZE:
        size = ai_size or detect_size(text)
        if not size:
            if is_question(text) or intent == "QUERY":
                ans = ai_text or "আমাদের চুড়ির সব প্যাকেজেই ডেলিভারি সম্পূর্ণ ফ্রি! 😊"
                reply_msg = f"{ans}\n\nঅর্ডারটি কনফার্ম করার জন্য আপনার হাতের মাপটি (২৪ / ২৬ / ২৮) জানিয়ে দিন প্লিজ 😊"
            else:
                r_count = get_retry_count(sender_id, "ASK_SIZE")
                if r_count == 1:
                    reply_msg = "সাইজটি বুঝতে পারিনি স্যার/ম্যাডাম 😊\nআমাদের এভেলেবল সাইজ: ২৪ / ২৬ / ২৮\n\nদয়া করে শুধু সংখ্যায় লিখুন (যেমন: ২৪ বা ২৬):"
                elif r_count == 2:
                    reply_msg = "হাতের সাইজটি জানালে একদম পারফেক্ট মাপের চুড়ি পৌঁছে দিতে পারবো আপু/ভাইয়া! 💖\nআপনার হাতের মাপ অনুযায়ী ২৪, ২৬ অথবা ২৮—কোনটি দিতে হবে বলুন তো?"
                else:
                    reply_msg = "সাধারণত মাঝারি মাপের হাতে ২৬ এবং কিছুটা চিকন হাতে ২৪ সাইজ সুন্দরভাবে ফিট হয়। আপনার কোন সাইজটি লাগবে জানিয়ে দিন প্লিজ 😊"

            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        if size in VALID_SIZES:
            sd["size"]  = size
            dozon_count = ai_dozen or detect_dozon_count(text)
            if dozon_count:
                sd["dozon"] = str(dozon_count)
                info = get_dozon_info(sd.get("product","কাশ্মীরি চুড়ি"), str(dozon_count))
                chosen_color = sd.get("color") or "মিক্সড"
                cart = [{
                    "product": sd.get("product", "কাশ্মীরি চুড়ি"),
                    "color": chosen_color,
                    "size": size,
                    "pieces": info["pieces"],
                    "price": info["price"],
                    "gift": info["gift_str"],
                    "details": f"সাইজ: {size}, রঙ: {chosen_color}, {info['pieces']} পিস"
                }]
                sd["cart"] = cart
                sd["state"] = ASK_CHECKOUT_DETAILS
                user_sessions[sender_id] = sd
                curr_tot = info["price"]
                reply_msg = (
                    f"✅ {sd.get('product','চুড়ি')} ({info['pieces']} পিস) নিশ্চিত করা হয়েছে! 🎁 {info['gift_str']}\n"
                    f"💰 সর্বমোট বিল: ৳{curr_tot:,} (ডেলিভারি চার্জ একদম ফ্রি 🚚)\n\n"
                    f"অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
                    f"• নাম:\n"
                    f"• মোবাইল নম্বর:\n"
                    f"• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
                    f"একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
                )
                txt(reply_msg)
                save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
                return actions

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

        raw_dozen = ai_dozen or detect_dozon_count(text)
        try:
            dozon_count = int(raw_dozen) if raw_dozen is not None else None
        except (ValueError, TypeError):
            dozon_count = detect_dozon_count(text)

        if dozon_count is None:
            if is_question(text) or intent == "QUERY":
                ans = ai_text or "আমাদের চুড়ির প্রতিটি প্যাকেজের সাথে আকর্ষণীয় ফ্রি গিফট ও ফ্রি ডেলিভারি রয়েছে! 😊"
                reply_msg = f"{ans}\n\nআপনি ১ ডজন (১২ পিস) নাকি ২ ডজন (২৪ পিস) নিতে চাচ্ছেন জানাবেন কি?"
            else:
                r_count = get_retry_count(sender_id, "ASK_DOZON")
                if r_count == 1:
                    reply_msg = "কয় ডজন নিতে চান স্যার/ম্যাডাম?\n\"১\" (১২ পিস) অথবা \"২\" (২৪ পিস) লিখুন:"
                elif r_count == 2:
                    reply_msg = "১ ডজনে পাচ্ছেন ৪ পিস ঘুঙুর ফ্রি (৳৬৫০) এবং ২ ডজনে ৮ পিস ঘুঙুর ফ্রি (৳১,১০০)। আপনার কয় ডজন প্রয়োজন বলুন তো? 😊"
                else:
                    reply_msg = "আপনার কত ডজন চুড়ি লাগবে জানিয়ে দিন আপু/ভাইয়া (\"১\" অথবা \"২\" লিখে পাঠাতে পারেন) 🎁"
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

        # Normal 1 or 2 dozen -> Transition to ASK_CHECKOUT_DETAILS
        sd["dozon"] = str(dozon_count)
        info = get_dozon_info(sd.get("product","কাশ্মীরি চুড়ি"), str(dozon_count))
        chosen_color = sd.get("color", "মিক্সড")
        chosen_size = sd.get("size", "২৬")
        cart = [{
            "product": sd.get("product", "কাশ্মীরি চুড়ি"),
            "color": chosen_color,
            "size": chosen_size,
            "pieces": info["pieces"],
            "price": info["price"],
            "gift": info["gift_str"],
            "details": f"সাইজ: {chosen_size}, রঙ: {chosen_color}, {info['pieces']} পিস"
        }]
        sd["cart"] = cart
        sd["state"] = ASK_CHECKOUT_DETAILS
        user_sessions[sender_id] = sd
        curr_tot = info["price"]
        reply_msg = (
            f"✅ {sd.get('product','চুড়ি')} ({info['pieces']} পিস) নিশ্চিত করা হয়েছে! 🎁 {info['gift_str']}\n"
            f"💰 সর্বমোট বিল: ৳{curr_tot:,} (ডেলিভারি চার্জ একদম ফ্রি 🚚)\n\n"
            f"অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
            f"• নাম:\n"
            f"• মোবাইল নম্বর:\n"
            f"• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
            f"একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
        )
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions
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

    # ── ASK_ANYTHING_ELSE: মাল্টি-প্রোডাক্ট কার্ট ও ক্রস-সেলিং হ্যান্ডলার ──
    if state == ASK_ANYTHING_ELSE:
        tl = text.lower()
        is_checkout = (
            is_negative(text)
            or any(w in tl for w in [
                "না", "no", "na", "lagbe na", "লাগবে না", "dorkar nai", "দরকার নেই",
                "আর না", "কনফার্ম", "confirm", "order confirm", "অর্ডার কনফার্ম",
                "ok", "done", "আর কিছু না", "শুধু এইটা", "আর নিব না", "আর লাগবে না"
            ])
        )

        if is_checkout:
            sd["state"] = ASK_CHECKOUT_DETAILS
            user_sessions[sender_id] = sd
            reply_msg = (
                "দারুণ! অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
                "• নাম:\n"
                "• মোবাইল নম্বর:\n"
                "• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
                "একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
            )
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # Check if customer mentions another product to add (Dynamic from database)
        matched_items = detect_products_list(text)
        if matched_items:
            cart = sd.get("cart", [])
            for item_p in matched_items:
                p_name = item_p["name"]
                base_cat = item_p.get("category", "")
                
                if base_cat == "চুড়ি":
                    sd["state"] = ASK_COLOR_SIZE
                    sd["product"] = p_name
                    user_sessions[sender_id] = sd
                    reply_msg = "নিশ্চয়ই! কাশ্মীরি চুড়ির জন্য আপনার হাতের মাপ কত? (২৪ / ২৬ / ২৮) এবং কোন কালারটি নিতে চান?"
                    txt(reply_msg)
                    save_conversation_log(sender_id, text, reply_msg, sentiment, p_name)
                    return actions
                else:
                    qty = item_p.get("qty", 1)
                    unit = item_p.get("unit_name", "পিস")
                    item_price = item_p.get("price", 0) * qty
                    cart.append({
                        "product": p_name,
                        "color": detect_color(text) or "স্ট্যান্ডার্ড",
                        "size": "-",
                        "pieces": qty,
                        "unit": unit,
                        "price": item_price,
                        "gift": item_p.get("free_gift", "ডেলিভারি ফ্রি"),
                        "details": f"{qty} {unit}"
                    })
                    
            sd["cart"] = cart
            curr_tot = sum(i["price"] for i in cart)
            last_added = matched_items[-1]
            qty_str = f"{last_added.get('qty', 1)} {last_added.get('unit_name', 'পিস')}"
            reply_msg = (
                f"✅ {last_added['name']} ({qty_str}) কার্টে যোগ হয়েছে! (৳{last_added['price'] * last_added.get('qty', 1):,})\n\n"
                f"🛍️ কার্টে মোট {len(cart)}টি পণ্য যোগ হয়েছে।\n"
                f"💰 বর্তমান সর্বমোট বিল: ৳{curr_tot:,} (ডেলিভারি চার্জ একদম ফ্রি 🚚)\n\n"
                f"আরও কিছু কি যোগ করতে চান? নাকি অর্ডার কনফার্ম করবেন?\n"
                f"(কনফার্ম করতে 'না' বা 'কনফার্ম' লিখুন, অথবা অন্য পণ্যের নাম লিখুন)"
            )
            txt(reply_msg)
            imgs = get_keyword_product_images_list(last_added["name"])
            for u in imgs[:2]: img(u)
            save_conversation_log(sender_id, text, reply_msg, sentiment, last_added["name"])
            return actions

        # If customer said general affirmative "হ্যাঁ" / "yes"
        if any(w in tl for w in ["হ্যাঁ", "yes", "ha", "hae", "হুম", "দেখাও", "pic", "ছবি"]):
            reply_msg = (
                "আমাদের কাছে পাওয়া যাচ্ছে:\n"
                "• কাশ্মীরি চুড়ি — ৳৬৫০ (৪ পিস ঘুগুর ফ্রি)\n"
                "• বাটারফ্লাই জুয়েলারি সেট — ৳৬৫০\n"
                "• স্নেক গোল্ড পায়েল — ৳৩৫০\n\n"
                "কোনটি কার্টে যোগ করতে চান জানাবেন প্লিজ? 😊"
            )
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # If customer asks a question in ASK_ANYTHING_ELSE
        if is_question(text) or intent == "QUERY":
            ans = ai_text or "আমাদের সব পণ্যে ডেলিভারি সম্পূর্ণ ফ্রি এবং ক্যাশ অন ডেলিভারি সুবিধা রয়েছে! 😊"
            curr_tot = sum(i["price"] for i in sd.get("cart", []))
            reply_msg = f"{ans}\n\nআপনার কার্টে বর্তমান মোট বিল: ৳{curr_tot:,}। অর্ডারটি কি কনফার্ম করে দেব, নাকি সাথে অন্য কিছু যোগ করবেন? 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # Default fallback in ASK_ANYTHING_ELSE
        curr_tot = sum(i["price"] for i in sd.get("cart", []))
        reply_msg = (
            f"আপনার কার্টে মোট {len(sd.get('cart',[]))}টি পণ্য রয়েছে (মোট বিল: ৳{curr_tot:,})।\n\n"
            f"অর্ডার কনফার্ম করতে চাইলে 'কনফার্ম' লিখুন, আর নতুন পণ্য যোগ করতে চাইলে পণ্যের নাম লিখুন (যেমন: পায়েল, সেট বা চুড়ি)।"
        )
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_CHECKOUT_DETAILS: নাম, মোবাইল ও ডেলিভারি ঠিকানা ১ মেসেজে গ্রহণ ──
    if state == ASK_CHECKOUT_DETAILS:
        info = extract_checkout_info(text)
        name = info.get("name") or sd.get("name")
        mobile = info.get("mobile") or sd.get("mobile")
        address = info.get("address") or sd.get("address")

        if name: sd["name"] = name
        if mobile: sd["mobile"] = mobile
        if address: sd["address"] = address
        user_sessions[sender_id] = sd

        # Check missing fields
        missing = []
        if not sd.get("name"): missing.append("আপনার পুরো নাম")
        if not sd.get("mobile"): missing.append("১১ সংখ্যার মোবাইল নম্বর")
        if not sd.get("address"): missing.append("সম্পূর্ণ ডেলিভারি ঠিকানা (বাসা/রোড, এলাকা/থানা, জেলা)")

        if missing:
            missing_str = " এবং ".join(missing)
            reply_msg = f"ধন্যবাদ! অর্ডারটি কনফার্ম করতে অনুগ্রহ করে {missing_str} লিখে পাঠিয়ে দিন প্লিজ 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # ALL 3 DETAILS PROVIDED -> CONFIRM ORDER FIRST!
        cart = sd.get("cart", [])
        if not cart and sd.get("product"):
            info_doz = get_dozon_info(sd.get("product","কাশ্মীরি চুড়ি"), sd.get("dozon","1"))
            cart = [{
                "product": sd.get("product","কাশ্মীরি চুড়ি"),
                "details": f"সাইজ: {sd.get('size','২৬')}, রঙ: {sd.get('color','মিক্সড')}",
                "price": info_doz["price"],
                "gift": info_doz["gift_str"],
                "pieces": info_doz["pieces"]
            }]
            sd["cart"] = cart

        total_price = sum(item["price"] for item in cart)
        prod_names = ", ".join([item['product'] for item in cart])
        details_list = " | ".join([f"{item['product']}: {item.get('details','')} (৳{item['price']})" for item in cart]) + f" | সর্বমোট: ৳{total_price:,}"

        import random
        order_id = f"BB-{random.randint(1000, 9999)}"
        final_name = sd.get("name","কাস্টমার")
        final_mobile = sd.get("mobile","")
        final_address = sd.get("address","")

        save_order(
            name=final_name,
            mobile=final_mobile,
            address=final_address,
            product=prod_names,
            color_size=details_list,
            payment="ক্যাশ অন ডেলিভারি",
            order_id=order_id
        )

        items_summary = ", ".join([f"{itm['product']} ({itm.get('details','')})" for itm in cart])

        # Step 5: Order Confirmation First
        confirm_msg = (
            f"ধন্যবাদ {final_name}! 🎉 আপনার অর্ডার কনফার্ম করা হলো (Order ID: #{order_id})।\n\n"
            f"📦 পণ্য: {items_summary}\n"
            f"💰 মোট বিল: ৳{total_price:,} (ক্যাশ অন ডেলিভারি, ডেলিভারি ফ্রি 🚚)\n"
            f"📱 মোবাইল: {final_mobile}\n"
            f"📍 ঠিকানা: {final_address}\n\n"
        )

        # Step 6: Post-Confirmation Upsell (Cross-sell suggestion)
        has_churi = any(is_churi(i["product"]) for i in cart)
        has_payal = any(is_payal(i["product"]) for i in cart)

        if has_churi:
            suggested_upsell = "স্নেক গোল্ড পায়েল"
            upsell_price = 350
            upsell_text = (
                "✨ স্যার/ম্যাডাম, চুড়ির সাথে পরার মতো আমাদের আকর্ষণীয় 'স্নেক গোল্ড পায়েল' (মাত্র ৳৩৫০) অথবা 'বাটারফ্লাই জুয়েলারি সেট' (৳৬৫০) নিতে চান কি? একসাথে নিলে একই পার্সলে পেয়ে যাবেন! 😊"
            )
        elif has_payal:
            suggested_upsell = "কাশ্মীরি চুড়ি (১ ডজন)"
            upsell_price = 650
            upsell_text = (
                "✨ স্যার/ম্যাডাম, পায়েলের সাথে পরার মতো আমাদের জনপ্রিয় 'কাশ্মীরি চুড়ি' (১ ডজন ৳৬৫০ + ৪ পিস ঘুঙুর ফ্রি) নিতে চান কি? একসাথে নিলে একই পার্সলে পেয়ে যাবেন! 😊"
            )
        else:
            suggested_upsell = "স্নেক গোল্ড পায়েল"
            upsell_price = 350
            upsell_text = (
                "✨ স্যার/ম্যাডাম, সেটের সাথে পরার মতো আমাদের আকর্ষণীয় 'স্নেক গোল্ড পায়েল' (মাত্র ৳৩৫০) নিতে চান কি? একসাথে নিলে একই পার্সলে পেয়ে যাবেন! 😊"
            )

        sd["confirmed_order"] = {
            "order_id": order_id,
            "name": final_name,
            "mobile": final_mobile,
            "address": final_address,
            "original_bill": total_price,
            "prod_names": prod_names,
            "suggested_upsell": suggested_upsell,
            "upsell_price": upsell_price,
            "cart": cart
        }
        sd["state"] = ASK_UPSELL
        user_sessions[sender_id] = sd

        full_reply = confirm_msg + upsell_text
        txt(full_reply)
        save_conversation_log(sender_id, text, full_reply, sentiment, current_prod)
        return actions

    # ── ASK_UPSELL: অর্ডার কনফার্মের পর ক্রস-সেলিং হ্যান্ডলার ──
    if state == ASK_UPSELL:
        order_info = sd.get("confirmed_order", {})
        original_bill = order_info.get("original_bill", 0)
        order_id = order_info.get("order_id", "BB-1001")
        name = order_info.get("name", "স্যার/ম্যাডাম")
        mobile = order_info.get("mobile", "")
        address = order_info.get("address", "")
        suggested_upsell = order_info.get("suggested_upsell", "স্নেক গোল্ড পায়েল")

        tl = text.lower().strip()
        matched_items = detect_products_list(text)
        is_yes = any(w in tl for w in ["হ্যাঁ", "yes", "ha", "hae", "হুম", "নেব", "নেবো", "নিব", "নিবো", "দাও", "দেন", "চাই", "add", "পায়েল", "payel", "সেট", "set", "চুড়ি", "churi"])

        # Customer DECLINED upsell
        if is_negative(text) or any(w in tl for w in ["না", "no", "nah", "দরকার নেই", "দরকার নাই", "শুধু এইটা", "শুধু এটাই", "shudu eta", "shudu ei"]):
            reply_msg = (
                f"ঠিক আছে {name}! 😊\n"
                f"আপনার পার্সেলের সর্বমোট বিল: ৳{original_bill:,} (ডেলিভারি চার্জ সম্পূর্ণ ফ্রি 🚚)\n\n"
                f"🚚 আমরা খুব দ্রুত পার্সেলটি প্যাকেজিং করে ডেলিভারিতে পাঠিয়ে দিচ্ছি।\n"
                f"এই {original_bill:,} টাকা দিয়ে পার্সেলটি রিসিভ করে নিবেন স্যার/ম্যাডাম! 😊💖\n"
                f"(অর্ডারের যেকোনো তথ্য জানতে অর্ডার আইডি #{order_id} দিয়ে মেসেজ দিন)\n"
                f"বেলা বাস্কেটের সাথে থাকার জন্য আপনাকে অসংখ্য ধন্যবাদ! 🎁"
            )
            txt(reply_msg)
            user_sessions.pop(sender_id, None)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # Customer ACCEPTED upsell (either explicitly named product or said yes)
        if is_yes or matched_items:
            chosen_product = suggested_upsell
            upsell_price = order_info.get("upsell_price", 350)
            if matched_items:
                chosen_product = matched_items[0]["name"]
                upsell_price = matched_items[0]["price"] * matched_items[0].get("qty", 1)

            new_total = original_bill + upsell_price

            # Send upsell product picture!
            upsell_imgs = get_keyword_product_images_list(chosen_product)
            if upsell_imgs:
                for u in upsell_imgs[:2]:
                    img(u)

            # Update order in order book
            updated_prods = f"{order_info.get('prod_names','')}, {chosen_product}"
            save_order(
                name=name,
                mobile=mobile,
                address=address,
                product=updated_prods,
                color_size=f"পূর্বের পণ্য + {chosen_product} (৳{upsell_price:,}) | সর্বমোট: ৳{new_total:,}",
                payment="ক্যাশ অন ডেলিভারি",
                order_id=order_id
            )

            reply_msg = (
                f"দারুণ পছন্দ! আপনার অর্ডারে '{chosen_product}' যোগ করা হয়েছে। ✅\n"
                f"📦 আপনার পার্সেলের সর্বমোট বিল: ৳{new_total:,} (ডেলিভারি চার্জ সম্পূর্ণ ফ্রি 🚚)\n\n"
                f"🚚 আমরা খুব দ্রুত পার্সেলটি প্যাকেজিং করে ডেলিভারিতে পাঠিয়ে দিচ্ছি।\n"
                f"এই {new_total:,} টাকা দিয়ে পার্সেলটি রিসিভ করে নিবেন স্যার/ম্যাডাম! 😊💖\n"
                f"(অর্ডারের যেকোনো তথ্য জানতে অর্ডার আইডি #{order_id} দিয়ে মেসেজ দিন)\n"
                f"বেলা বাস্কেটের সাথে থাকার জন্য আপনাকে অসংখ্য ধন্যবাদ! 🎁"
            )
            txt(reply_msg)
            user_sessions.pop(sender_id, None)
            save_conversation_log(sender_id, text, reply_msg, sentiment, chosen_product)
            return actions

        # If question in ASK_UPSELL
        if is_question(text):
            ans = ai_text or "পণ্য হাতে পেয়ে দেখে চেক করে তারপর মূল্য পরিশোধ করার সুযোগ রয়েছে (ক্যাশ অন ডেলিভারি)! 😊"
            reply_msg = (
                f"{ans}\n\n"
                f"আপনি কি সাথে {suggested_upsell} যোগ করতে চান? ('হ্যাঁ' অথবা 'না' লিখে জানান প্লিজ) 😊"
            )
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        # Fallback in ASK_UPSELL
        reply_msg = (
            f"আপনার অর্ডার #{order_id} কনফার্ম রয়েছে (বিল: ৳{original_bill:,})।\n"
            f"সাথে কি {suggested_upsell} যোগ করবেন? ('হ্যাঁ' অথবা 'না' লিখুন প্লিজ) 😊"
        )
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_NAME ──
    if state == ASK_NAME:
        name = text.strip()
        if len(name) < 2 or is_question(name) or intent == "QUERY":
            if is_question(name) or intent == "QUERY":
                ans = ai_text or "পণ্য হাতে পেয়ে দেখে নেওয়ার সম্পূর্ণ সুবিধা রয়েছে (ক্যাশ অন ডেলিভারি)! 😊"
                if any(k in ans for k in ["নাম", "নামটা", "শুভ নাম"]):
                    reply_msg = ans
                else:
                    reply_msg = f"{ans}\n\nঅর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার পুরো নামটা একটু লিখে দিন স্যার/ম্যাডাম:"
            else:
                r_count = get_retry_count(sender_id, "ASK_NAME")
                if r_count == 1:
                    reply_msg = "স্যার/ম্যাডাম, নামটা দিলে অর্ডারটা কনফার্ম করবো! 😊\nআপনার পুরো নাম লিখুন:"
                elif r_count == 2:
                    reply_msg = "পার্সেলের গায়ে লেখার জন্য আপনার শুভ নামটি প্রয়োজন আপু/ভাইয়া, পুরো নামটা একটু লিখে দিন প্লিজ 🌸"
                else:
                    reply_msg = "আপনার নাম জানালে আমরা সাথে সাথে অর্ডারটি কনফার্ম করে ডেলিভারিতে পাঠিয়ে দেবো 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        sd["name"] = name
        sd["state"] = ASK_MOBILE
        user_sessions[sender_id] = sd
        reply_msg = f"ধন্যবাদ {name}! 😊\nস্যার/ম্যাডাম, আপনার ১১ সংখ্যার মোবাইল নম্বরটি দিন:"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_MOBILE ──
    if state == ASK_MOBILE:
        raw = text.strip()
        valid, clean = is_valid_mobile(raw)
        if not valid:
            if is_question(raw) or intent == "QUERY":
                ans = ai_text or "ডেলিভারি ম্যান পৌঁছানোর আগে অবশ্যই আপনাকে কল করবে 😊"
                reply_msg = f"{ans}\n\nঅনুগ্রহ করে আপনার ১১ সংখ্যার মোবাইল নম্বরটি দিন (যেমন: 01712345678):"
            else:
                r_count = get_retry_count(sender_id, "ASK_MOBILE")
                if r_count == 1:
                    reply_msg = "স্যার/ম্যাডাম, সঠিক মোবাইল নম্বরটা (১১ সংখ্যার) দিলে অর্ডারটা কনফার্ম করবো 😊\n(যেমন: 01712345678):"
                elif r_count == 2:
                    reply_msg = "ডেলিভারি ম্যান পৌঁছানোর আগে কল করার জন্য আপনার সচল মোবাইল নম্বরটি প্রয়োজন (১১ ডিজিট) 📱"
                else:
                    reply_msg = "অনুগ্রহ করে একটি সঠিক ১১ সংখ্যার মোবাইল নম্বর দিন যেন কোনো সমস্যা ছাড়াই পার্সেল পৌঁছে যায় 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        sd["mobile"] = clean
        sd["state"]  = ASK_ADDRESS
        user_sessions[sender_id] = sd
        reply_msg = "স্যার/ম্যাডাম, সম্পূর্ণ ডেলিভারি ঠিকানাটা দিন:\n(গ্রাম / মহল্লা / বাসা নং):"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_ADDRESS ──
    if state == ASK_ADDRESS:
        addr = text.strip()
        if len(addr) < 3 or is_question(addr) or intent == "QUERY":
            if is_question(addr) or intent == "QUERY":
                ans = ai_text or "আমরা দ্রুততম সময়ে সারা বাংলাদেশে হোম ডেলিভারি দিয়ে থাকি! 🚚"
                reply_msg = f"{ans}\n\nআপনার সম্পূর্ণ ডেলিভারি ঠিকানাটা (গ্রাম / মহল্লা / বাসা নং) লিখে পাঠান প্লিজ:"
            else:
                r_count = get_retry_count(sender_id, "ASK_ADDRESS")
                if r_count == 1:
                    reply_msg = "স্যার/ম্যাডাম, ঠিকানাটা দিলে অর্ডারটা কনফার্ম করবো! 😊\n(গ্রাম/এলাকার নাম লিখুন):"
                elif r_count == 2:
                    reply_msg = "পার্সেলটি সঠিক ঠিকানায় পৌঁছাতে আপনার বাসা/রোড বা এলাকার বিস্তারিত নাম লিখে দিন প্লিজ 📍"
                else:
                    reply_msg = "আপনার এলাকার বিস্তারিত ঠিকানা দিলে ডেলিভারি করতে সুবিধা হবে আপু/ভাইয়া 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        sd["address"] = addr
        sd["state"]   = ASK_THANA
        user_sessions[sender_id] = sd
        reply_msg = "স্যার/ম্যাডাম, আপনার থানা বা উপজেলার নামটা লিখুন:"
        txt(reply_msg)
        save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
        return actions

    # ── ASK_THANA: সম্পূর্ণ অর্ডার সামারি তৈরি ও সর্বমোট মূল্য প্রদর্শন ──
    if state == ASK_THANA:
        thana = text.strip()
        if len(thana) < 2 or is_question(thana) or intent == "QUERY":
            if is_question(thana) or intent == "QUERY":
                ans = ai_text or "আমাদের ডেলিভারি খুব দ্রুত সম্পন্ন করা হয়! 🚚"
                reply_msg = f"{ans}\n\nআপনার থানা বা উপজেলার নামটা একটু লিখে দিন প্লিজ:"
            else:
                r_count = get_retry_count(sender_id, "ASK_THANA")
                if r_count == 1:
                    reply_msg = "স্যার/ম্যাডাম, থানা/উপজেলার নামটা দিলে অর্ডারটা কনফার্ম করবো! 😊"
                elif r_count == 2:
                    reply_msg = "কুরিয়ার সার্ভিসের সুবিধার্থে আপনার জেলা ও থানার নামটি একটু জানিয়ে দিন প্লিজ 📍"
                else:
                    reply_msg = "কোন থানার অধীনে পার্সেলটি পাঠাবো, থানা বা উপজেলার নাম লিখে দিন প্লিজ 😊"
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, sentiment, current_prod)
            return actions

        sd["thana"] = thana
        sd["state"] = ASK_PAYMENT
        user_sessions[sender_id] = sd

        cart = sd.get("cart", [])
        if not cart and sd.get("product"):
            info = get_dozon_info(sd.get("product",""), sd.get("dozon","1"))
            cart = [{
                "product": sd.get("product",""),
                "details": f"সাইজ: {sd.get('size','-')}, রঙ: {sd.get('color','-')}",
                "price": info["price"],
                "gift": info["gift_str"],
                "pieces": info["pieces"]
            }]
            sd["cart"] = cart

        total_price = sum(item["price"] for item in cart)
        items_summary = ""
        for idx, itm in enumerate(cart, 1):
            items_summary += f"{idx}. {itm['product']} ({itm.get('details','')}) — ৳{itm['price']:,}\n"

        summary = (
            f"📋 আপনার সম্পূর্ণ অর্ডার সামারি:\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 নাম: {sd['name']}\n"
            f"📱 মোবাইল: {sd['mobile']}\n"
            f"📍 ঠিকানা: {sd['address']}, {thana}\n\n"
            f"📦 নির্বাচিত পণ্যসমূহ ({len(cart)}টি):\n"
            f"{items_summary}\n"
            f"💰 সর্বমোট বিল: ৳{total_price:,} (ডেলিভারি চার্জ একদম ফ্রি 🚚)\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"পেমেন্ট কিভাবে করতে চান?\n"
            f"১. বিকাশ\n"
            f"২. ক্যাশ অন ডেলিভারি\n\n"
            f"\"বিকাশ\" অথবা \"ক্যাশ অন\" লিখুন:"
        )
        txt(summary)
        save_conversation_log(sender_id, text, summary, sentiment, current_prod)
        return actions

    # ── ASK_PAYMENT: কনফার্মেশন ও 'পার্সেলটি রিসিভ করে নিবেন' বার্তা ──
    if state == ASK_PAYMENT:
        tl = text.lower()
        if "বিকাশ" in tl or "bkash" in tl: payment = "বিকাশ"
        elif "নগদ" in tl:  payment = "নগদ"
        elif "রকেট" in tl: payment = "রকেট"
        else: payment = "ক্যাশ অন ডেলিভারি"

        cart = sd.get("cart", [])
        if not cart and sd.get("product"):
            info = get_dozon_info(sd.get("product",""), sd.get("dozon","1"))
            cart = [{
                "product": sd.get("product",""),
                "details": f"সাইজ: {sd.get('size','-')}, রঙ: {sd.get('color','-')}",
                "price": info["price"],
                "gift": info["gift_str"],
                "pieces": info["pieces"]
            }]

        total_price = sum(item["price"] for item in cart)
        prod_names = ", ".join([item['product'] for item in cart])
        details_list = " | ".join([f"{item['product']}: {item.get('details','')} (৳{item['price']})" for item in cart]) + f" | সর্বমোট: ৳{total_price:,}"

        import random
        order_id = f"BB-{random.randint(1000, 9999)}"
        save_order(
            name=sd.get("name",""),
            mobile=sd.get("mobile",""),
            address=f"{sd.get('address','')} — {sd.get('thana','')}",
            product=prod_names,
            color_size=details_list,
            payment=payment,
            order_id=order_id
        )
        user_sessions.pop(sender_id, None)
        user_no_count.pop(sender_id, None)

        items_summary = ""
        for idx, itm in enumerate(cart, 1):
            items_summary += f"• {itm['product']} ({itm.get('details','')}) — ৳{itm['price']:,}\n"

        reply = (
            f"✅ আপনার অর্ডারটি সফলভাবে কনফার্ম হয়েছে! 🎉\n\n"
            f"🆔 আপনার অর্ডার আইডি: #{order_id}\n"
            f"📦 অর্ডারের পণ্যসমূহ:\n{items_summary}\n"
            f"💰 সর্বমোট বিল: ৳{total_price:,}\n"
            f"💳 পেমেন্ট মাধ্যম: {payment}\n"
        )
        if payment == "বিকাশ":
            reply += f"\n💳 বিকাশ (পার্সোনাল): {BKASH_NUMBER}\nপেমেন্ট করে স্ক্রিনশট পাঠান! 😊"
        else:
            reply += "\n🚚 পণ্য হাতে পেয়ে দেখে তারপর ডেলিভারি ম্যানকে টাকা দেবেন।"

        reply += (
            f"\n\n🚚 আমরা খুব দ্রুত আপনার পার্সেলটি প্যাকেজিং করে ডেলিভারিতে পাঠিয়ে দিচ্ছি।"
            f"\n⚠️ ডেলিভারি ম্যান পৌঁছালে অনুগ্রহ করে পার্সেলটি রিসিভ করে নিবেন স্যার/ম্যাডাম! 😊💖\n"
            f"(অর্ডারের যেকোনো তথ্য জানতে অর্ডার আইডি #{order_id} দিয়ে মেসেজ দিন)\n"
            f"বেলা বাস্কেটের সাথে থাকার জন্য আপনাকে অসংখ্য ধন্যবাদ! 🎁"
        )
        txt(reply)
        save_conversation_log(sender_id, text, reply, sentiment, current_prod)
        return actions

    # ══════════════════════════════════════════
    # IDLE MODE — AI Context First Flow
    # ══════════════════════════════════════════

    if state == IDLE:
        # ── 1. Order Status / Order ID Lookup ──
        # কাস্টমার যদি অর্ডার আইডি (যেমন BB-1234) বা 'আমার অর্ডার', 'অর্ডার স্ট্যাটাস', 'order status' জানতে চায়
        is_status_query = any(k in text.lower() for k in ["অর্ডার স্ট্যাটাস", "order status", "আমার অর্ডার", "amar order", "order kothay", "কবে পাব", "কবে আসবে"])
        order_id_match = re.search(r'\b(?:bb-)?(\d{4})\b', text.lower()) or ("bb-" in text.lower())
        if is_status_query or ("bb-" in text.lower() and not is_order_intent(text)):
            query_key = text
            if order_id_match and hasattr(order_id_match, 'group'):
                query_key = order_id_match.group()
            found_order = find_order_by_id_or_mobile(query_key)
            if found_order:
                status_msg = (
                    f"📦 আপনার অর্ডারের তথ্য পাওয়া গেছে! 😊\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 অর্ডার আইডি: #{found_order.get('order_id', '-')}\n"
                    f"👤 নাম: {found_order.get('name', '-')}\n"
                    f"🛍️ পণ্য: {found_order.get('product', '-')}\n"
                    f"📍 ডেলিভারি ঠিকানা: {found_order.get('address', '-')}\n"
                    f"🚚 বর্তমান স্ট্যাটাস: 【{found_order.get('status', 'নতুন')}】\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"আপনার পার্সেলটি খুব দ্রুত নিরাপদে ডেলিভারি নিশ্চিত করতে আমাদের টিম কাজ করছে 💖"
                )
                txt(status_msg)
                save_conversation_log(sender_id, text, status_msg, "General", "Order Status")
                return actions
            elif "bb-" in text.lower():
                not_found_msg = "দুঃখিত স্যার/ম্যাডাম! আপনার দেওয়া অর্ডার আইডি দিয়ে কোনো অর্ডার খুঁজে পাওয়া যায়নি। অনুগ্রহ করে সঠিক আইডি অথবা আপনার মোবাইল নম্বরটি লিখে পাঠান 😊"
                txt(not_found_msg)
                save_conversation_log(sender_id, text, not_found_msg, "General", "Order Status")
                return actions

        # ── 1b. Admin Custom Reply Check (for specific exact admin keywords like যোগাযোগ, বিকাশ, etc.) ──
        if not is_order_intent(text) and not is_price_inquiry(text) and not is_pic_inquiry(text):
            custom_rep = get_custom_reply(text)
            if custom_rep:
                txt(custom_rep)
                img_url = get_keyword_product_image(text)
                if img_url: img(img_url)
                save_conversation_log(sender_id, text, custom_rep, "General", current_prod)
                return actions

        # ── 1c. First Message Personalized Greeting (Option 3 with Facebook Profile Name) ──
        # কাস্টমার প্রথমবার মেসেজ দিলে (যদি হিস্ট্রিতে শুধু ১টি ইউজার মেসেজ থাকে এবং কার্ট ফাঁকা থাকে)
        matched_inquiry_prods = detect_products_list(text)
        user_msgs = [m for m in user_chat_history.get(sender_id, []) if m.get("role") == "user"]
        is_greeting = any(g in text.lower() for g in ["hi", "hello", "hlw", "hy", "hey", "হ্যালো", "হাই", "সালাম", "assalamualaikum", "salam"])
        if (is_greeting and not matched_inquiry_prods and not is_order_intent(text)) or (len(user_msgs) <= 1 and not matched_inquiry_prods and not is_order_intent(text) and not is_pic_inquiry(text)):
            c_name = get_user_profile(sender_id)
            name_part = f" {c_name}" if c_name else ""
            welcome_msg = (
                f"আসসালামু আলাইকুম{name_part} আপু/ভাইয়া! 💖\n"
                f"আপনাকে আমাদের Bella Basket Jewelry-তে পেয়ে খুব আনন্দিত হলাম। 🌸\n\n"
                f"আপনি আমাদের কোন পণ্যটি দেখতে বা নিতে ইচ্ছুক? (যেমন: কাশ্মীরি চুড়ি, স্নেক গোল্ড পায়েল, নাকি বাটারফ্লাই জুয়েলারি সেট?) 😊"
            )
            txt(welcome_msg)
            save_conversation_log(sender_id, text, welcome_msg, "Good", "Welcome Greeting")
            return actions

        # ── 2. Price / Picture / Product Sales Funnel (Dynamic Multi-Product & Multi-Image) ──
        # কাস্টমার পণ্য দেখতে চাইলে বা একাধিক পণ্যের ছবি/দাম জানতে চাইলে সবগুলোর ছবি ও বিবরণ দেওয়া
        if (is_price_inquiry(text) or is_pic_inquiry(text) or matched_inquiry_prods) and not (is_order_intent(text) or intent == "ORDER"):
            return handle_product_inquiry(matched_inquiry_prods)

        # ── 3. Customer Refusal / Hesitation (Alternative Product Suggestion) ──
        if sentiment == "Bad" or is_negative(text) or intent == "REFUSAL":
            no_count = user_no_count.get(sender_id, 0) + 1
            user_no_count[sender_id] = no_count
            
            if no_count == 1:
                reply_msg = (
                    "আজকের জন্যই কিন্তু আমাদের এই স্পেশাল অফার এবং ডেলিভারি ফ্রি চলছে স্যার/ম্যাডাম! 😊\n"
                    "ক্যাশ অন ডেলিভারিতে চেক করে নেওয়ার সুযোগ আছে।"
                )
            elif no_count == 2:
                reply_msg = (
                    "কোনো সমস্যা নেই স্যার/ম্যাডাম! 😊\n"
                    "চুড়ি না লাগলে আমাদের জনপ্রিয় অন্য পণ্যগুলো দেখতে পারেন:\n"
                    "✨ বাটারফ্লাই ব্লিস জুয়েলারি সেট — ৳৬৫০ (ডেলিভারি ফ্রি)\n"
                    "✨ স্নেক গোল্ড পায়েল — মাত্র ৳৩৫০ (ডেলিভারি ফ্রি)\n\n"
                    "কোনোটির ছবি বা বিস্তারিত দেখতে চান?"
                )
            else:
                reply_msg = "ঠিক আছে স্যার/ম্যাডাম, কোনো ব্যাপার না! ভবিষ্যতে কিছু লাগলে আমাদের অবশ্যই জানাবেন। আপনার দিনটি শুভ হোক! 🌸"
                
            txt(reply_msg)
            save_conversation_log(sender_id, text, reply_msg, "Bad", current_prod)
            return actions

        # ── 3. Order Intent Detection (Single or Multiple Products) ──
        if intent == "ORDER" or is_order_intent(text):
            user_no_count.pop(sender_id, None)
            detected_items = detect_products_list(text)
            if not detected_items:
                single_p = detect_product(text) or user_product.get(sender_id, "কাশ্মীরি চুড়ি (১ ডজন)")
                # Wrap single fallback into item dict
                p_obj = get_product_by_name(single_p) or {
                    "id": "1", "name": single_p, "price": 650, "unit_name": "ডজন", "category": "চুড়ি"
                }
                item_dict = dict(p_obj)
                item_dict["qty"] = 1
                item_dict["total_price"] = p_obj.get("price", 650)
                detected_items = [item_dict]

            has_churi = any(is_churi(p["name"]) or p.get("category") == "চুড়ি" for p in detected_items)
            churi_items = [p for p in detected_items if is_churi(p["name"]) or p.get("category") == "চুড়ি"]
            other_prods = [p for p in detected_items if not (is_churi(p["name"]) or p.get("category") == "চুড়ি")]

            # Multi-product order containing Churi + other item(s) (e.g. Churi + Payel)
            if has_churi and other_prods:
                cart = []
                for p in other_prods:
                    qty = p.get("qty", 1)
                    unit = p.get("unit_name", "পিস")
                    tot_p = p.get("total_price", p.get("price", 0) * qty)
                    cart.append({
                        "product": p["name"],
                        "color": detect_color(text) or "স্ট্যান্ডার্ড",
                        "size": "-",
                        "pieces": qty,
                        "unit": unit,
                        "price": tot_p,
                        "gift": p.get("free_gift", "ডেলিভারি ফ্রি"),
                        "details": f"{qty} {unit}"
                    })

                user_size = ai_size or detect_size(text)
                user_color = detect_color(text) or ""

                if user_size in VALID_SIZES:
                    churi_p = churi_items[0] if churi_items else {"name": "কাশ্মীরি চুড়ি (১ ডজন)"}
                    churi_qty = churi_p.get("qty", 1)
                    info = get_dozon_info(churi_p["name"], str(churi_qty))
                    cart.append({
                        "product": churi_p["name"],
                        "color": user_color or "মিক্সড",
                        "size": user_size,
                        "pieces": info["pieces"],
                        "price": info["price"],
                        "gift": info["gift_str"],
                        "details": f"সাইজ: {user_size}, রঙ: {user_color or 'মিক্সড'}, {info['pieces']} পিস"
                    })
                    sd["cart"] = cart
                    sd["state"] = ASK_CHECKOUT_DETAILS
                    user_sessions[sender_id] = sd
                    curr_tot = sum(i["price"] for i in cart)
                    items_desc = "\n".join([f"• {i['product']} ({i.get('details','')}) — ৳{i['price']:,}" for i in cart])
                    reply_msg = (
                        f"দারুণ পছন্দ! ✅ আপনার কার্টে পণ্যগুলো যোগ করা হয়েছে:\n{items_desc}\n\n"
                        f"💰 সর্বমোট বিল: ৳{curr_tot:,} (ডেলিভারি চার্জ সম্পূর্ণ ফ্রি! 🚚)\n\n"
                        f"অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
                        f"• নাম:\n"
                        f"• মোবাইল নম্বর:\n"
                        f"• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
                        f"একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
                    )
                    txt(reply_msg)
                    save_conversation_log(sender_id, text, reply_msg, sentiment, "মাল্টি-অর্ডার")
                    return actions
                else:
                    churi_p = churi_items[0] if churi_items else {"name": "কাশ্মীরি চুড়ি (১ ডজন)"}
                    sd["product"] = churi_p["name"]
                    sd["color"] = user_color
                    sd["cart"] = cart
                    sd["state"] = ASK_COLOR_SIZE
                    user_sessions[sender_id] = sd

                    other_desc = " এবং ".join([f"{i['product']} ({i.get('details','')}, ৳{i['price']:,})" for i in cart])
                    total_est = sum(i["price"] for i in cart) + 650

                    reply_msg = (
                        f"দারুণ পছন্দ! ✅ {other_desc} আপনার কার্টে যোগ করা হয়েছে।\n\n"
                        f"সাথে কাশ্মীরি চুড়ি (১ ডজন ৳৬৫০) যুক্ত করতে আপনার পছন্দের কালার কোনটি এবং হাতের সাইজ কত? (২৪ / ২৬ / ২৮) 😊\n\n"
                        f"💰 সর্বমোট বিল হবে: ৳{total_est:,} (ডেলিভারি চার্জ সম্পূর্ণ ফ্রি! 🚚)\n\n"
                        f"কালার বেছে নিতে নিচের ছবিগুলো দেখতে পারেন 💖"
                    )
                    txt(reply_msg)
                    images_to_send = get_keyword_product_images_list("চুড়ি")
                    if images_to_send:
                        for url in images_to_send:
                            img(url)
                    save_conversation_log(sender_id, text, reply_msg, sentiment, "মাল্টি-অর্ডার")
                    return actions

            # Multi-product order without Churi (e.g. 2 jora Payel + 3 set Jewelry Set)
            elif len(detected_items) > 1 and not has_churi:
                cart = []
                for p in detected_items:
                    qty = p.get("qty", 1)
                    unit = p.get("unit_name", "পিস")
                    tot_p = p.get("total_price", p.get("price", 0) * qty)
                    cart.append({
                        "product": p["name"],
                        "details": f"{qty} {unit}",
                        "price": tot_p,
                        "gift": p.get("free_gift", "ডেলিভারি ফ্রি"),
                        "pieces": qty,
                        "unit": unit
                    })
                sd["cart"] = cart
                sd["state"] = ASK_CHECKOUT_DETAILS
                user_sessions[sender_id] = sd
                curr_tot = sum(i["price"] for i in cart)
                items_desc = "\n".join([f"• {i['product']} ({i.get('details','')}) — ৳{i['price']:,}" for i in cart])
                reply_msg = (
                    f"দারুণ পছন্দ! ✅ আপনার কার্টে পণ্যগুলো যোগ করা হয়েছে:\n{items_desc}\n\n"
                    f"💰 সর্বমোট বিল: ৳{curr_tot:,} (ডেলিভারি চার্জ সম্পূর্ণ ফ্রি! 🚚)\n\n"
                    f"অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
                    f"• নাম:\n"
                    f"• মোবাইল নম্বর:\n"
                    f"• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
                    f"একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
                )
                txt(reply_msg)
                save_conversation_log(sender_id, text, reply_msg, sentiment, "মাল্টি-অর্ডার")
                return actions

            # Single product order
            else:
                p_item = detected_items[0] if detected_items else {"name": "কাশ্মীরি চুড়ি (১ ডজন)", "price": 650, "unit_name": "ডজন", "category": "চুড়ি"}
                prod = p_item["name"]
                if is_churi(prod) or p_item.get("category") == "চুড়ি":
                    user_size = ai_size or detect_size(text)
                    user_color = detect_color(text) or ""
                    if user_size in VALID_SIZES:
                        sd["state"] = ASK_DOZON
                        sd["product"] = prod
                        sd["size"] = user_size
                        sd["color"] = user_color or "মিক্সড"
                        user_sessions[sender_id] = sd
                        reply_msg = (
                            f"{user_color + ' কালার, ' if user_color else ''}সাইজ {user_size} কনফার্ম! ✅\n\n"
                            f"কয় ডজন নিতে চান?\n\n"
                            f"১ ডজন (১২ পিস) → ৳৬৫০ 🎁 ৪ পিস ঘুঙুর ফ্রি + ফ্রি ডেলিভারি\n"
                            f"২ ডজন (২৪ পিস) → ৳১,১০০ 🎁 ৮ পিস ঘুঙুর ফ্রি + ফ্রি ডেলিভারি\n\n"
                            f"\"১\" অথবা \"২\" লিখুন:"
                        )
                        txt(reply_msg)
                        save_conversation_log(sender_id, text, reply_msg, sentiment, prod)
                        return actions
                    else:
                        user_sessions[sender_id] = {
                            "state": ASK_COLOR_SIZE,
                            "product": prod,
                            "color": user_color,
                            "cart": []
                        }
                        images_to_send = get_keyword_product_images_list(prod) or get_keyword_product_images_list("চুড়ি")
                        if images_to_send:
                            for url in images_to_send:
                                img(url)
                        ai_prefix = f"{ai_text}\n\n" if ai_text else ""
                        reply_msg = f"{ai_prefix}এখানে আমাদের সুন্দর কিছু কালার দেওয়া হলো! 😊\n\nআপনি কোন কালারটি নিতে চাচ্ছেন? এবং আপনার হাতের মাপ কত? (২৪, ২৬, ২৮)"
                        txt(reply_msg)
                        save_conversation_log(sender_id, text, reply_msg, sentiment, prod)
                        return actions
                else:
                    qty = p_item.get("qty", 1)
                    unit = p_item.get("unit_name", "পিস")
                    tot_p = p_item.get("total_price", p_item.get("price", 0) * qty)
                    qty_desc = f"{qty} {unit}"
                    user_sessions[sender_id] = {
                        "state": ASK_CHECKOUT_DETAILS,
                        "product": prod,
                        "color": detect_color(text) or "স্ট্যান্ডার্ড",
                        "cart": [{
                            "product": prod,
                            "details": qty_desc,
                            "price": tot_p,
                            "gift": p_item.get("free_gift", "ডেলিভারি ফ্রি"),
                            "pieces": qty,
                            "unit": unit
                        }]
                    }
                    reply_msg = (
                        f"✅ {prod} ({qty_desc}) নিশ্চিত করা হয়েছে! 🎁 ডেলিভারি ফ্রি 🚚\n"
                        f"💰 সর্বমোট বিল: ৳{tot_p:,}\n\n"
                        f"অর্ডারটি কনফার্ম করার জন্য অনুগ্রহ করে আপনার:\n"
                        f"• নাম:\n"
                        f"• মোবাইল নম্বর:\n"
                        f"• সম্পূর্ণ ডেলিভারি ঠিকানা:\n"
                        f"একসাথে লিখে পাঠিয়ে দিন প্লিজ! 😊"
                    )
                    txt(reply_msg)
                    images_to_send = get_keyword_product_images_list(prod) or get_keyword_product_images_list(text)
                    if images_to_send:
                        for url in images_to_send:
                            img(url)
                    save_conversation_log(sender_id, text, reply_msg, sentiment, prod)
                    return actions

        # ── 4. General Conversation (QUERY, GREETING, OTHER) ──
        if ai_text:
            txt(ai_text)
            images_to_send = get_keyword_product_images_list(ai_prod) if ai_prod else []
            if not images_to_send:
                images_to_send = get_keyword_product_images_list(text)
                
            for url in images_to_send:
                img(url)
            
            if ai_size and is_churi(text):
                user_sessions[sender_id] = {"state": ASK_DOZON, "product": "কাশ্মীরি চুড়ি (১ ডজন)", "size": ai_size, "cart": []}
                
            save_conversation_log(sender_id, text, ai_text, sentiment, current_prod)
            return actions

        # ── 5. Smart Fallback ──
        fallback_prod = detect_product(text)
        if fallback_prod:
            images = get_keyword_product_images_list(fallback_prod) or get_keyword_product_images_list(text)
            if images:
                for url in images:
                    img(url)
                fallback_msg = f"আমাদের {fallback_prod} এর কিছু ছবি দেওয়া হলো! 😊 বিস্তারিত জানতে বা অর্ডার করতে লিখুন:\n\"অর্ডার\""
                txt(fallback_msg)
                save_conversation_log(sender_id, text, fallback_msg, "General", fallback_prod)
                return actions

        # Simple greetings fallback
        tl = text.lower()
        if any(g in tl for g in ["hi", "hello", "hlw", "hy", "hey", "হ্যালো", "হাই", "সালাম"]):
            fallback_msg = (
                "আসসালামু আলাইকুম স্যার/ম্যাডাম! Bella Basket Jewelry-তে আপনাকে স্বাগতম! 💖\n\n"
                "আপনি আমাদের কোন পণ্যটি দেখতে বা নিতে ইচ্ছুক? (যেমন: কাশ্মীরি চুড়ি, স্নেক গোল্ড পায়েল, নাকি বাটারফ্লাই জুয়েলারি সেট?) 😊"
            )
        else:
            fallback_msg = "ধন্যবাদ! 😊 বিস্তারিত জানতে পণ্যের নাম লিখুন (যেমন: চুড়ি, বাটারফ্লাই সেট, পায়েল)।"
            
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
    import html
    old = request.form.get("old_keyword","").strip()
    kw  = request.form.get("keyword","").strip()
    rp  = request.form.get("reply","").strip()
    if kw and rp:
        d = load_replies()
        d.pop(old, None)
        d.pop(html.unescape(old), None)
        d[kw] = rp
        save_replies(d)
    return redirect(url_for("admin_replies", msg="আপডেট হয়েছে!"))

@app.route("/admin/replies/delete", methods=["POST"])
@login_required
def admin_reply_delete():
    d=load_replies(); d.pop(request.form.get("keyword",""),None); save_replies(d)
    return redirect(url_for("admin_replies", msg="মুছে ফেলা হয়েছে!"))

# ── Conversation Logs Management ──
@app.route("/admin/logs/edit", methods=["POST"])
@login_required
def admin_log_edit():
    row_index    = request.form.get("row_index")
    user_message = request.form.get("user_message", "").strip()
    bot_reply    = request.form.get("bot_reply", "").strip()
    sentiment    = request.form.get("sentiment", "General").strip()
    product      = request.form.get("product", "").strip()

    if row_index:
        update_conversation_log(row_index, user_message, bot_reply, sentiment, product)
        return redirect(url_for("admin_dashboard", msg="কথা ও সেন্টিমেন্ট সফলভাবে আপডেট করা হয়েছে!"))
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/orders/status", methods=["POST"])
@login_required
def admin_order_status():
    order_id = request.form.get("order_id", "").strip()
    status   = request.form.get("status", "নতুন").strip()
    if order_id:
        update_order_status(order_id, status)
        return redirect(url_for("admin_dashboard", msg=f"অর্ডার #{order_id} এর স্ট্যাটাস '{status}' করা হয়েছে!"))
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logs/delete", methods=["POST"])
@login_required
def admin_log_delete():
    row_index = request.form.get("row_index")
    if row_index:
        delete_conversation_log(row_index)
        return redirect(url_for("admin_dashboard", msg="লগ সফলভাবে মুছে ফেলা হয়েছে!"))
    return redirect(url_for("admin_dashboard"))

# ── Products ──
@app.route("/admin/products")
@login_required
def admin_products():
    return render_template("products.html", products=load_products(), msg=request.args.get("msg"))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'webp', 'gif'}

@app.route("/admin/products/add", methods=["POST"])
@login_required
def admin_product_add():
    products = load_products()
    new_id   = max((p["id"] for p in products), default=0) + 1
    colors   = [c.strip() for c in request.form.get("colors","").split(",") if c.strip()]
    
    images = []
    # Handle files
    files = request.files.getlist("image_files")
    for f in files:
        if f and allowed_file(f.filename):
            filename = secure_filename(f"{new_id}_{uuid.uuid4().hex[:6]}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            images.append(f"/static/uploads/{filename}")
            
    # Handle single text URL as fallback
    text_url = request.form.get("image_url","").strip()
    if text_url:
        images.append(text_url)

    unit_name = request.form.get("unit_name", "পিস").strip()
    try:
        unit_qty = int(request.form.get("unit_quantity", 1) or 1)
    except:
        unit_qty = 1

    keywords_raw = request.form.get("keywords", "")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    if not keywords:
        name_val = request.form.get("name","").strip()
        cat_val = request.form.get("category","").strip()
        keywords = [name_val]
        if cat_val and cat_val != name_val:
            keywords.append(cat_val)

    products.append({
        "id":new_id,
        "name":request.form.get("name","").strip(),
        "category":request.form.get("category","").strip(),
        "unit_name":unit_name,
        "unit_quantity":unit_qty,
        "price":int(request.form.get("price",0) or 0),
        "package":request.form.get("package","").strip(),
        "free_gift":request.form.get("free_gift","-").strip(),
        "delivery":request.form.get("delivery","ফ্রি").strip(),
        "ai_instructions":request.form.get("ai_instructions","").strip(),
        "keywords":keywords,
        "colors":colors,
        "description":request.form.get("description","").strip(),
        "images":images,
        "image": images[0] if images else "" # Backwards compatibility
    })
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্য যোগ হয়েছে!"))

@app.route("/admin/products/update_image", methods=["POST"])
@login_required
def admin_product_update_image():
    pid = int(request.form.get("id",0))
    products = load_products()
    
    for p in products:
        if p["id"] == pid:
            images = p.get("images", [p.get("image")] if p.get("image") else [])
            
            # Add new files
            files = request.files.getlist("image_files")
            for f in files:
                if f and allowed_file(f.filename):
                    filename = secure_filename(f"{pid}_{uuid.uuid4().hex[:6]}_{f.filename}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    images.append(f"/static/uploads/{filename}")
                    
            # Add new text URL
            text_url = request.form.get("image_url","").strip()
            if text_url and text_url not in images:
                images.append(text_url)
                
            p["images"] = images
            if images:
                p["image"] = images[0]
            break
            
    save_products(products)
    return redirect(url_for("admin_products", msg="ছবি আপডেট হয়েছে!"))

@app.route("/admin/products/edit", methods=["POST"])
@login_required
def admin_product_edit():
    pid = int(request.form.get("id", 0))
    products = load_products()
    for p in products:
        if p["id"] == pid:
            if "name" in request.form and request.form.get("name").strip():
                p["name"] = request.form.get("name").strip()
            if "category" in request.form:
                p["category"] = request.form.get("category").strip()
            if "price" in request.form:
                p["price"] = int(request.form.get("price", 0) or 0)
            if "unit_name" in request.form:
                p["unit_name"] = request.form.get("unit_name", "পিস").strip()
            if "unit_quantity" in request.form:
                try:
                    p["unit_quantity"] = int(request.form.get("unit_quantity", 1) or 1)
                except:
                    p["unit_quantity"] = 1
            if "package" in request.form:
                p["package"] = request.form.get("package", "").strip()
            if "free_gift" in request.form:
                p["free_gift"] = request.form.get("free_gift", "-").strip()
            if "delivery" in request.form:
                p["delivery"] = request.form.get("delivery", "ফ্রি").strip()
            if "ai_instructions" in request.form:
                p["ai_instructions"] = request.form.get("ai_instructions", "").strip()
            if "description" in request.form:
                p["description"] = request.form.get("description", "").strip()
            if "keywords" in request.form:
                kw_raw = request.form.get("keywords", "")
                kws = [k.strip() for k in kw_raw.split(",") if k.strip()]
                if kws:
                    p["keywords"] = kws
            if "colors" in request.form:
                p["colors"] = [c.strip() for c in request.form.get("colors", "").split(",") if c.strip()]
            break
    save_products(products)
    return redirect(url_for("admin_products", msg="পণ্যের তথ্য সফলভাবে আপডেট হয়েছে!"))

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
        img_res = analyze_product_image(msg)
        reply_txt = img_res.get("reply", "ছবিটি দেখেছি!") if isinstance(img_res, dict) else str(img_res)
        save_conversation_log("DEMO_ADMIN", "[IMAGE_SENT]", reply_txt, "General", img_res.get("matched_product", ""))
        return jsonify({"replies":[{"type":"text","content":reply_txt}]})
    actions = process_message("DEMO_ADMIN", msg)
    return jsonify({"replies": actions})

@app.route("/admin/chat/reset", methods=["POST"])
@login_required
def admin_chat_reset():
    user_sessions.pop("DEMO_ADMIN", None)
    user_chat_history.pop("DEMO_ADMIN", None)
    user_product.pop("DEMO_ADMIN", None)
    user_no_count.pop("DEMO_ADMIN", None)
    user_state_retries.pop("DEMO_ADMIN", None)
    return jsonify({"status": "ok", "msg": "Chat session reset successfully"})


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
                        att_type = att.get("type")
                        att_url  = att.get("payload", {}).get("url", "")

                        if att_type == "audio":
                            send_typing(sid)
                            transcribed_text = analyze_audio_attachment(att_url, PAGE_ACCESS_TOKEN)
                            if transcribed_text:
                                save_conversation_log(sid, f"[VOICE_NOTE: {transcribed_text}]", "", "General", "")
                                # Process the transcribed voice note as normal customer text!
                                actions = process_message(sid, transcribed_text)
                                for act in actions:
                                    if act["type"] == "text": send_text(sid, act["content"])
                                    elif act["type"] == "image": send_image(sid, act["content"])
                            else:
                                send_text(sid, "আপনার ভয়েস মেসেজটি শুনেছি! বিস্তারিত জানতে বা অর্ডার করতে টেক্সট এ লিখুন 😊")

                        elif att_type == "image":
                            send_typing(sid)
                            img_res = analyze_product_image(att_url, PAGE_ACCESS_TOKEN)
                            reply_type = img_res.get("type", "product")
                            reply_msg  = img_res.get("reply", "")
                            matched_p  = img_res.get("matched_product")

                            send_text(sid, reply_msg)
                            save_conversation_log(sid, "[IMAGE_ATTACHMENT]", reply_msg, "General", matched_p or "Image Search")

                            # If similar product identified and has images, send product picture
                            if matched_p:
                                prod_imgs = get_keyword_product_images_list(matched_p)
                                if prod_imgs:
                                    for p_url in prod_imgs[:2]:
                                        send_image(sid, p_url)

                            if reply_type == "product" and matched_p and is_churi(matched_p):
                                send_text(sid, "এটা নিতে চাইলে হাতের মাপ কত জানাবেন স্যার/ম্যাডাম? (২৪ / ২৬ / ২৮) 😊")
                                user_sessions[sid] = {"state": ASK_SIZE, "product": matched_p, "color": ""}
                        else:
                            send_text(sid, "ধন্যবাদ! কিছু জানতে বা অর্ডার করতে টেক্সটে পণ্যের নাম লিখুন। 😊")
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
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    print("="*50)
    print("  Bella Basket Bot — Intelligent AI & Excel Logging Active")
    print(f"  Admin: http://localhost:{port}/admin")
    print(f"  Chat:  http://localhost:{port}/admin/chat")
    print("="*50)
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
