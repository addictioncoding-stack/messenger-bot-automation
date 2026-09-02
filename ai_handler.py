"""
=====================================================
  Gemini AI + Vision Handler — Bella Basket Bot
  Uses google-genai SDK
=====================================================
"""

import os, json
import httpx

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[WARNING] google-genai not installed. AI disabled.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_client = None

def _get_client():
    global _client
    if _client is None and GEMINI_AVAILABLE and GEMINI_API_KEY:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _load_products():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "products.json")
    try:
        with open(f, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except:
        return []


def _products_text():
    lines = ""
    for p in _load_products():
        colors = ", ".join(p.get("colors", [])) or "-"
        gift   = p.get("free_gift", "-")
        lines += f"• {p['name']} — ৳{p['price']} | প্যাকেজ: {p['package']} | গিফট: {gift}"
        if colors != "-":
            lines += f" | রঙ: {colors}"
        lines += "\n"
    return lines


def _system_prompt():
    return f"""তুমি Bella Basket Jewelry-এর customer service agent। তোমার নাম "Bella"।

আমাদের পণ্য:
{_products_text()}
আজকের অফার: গিফট সম্পূর্ণ ফ্রি + ডেলিভারি সম্পূর্ণ ফ্রি!
বিকাশ নম্বর: 01937281260 (পার্সোনাল)
ক্যাশ অন ডেলিভারি: পণ্য পেয়ে টাকা দিন।

নিয়ম:
- সবসময় বাংলায় কথা বলো
- customer কে "আপু" বা "ভাই" বলে ডাকো
- reply সংক্ষিপ্ত রাখো (৩-৫ লাইন)
- অর্ডার করতে চাইলে "অর্ডার করব" লিখতে বলো"""


# ====================================================
# TEXT REPLY
# ====================================================

def get_ai_reply_simple(user_message: str) -> str:
    """Text message থেকে AI reply"""
    client = _get_client()
    if not client:
        return None
    try:
        prompt = f"{_system_prompt()}\n\nCustomer বলেছে: {user_message}"
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        reply = response.text.strip()
        print(f"[AI] Text reply ({len(reply)} chars)")
        return reply
    except Exception as e:
        print(f"[AI ERROR] {e}")
        return None


# ====================================================
# IMAGE / VISION REPLY
# ====================================================

def analyze_product_image(image_url: str, page_access_token: str = None) -> str:
    """
    Customer এর পাঠানো ছবি দেখে Gemini Vision দিয়ে product identify করো।
    Returns: বাংলায় reply string
    """
    client = _get_client()
    if not client:
        return "ছবিটি দেখতে পাচ্ছি! আমাদের পণ্য সম্পর্কে জানতে 'চুড়ি' বা 'পায়েল' লিখুন। 😊"

    try:
        # Facebook image download (access_token দরকার হতে পারে)
        headers = {}
        if page_access_token:
            headers["Authorization"] = f"Bearer {page_access_token}"

        img_resp = httpx.get(image_url, headers=headers, timeout=20, follow_redirects=True)
        img_data = img_resp.content
        mime_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()

        if not img_data:
            return "ছবিটি ঠিকমতো লোড হয়নি। আবার পাঠান! 😊"

        prompt = f"""এই ছবিতে কী jewelry দেখা যাচ্ছে তা বাংলায় বলো।

আমাদের Bella Basket Jewelry-এর পণ্য তালিকা:
{_products_text()}

নির্দেশনা:
- ছবির jewelry টি আমাদের কোন পণ্যের মতো তা বলো
- সেই পণ্যের দাম ও অফার জানাও
- যদি না মিলে, তবু সুন্দরভাবে বলো এবং আমাদের কাছে আসতে বলো
- সবসময় বাংলায় কথা বলো
- আপু/ভাই বলে সম্বোধন করো
- ৩-৪ লাইনে reply দাও
- শেষে অর্ডার করার কথা মনে করিয়ে দাও"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=img_data, mime_type=mime_type),
                prompt,
            ],
        )
        reply = response.text.strip()
        print(f"[VISION] Image analyzed ({len(reply)} chars)")
        return reply

    except Exception as e:
        print(f"[VISION ERROR] {e}")
        return ("ছবিটি দেখলাম! আমাদের পণ্য সম্পর্কে জানতে লিখুন:\n"
                "\"চুড়ি\" | \"পায়েল\" | \"জুয়েলারি সেট\" 😊")


# ====================================================
# PRODUCT IMAGE URL LOOKUP
# ====================================================

def get_product_image_url(product_name: str) -> str:
    """পণ্যের নাম দিয়ে image URL বের করো"""
    products = _load_products()
    name_lower = product_name.lower()
    for p in products:
        if p["name"].lower() in name_lower or name_lower in p["name"].lower():
            url = p.get("image", "").strip()
            if url:
                return url
    return None


def get_keyword_product_image(keyword: str) -> str:
    """Keyword দিয়ে matching product এর image URL বের করো"""
    products = _load_products()
    kl = keyword.lower()
    for p in products:
        name = p["name"].lower()
        cat  = p.get("category", "").lower()
        if kl in name or kl in cat:
            url = p.get("image", "").strip()
            if url:
                return url
    return None
