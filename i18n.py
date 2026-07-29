"""
Internationalization module for DEEN Commerce WhatsApp Bot.

Supports three languages:
  - en  → English
  - bn  → Bangla (বাংলা)
  - blish → Banglish (Bangla written in Latin script, e.g. "ami" = আমি)

The ``get_text()`` helper fetches the correct string, falling back to English.
For messages containing placeholders, use the ``format_text()`` helper which
applies Python's ``.format()`` after translation.
"""

TRANSLATIONS = {
    # =========================================================================
    # ENGLISH
    # =========================================================================
    "en": {
        # --- Menu labels ---
        "menu_main": "🏠 Main Menu",
        "menu_categories": "Browse Catalog",
        "menu_cart": "My Cart",
        "menu_orders": "My Orders",
        "menu_human": "Talk to Staff",
        "menu_language": "Change Language",
        "menu_search": "Search Products",
        "menu_recommend": "Recommended for You",
        "menu_size": "Find My Size",
        "menu_cancel_order": "Cancel Order",
        "menu_browse": "Browse Catalog",
        "cart_checkout": "Checkout",
        "cart_clear": "Clear Cart",
        "btn_select_size": "Select Size",
        "btn_view_cart": "🛍️ View Cart",
        "btn_browse_more": "Browse More",
        "btn_main_menu": "🏠 Main Menu",
        "btn_start_shopping": "Start Shopping",
        "btn_browse_catalog": "Browse Catalog",
        "btn_view_orders": "📦 View Orders",
        "btn_confirm_order": "👍 Confirm Order",
        "btn_cancel": "❌ Cancel",
        "btn_yes_cancel": "Yes, Cancel Order",
        "btn_no_keep": "No, Keep Order",
        "btn_select_product": "Select Product",
        "btn_view_matches": "View Matches",
        "btn_view_products": "View Products",
        "btn_open_menu": "☰ Open Menu",
        "btn_select_category": "Select Category",
        "btn_add_to_cart": "🛒 Add to Cart",
        "btn_size_chart": "📐 Size Chart",
        "btn_select_option": "Select Option",
        "btn_view_detail": "View details",

        # --- Welcome & main menu ---
        "welcome": "Welcome to DEEN Commerce! 👋 How can I help you today?",
        "categories_body": "Choose a category from the list below to view products:",
        "categories_btn": "Select Category",
        "choose_category": "Choose a category:",
        "select_product": "Select a product to see details:",

        # --- Descriptions for the main menu list items ---
        "desc_search": "Find exactly what you're looking for",
        "desc_explore": "Explore our collections and special offers",
        "desc_for_you": "Personalized picks based on your purchase history",
        "desc_cart_items": "You have items waiting — ready to checkout?",
        "desc_empty_cart": "Your cart is currently empty",
        "desc_find_size": "Get instant size recommendations",
        "desc_view_orders": "Track your recent purchases",
        "desc_cancel_order": "Request cancellation for a recent order",
        "desc_talk_human": "Chat with a real human agent",
        "desc_change_lang": "Switch between English / বাংলা",
        "desc_clear_cart": "Remove all items from your cart",
        "desc_view_detail": "View details",
        "desc_out_of_stock": "Out of Stock",

        # --- Cart ---
        "cart_empty": "🛒 Your cart is currently empty.",
        "cart_empty_shop": "Your shopping cart is currently empty! 🛒\n\nBrowse our catalog to add items.",
        "cart_summary": "🛒 *Your Shopping Cart:*",
        "cart_total": "Total Amount",
        "cart_item_price": "Price",
        "cart_item_subtotal": "Subtotal",
        "cart_remove_hint": "Remove: Reply _Remove {product_id}_",
        "item_added": "✅ *{product_name}* has been added to your cart!",
        "item_removed": "❌ Removed product #{product_id} from your cart.",
        "variation_added": "✅ *{product_name}* has been added to your cart!",
        "cart_cleared": "🗑️ Your shopping cart has been cleared.",
        "no_items_to_checkout": "Your cart is empty. Please add items before checking out.",
        "cart_empty_shop_start": "Your cart is empty. Browse products to start shopping!",

        # --- Checkout ---
        "checkout_instruction": (
            "💳 *Checkout Instructions*\n\n"
            "Please reply with your name and shipping address in the following format:\n\n"
            "*Your Full Name, Your Shipping Address*\n\n"
            "Example:\n"
            "_John Doe, 123 Main Street, New York_\n\n"
            "Or type *cancel* to go back."
        ),
        "checkout_invalid_format": (
            "⚠️ Invalid format.\n\n"
            "Please reply like this:\n"
            "*Name, Full Address*\n\n"
            "Or type *cancel* to go back."
        ),
        "checkout_confirm_title": "📋 *Confirm your Cash on Delivery (COD) Order*\n\n",
        "checkout_confirm_fields": (
            "Name: *{name}*\n"
            "Shipping Address:\n_{address}_\n\n"
            "Total Amount: *BDT {total:.2f}*\n"
            "Payment Method: *Cash on Delivery (COD)*\n\n"
            "Do you want to confirm and place this order?"
        ),
        "checkout_placing": "⏳ Placing your order, please wait...",
        "checkout_success": (
            "🎉 *Order Placed Successfully!*\n\n"
            "Order ID: *#{order_id}*\n"
            "Total Amount: *BDT {total}*\n"
            "Payment Method: *{payment_method}*\n\n"
            "We will ship your items to:\n_{address}_\n\n"
            "Thank you for shopping with us!"
        ),
        "checkout_failed": "❌ Failed to place order in our system. Please try again later.",
        "checkout_cancelled": "Order checkout cancelled.",
        "session_expired": "❌ Session expired. Checkout cancelled.",
        "product_unavailable": "Sorry, that product is no longer available.",
        "size_unavailable": "Sorry, that size option is no longer available.",

        # --- Orders ---
        "no_orders": "You haven't placed any orders with this phone number yet.",
        "orders_title": "📦 *Your Recent Orders:*\n\n",
        "order_line": "• *Order #{order_id}* - {date}\n  Status: *{status}*\n  Items: {items}\n  Total: BDT {total:.2f}\n\n",
        "order_not_found": "❌ We couldn't find order #{order_id} in our store.",
        "order_lookup": "🔍 Looking up order #{order_id}...",
        "order_cancelling": "⏳ Cancelling order #{order_id}...",
        "cancel_failed": "❌ Failed to cancel the order. Please try again or contact support.",
        "cancel_success": "✅ *Order #{order_id} has been cancelled.*\n\nThank you. We hope to serve you again in the future!",
        "cancel_aborted": "Order cancellation aborted. Your order is safe! 👍",

        # --- Order cancellation flow ---
        "cancel_title": "❌ *Order Cancellation*\n\nPlease reply with the Order ID you wish to cancel (e.g. _10254_):\n\nType *cancel* to go back.",
        "cancel_invalid_id": "⚠️ Invalid Order ID. Please reply with a valid numeric Order ID:",
        "cancel_security_fail": (
            "⚠️ Security Check Failed.\n\n"
            "For security reasons, you can only cancel orders placed using this phone number."
        ),
        "cancel_not_possible": (
            "⚠️ Cancellation Not Possible.\n\n"
            "Order #{order_id} is currently *{status}*. "
            "Only orders that are pending or processing can be cancelled automatically. "
            "Please contact a human agent if you need assistance."
        ),
        "cancel_confirm_q": "❓ *Confirm Cancellation*\n\nAre you sure you want to cancel order *#{order_id}*?",

        # --- Products & Search ---
        "no_categories": "Sorry, I couldn't load store categories right now.",
        "no_products_in_cat": "This category doesn't have any products currently.",
        "no_product_details": "Sorry, I couldn't find details for that product.",
        "no_sizes_available": "This product has no available size options at the moment.",
        "no_sizes_available_now": "No sizes are currently available for this product.",
        "search_prompt": "🔍 What are you looking for? Type a product name, category, or description:",
        "search_wait": "🔍 Searching the catalog, please wait...",
        "what_next": "What would you like to do next?",
        "choose_size_for": "Choose your size for *{product_name}*:",
        "available_sizes": "Available Sizes",
        "help_section": "Help",
        "view_size_chart": "📐 View Size Chart",
        "see_sizing_guide": "See our sizing guide",
        "found_matches": "I found these items based on your search:",

        # --- Size Guide ---
        "size_guide_title": "📏 *Size Guide*",
        "size_guide_full": (
            "📏 *Size Guide*\n\n"
            "*Panjabis & Shirts:*\n"
            "• S (Small): Height 5'2\"-5'5\", Weight 50-60 kg (Chest: 38\")\n"
            "• M (Medium): Height 5'5\"-5'7\", Weight 60-70 kg (Chest: 40\")\n"
            "• L (Large): Height 5'7\"-5'10\", Weight 70-80 kg (Chest: 42\")\n"
            "• XL (XL): Height 5'10\"-6'0\", Weight 80-90 kg (Chest: 44\")\n"
            "• XXL (2XL): Height 6'0\"+, Weight 90+ kg (Chest: 46\")\n\n"
            "*Delivery:*\n"
            "• Inside Dhaka: 80 BDT, 2-3 days\n"
            "• Outside Dhaka: 150 BDT, 3-5 days\n"
            "• Cash on Delivery (COD) available nationwide.\n\n"
            "Need a personal recommendation? Use the *Size Assistant* from the main menu!"
        ),

        # --- Size Assistant ---
        "size_assist_title": "📏 *Size Assistant*\n\nLet's find your perfect size! Please reply with your *height* (e.g., _5'6\"_ or _170 cm_):\n\nType *cancel* to abort.",
        "size_height_prompt": "Recorded Height: *{height}*.\n\nNow please reply with your *weight* (e.g., _65 kg_ or _140 lbs_):\n\nType *cancel* to abort.",
        "size_results_title": "📏 *Size Recommendation Results*\n\nRecommended Size: *{size}* (Chest: {chest})\nConfidence Level: *{confidence}*\n\n📝 *Fit Notes:*\n{notes}\n\n🚚 *Delivery Policy:*\n• Inside Dhaka: 80 BDT (2-3 days)\n• Outside Dhaka: 150 BDT (3-5 days)\n• Cash on Delivery (COD) is available nationwide.",
        "size_conf_high": "High",
        "size_conf_medium": "Medium",
        "size_fit_perfect": "Perfect fit! Both your height and weight align with size *{size}* (Chest: {chest}).",
        "size_fit_notes": "Your height suggests size *{small_size}* and weight suggests size *{large_size}* (or vice versa). We recommend size *{rec_size}* (Chest: {chest}) for a comfortable, regular fit. You can choose *{small_size}* if you prefer a tighter, slim fit.",

        # --- Support ---
        "bot_paused_msg": (
            "⏸️ I have paused my automated responses.\n\n"
            "Please click this link to chat directly with our human agent on WhatsApp:\n👉 https://wa.me/{phone}\n\n"
            "Type */resume* when you want me to take over again."
        ),
        "bot_resumed": "✅ Bot resumed. How can I help you?",
        "process_cancelled": "❌ Process cancelled.",
        "action_not_recognized": "I didn't recognize that action. Returning to main menu.",
        "unknown_error": "Sorry, I had trouble processing that action. Returning to main menu.",

        # --- Sentiment escalation ---
        "escalation_msg": (
            "⚠️ *Human Agent Escalation*\n\n"
            "I detect that you are frustrated or need urgent assistance. "
            "I am pausing my automated responses and transferring you to our human support team."
        ),

        # --- Recommendations ---
        "recommend_no_history": "I don't have enough purchase history to make personalized recommendations yet. 😅 But here are some of our most popular items!",
        "recommend_no_items": "I couldn't find items in your past orders. Here are some popular products!",
        "recommend_searching": "Based on your past purchases of:\n_{purchased}_\n\nLet me find some great recommendations for you... 🔍",
        "recommended_items_title": "Recommended Items",
        "matching_results_title": "Matching Results",
        "click_to_view": "Click below to see the specifications, photos or add recommended products to cart:",
        "browse_prompt": "What would you like to do?",
        "no_recommendations": "I couldn't find any specific recommendations right now.",

        # --- Delivery ---
        "delivery_policy": (
            "🚚 *Delivery Policy:*\n"
            "• Inside Dhaka: 80 BDT (2-3 days)\n"
            "• Outside Dhaka: 150 BDT (3-5 days)\n"
            "• Cash on Delivery (COD) is available nationwide."
        ),
        "delivery_dhaka": "Inside Dhaka: 80 BDT (2-3 days)",
        "delivery_outside": "Outside Dhaka: 150 BDT (3-5 days)",
        "delivery_cod": "Cash on Delivery (COD) is available nationwide.",

        # --- Section titles ---
        "section_store": "🛍️ Shop",
        "section_account": "👤 My Account",
        "section_support": "⚙️ Help & Settings",
        "section_special_offers": "🔥 Special Offers",
        "section_mens_collection": "👔 Men's Collection",
        "section_other_categories": "📦 Other Categories",
        "section_available_products": "Available Products",

        # --- Abandoned cart reminders ---
        "cart_reminder_1h": (
            "🛒 *You left items in your cart!*\n\n"
            "Complete your order today to enjoy fast delivery. "
            "Reply with *Cart* to view your items!"
        ),
        "cart_reminder_24h": (
            "🛒 *Friendly Reminder!*\n\n"
            "Your cart is still waiting for you. Would you like to complete your order?\n\n"
            "Reply with *Cart* to view your items, or browse more to add others!"
        ),
        "cart_reminder_72h": (
            "🛒 *Last Chance!*\n\n"
            "We are holding your items for a little longer. "
            "Complete your purchase now before they sell out!\n\n"
            "Reply with *Cart* to view your items and check out."
        ),

        # --- WooCommerce order update ---
        "order_update": "🔔 *Order Update*\n\nYour order #{order_id} is now: *{status}*.",

        # --- Fallback / misc ---
        "price_on_request": "Price on request",
        "in_stock": "✅ In Stock",
        "out_of_stock": "❌ Out of Stock",
        "on_backorder": "⏳ On Backorder",
        "no_reviews": "No reviews yet",
        "general_category": "General",
    },

    # =========================================================================
    # BANGLA (বাংলা)
    # =========================================================================
    "bn": {
        "menu_main": "🏠 মেইন মেনু",
        "menu_categories": "ক্যাটালগ ব্রাউজ করুন",
        "menu_cart": "আমার কার্ট",
        "menu_orders": "আমার অর্ডার",
        "menu_human": "স্টাফের সাথে কথা বলুন",
        "menu_language": "ভাষা পরিবর্তন",
        "menu_search": "পণ্য খুঁজুন",
        "menu_recommend": "আপনার জন্য প্রস্তাবিত",
        "menu_size": "সাইজ খুঁজুন",
        "menu_cancel_order": "অর্ডার বাতিল",
        "menu_browse": "ক্যাটালগ ব্রাউজ করুন",
        "cart_checkout": "চেকআউট",
        "cart_clear": "কার্ট খালি করুন",
        "btn_select_size": "সাইজ নির্বাচন",
        "btn_view_cart": "🛍️ কার্ট দেখুন",
        "btn_browse_more": "আরও ব্রাউজ করুন",
        "btn_main_menu": "🏠 মেইন মেনু",
        "btn_start_shopping": "শপিং শুরু করুন",
        "btn_browse_catalog": "ক্যাটালগ ব্রাউজ করুন",
        "btn_view_orders": "📦 অর্ডার দেখুন",
        "btn_confirm_order": "👍 অর্ডার কনফার্ম",
        "btn_cancel": "❌ বাতিল",
        "btn_yes_cancel": "হ্যাঁ, অর্ডার বাতিল করুন",
        "btn_no_keep": "না, অর্ডার রাখুন",
        "btn_select_product": "পণ্য নির্বাচন",
        "btn_view_matches": "ম্যাচ দেখুন",
        "btn_view_products": "পণ্য দেখুন",
        "btn_open_menu": "☰ মেনু খুলুন",
        "btn_select_category": "ক্যাটাগরি নির্বাচন করুন",
        "btn_add_to_cart": "🛒 কার্টে যোগ করুন",
        "btn_size_chart": "📐 সাইজ চার্ট",
        "btn_select_option": "অপশন বেছে নিন",
        "btn_view_detail": "বিস্তারিত দেখুন",

        "welcome": "DEEN Commerce এ স্বাগতম! 👋 আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
        "categories_body": "পণ্য দেখতে নিচের তালিকা থেকে একটি ক্যাটাগরি বেছে নিন:",
        "categories_btn": "ক্যাটাগরি নির্বাচন করুন",
        "choose_category": "একটি ক্যাটাগরি বেছে নিন:",
        "select_product": "বিস্তারিত দেখতে একটি পণ্য নির্বাচন করুন:",

        "desc_search": "আপনি যা খুঁজছেন তা সরাসরি খুঁজে নিন",
        "desc_explore": "আমাদের কালেকশন এবং বিশেষ অফার দেখুন",
        "desc_for_you": "আপনার ইতিহাসের ভিত্তিতে শুধু আপনার জন্য নির্বাচিত পণ্য",
        "desc_cart_items": "আইটেম অপেক্ষা করছে! চেকআউট করতে প্রস্তুত?",
        "desc_empty_cart": "আপনার কার্ট বর্তমানে খালি",
        "desc_find_size": "তাত্ক্ষণিকভাবে আপনার পারফেক্ট ফিট খুঁজুন",
        "desc_view_orders": "আপনার সাম্প্রতিক ক্রয় এবং স্ট্যাটাস দেখুন",
        "desc_cancel_order": "সাম্প্রতিক অর্ডার বাতিলের অনুরোধ করুন",
        "desc_talk_human": "AI পজ করে একজন রিয়েল হিউম্যানের সাথে চ্যাট করুন",
        "desc_change_lang": "English / বাংলা",
        "desc_clear_cart": "আপনার কার্ট থেকে সব আইটেম মুছুন",
        "desc_view_detail": "বিস্তারিত দেখুন",
        "desc_out_of_stock": "স্টকে নেই",

        "cart_empty": "🛒 আপনার কার্ট বর্তমানে খালি আছে।",
        "cart_empty_shop": "🛒 আপনার শপিং কার্ট বর্তমানে খালি!\n\nআইটেম যোগ করতে আমাদের ক্যাটালগ ব্রাউজ করুন।",
        "cart_summary": "🛒 *আপনার শপিং কার্ট:*",
        "cart_total": "মোট পরিমাণ",
        "cart_item_price": "মূল্য",
        "cart_item_subtotal": "সাবটোটাল",
        "cart_remove_hint": "মুছুন: _Remove {product_id}_ লিখে রিপ্লাই দিন",
        "item_added": "✅ *{product_name}* আপনার কার্টে যোগ করা হয়েছে!",
        "item_removed": "❌ প্রোডাক্ট #{product_id} আপনার কার্ট থেকে সরানো হয়েছে।",
        "variation_added": "✅ *{product_name}* আপনার কার্টে যোগ করা হয়েছে!",
        "cart_cleared": "🗑️ আপনার শপিং কার্ট খালি করা হয়েছে।",
        "no_items_to_checkout": "আপনার কার্ট খালি। চেকআউট করার আগে আইটেম যোগ করুন।",
        "cart_empty_shop_start": "আপনার কার্ট খালি। শপিং শুরু করতে পণ্য ব্রাউজ করুন!",

        "checkout_instruction": (
            "💳 *চেকআউট নির্দেশনা*\n\n"
            "আপনার নাম এবং শিপিং ঠিকানা নিচের ফরম্যাটে লিখে রিপ্লাই দিন:\n\n"
            "*আপনার পুরো নাম, আপনার শিপিং ঠিকানা*\n\n"
            "উদাহরণ:\n"
            "_জন ডো, ১২৩ মেইন স্ট্রিট, নিউ ইয়র্ক_\n\n"
            "অথবা ফিরে যেতে *cancel* টাইপ করুন।"
        ),
        "checkout_invalid_format": (
            "⚠️ ভুল ফরম্যাট।\n\n"
            "অনুগ্রহ করে এভাবে রিপ্লাই দিন:\n"
            "*নাম, সম্পূর্ণ ঠিকানা*\n\n"
            "অথবা ফিরে যেতে *cancel* টাইপ করুন।"
        ),
        "checkout_confirm_title": "📋 *আপনার ক্যাশ অন ডেলিভারি (COD) অর্ডার কনফার্ম করুন*\n\n",
        "checkout_confirm_fields": (
            "নাম: *{name}*\n"
            "শিপিং ঠিকানা:\n_{address}_\n\n"
            "মোট পরিমাণ: *BDT {total:.2f}*\n"
            "পেমেন্ট মেথড: *ক্যাশ অন ডেলিভারি (COD)*\n\n"
            "আপনি কি অর্ডারটি কনফার্ম করতে চান?"
        ),
        "checkout_placing": "⏳ আপনার অর্ডার প্লেস করা হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...",
        "checkout_success": (
            "🎉 *অর্ডার সফলভাবে প্লেস হয়েছে!*\n\n"
            "অর্ডার আইডি: *#{order_id}*\n"
            "মোট পরিমাণ: *BDT {total}*\n"
            "পেমেন্ট মেথড: *{payment_method}*\n\n"
            "আপনার আইটেম পাঠানো হবে:\n_{address}_\n\n"
            "আমাদের সাথে শপিং করার জন্য ধন্যবাদ!"
        ),
        "checkout_failed": "❌ আমাদের সিস্টেমে অর্ডার প্লেস করতে ব্যর্থ। পরে আবার চেষ্টা করুন।",
        "checkout_cancelled": "অর্ডার চেকআউট বাতিল করা হয়েছে।",
        "session_expired": "❌ সেশন শেষ। চেকআউট বাতিল করা হয়েছে।",
        "product_unavailable": "দুঃখিত, এই পণ্যটি আর উপলব্ধ নেই।",
        "size_unavailable": "দুঃখিত, এই সাইজ অপশনটি আর উপলব্ধ নেই।",

        "no_orders": "আপনি এই ফোন নম্বর দিয়ে এখনও কোনো অর্ডার দেননি।",
        "orders_title": "📦 *আপনার সাম্প্রতিক অর্ডার:*\n\n",
        "order_line": "• *অর্ডার #{order_id}* - {date}\n  স্ট্যাটাস: *{status}*\n  আইটেম: {items}\n  মোট: BDT {total:.2f}\n\n",
        "order_not_found": "❌ আমরা স্টোরে অর্ডার #{order_id} খুঁজে পাইনি।",
        "order_lookup": "🔍 অর্ডার #{order_id} খুঁজছি...",
        "order_cancelling": "⏳ অর্ডার #{order_id} বাতিল করা হচ্ছে...",
        "cancel_failed": "❌ অর্ডার বাতিল করতে ব্যর্থ। আবার চেষ্টা করুন বা সাপোর্টে যোগাযোগ করুন।",
        "cancel_success": "✅ *অর্ডার #{order_id} বাতিল করা হয়েছে।*\n\nধন্যবাদ। আমরা ভবিষ্যতে আবার আপনাকে সেবা দেওয়ার আশা করি!",
        "cancel_aborted": "অর্ডার বাতিল বাতিল করা হয়েছে। আপনার অর্ডার নিরাপদ! 👍",

        "cancel_title": "❌ *অর্ডার বাতিল*\n\nআপনি যে অর্ডার আইডি বাতিল করতে চান সেটি লিখে রিপ্লাই দিন (যেমন _10254_):\n\nফিরে যেতে *cancel* টাইপ করুন।",
        "cancel_invalid_id": "⚠️ ভুল অর্ডার আইডি। একটি বৈধ সংখ্যাসূচক অর্ডার আইডি দিয়ে রিপ্লাই দিন:",
        "cancel_security_fail": (
            "⚠️ সিকিউরিটি চেক ব্যর্থ।\n\n"
            "নিরাপত্তার কারণে, আপনি শুধুমাত্র এই ফোন নম্বর দিয়ে দেওয়া অর্ডার বাতিল করতে পারেন।"
        ),
        "cancel_not_possible": (
            "⚠️ বাতিল করা সম্ভব নয়।\n\n"
            "অর্ডার #{order_id} বর্তমানে *{status}* অবস্থায় আছে। "
            "শুধুমাত্র পেন্ডিং বা প্রসেসিং অর্ডার স্বয়ংক্রিয়ভাবে বাতিল করা যেতে পারে। "
            "সাহায্যের প্রয়োজন হলে একজন হিউম্যান এজেন্টের সাথে যোগাযোগ করুন।"
        ),
        "cancel_confirm_q": "❓ *বাতিল নিশ্চিত করুন*\n\nআপনি কি অর্ডার *#{order_id}* বাতিল করতে চান?",

        "no_categories": "দুঃখিত, এখন স্টোর ক্যাটাগরি লোড করতে পারছি না।",
        "no_products_in_cat": "এই ক্যাটাগরিতে বর্তমানে কোনো পণ্য নেই।",
        "no_product_details": "দুঃখিত, এই পণ্যের বিস্তারিত খুঁজে পাইনি।",
        "no_sizes_available": "এই পণ্যটির বর্তমানে কোনো সাইজ অপশন উপলব্ধ নেই।",
        "no_sizes_available_now": "এই পণ্যটির জন্য বর্তমানে কোনো সাইজ উপলব্ধ নেই।",
        "search_prompt": "🔍 আপনি কী খুঁজছেন? পণ্যের নাম, ক্যাটাগরি, বা বিবরণ লিখুন:",
        "search_wait": "🔍 ক্যাটালগ সার্চ করা হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...",
        "what_next": "আপনি এখন কী করতে চান?",
        "choose_size_for": "*{product_name}* এর জন্য আপনার সাইজ নির্বাচন করুন:",
        "available_sizes": "উপলব্ধ সাইজ",
        "help_section": "সাহায্য",
        "view_size_chart": "📐 সাইজ চার্ট দেখুন",
        "see_sizing_guide": "আমাদের সাইজিং গাইড দেখুন",
        "found_matches": "আমি আপনার সার্চের ভিত্তিতে এই আইটেমগুলি খুঁজে পেয়েছি:",

        "size_guide_title": "📏 *সাইজ গাইড*",
        "size_guide_full": (
            "📏 *সাইজ গাইড*\n\n"
            "*পাঞ্জাবি ও শার্ট:*\n"
            "• S (স্মল): উচ্চতা ৫'২\"-৫'৫\", ওজন ৫০-৬০ কেজি (চেস্ট: ৩৮\")\n"
            "• M (মিডিয়াম): উচ্চতা ৫'৫\"-৫'৭\", ওজন ৬০-৭০ কেজি (চেস্ট: ৪০\")\n"
            "• L (লার্জ): উচ্চতা ৫'৭\"-৫'১০\", ওজন ৭০-৮০ কেজি (চেস্ট: ৪২\")\n"
            "• XL (এক্সএল): উচ্চতা ৫'১০\"-৬'০\", ওজন ৮০-৯০ কেজি (চেস্ট: ৪৪\")\n"
            "• XXL (২এক্সএল): উচ্চতা ৬'০\"+, ওজন ৯০+ কেজি (চেস্ট: ৪৬\")\n\n"
            "*ডেলিভারি:*\n"
            "• ঢাকার ভিতরে: ৮০ টাকা, ২-৩ দিন\n"
            "• ঢাকার বাইরে: ১৫০ টাকা, ৩-৫ দিন\n"
            "• ক্যাশ অন ডেলিভারি (COD) সারা দেশে উপলব্ধ।\n\n"
            "পার্সোনাল রেকমেন্ডেশন দরকার? মেইন মেনু থেকে *সাইজ অ্যাসিস্ট্যান্ট* ব্যবহার করুন!"
        ),

        "size_assist_title": "📏 *সাইজ অ্যাসিস্ট্যান্ট*\n\nআপনার পারফেক্ট সাইজ খুঁজে বের করি! অনুগ্রহ করে আপনার *উচ্চতা* লিখুন (যেমন _৫'৬\"_ বা _১৭০ সেমি_):\n\nবাতিল করতে *cancel* টাইপ করুন।",
        "size_height_prompt": "উচ্চতা রেকর্ড করা হয়েছে: *{height}*\n\nএখন আপনার *ওজন* লিখুন (যেমন _৬৫ কেজি_ বা _১৪০ পাউন্ড_):\n\nবাতিল করতে *cancel* টাইপ করুন।",
        "size_results_title": "📏 *সাইজ রেকমেন্ডেশন ফলাফল*\n\nপ্রস্তাবিত সাইজ: *{size}* (চেস্ট: {chest})\nকনফিডেন্স লেভেল: *{confidence}*\n\n📝 *ফিট নোট:*\n{notes}\n\n🚚 *ডেলিভারি পলিসি:*\n• ঢাকার ভিতরে: ৮০ টাকা (২-৩ দিন)\n• ঢাকার বাইরে: ১৫০ টাকা (৩-৫ দিন)\n• ক্যাশ অন ডেলিভারি (COD) সারা দেশে উপলব্ধ।",
        "size_conf_high": "উচ্চ",
        "size_conf_medium": "মাঝারি",
        "size_fit_perfect": "পারফেক্ট ফিট! আপনার উচ্চতা এবং ওজন উভয়ই সাইজ *{size}* (চেস্ট: {chest}) এর সাথে মেলে।",
        "size_fit_notes": "আপনার উচ্চতা অনুযায়ী সাইজ *{small_size}* এবং ওজন অনুযায়ী সাইজ *{large_size}* (বা উল্টো)। আমরা আরামদায়ক রেগুলার ফিটের জন্য সাইজ *{rec_size}* (চেস্ট: {chest}) রেকমেন্ড করি। আপনি যদি টাইট ফিট পছন্দ করেন তবে *{small_size}* বেছে নিতে পারেন।",

        "bot_paused_msg": (
            "⏸️ আমি আমার অটোমেটেড রেসপন্স পজ করেছি।\n\n"
            "অনুগ্রহ করে ওয়াটসঅ্যাপে আমাদের হিউম্যান এজেন্টের সাথে সরাসরি চ্যাট করতে এই লিঙ্কে ক্লিক করুন:\n👉 https://wa.me/{phone}\n\n"
            "আমাকে আবার চালু করতে */resume* টাইপ করুন।"
        ),
        "bot_resumed": "✅ বট আবার চালু হয়েছে। আমি কীভাবে আপনাকে সাহায্য করতে পারি?",
        "process_cancelled": "❌ প্রক্রিয়া বাতিল করা হয়েছে।",
        "action_not_recognized": "আমি এই অ্যাকশন চিনতে পারিনি। মেইন মেনুতে ফিরে যাচ্ছি।",
        "unknown_error": "দুঃখিত, এই অ্যাকশন প্রসেস করতে সমস্যা হয়েছে। মেইন মেনুতে ফিরে যাচ্ছি।",

        "escalation_msg": (
            "⚠️ *হিউম্যান এজেন্টে স্থানান্তর*\n\n"
            "আমি বুঝতে পেরেছি যে আপনি হতাশ বা জরুরি সাহায্যের প্রয়োজন। "
            "আমি আমার অটোমেটেড রেসপন্স পজ করে আপনাকে আমাদের হিউম্যান সাপোর্ট টিমের কাছে স্থানান্তর করছি।"
        ),

        "recommend_no_history": "আপনার শপিং ইতিহাস এখনও যথেষ্ট নয় পার্সোনালাইজড রেকমেন্ডেশন দেওয়ার জন্য। 😅 তবে এখানে আমাদের কিছু জনপ্রিয় পণ্য!",
        "recommend_no_items": "আপনার আগের অর্ডারে আইটেম খুঁজে পাইনি। এখানে কিছু জনপ্রিয় পণ্য!",
        "recommend_searching": "আপনার আগের কেনাকাটার ভিত্তিতে:\n_{purchased}_\n\nআমি আপনার জন্য কিছু দারুণ রেকমেন্ডেশন খুঁজছি... 🔍",
        "recommended_items_title": "প্রস্তাবিত আইটেম",
        "matching_results_title": "ম্যাচিং ফলাফল",
        "click_to_view": "বিস্তারিত দেখতে বা কার্টে যোগ করতে নিচে ক্লিক করুন:",
        "browse_prompt": "আপনি কী করতে চান?",
        "no_recommendations": "এই মুহূর্তে কোনো নির্দিষ্ট রেকমেন্ডেশন খুঁজে পাইনি।",

        "delivery_policy": (
            "🚚 *ডেলিভারি পলিসি:*\n"
            "• ঢাকার ভিতরে: ৮০ টাকা (২-৩ দিন)\n"
            "• ঢাকার বাইরে: ১৫০ টাকা (৩-৫ দিন)\n"
            "• ক্যাশ অন ডেলিভারি (COD) সারা দেশে উপলব্ধ।"
        ),
        "delivery_dhaka": "ঢাকার ভিতরে: ৮০ টাকা (২-৩ দিন)",
        "delivery_outside": "ঢাকার বাইরে: ১৫০ টাকা (৩-৫ দিন)",
        "delivery_cod": "ক্যাশ অন ডেলিভারি (COD) সারা দেশে উপলব্ধ।",

        "section_store": "🛍️ শপিং",
        "section_account": "👤 আমার অ্যাকাউন্ট",
        "section_support": "⚙️ সাহায্য ও সেটিংস",
        "section_special_offers": "🔥 স্পেশাল অফার",
        "section_mens_collection": "👔 পুরুষদের কালেকশন",
        "section_other_categories": "📦 অন্য ক্যাটাগরি",
        "section_available_products": "উপলব্ধ পণ্য",

        "cart_reminder_1h": (
            "🛒 *আপনি আপনার কার্টে আইটেম রেখেছেন!*\n\n"
            "দ্রুত ডেলিভারি পেতে আজই আপনার অর্ডার সম্পূর্ণ করুন। "
            "আপনার আইটেম দেখতে *Cart* লিখে রিপ্লাই দিন!"
        ),
        "cart_reminder_24h": (
            "🛒 *বন্ধুত্বপূর্ণ রিমাইন্ডার!*\n\n"
            "আপনার কার্ট এখনও অপেক্ষা করছে। আপনি কি আপনার অর্ডার সম্পূর্ণ করতে চান?\n\n"
            "আপনার আইটেম দেখতে *Cart* লিখে রিপ্লাই দিন!"
        ),
        "cart_reminder_72h": (
            "🛒 *শেষ সুযোগ!*\n\n"
            "আমরা আপনার আইটেম আর কিছুদিন ধরে রাখছি। "
            "এগুলো স্টক আউট হওয়ার আগে এখনই আপনার কেনাকাটা সম্পূর্ণ করুন!\n\n"
            "আপনার আইটেম দেখতে এবং চেকআউট করতে *Cart* লিখে রিপ্লাই দিন।"
        ),

        "order_update": "🔔 *অর্ডার আপডেট*\n\nআপনার অর্ডার #{order_id} এখন: *{status}*।",

        "price_on_request": "মূল্য জিজ্ঞাসা করুন",
        "in_stock": "✅ স্টকে আছে",
        "out_of_stock": "❌ স্টকে নেই",
        "on_backorder": "⏳ ব্যাকঅর্ডারে",
        "no_reviews": "এখনও রিভিউ নেই",
        "general_category": "সাধারণ",
    },

    # =========================================================================
    # BANGLISH (বাংলা in Latin script)
    # =========================================================================
    "blish": {
        "menu_main": "🏠 Main Menu",
        "menu_categories": "Category browse korun",
        "menu_cart": "Amar Cart",
        "menu_orders": "Amar Orders",
        "menu_human": "Staff er sathe kotha bolun",
        "menu_language": "Language Change korun",
        "menu_search": "Products Khujun",
        "menu_recommend": "Apnar jonno Proshongsha",
        "menu_size": "Amar Size Khujun",
        "menu_cancel_order": "Order Cancel",
        "menu_browse": "Catalog browse korun",
        "cart_checkout": "Checkout",
        "cart_clear": "Cart Khali Korun",
        "btn_select_size": "Size Select Korun",
        "btn_view_cart": "Cart Dekhun",
        "btn_browse_more": "Aro Browse Korun",
        "btn_main_menu": "🏠 Main Menu",
        "btn_start_shopping": "Shopping Shuru Korun",
        "btn_browse_catalog": "Catalog Browse Korun",
        "btn_view_orders": "Order Dekhun",
        "btn_confirm_order": "Order Confirm",
        "btn_cancel": "Cancel",
        "btn_yes_cancel": "Haan, Order Cancel Korun",
        "btn_no_keep": "Na, Order Ti Rakhte Chan",
        "btn_select_product": "Product Select Korun",
        "btn_view_matches": "Matches Dekhun",
        "btn_view_products": "Products Dekhun",
        "btn_open_menu": "☰ Menu Khulun",
        "btn_select_category": "Category Select Korun",
        "btn_add_to_cart": "Cart E Add Korun",
        "btn_size_chart": "Size Chart",
        "btn_select_option": "Option Nei",
        "btn_view_detail": "Details Dekhun",

        "welcome": "DEEN Commerce e swagotom! 👋 Ami apnake kivabe sahajjo korte pari?",
        "categories_body": "Product dekhartte niche kategori list theke ekta niye click korun:",
        "categories_btn": "Category select korun",
        "choose_category": "Akti kategori bche nin:",
        "select_product": "Details dekhartte ekta product select korun:",

        "desc_search": "Apni ja khujchen ta directly khujun",
        "desc_explore": "Amader kolekshon O special offer gula dekhun",
        "desc_for_you": "Apnar history onujayi just apnar jonno product select kora hoyeche",
        "desc_cart_items": "Item gula wait korche! Checkout kortte ready?",
        "desc_empty_cart": "Apnar cart ekti shomoy khali",
        "desc_find_size": "Ek shathe sizetaktik khunjon",
        "desc_view_orders": "Aponar recent Purchases O Status dekhante click korun",
        "desc_cancel_order": "Order er cancellation request korun",
        "desc_talk_human": "Pause koren AI then kotha bolun Staff er sathe",
        "desc_change_lang": "English / বাংলা",
        "desc_clear_cart": "Cart theke sob items Muche den",
        "desc_view_detail": "Details dekhun",
        "desc_out_of_stock": "Stock e nai",

        "cart_empty": "🛒 Apnar cart ekti shomoy khali.",
        "cart_empty_shop": "🛒 Apnar shopping cart ekti shomoy khali!\n\nItem jog kortte catalog browse korun.",
        "cart_summary": "🛒 *Apnar Shopping Cart:*",
        "cart_total": "Molly",
        "cart_item_price": "Damn",
        "cart_item_subtotal": "Subtotal",
        "cart_remove_hint": "Remove: _Remove {product_id}_ likhe reply den",
        "item_added": "✅ *{product_name}* apnar cart e add kora hoyeche!",
        "item_removed": "❌ Product #{product_id} cart theke sorano hoyeche.",
        "variation_added": "✅ *{product_name}* apnar cart e add kora hoyeche!",
        "cart_cleared": "🗑️ Apnar shopping cart khali kora hoyeche.",
        "no_items_to_checkout": "Cart khali. Checkout er jonno age item add korun.",
        "cart_empty_shop_start": "Apnar cart khali. Shopping korar jonno product browse korun!",

        "checkout_instruction": (
            "💳 *Checkout Instructions*\n\n"
            "Apnar naam O shipping address niche format e likhe reply den:\n\n"
            "*Apnar complete Naam, Apnar Shipping Address*\n\n"
            "Uddahoron:\n"
            "_John Doe, 123 Main Street, New York_\n\n"
            "Athoba cancel likhe reply den."
        ),
        "checkout_invalid_format": (
            "⚠️ Vul format.\n\n"
            "Doya kore eivabe reply din:\n"
            "*Naam, Pura Address*\n\n"
            "Athoba cancel likhun."
        ),
        "checkout_confirm_title": "📋 *Cash on Delivery (COD) Order confirm korun*\n\n",
        "checkout_confirm_fields": (
            "Naam: *{name}*\n"
            "Shipping Address:\n_{address}_\n\n"
            "Total Amount: *BDT {total:.2f}*\n"
            "Payment Method: *Cash on Delivery (COD)*\n\n"
            "Aapni ki Order Confirm korte chan?"
        ),
        "checkout_placing": "⏳ Apnar order place kora hochhe, doya kore wait korun...",
        "checkout_success": (
            "🎉 *Order Successfully Placed!*\n\n"
            "Order ID: *#{order_id}*\n"
            "Total Amount: *BDT {total}*\n"
            "Payment Method: *{payment_method}*\n\n"
            "Apnar items pathano hobe:\n_{address}_\n\n"
            "Amader sathe shopping korar jonno thanks!"
        ),
        "checkout_failed": "❌ Amader system e order place kora fail kortheche. Pore abar try korun.",
        "checkout_cancelled": "Checkout cancel kora hoyeche.",
        "session_expired": "❌ Session sesh hoyeche. Checkout cancel kora hoyeche.",
        "product_unavailable": "Dukhito, ei product ar available nei.",
        "size_unavailable": "Dukhito, ei size option ar available nei.",

        "no_orders": "Aapni ei onno number diye akhono kono Order den ni.",
        "orders_title": "📦 *Apnar Recent Orders:*\n\n",
        "order_line": "• *Order #{order_id}* - {date}\n  Status: *{status}*\n  Items: {items}\n  Total: BDT {total:.2f}\n\n",
        "order_not_found": "❌ Amra store e Order #{order_id} pailam na.",
        "order_lookup": "🔍 Order #{order_id} khunjchi...",
        "order_cancelling": "⏳ Order #{order_id} cancel korchchi...",
        "cancel_failed": "❌ Order cancel kora fail. Abar try korun na support e contact korun.",
        "cancel_success": "✅ *Order #{order_id} cancel kora hoyeche.*\n\nDhonnobad. Amra bhabishyote abar apnake shoba dite chai!",
        "cancel_aborted": "Order cancel abort kora hoyeche. Halka Order ti safe! 👍",

        "cancel_title": "❌ *Order Cancellation*\n\nApnar order ID ti likhe reply den (Jemon _10254_):\n\nBack korte *cancel* type korun.",
        "cancel_invalid_id": "⚠️ Vul Order ID. Kkini order ID diye reply korun:",
        "cancel_security_fail": (
            "⚠️ Security Check Failed.\n\n"
            "Shurukkhar karone, app sudhu matro ei phone number diye Order cancel korte parben."
        ),
        "cancel_not_possible": (
            "⚠️ Cancel kora somvob nai.\n\n"
            "Order #{order_id} ekti shomoy *{status}* obostha pore. "
            "Shudhu matro pending ba processing order automatic cancel kora jai. "
            "Apnake help lagle human support e contact korun."
        ),
        "cancel_confirm_q": "❓ *Nischoy cancel korben?*\n\nAapni ki order *#{order_id}* cancel korte chan?",

        "no_categories": "Dukhito, ekhna store category load kora jacchhe na.",
        "no_products_in_cat": "Ei category te ekti shomoy product nai.",
        "no_product_details": "Dukhito, ei product er details pailam na.",
        "no_sizes_available": "Ei product e ekti shomoy size option nei.",
        "no_sizes_available_now": "Ei product e ekti shomoy size nei.",
        "search_prompt": "🔍 Apni ki khujchen? Product name, category, ba description likhun:",
        "search_wait": "🔍 Catalog search kora hochhe, please wait...",
        "what_next": "Aapni ekhon ki korte chan?",
        "choose_size_for": "*{product_name}* er jonno apnar size select korun:",
        "available_sizes": "Size gula",
        "help_section": "Help",
        "view_size_chart": "📐 Size chart dekhun",
        "see_sizing_guide": "Amader sizing guide dekhun",
        "found_matches": "Ami apnar search er based on ei items khuje pelam:",

        "size_guide_title": "📏 *Size Guide*",
        "size_guide_full": (
            "📏 *Size Guide*\n\n"
            "*Panjabis & Shirts:*\n"
            "• S (Small): Uchchha 5'2\"-5'5\", Ojon 50-60 kg (Chest: 38\")\n"
            "• M (Medium): Uchchha 5'5\"-5'7\", Ojon 60-70 kg (Chest: 40\")\n"
            "• L (Large): Uchchha 5'7\"-5'10\", Ojon 70-80 kg (Chest: 42\")\n"
            "• XL (XL): Uchchha 5'10\"-6'0\", Ojon 80-90 kg (Chest: 44\")\n"
            "• XXL (2XL): Uchchha 6'0\"+, Ojon 90+ kg (Chest: 46\")\n\n"
            "*Delivery:*\n"
            "• Dhakar moddhe: 80 TK, 2-3 din\n"
            "• Dhakar baire: 150 TK, 3-5 din\n"
            "• Cash on Delivery (COD) desh e shamne.\n\n"
            "Personal recommendation chai? Main Menu theke *Size Assistant* use korun!"
        ),

        "size_assist_title": "📏 *Size Assistant*\n\nApnar perfect size khunje ber kori! Doya kore apnar *Uchchha* likhun (Jemon _5'6\"_ ba _170 cm_):\n\nCancel korte *cancel* type korun.",
        "size_height_prompt": "Height record kora hoyeche: *{height}*\n\nEkhon apnar *Ojon* likhun (Jemon _65 kg_ ba _140 lbs_):\n\nCancel korte *cancel* type korun.",
        "size_results_title": "📏 *Size Recommendation Results*\n\nProshongshito Size: *{size}* (Chest: {chest})\nConfidence Level: *{confidence}*\n\n📝 *Fit Notes:*\n{notes}\n\n🚚 *Delivery Policy:*\n• Dhakar moddhe: 80 TK (2-3 din)\n• Dhakar baire: 150 TK (3-5 din)\n• Cash on Delivery (COD) desh e shamne.",
        "size_conf_high": "High",
        "size_conf_medium": "Medium",
        "size_fit_perfect": "Perfect fit! Apnar uchchha O ojon duitai size *{size}* (Chest: {chest}) er sathe male.",
        "size_fit_notes": "Apnar uchchha onujayi size *{small_size}* ebong ojon onujayi size *{large_size}* (nitto ulto). Amra aram daik regular fit er jonno size *{rec_size}* (Chest: {chest}) recommend kori. Aapni tight fit pasand kortte *{small_size}* select korte paren.",

        "bot_paused_msg": (
            "⏸️ Ami amar automated response pause korechi.\n\n"
            "WhatsApp e human agent er sathe direct chat korte link e click korun:\n👉 https://wa.me/{phone}\n\n"
            "Abar shuru korte */resume* type korun."
        ),
        "bot_resumed": "✅ Bot abar shuru hoyeche. Ki vabe help korte pari?",
        "process_cancelled": "❌ Process cancel kora hoyeche.",
        "action_not_recognized": "Ami ei action chinate parini. Main menu te firtte jacchi.",
        "unknown_error": "Dukhito, ei action process korte problem. Main menu te firtte jacchi.",

        "escalation_msg": (
            "⚠️ *Human Agent e transfer*\n\n"
            "Ami bujhte parchi aapni frustrated ba emergency help lagbe. "
            "Ami automated response pause kore human support team a transfer korchi."
        ),

        "recommend_no_history": "Personalized recommendation to test e shathey aapnar shopping history pretty nai. 😅 Tobe amader kichu popular products:",
        "recommend_no_items": "Aapnar aage order er items khuje pelam na. Tobe kichu popular products:",
        "recommend_searching": "Aapnar age shopping based on:\n_{purchased}_\n\nAmi apnar jonno aktuo recommendation khojchi... 🔍",
        "recommended_items_title": "Recommendation Items",
        "matching_results_title": "Matching Results",
        "click_to_view": "Cart e add korar jonno below click korun:",
        "browse_prompt": "Aapni ki korte chan?",
        "no_recommendations": "Ekhon recommended item thik moto khuja jacche na.",

        "delivery_policy": (
            "🚚 *Delivery Policy:*\n"
            "• Dhaka moddhe: 80 TK (2-3 din)\n"
            "• Dhaka baire: 150 TK (3-5 din)\n"
            "• Cash on Delivery (COD) desh e samne."
        ),
        "delivery_dhaka": "Dhakar moddhe: 80 TK (2-3 din)",
        "delivery_outside": "Dhakar baire: 150 TK (3-5 din)",
        "delivery_cod": "Cash on Delivery (COD) desh e shamne.",

        "section_store": "🛍️ Shop",
        "section_account": "👤 My Account",
        "section_support": "⚙️ Help & Settings",
        "section_special_offers": "🔥 Special Offers",
        "section_mens_collection": "👔 Men's Collection",
        "section_other_categories": "📦 Other Categories",
        "section_available_products": "Available Products",

        "cart_reminder_1h": (
            "🛒 *You left items in your cart!*\n\n"
            "Fast delivery er jonno aaj e order complete korun. "
            "Items dekhar jonno *Cart* reply korun!"
        ),
        "cart_reminder_24h": (
            "🛒 *Friendly Reminder!*\n\n"
            "Apnar cart wait korche. Apni ki order complete korte chan?\n\n"
            "Items dekhartte *Cart* reply korun!"
        ),
        "cart_reminder_72h": (
            "🛒 *Last Chance!*\n\n"
            "Amra apnar items kichudin dhore rakhchi. "
            "Shegula stock sure jaoar age akhon e shopping complete korun!\n\n"
            "Items dekhar jonno *Cart* reply korun."
        ),

        "order_update": "🔔 *Order Update*\n\nApnar order #{order_id} aakhn: *{status}*.",

        "price_on_request": "Dam jiggasa korun",
        "in_stock": "✅ In Stock",
        "out_of_stock": "❌ Out of Stock",
        "on_backorder": "⏳ Backorder e",
        "no_reviews": "Review nai ekhono",
        "general_category": "Shadharon",
    },
}


def get_text(lang: str, key: str) -> str:
    """Return the translated string for *lang* and *key*, falling back to English.

    Args:
        lang: Language code (``"en"``, ``"bn"``, or ``"blish"``).
        key: Translation key.

    Returns:
        The translated string, or the key itself if not found anywhere.
    """
    return (
        TRANSLATIONS.get(lang, TRANSLATIONS["en"])
        .get(key, TRANSLATIONS["en"].get(key, key))
    )


def format_text(lang: str, key: str, **kwargs) -> str:
    """Return the translated string with placeholder substitution.

    Usage::

        msg = format_text(lang, "item_added", product_name="Panjabi")

    Args:
        lang: Language code.
        key: Translation key.
        **kwargs: Values for ``{placeholder}`` in the translated string.

    Returns:
        The formatted translated string.
    """
    template = get_text(lang, key)
    try:
        return template.format(**kwargs)
    except KeyError as exc:
        # Log the missing placeholder (at DEBUG level so production isn't noisy)
        import logging
        logging.getLogger(__name__).warning(
            "Missing format placeholder %s in i18n key '%s' for lang '%s'",
            exc, key, lang,
        )
        return template
    except Exception:
        return template
