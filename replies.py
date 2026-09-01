"""
=====================================================
  Facebook Messenger Auto-Reply Bot
  ফেসবুক মেসেঞ্জার অটো-রিপ্লাই বট
=====================================================

এই ফাইলে আপনার auto-reply rules সেট করুন।
"""

# ====================================================
# AUTO-REPLY RULES (এখানে আপনার উত্তর সেট করুন)
# ====================================================

# Keyword-based replies
# যদি customer এর মেসেজে এই শব্দ থাকে, তাহলে এই উত্তর যাবে
KEYWORD_REPLIES = {
    # সালাম / হ্যালো
    "হ্যালো": "হ্যালো! আমাদের পেজে স্বাগতম 😊 আপনাকে কিভাবে সাহায্য করতে পারি?",
    "hello": "Hello! Welcome to our page 😊 How can I help you?",
    "hi": "Hi there! 👋 How can I assist you today?",
    "salam": "ওয়ালাইকুমুস সালাম! 😊 আপনাকে কিভাবে সাহায্য করতে পারি?",
    "salaam": "ওয়ালাইকুমুস সালাম! 😊 আপনাকে কিভাবে সাহায্য করতে পারি?",
    "আস্সালামু আলাইকুম": "ওয়ালাইকুমুস সালাম! 😊 আপনাকে কিভাবে সাহায্য করতে পারি?",

    # দাম জিজ্ঞেস
    "দাম": "আমাদের পণ্যের দাম জানতে নিচের লিংক ভিজিট করুন অথবা আপনার পণ্যের নাম লিখুন:\n👉 www.yourwebsite.com/products",
    "price": "Please visit our website for pricing or mention the product name:\n👉 www.yourwebsite.com/products",
    "কত টাকা": "আপনি কোন পণ্যের দাম জানতে চাইছেন? পণ্যের নামটি লিখুন, আমরা জানিয়ে দেবো 😊",
    "মূল্য": "আপনি কোন পণ্যের মূল্য জানতে চাইছেন? পণ্যের নামটি লিখুন, আমরা জানিয়ে দেবো 😊",

    # অর্ডার
    "অর্ডার": "অর্ডার করতে নিচের ফর্ম পূরণ করুন:\n👉 www.yourwebsite.com/order\nঅথবা আমাদের হোয়াটসঅ্যাপে যোগাযোগ করুন: 01XXXXXXXXX",
    "order": "To place an order, fill out this form:\n👉 www.yourwebsite.com/order\nOr WhatsApp us: 01XXXXXXXXX",

    # ডেলিভারি
    "ডেলিভারি": "আমরা সারা বাংলাদেশে ডেলিভারি দিই 🚚\nঢাকার ভেতরে: ১-২ দিন\nঢাকার বাইরে: ৩-৫ দিন",
    "delivery": "We deliver all over Bangladesh 🚚\nInside Dhaka: 1-2 days\nOutside Dhaka: 3-5 days",

    # পেমেন্ট
    "পেমেন্ট": "আমরা নিচের মাধ্যমে পেমেন্ট নিই:\n💳 বিকাশ\n💳 নগদ\n💳 রকেট\n💳 ক্যাশ অন ডেলিভারি",
    "payment": "We accept:\n💳 bKash\n💳 Nagad\n💳 Rocket\n💳 Cash on Delivery",
    "bkash": "আমাদের বিকাশ নম্বর: 01XXXXXXXXX (পার্সোনাল)\nপেমেন্টের পর স্ক্রিনশট পাঠান।",

    # যোগাযোগ
    "ফোন": "আমাদের ফোন নম্বর: 01XXXXXXXXX\nসময়: সকাল ৯টা - রাত ৯টা",
    "contact": "📞 Phone: 01XXXXXXXXX\n📧 Email: your@email.com\n⏰ Hours: 9AM - 9PM",
    "নম্বর": "আমাদের ফোন নম্বর: 01XXXXXXXXX\nসময়: সকাল ৯টা - রাত ৯টা",

    # ধন্যবাদ
    "ধন্যবাদ": "আপনাকেও ধন্যবাদ! 😊 আর কোনো প্রশ্ন থাকলে জানাবেন।",
    "thanks": "You're welcome! 😊 Feel free to ask if you have more questions.",
    "thank you": "You're welcome! 😊 Feel free to ask if you have more questions.",
}

# Default reply - যদি কোনো keyword না মিলে
DEFAULT_REPLY = """আপনার মেসেজের জন্য ধন্যবাদ! 😊

আমাদের টিম শীঘ্রই আপনার সাথে যোগাযোগ করবে।

এর আগে এই তথ্যগুলো কাজে লাগতে পারে:
📦 পণ্য দেখতে: www.yourwebsite.com
📞 ফোন: 01XXXXXXXXX
⏰ অফিস সময়: সকাল ৯টা - রাত ৯টা

আপনি যদি দ্রুত উত্তর পেতে চান, এই keywords লিখুন:
• "দাম" - পণ্যের মূল্য জানতে
• "অর্ডার" - অর্ডার করতে
• "ডেলিভারি" - ডেলিভারি তথ্য
• "পেমেন্ট" - পেমেন্ট পদ্ধতি"""
