TRANSLATIONS = {
    "en": {
        "menu_main": "🏠 Main Menu",
        "menu_categories": "🛍️ Shop by Category",
        "menu_cart": "🛒 My Cart",
        "menu_orders": "📦 Order Status",
        "menu_human": "🧑‍💻 Talk to Staff",
        "menu_language": "🌐 Change Language",
        "menu_recommend": "✨ Recommended for You",
        "cart_checkout": "💳 Checkout",
        "cart_clear": "🗑️ Clear Cart",
        "menu_size": "📏 Find My Size",
        "welcome": "Welcome to DEEN Commerce! 👋 How can I help you today?",
        "categories_body": "Choose a category from the list below to view products:",
        "categories_btn": "Select Category",
        "cart_empty": "🛒 Your cart is currently empty.",
        "cart_summary": "🛒 *Your Cart Summary*",
        "total": "Total",
        "options": "Options",
        "btn_select": "Select Option"
    },
    "bn": {
        "menu_main": "🏠 মেইন মেনু",
        "menu_categories": "🛍️ ক্যাটাগরি দেখুন",
        "menu_cart": "🛒 আমার কার্ট",
        "menu_orders": "📦 অর্ডার স্ট্যাটাস",
        "menu_human": "🧑‍💻 স্টাফের সাথে কথা বলুন",
        "menu_language": "🌐 Change Language",
        "menu_recommend": "✨ আপনার জন্য প্রস্তাবিত",
        "cart_checkout": "💳 চেকআউট",
        "cart_clear": "🗑️ কার্ট খালি করুন",
        "menu_size": "📏 সাইজ খুঁজুন",
        "welcome": "DEEN Commerce এ স্বাগতম! 👋 আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
        "categories_body": "পণ্য দেখতে নিচের তালিকা থেকে একটি ক্যাটাগরি বেছে নিন:",
        "categories_btn": "ক্যাটাগরি নির্বাচন করুন",
        "cart_empty": "🛒 আপনার কার্ট বর্তমানে খালি আছে।",
        "cart_summary": "🛒 *আপনার কার্টের সারসংক্ষেপ*",
        "total": "মোট",
        "options": "অপশন",
        "btn_select": "অপশন বেছে নিন"
    }
}

def get_text(lang: str, key: str) -> str:
    """Helper to get translated text with fallback to English."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
