"""
=====================================================
  Gemini AI + Vision + Context Intelligence Handler
  Bella Basket Jewelry Bot
  Uses google-genai SDK (gemini-3.6-flash)
=====================================================
"""

import os, json, re
import httpx
from dotenv import load_dotenv

load_dotenv()

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
        delivery = p.get("delivery", "ফ্রি")
        ai_inst = p.get("ai_instructions", "").strip()
        lines += f"• {p['name']} — ৳{p['price']} | একক: {p.get('unit_name','পিস')} | প্যাকেজ: {p['package']} | ডেলিভারি: {delivery} | গিফট: {gift}"
        if colors != "-":
            lines += f" | রঙ: {colors}"
        if ai_inst:
            lines += f" | ⚠️ বিশেষ অফার/AI নির্দেশনা: {ai_inst}"
        lines += "\n"
    return lines


def _custom_replies_text():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "replies.json")
    try:
        with open(f, "r", encoding="utf-8") as fp:
            reps = json.load(fp)
            if not reps: return ""
            return "\n".join([f"• '{k}': {v}" for k, v in reps.items()])
    except:
        return ""


def _system_prompt():
    custom_reps = _custom_replies_text()
    custom_reps_section = f"\nঅ্যাডমিন দ্বারা নির্ধারিত কাস্টম রিপ্লাই (এই বিষয়গুলো জিজ্ঞেস করলে এই তথ্য দেবে):\n{custom_reps}\n" if custom_reps else ""

    return f"""তুমি Bella Basket Jewelry-এর অত্যন্ত বুদ্ধিমান AI কাস্টমার সার্ভিস এজেন্ট। তোমার নাম "Bella"।

আমাদের পণ্যসমূহ:
{_products_text()}
{custom_reps_section}
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
   - বাটারফ্লাই ব্লিস জুয়েলারি সেট: ৳৬৫০
   - লাভ ব্লিস জুয়েলারি সেট: ৳৬৫০
   - স্নেক গোল্ড পায়েল: ৳৩৫০
   - নেকলেস এবং পায়েলের সাথে কোনো ফ্রি গিফট নেই, কিন্তু ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!

5. **ক্রস-সেলিং (Cross-sell) নিয়ম:**
   - কাস্টমার যখন একটি পণ্য নিতে আগ্রহ দেখাবে বা অর্ডার করবে, তাকে সাথে আরেকটি পণ্যও অফার করবে। যেমন:
     - চুড়ি কিনলে সাথে পরার জন্য স্নেক গোল্ড পায়েল (৳৩৫০) অথবা বাটারফ্লাই সেট (৳৬৫০) সাজেস্ট করবে।
     - একাধিক পণ্য নিলে সবগুলোর দাম একসাথে যোগ করে মোট মূল্য জানাবে এবং ডেলিভারি ফ্রি নিশ্চিত করবে।

6. **কাস্টমার না নিতে চাইলে অন্য পণ্য সাজেশন (Alternative Suggestion):**
   - কাস্টমার যদি কোনো পণ্য না নিতে চায় বা দ্বিধাদ্বন্দ্বে থাকে (যেমন "না", "দরকার নেই", "নিব না", "দাম বেশি"):
     - প্রথমে বলবে: "আজকের জন্যই এই স্পেশাল অফার এবং ডেলিভারি ফ্রি ম্যাডাম/স্যার!"
     - তারপরও না চাইলে অন্য পণ্য সাজেস্ট করবে: "চুড়ি না লাগলে আমাদের জনপ্রিয় বাটারফ্লাই জুয়েলারি সেট (৳৬৫০) অথবা স্নেক গোল্ড পায়েল (৳৩৫০) দেখতে পারেন। ছবি পাঠাবো কি?"

7. **পণ্য তালিকা সংক্রান্ত নিয়ম (কাস্টমার যদি 'কি কি আছে', 'কী আছে', 'ki ki ache', 'products', 'কী পণ্য আছে' জানতে চায়):**
   - সবসময় সুন্দরভাবে আমাদের সব পণ্য, দাম ও অফার তালিকা করে জানিয়ে দেবে:
     ✨ কাশ্মীরি চুড়ি: ১ ডজন ৳৬৫০ (৪ পিস ঘুগুর ফ্রি), ২ ডজন ৳১,১০০ (৮ পিস ঘুগুর ফ্রি)
     ✨ বাটারফ্লাই ব্লিস জুয়েলারি সেট — ৳৬৫০
     ✨ লাভ ব্লিস জুয়েলারি সেট — ৳৬৫০
     ✨ স্নেক গোল্ড পায়েল — ৳৩৫০
   - আজ সব পণ্যে ডেলিভারি চার্জ সম্পূর্ণ ফ্রি তা মনে করিয়ে দিয়ে আন্তরিকভাবে জিজ্ঞেস করবে কোনটি দেখতে চান।

8. **কথাবার্তার ধরন ও ভদ্রতা:**
   - সবসময় কাস্টমারকে "আপু", "ভাই", "ম্যাডাম" বা "স্যার" বলে সম্বোধন করবে।
   - উত্তর সবসময় সুন্দর, স্বাভাবিক, কাস্টমারবান্ধব বাংলায় দেবে।

9. **প্রোডাক্ট ও দাম সংক্রান্ত বিক্রয় ফানেল (Sales Funnel - অত্যন্ত গুরুত্বপূর্ণ):**
   - কাস্টমার যদি কোনো পণ্যের দাম জানতে চায় বা দেখতে চায় (যেমন "দাম কত", "dam koto", "চুড়ির দাম কত", "price?", "চুড়ি দেখাও", "pic"):
     - প্রথমে সুন্দরভাবে ছবির কালারগুলো দেখতে বলবে এবং আন্তরিকভাবে জিজ্ঞেস করবে: "আপু/ভাইয়া, এখানে আমাদের আকর্ষণীয় কালারগুলো দেওয়া হলো! আপনার কোন কালারটি সবচেয়ে বেশি পছন্দ হয়েছে বলুন তো? 😊"
   - কাস্টমার যখন কোনো কালার পছন্দ করবে বা কালারের কথা বলবে:
     - তখন আন্তরিক প্রশংসার সাথে দাম ও আকর্ষণীয় অফার তুলে ধরবে:
       "দারুণ পছন্দ! এই কালারটি সত্যিই অসম্ভব সুন্দর লাগে। 💖
       আমাদের কাশ্মীরি চুড়ির অফার মূল্য:
       • ১ ডজন (১২ পিস) — মাত্র ৳৬৫০ (🎁 সাথে ৪ পিস ঘুঙুর একদম ফ্রি!)
       • ২ ডজন (২৪ পিস) — মাত্র ৳১,১০০ (🎁 সাথে ৮ পিস ঘুঙুর ফ্রি!)
       🚚 ডেলিভারি চার্জ সম্পূর্ণ ফ্রি!
       আপনার হাতের মাপ কত? (২৪ / ২৬ / ২৮) এবং কয় ডজন নিতে চান জানাবেন?"
   - কাস্টমার যদি দ্বিধাদ্বন্দ্বে থাকে, দাম বেশি বলে বা পছন্দ হচ্ছে না বলে:
     - তাকে সুন্দর করে পুশ করবে (Persuasion Push): "আজকের জন্যই কিন্তু আমাদের এই বিশেষ ছাড় ও ফ্রি গিফট অফার আপু/ভাইয়া! প্রিমিয়াম কোয়ালিটি এবং ক্যাশ অন ডেলিভারিতে চেক করে মূল্য দেওয়ার সুযোগ রয়েছে, তাই কোনো ঝুঁকি নেই!"
   - কাস্টমার যদি তবুও চুড়ি না নিতে চায় বা রিফিউজ করে:
     - তখন আন্তরিকভাবে বিকল্প অন্য পণ্য সাজেস্ট করবে: "কোনো সমস্যা নেই আপু/ভাইয়া! 😊 চুড়ি না নিতে চাইলে আমাদের বাটারফ্লাই জুয়েলারি সেট (৳৬৫০) অথবা স্নেক গোল্ড পায়েল (৳৩৫০) দেখতে পারেন।"

JSON Output Format (বাধ্যতামূলক):
তুমি নিচের JSON ফরম্যাটে উত্তর দেবে:
{{
  "reply_text": "কাস্টমারকে পাঠানোর মতো বাংলায় সুন্দর উত্তর",
  "sentiment": "Good" (যদি পজিটিভ, প্রশংসা, অর্ডার ইচ্ছুক হয়) / "Bad" (যদি না করে, কমপ্লেন করে, রাগ করে, অনিচ্ছুক হয়) / "General" (যদি সাধারণ প্রশ্ন বা হাই-হ্যালো হয়),
  "intent": "কাস্টমারের মেসেজের উদ্দেশ্য (GREETING/QUERY/ORDER/REFUSAL/SIZE/DOZEN/OTHER)",
  "detected_product": "যদি কোনো পণ্যের নাম বোঝা যায়",
  "detected_color": "যদি কোনো কালারের নাম বা পছন্দ উল্লেখ করে",
  "detected_size": "যদি সাইজ উল্লেখ করে (24, 26, 28, 22, 30)",
  "detected_dozen": "যদি ডজন উল্লেখ করে"
}}
"""


def analyze_and_reply(user_message: str, current_state: str = "IDLE", product_context: str = "", chat_history: str = "") -> dict:
    """
    Gemini AI দিয়ে মেসেজ ও পূর্ববর্তী ১০টি মেসেজের ইতিহাস বিশ্লেষণ করে বুদ্ধিমান উত্তর, সেন্টিমেন্ট এবং ইন্টেন্ট দেয়।
    """
    client = _get_client()
    if not client:
        return None

    try:
        context_info = f"বর্তমান স্টেট: {current_state}"
        if product_context:
            context_info += f" | কাস্টমারের পছন্দের পণ্য: {product_context}"

        history_section = f"\n[পূর্ববর্তী কথপোকথন / চ্যাট ইতিহাস]:\n{chat_history}\n" if chat_history else ""

        prompt = f"""{_system_prompt()}

[{context_info}]
{history_section}
Customer এর নতুন বার্তা: "{user_message}"

নির্দেশনা:
- কাস্টমারের আগের কথাগুলো এবং নতুন বার্তার ধারাবাহিকতা (Context) খুব ভালো করে পড়বে।
- কাস্টমার যদি আগের মেসেজে চুড়ি বা কোনো পণ্য নিয়ে কথা বলছিল, কিন্তু এখন অনিচ্ছা প্রকাশ করে (যেমন "nibo na", "nibo na churi", "দরকার নেই", "নিব না", "পরে নিব", "চাই না"):
  - intent নির্ধারণ করবে "REFUSAL"
  - sentiment নির্ধারণ করবে "Bad"
  - কোনো অবস্থাতেই সাইজ বা মাপ জানতে চাইবে না!
  - বরং ভদ্রভাবে বলবে যে কোনো সমস্যা নেই, এবং সাথে অন্য কোনো আকর্ষণীয় পণ্য (যেমন বাটারফ্লাই জুয়েলারি সেট ৳৬৫০ বা স্নেক গোল্ড পায়েল ৳৩৫০) দেখতে চান কি না সুন্দরভাবে জানতে চাইবে।
- কাস্টমার যদি কোনো অর্ডার স্টেটে থাকা অবস্থায় (যেমন সাইজ, ডজন, নাম, মোবাইল বা ঠিকানা চাওয়ার সময়) সরাসরি উত্তর না দিয়ে কোনো প্রশ্ন করে (যেমন "ডেলিভারি চার্জ কত?", "কবে পাবো?", "দোকান কোথায়?", "ক্যাশ অন আছে?"):
  - intent নির্ধারণ করবে "QUERY"
  - কাস্টমারের প্রশ্নের সরাসরি সঠিক তথ্য দিয়ে আন্তরিক ও সাহায্যকারী উত্তর দেবে।
  - রোবটের মতো একই কথা বারবার হুবহু রিপিট করবে না।
"""
        
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


def analyze_audio_attachment(audio_url: str, page_access_token: str = None) -> str:
    """
    Customer এর পাঠানো Voice Note অডিও ফাইল Gemini দিয়ে শুনে টেক্সট/ভাবার্থ উদ্ধার করে।
    """
    client = _get_client()
    if not client:
        return ""

    try:
        headers = {}
        if page_access_token:
            headers["Authorization"] = f"Bearer {page_access_token}"

        resp = httpx.get(audio_url, headers=headers, timeout=25, follow_redirects=True)
        audio_data = resp.content
        mime_type = resp.headers.get("content-type", "audio/mp4").split(";")[0].strip()

        if not audio_data:
            return ""

        prompt = "এই ভয়েস মেসেজটিতে কাস্টমার বাংলায় কী বলেছেন তা হুবহু টেক্সটে রূপান্তর (transcribe) করো। কোনো বাড়তি ভূমিকা দরকার নেই।"

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(data=audio_data, mime_type=mime_type),
                prompt,
            ],
        )
        transcription = response.text.strip()
        print(f"[AUDIO TRANSCRIBED] {transcription}")
        return transcription
    except Exception as e:
        print(f"[AUDIO ERROR] {e}")
        return ""


def analyze_product_image(image_url: str, page_access_token: str = None) -> dict:
    """
    Customer এর পাঠানো ছবি দেখে Gemini Vision দিয়ে:
    1. পেমেন্ট স্লিপ/স্ক্রিনশট কিনা (bKash/Nagad/Rocket) তা যাচাই করে
    2. নাকি গহনা/পণ্য খুঁজেছে তা সনাক্ত করে
    Returns dict: {"type": "payment"|"product"|"other", "reply": "...", "matched_product": "..."}
    """
    client = _get_client()
    if not client:
        return {
            "type": "product",
            "reply": "ছবিটি দেখতে পাচ্ছি! আমাদের পণ্য সম্পর্কে জানতে 'চুড়ি' বা 'পায়েল' লিখুন। 😊",
            "matched_product": None
        }

    try:
        headers = {}
        if page_access_token:
            headers["Authorization"] = f"Bearer {page_access_token}"

        img_resp = httpx.get(image_url, headers=headers, timeout=20, follow_redirects=True)
        img_data = img_resp.content
        mime_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()

        if not img_data:
            return {
                "type": "error",
                "reply": "ছবিটি ঠিকমতো লোড হয়নি। আবার পাঠান! 😊",
                "matched_product": None
            }

        prompt = f"""এই ছবিটি ভালো করে বিশ্লেষণ করো এবং JSON ফরম্যাটে উত্তর দাও:

আমাদের Bella Basket Jewelry-এর পণ্য তালিকা:
{_products_text()}

নির্দেশনা:
1. যদি এটি কোনো পেমেন্ট স্লিপ বা ট্রানজেকশন স্ক্রিনশট হয় (যেমন বিকাশ, নগদ, রকেটে টাকা পাঠানোর স্ক্রিনশট বা TrxID):
   - type: "payment"
   - reply: "আপনার পেমেন্টের স্ক্রিনশটটি সফলভাবে পেয়েছি! ধন্যবাদ 😊 আমরা ট্রানজেকশনটি ভেরিফাই করে দ্রুত অর্ডারটি পাঠিয়ে দেবো।"
2. যদি এটি কোনো jewelry বা পণ্যের ছবি হয়:
   - type: "product"
   - matched_product: আমাদের তালিকাভুক্ত পণ্যটির নাম (যেমন 'কাশ্মীরি চুড়ি (১ ডজন)', 'বাটারফ্লাই ব্লিস জুয়েলারি সেট', 'স্নেক গোল্ড পায়েল')
   - reply: ছবির গহনাটি আমাদের কোন পণ্যের অনুরূপ তা জানিয়ে দাম ও আকর্ষণীয় অফারসহ ৩-৪ লাইনে সুন্দর বাংলায় উত্তর দাও।
3. অন্য কোনো ছবি হলে:
   - type: "other"
   - reply: "ছবিটি দেখলাম! আমাদের সুন্দর সব গহনা দেখতে 'চুড়ি', 'পায়েল' বা 'জুয়েলারি সেট' লিখে পাঠান 😊"

JSON ফরম্যাট:
{{
  "type": "payment" | "product" | "other",
  "matched_product": "পণ্যের নাম বা null",
  "reply": "বাংলায় মেসেজ"
}}
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(data=img_data, mime_type=mime_type),
                prompt,
            ],
        )
        raw_text = response.text.strip()
        # Clean potential markdown wrapping
        cleaned = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        print(f"[VISION ANALYZED] Type: {data.get('type')}")
        return data

    except Exception as e:
        print(f"[VISION ERROR] {e}")
        return {
            "type": "product",
            "reply": "ছবিটি দেখলাম! আমাদের পণ্য সম্পর্কে জানতে লিখুন:\n\"চুড়ি\" | \"পায়েল\" | \"জুয়েলারি সেট\" 😊",
            "matched_product": None
        }


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
            if url and (url.startswith("http") or url.startswith("/")):
                return url
    return None

def get_keyword_product_images_list(keyword: str) -> list:
    if not keyword:
        return []
    products = _load_products()
    kl = str(keyword).lower()
    base_dir = os.path.dirname(os.path.abspath(__file__))

    def filter_valid(images):
        valid = []
        for url in images:
            if not url: continue
            if url.startswith("http"):
                valid.append(url)
            elif url.startswith("/static/"):
                rel = url.lstrip("/").replace("/", os.sep)
                full = os.path.join(base_dir, rel)
                if os.path.exists(full):
                    valid.append(url)
            elif url.startswith("/"):
                valid.append(url)
        return valid

    # 1. Direct name match first
    for p in products:
        p_name = p["name"].lower()
        if p_name in kl or (len(kl) > 3 and kl in p_name):
            imgs = p.get("images", [])
            if not imgs and p.get("image"):
                imgs = [p.get("image").strip()]
            valid = filter_valid(imgs)
            if valid:
                return valid

    # 2. Banglish and Bangla category keywords
    target_category = None
    has_churi_kw = any(k in kl for k in ["চুড়ি", "চুড়ি", "churi", "chury", "বাংলস", "bangle", "bangles", "কাশ্মীরি", "kashmiri"])
    has_payal_kw = any(k in kl for k in ["পায়েল", "পায়েল", "payel", "payal", "pael", "নূপুর", "nupur", "স্নেক", "snake"])
    has_set_kw   = any(k in kl for k in ["বাটারফ্লাই", "butterfly", "লাভ ব্লিস", "love bliss", "নেকলেস", "necklace", "জুয়েলারি", "jewelry"]) or (("সেট" in kl or "set" in kl) and not has_churi_kw and not has_payal_kw)

    if has_payal_kw and not has_churi_kw:
        target_category = "পায়েল"
    elif has_set_kw and not has_churi_kw:
        target_category = "জুয়েলারি সেট"
    elif has_churi_kw:
        target_category = "চুড়ি"

    if target_category:
        for p in products:
            if p.get("category", "").lower() == target_category.lower():
                imgs = p.get("images", [])
                if not imgs and p.get("image"):
                    imgs = [p.get("image").strip()]
                valid = filter_valid(imgs)
                if valid:
                    return valid

    # 3. General word match
    for p in products:
        name = p["name"].lower()
        cat  = p.get("category", "").lower()
        if any(word in name or word in cat for word in kl.split() if len(word) > 2):
            imgs = p.get("images", [])
            if not imgs and p.get("image"):
                imgs = [p.get("image").strip()]
            valid = filter_valid(imgs)
            if valid:
                return valid

    return []
