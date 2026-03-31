from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_admin_main_menu(permissions: list):
    buttons = [
        [
            KeyboardButton(text="🏠 হাউজ ম্যানেজমেন্ট"),
            KeyboardButton(text="👤 ইউজার ম্যানেজমেন্ট")
        ],
    ]

    # যদি ইউজারের কাছে 'dms_access' পারমিশন থাকে তবেই বাটনটি অ্যাড হবে
    if "dms_access" in permissions:
        buttons.append([KeyboardButton(text="🤖 DMS Tasks")])
    
    buttons.append([KeyboardButton(text="⚙️ সেটিংস")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_house_mgmt_menu():
    buttons = [
        [KeyboardButton(text="➕ নতুন হাউজ তৈরি"), KeyboardButton(text="📋 হাউজ লিস্ট দেখুন")],
        [KeyboardButton(text="🔙 প্রধান মেনু")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_user_mgmt_menu():
    buttons = [
        [KeyboardButton(text="➕ নতুন ইউজার তৈরি"), KeyboardButton(text="📋 ইউজার লিস্ট দেখুন")],
        [KeyboardButton(text="🔙 প্রধান মেনু")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_settings_menu():
    buttons = [
        [KeyboardButton(text="➕ নতুন রোল তৈরি"), KeyboardButton(text="➕ নতুন পারমিশন তৈরি")],
        [KeyboardButton(text="📋 রোল ও পারমিশন লিস্ট")],
        [KeyboardButton(text="🔙 প্রধান মেনু")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)