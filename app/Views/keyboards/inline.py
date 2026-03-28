from aiogram.utils.keyboard import InlineKeyboardBuilder
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
    builder.button(text="❌ ডিলিট করুন", callback_data=f"conf_del_u_{user_id}")
    builder.button(text="🔙 তালিকায় ফিরে যান", callback_data="back_to_ulist")
    builder.adjust(2)
    return builder.as_markup()