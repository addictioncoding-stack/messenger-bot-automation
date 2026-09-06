"""
=====================================================
  Gemini AI + Vision + Context Intelligence Handler
  Bella Basket Jewelry Bot
  Uses google-genai SDK (gemini-3.6-flash)
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
    return f"""তুমি Bella Basket Jewelry-এর অত্যন্ত বুদ্ধিমান AI কাস্টমার সার্ভিস এজেন্ট। তোমার নাম "Bella"।

আমাদের পণ্যসমূহ:
{_products_text()}

শপের মূল নিয়মাবলী (বাধ্যতামূলকভাবে মেনে চলবে):
1. **চুড়ির গিফট নিয়ম:**
   - প্রতি ১২ পিস (১ ডজন) চুড়ির সাথে ৪ পিস ঘুগুর (Gugur / Ghungroo) একদম ফ্রি!
   - ২৪ পিস (২ ডজন) চুড়ির সাথে ৮ পিস ঘুগুর ফ্রি!
   - হিসাব: প্রতি ১২ পিস চুড়িতে ৪ পিস ঘুগুর ফ্রি উপহার হিসেবে দেওয়া হবে।
   - চুড়ির দাম: ১ ডজন (১২ পিস) ৳৬৫০, ২ ডজন (২৪ পিস) ৳১,১০০।
   - চুড়ির সাথে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!

2. **পরিমাণ সংক্রান্ত নিয়ম:**
   - কাস্টমার যদি ৬ পিস (হাফ ডজন) চুড়ি কিনতে চায়, তাকে আমাদের ওয়েবসাইট থেকে অর্ডার করতে বলো: www.bellabasket.store
   - কাস্টমার যদি ২ ডজনের বেশি (২৪ পিসের বেশি, যেমন ৩ বা ৪ ডজন) চুড়ি নিতে চায়, তবে তাকে ২০০ টাকা অগ্রিম পেমেন্ট করতে বলো (বিকাশ পার্সোনাল: 01937281260)।

3. **চুড়ির সাইজ সংক্রান্ত নিয়ম:**
   - চুড়ির এভেলেবল সাইজ: ২৪, ২৬, এবং ২৮।
   - যদি কাস্টমার ২২ বা ৩০ সাইজ চায়, তবে বলবে: "স্যার/ম্যাডাম চেক করে জানাচ্ছি। একটু অপেক্ষা করুন!"

4. **নেকলেস (জুয়েলারি সেট) ও পায়েল সংক্রান্ত নিয়ম:**
   - নেকলেস এবং পায়েলের সাথে কোনো ফ্রি গিফট নেই।
   - কিন্তু স্পেশাল অফারে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!

5. **কাস্টমার না নিতে চাইলে (Persuasion Engine):**
   - কাস্টমার যদি না করতে চায় বা দ্বিধাদ্বন্দ্বে থাকে (যেমন "না", "পরে নিব", "দাম বেশি", "দরকার নেই"):
     - প্রথমে বলবে: "আজকের জন্যই এই অফার ম্যাডাম/স্যার! আজ ফ্রি গিফট + ফ্রি ডেলিভারি অফার চলছে।"
     - এরপরও না বললে তাদের বোঝাবে যে ক্যাশ অন ডেলিভারিতে চেক করে নেওয়ার সুযোগ আছে এবং কোয়ালিটি সেরা।
     - তাও না নিলে অন্য পণ্য (যেমন চুড়ি, নেকলেস, বা পায়েল) সাজেস্ট করবে।

6. **কথাবার্তার ধরন ও ভদ্রতা:**
   - সবসময় কাস্টমারকে "আপু", "ভাই", "ম্যাডাম" বা "স্যার" বলে সম্বোধন করবে।
   - উত্তর সবসময় সুন্দর, স্বাভাবিক, কাস্টমারবান্ধব বাংলায় দেবে।

JSON Output Format (বাধ্যতামূলক):
তুমি নিচের JSON ফরম্যাটে উত্তর দেবে:
{{
  "reply_text": "কাস্টমারকে পাঠানোর মতো বাংলায় সুন্দর উত্তর",
  "sentiment": "Good" (যদি পজিটিভ, প্রশংসা, অর্ডার ইচ্ছুক হয়) / "Bad" (যদি না করে, কমপ্লেন করে, রাগ করে, অনিচ্ছুক হয়) / "General" (যদি সাধারণ প্রশ্ন বা হাই-হ্যালো হয়),
  "intent": "কাস্টমারের মেসেজের উদ্দেশ্য (GREETING/QUERY/ORDER/REFUSAL/SIZE/DOZEN/OTHER)",
  "detected_product": "যদি কোনো পণ্যের নাম বোঝা যায়",
  "detected_size": "যদি সাইজ উল্লেখ করে (24, 26, 28, 22, 30)",
  "detected_dozen": "যদি ডজন উল্লেখ করে"
}}
"""


def analyze_and_reply(user_message: str, current_state: str = "IDLE", product_context: str = "") -> dict:
    """
    Gemini AI দিয়ে মেসেজ বিশ্লেষণ করে বুদ্ধিমান উত্তর, সেন্টিমেন্ট এবং ইন্টেন্ট দেয়।
    """
    client = _get_client()
    if not client:
        return None

    try:
        context_info = f"বর্তমান স্টেট: {current_state}"
        if product_context:
            context_info += f" | কাস্টমারের পছন্দের পণ্য: {product_context}"

        prompt = f"{_system_prompt()}\n\n[{context_info}]\nCustomer বলেছে: \"{user_message}\""
        
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        raw_json = response.text.strip()
        data = json.loads(raw_json)
        print(f"[AI INTEL] Sentiment: {data.get('sentiment')} | Intent: {data.get('intent')}")
        return data
    except Exception as e:
        print(f"[AI INTEL ERROR] {e}")
        return None


def get_ai_reply_simple(user_message: str) -> str:
    """Fallback simple text reply"""
    res = analyze_and_reply(user_message)
    if res and res.get("reply_text"):
        return res.get("reply_text")
    return None


def analyze_product_image(image_url: str, page_access_token: str = None) -> str:
    """
    Customer এর পাঠানো ছবি দেখে Gemini Vision দিয়ে product identify করে।
    """
    client = _get_client()
    if not client:
        return "ছবিটি দেখতে পাচ্ছি! আমাদের পণ্য সম্পর্কে জানতে 'চুড়ি' বা 'পায়েল' লিখুন। 😊"

    try:
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
- সেই পণ্যের দাম ও অফার জানাও (চুড়ি হলে প্রতি ১২ পিসে ৪ পিস ঘুগুর ফ্রি + ডেলিভারি ফ্রি)
- যদি না মিলে, তবু সুন্দরভাবে বলো এবং আমাদের পণ্য দেখার আমন্ত্রণ জানাও
- সবসময় বাংলায় কথা বলো
- ম্যাডাম/স্যার বা আপু/ভাই বলে সম্বোধন করো
- ৩-৪ লাইনে reply দাও"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
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


def get_product_image_url(product_name: str) -> str:
    products = _load_products()
    name_lower = product_name.lower()
    for p in products:
        if p["name"].lower() in name_lower or name_lower in p["name"].lower():
            url = p.get("image", "").strip()
            if url and url.startswith("http"):
                return url
    return None


def get_keyword_product_image(keyword: str) -> str:
    products = _load_products()
    kl = keyword.lower()
    for p in products:
        name = p["name"].lower()
        cat  = p.get("category", "").lower()
        if kl in name or kl in cat:
            url = p.get("image", "").strip()
            if url and url.startswith("http"):
                return url
    return None
