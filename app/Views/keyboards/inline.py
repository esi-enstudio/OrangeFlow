from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup


def get_house_list_keyboard(houses):
    builder = InlineKeyboardBuilder()

    for house in houses:
        # বাটনের টেক্সট হবে হাউজের নাম এবং ক্লিক করলে callback_data তে হাউজ আইডি যাবে
        builder.button(text=f"🏢 {house.name} ({house.code})", callback_data=f"view_house_{house.id}")

    builder.adjust(1)  # প্রতি লাইনে ১টি করে বাটন
    return builder.as_markup()

# ইউজারদের তালিকা বাটন আকারে
def get_user_list_kb(users):
    builder = InlineKeyboardBuilder()
    for u in users:
        builder.button(text=f"👤 {u.name}", callback_data=f"manage_user_{u.id}")
    builder.adjust(1)
    return builder.as_markup()

# একটি নির্দিষ্ট ইউজারের জন্য অ্যাকশন বাটন
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

# হাউজ লিস্ট কিবোর্ড (পেজিনেশনসহ)
def get_house_pagination_kb(houses, page, total_pages):
    builder = InlineKeyboardBuilder()
    for h in houses:
        status = "✅" if h.is_active else "❌"
        builder.button(text=f"{h.name} ({h.code}) {status}", callback_data=f"view_h_{h.id}")
    
    # পেজিনেশন বাটন
    nav_btns = []
    if page > 1: nav_btns.append(InlineKeyboardButton(text="⬅️", callback_data=f"hlist_page_{page-1}"))
    if page < total_pages: nav_btns.append(InlineKeyboardButton(text="➡️", callback_data=f"hlist_page_{page+1}"))
    if nav_btns: builder.row(*nav_btns)
    
    builder.button(text="🔍 হাউজ সার্চ করুন", callback_data="search_house_start")
    builder.adjust(1)
    return builder.as_markup()

# হাউজ অ্যাকশন কিবোর্ড
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
    # প্রতি লাইনে ২ টি করে বাটন
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