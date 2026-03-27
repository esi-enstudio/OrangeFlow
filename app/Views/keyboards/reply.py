from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_admin_main_menu():
    buttons = [
        [KeyboardButton(text="🏠 হাউজ ম্যানেজমেন্ট"), KeyboardButton(text="👤 ইউজার ম্যানেজমেন্ট")],
        [KeyboardButton(text="⚙️ সেটিংস")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_house_mgmt_menu():
    buttons = [
        [KeyboardButton(text="➕ নতুন হাউজ তৈরি")],
        [KeyboardButton(text="📋 হাউজ লিস্ট দেখুন")],
        [KeyboardButton(text="🔙 প্রধান মেনু")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_user_mgmt_menu():
    buttons = [
        [KeyboardButton(text="➕ নতুন ইউজার তৈরি")],
        [KeyboardButton(text="📋 ইউজার লিস্ট দেখুন")],
        [KeyboardButton(text="🔙 প্রধান মেনু")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_settings_menu():
    buttons = [
        [KeyboardButton(text="➕ নতুন রোল তৈরি"), KeyboardButton(text="➕ নতুন পারমিশন তৈরি")],
        [KeyboardButton(text="🔙 প্রধান মেনু")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)