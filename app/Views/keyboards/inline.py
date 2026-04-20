from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

# ==========================================
# ১. ফিল্ড ফোর্স (Field Force) মডিউল
# ==========================================

def get_field_force_house_selection_kb(houses):
    """ফিল্ড ফোর্সের জন্য হাউস নির্বাচন"""
    builder = InlineKeyboardBuilder()
    for h in houses:
        builder.button(text=f"🏢 {h.display_name}", callback_data=f"ff_hsel_{h.id}")
    builder.adjust(1)
    return builder.as_markup()


def get_field_force_main_kb(house_id, total_count, permissions: list, is_admin: bool, personal_ff_id: int = None):
    builder = InlineKeyboardBuilder()

    # এডমিন ভিউ (সুপার এডমিন বা ম্যানেজার রোলের জন্য)
    if is_admin or "view_field_force" in permissions:
        # ১ম রো: লিস্ট এবং সার্চ
        if total_count > 0:
            builder.row(
                InlineKeyboardButton(text="📋 লিস্ট দেখুন", callback_data=f"ff_list_{house_id}_1"),
                InlineKeyboardButton(text="🔍 সার্চ করুন", callback_data=f"ff_search_{house_id}")
            )
    
    # ২য় রো: আপলোড বাটন (সুপার এডমিন হলে সবসময় দেখবে) ✅
        row2 = []
        if is_admin or "create_field_force" in permissions:
            row2.append(InlineKeyboardButton(text="📤 এক্সেল আপলোড", callback_data=f"ff_upload_{house_id}"))
        
        row2.append(InlineKeyboardButton(text="📥 স্যাম্পল ডাউনলোড", callback_data="ff_sample_dl"))
        builder.row(*row2)

    # সাধারণ ইউজার ভিউ (যদি সে এডমিন না হয় কিন্তু তার প্রোফাইল থাকে)
    if not is_admin and personal_ff_id:
        builder.row(InlineKeyboardButton(text="👤 আমার প্রোফাইল", callback_data=f"ff_view_{personal_ff_id}"))

    # ৩য় রো: হাউস পরিবর্তন
    builder.row(InlineKeyboardButton(text="🔄 হাউজ পরিবর্তন করুন", callback_data="ff_change_house"))
    
    return builder.as_markup()


def get_ff_pagination_kb(members, page, total_pages, house_id):
    builder = InlineKeyboardBuilder()
    for m in members:
        # এখানে itop_number দেখানো হচ্ছে ✅
        builder.button(text=f"👤 {m.name} ({m.itop_number or 'N/A'})", callback_data=f"ff_view_{m.id}")
    builder.adjust(1)


    nav_btns = []
    if page > 1:
        nav_btns.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"ff_list_{house_id}_{page-1}"))
    if page < total_pages:
        nav_btns.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"ff_list_{house_id}_{page+1}"))
    if nav_btns: builder.row(*nav_btns)
    
    builder.row(InlineKeyboardButton(text="🔙 মেইন মেনু", callback_data=f"ff_back_main_{house_id}"))
    return builder.as_markup()

def get_ff_action_kb(ff_id, house_id, status, permissions: list):
    """মেম্বার প্রোফাইল অ্যাকশন বাটন"""
    builder = InlineKeyboardBuilder()
    if "edit_field_force" in permissions:
        builder.button(text="📝 তথ্য এডিট", callback_data=f"ff_edit_{ff_id}")
        status_text = "🔴 ডি-এক্টিভ" if status == "Active" else "🟢 এক্টিভ করুন"
        builder.button(text=status_text, callback_data=f"ff_toggle_{ff_id}")
    if "delete_field_force" in permissions:
        builder.button(text="🗑 ডিলিট মেম্বার", callback_data=f"ff_del_conf_{ff_id}")
    
    builder.button(text="🔙 লিস্টে ফিরুন", callback_data=f"ff_list_{house_id}_1")
    builder.adjust(2)
    return builder.as_markup()

# --- নতুন ফিল্ড ফোর্স এডিট ফাংশনসমূহ (এরর ফিক্স) ---

def get_ff_edit_categories_kb(ff_id):
    """এডিট করার জন্য ক্যাটাগরি সিলেকশন মেনু"""
    builder = InlineKeyboardBuilder()
    # ক্যাটাগরি লিস্ট (নাম, কী)
    categories = [
        ("🆔 প্রাথমিক পরিচয়", "basic"),
        ("🏦 ব্যাংক তথ্য", "bank"),
        ("👤 ব্যক্তিগত তথ্য", "personal"),
        ("🎓 শিক্ষা ও প্রফেশনাল", "pro"),
        ("🛠 অফিসিয়াল ও অন্যান্য", "office")
    ]
    for label, cat_key in categories:
        # ফরম্যাট: ff_ecat_{key}_{id} -> ff_ecat_basic_1
        builder.button(text=label, callback_data=f"ff_ecat_{cat_key}_{ff_id}")
    
    builder.button(text="🔙 প্রোফাইলে ফিরুন", callback_data=f"ff_view_{ff_id}")
    builder.adjust(1)
    return builder.as_markup()

def get_ff_fields_by_category_kb(category_key, ff_id):
    builder = InlineKeyboardBuilder()
    fields_map = {
        "basic": [
            ("নাম", "name"), 
            ("ডিএমএস কোড", "dms_code"), 
            ("আইটপ নাম্বার", "itop_number"), # phone_number থেকে itop_number করা হলো ✅
            ("পার্সোনাল নং", "personal_number"), 
            ("রোল কোড", "assisted_retailer_code"), # এটিও যোগ করা হয়েছে
            ("টাইপ", "type")
        ],
        "bank": [("ব্যাংক নাম", "bank_name"), ("অ্যাকাউন্ট", "bank_account"), ("ব্রাঞ্চ", "branch_name"), ("রাউটিং নং", "routing_number")],
        "personal": [("বাবার নাম", "fathers_name"), ("মায়ের নাম", "mothers_name"), ("এনআইডি", "nid"), ("জন্মতারিখ", "dob"), ("রক্তের গ্রুপ", "blood_group"), ("ধর্ম", "religion"), ("হোম টাউন", "home_town")],
        "pro": [("শিক্ষা", "last_education"), ("প্রতিষ্ঠান", "institution_name"), ("পূর্বের কোম্পানি", "previous_company_name"), ("পূর্বের স্যালারি", "previous_company_salary")],
        "office": [("জয়েনিং", "joining_date"), ("স্যালারি", "salary"), ("মার্কেট টাইপ", "market_type"), ("বাইক", "motor_bike"), ("সাইকেল", "bicyle"), ("লাইসেন্স", "driving_license"), ("ঠিকানা", "present_address")]
    }

    
    fields = fields_map.get(category_key, [])
    for label, field_name in fields:
        # ফরম্যাট: ff_field_{field}_{id} -> ff_field_name_1
        builder.button(text=label, callback_data=f"ff_field_{field_name}_{ff_id}")
    
    builder.adjust(2) # ফিল্ড বাটন ২ কলামে
    # ব্যাক বাটন আলাদা রো-তে
    builder.row(InlineKeyboardButton(text="🔙 ক্যাটাগরিতে ফিরুন", callback_data=f"ff_edit_{ff_id}"))
    return builder.as_markup()



# ==========================================
# ২. ইউজার এবং হাউজ ম্যানেজমেন্ট (অপরিবর্তিত)
# ==========================================

def get_house_list_keyboard(houses):
    builder = InlineKeyboardBuilder()
    for house in houses:
        builder.button(text=f"🏢 {house.name} ({house.code})", callback_data=f"view_house_{house.id}")
    builder.adjust(1)
    return builder.as_markup()

def get_user_list_kb(users):
    builder = InlineKeyboardBuilder()
    for u in users:
        builder.button(text=f"👤 {u.name}", callback_data=f"manage_user_{u.id}")
    builder.adjust(1)
    return builder.as_markup()

def get_user_action_kb(user_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 নাম আপডেট", callback_data=f"edit_uname_{user_id}")
    builder.button(text="📞 ফোন আপডেট", callback_data=f"edit_uphone_{user_id}")
    builder.button(text="🎭 রোল পরিবর্তন", callback_data=f"edit_user_roles_{user_id}")
    builder.button(text="🏠 হাউজ পরিবর্তন", callback_data=f"edit_user_houses_{user_id}")
    builder.button(text="❌ ডিলিট করুন", callback_data=f"conf_del_u_{user_id}")
    builder.button(text="🔙 লিস্টে ফিরুন", callback_data="back_to_ulist")
    builder.adjust(2)
    return builder.as_markup()

def get_house_pagination_kb(houses, page, total_pages):
    builder = InlineKeyboardBuilder()
    for h in houses:
        status = "✅" if h.is_active else "❌"
        builder.button(text=f"{h.display_name} ({h.code}) {status}", callback_data=f"view_h_{h.id}")
    
    nav_btns = []
    if page > 1: nav_btns.append(InlineKeyboardButton(text="⬅️", callback_data=f"hlist_page_{page-1}"))
    if page < total_pages: nav_btns.append(InlineKeyboardButton(text="➡️", callback_data=f"hlist_page_{page+1}"))
    if nav_btns: builder.row(*nav_btns)
    
    builder.button(text="🔍 হাউজ সার্চ করুন", callback_data="search_house_start")
    builder.adjust(1)
    return builder.as_markup()

def get_house_action_kb(house_id, is_active):
    builder = InlineKeyboardBuilder()
    status_text = "🔴 ডি-এক্টিভ" if is_active else "🟢 এক্টিভ"
    builder.button(text="✏️ তথ্য আপডেট করুন", callback_data=f"edit_h_info_{house_id}")
    builder.button(text=status_text, callback_data=f"toggle_h_status_{house_id}")
    builder.button(text="🔙 লিস্টে ফিরুন", callback_data="hlist_page_1")
    builder.adjust(1)
    return builder.as_markup()

def get_house_edit_fields_kb(house_id):
    builder = InlineKeyboardBuilder()
    fields = [
        ("📛 নাম", "name"), ("🔑 কোড", "code"),
        ("🌍 ক্লাস্টার", "cluster"), ("📍 রিজিয়ন", "region"),
        ("📧 ইমেইল", "email"), ("🏠 ঠিকানা", "address"),
        ("📞 কন্টাক্ট", "contact"),("👤 DMS User", "dms_user"),
        ("🔑 DMS Pass", "dms_pass"), ("🆔 DMS ID", "dms_house_id")
    ]
    for label, field in fields:
        builder.button(text=label, callback_data=f"h_edit_{field}_{house_id}")
    builder.button(text="🔙 বিস্তারিত পেজে ফিরুন", callback_data=f"view_h_{house_id}")
    builder.adjust(2)
    return builder.as_markup()