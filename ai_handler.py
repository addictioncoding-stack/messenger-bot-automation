"""
=====================================================
  Gemini AI Handler — Bella Basket Jewelry Bot
  Uses new google-genai SDK
=====================================================
"""

import os
import json

try:
    from google import genai
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


def _build_system_prompt():
    products_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "products.json"
    )
    products_text = ""
    try:
        with open(products_file, "r", encoding="utf-8") as f:
            products = json.load(f)
        for p in products:
            colors = ", ".join(p.get("colors", [])) or "-"
            gift   = p.get("free_gift", "-")
            products_text += f"• {p['name']} — ৳{p['price']} | প্যাকেজ: {p['package']} | গিফট: {gift}"
            if colors != "-":
                products_text += f" | রঙ: {colors}"
            products_text += "\n"
    except Exception as e:
        print(f"[AI] products.json error: {e}")
        products_text = "তথ্য লোড হয়নি।"

    return f"""তুমি Bella Basket Jewelry-এর customer service agent। তোমার নাম "Bella"।

আমাদের পণ্য:
{products_text}
আজকের অফার: গিফট সম্পূর্ণ ফ্রি + ডেলিভারি সম্পূর্ণ ফ্রি!
বিকাশ নম্বর: 01937281260 (পার্সোনাল)
ক্যাশ অন ডেলিভারি: পণ্য পেয়ে টাকা দিন।
ডেলিভারি: ঢাকা ১-২ দিন, বাইরে ২-৪ দিন।

নিয়ম:
- সবসময় বাংলায় কথা বলো
- customer কে "আপু" বা "ভাই" বলে ডাকো
- reply সংক্ষিপ্ত রাখো (৩-৫ লাইন)
- অর্ডার করতে চাইলে "অর্ডার করব" লিখতে বলো
- কখনো ইংরেজিতে কথা বলবে না"""


def get_ai_reply_simple(user_message: str) -> str:
    """Gemini দিয়ে বাংলায় reply তৈরি করো"""
    client = _get_client()
    if client is None:
        return None
    try:
        system = _build_system_prompt()
        full_prompt = f"{system}\n\nCustomer বলেছে: {user_message}"
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
        )
        reply = response.text.strip()
        print(f"[AI] Generated reply ({len(reply)} chars)")
        return reply
    except Exception as e:
        print(f"[AI ERROR] {e}")
        return None
