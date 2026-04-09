from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_admin_main_menu(permissions: list):
    """ইউজারের পারমিশন অনুযায়ী প্রধান মেনু জেনারেট করবে"""
    buttons = []
    
    # ১ম রো: হাউজ এবং ইউজার ম্যানেজমেন্ট
    row1 = []
    if "view_houses" in permissions:
        row1.append(KeyboardButton(text="🏠 হাউজ ম্যানেজমেন্ট"))
    if "view_users" in permissions:
        row1.append(KeyboardButton(text="👤 ইউজার ম্যানেজমেন্ট"))
    if row1:
        buttons.append(row1)

    # ২য় রো: DMS Tasks
    if "dms_access" in permissions:
        buttons.append([KeyboardButton(text="🤖 DMS Tasks")])

    if "report_access" in permissions:
        buttons.append([KeyboardButton(text="📊 রিপোর্টস")])
    
    # ৩য় রো: সেটিংস
    if "manage_settings" in permissions:
        buttons.append([KeyboardButton(text="⚙️ সেটিংস")])
        
    # যদি কোনো পারমিশন না থাকে (যেমন নতুন বিপি)
    if not buttons:
        return None 

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_house_mgmt_menu(permissions: list):
    """হাউজ ম্যানেজমেন্টের ভেতরকার বাটনসমূহ (এখানে ব্যাক বাটন থাকবে)"""
    buttons = []
    row1 = []
    if "create_house" in permissions:
        row1.append(KeyboardButton(text="➕ নতুন হাউজ তৈরি"))
    if "view_houses" in permissions:
        row1.append(KeyboardButton(text="📋 হাউজ লিস্ট দেখুন"))
    
    if row1: buttons.append(row1)
    
    # সাব-মেনুতে সবসময় "🔙 প্রধান মেনু" বাটনটি থাকবে
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_user_mgmt_menu(permissions: list):
    """ইউজার ম্যানেজমেন্টের ভেতরকার বাটনসমূহ (এখানে ব্যাক বাটন থাকবে)"""
    buttons = []
    row1 = []
    if "create_user" in permissions:
        row1.append(KeyboardButton(text="➕ নতুন ইউজার তৈরি"))
    if "view_users" in permissions:
        row1.append(KeyboardButton(text="📋 ইউজার লিস্ট দেখুন"))
    
    if row1: buttons.append(row1)
    
    # সাব-মেনুতে সবসময় "🔙 প্রধান মেনু" বাটনটি থাকবে
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_settings_menu(permissions: list):
    """সেটিংস মেনুর বাটনসমূহ (এখানে ব্যাক বাটন থাকবে)"""
    buttons = []
    if "manage_settings" in permissions:
        buttons.append([
            KeyboardButton(text="➕ নতুন রোল তৈরি"),
            KeyboardButton(text="➕ নতুন পারমিশন তৈরি")
        ])
        buttons.append([KeyboardButton(text="📋 রোল ও পারমিশন লিস্ট")])
    
    # সাব-মেনুতে সবসময় "🔙 প্রধান মেনু" বাটনটি থাকবে
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)