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

    # ২য় রো: DMS Tasks এবং রিপোর্টস
    row2 = []
    if "dms_access" in permissions: 
        row2.append(KeyboardButton(text="🤖 DMS Tasks"))
    if "report_access" in permissions: 
        row2.append(KeyboardButton(text="📊 রিপোর্টস"))
    if row2: 
        buttons.append(row2)
    
    # ৩য় রো: ফিল্ড ফোর্স এবং রিটেইলার
    row3 = []
    ff_perms = ["create_field_force","view_field_force","edit_field_force","delete_field_force",]
    if any(p in permissions for p in ff_perms):
        row3.append(KeyboardButton(text="👥 ফিল্ড ফোর্স"))
    
    ret_perms = ["create_retailers","view_retailers","edit_retailers","delete_retailers",]
    if any(p in permissions for p in ret_perms):
        row3.append(KeyboardButton(text="🏪 রিটেইলারস"))
    
    if row3:
        buttons.append(row3)
    
    # ৪র্থ রো: মেলা এবং বিটিএস (আপডেটেড লজিক) ✅
    row4 = []
    
    # মেলা ম্যানেজমেন্ট চেক
    mela_perms = ["create_mela", "view_mela", "edit_mela", "delete_mela"]
    if any(p in permissions for p in mela_perms):
        row4.append(KeyboardButton(text="🎪 মেলা ম্যানেজমেন্ট"))
    
    # বিটিএস লিস্ট চেক (যেকোনো একটি পারমিশন থাকলে বাটন আসবে) ✅
    bts_perms = ["create_bts", "view_bts", "edit_bts", "delete_bts"]
    if any(p in permissions for p in bts_perms):
        row4.append(KeyboardButton(text="📡 বিটিএস লিস্ট"))
        
    if row4: 
        buttons.append(row4)
    
    # ৫তম রো: সেটিংস (যদি পারমিশন থাকে) ✅
    # যদি নিচের যেকোনো একটি পারমিশন থাকে তবেই সেটিংস বাটন দেখাবে
    setting_perms = [
        "create_new_role", "create_new_permission", 
        "manage_role_and_permission_list", "manage_ga_filter", 
        "manage_data_center", "manage_mela_settings"
    ]

    if any(p in permissions for p in setting_perms):
        buttons.append([KeyboardButton(text="⚙️ সেটিংস")])
        
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)






def get_settings_menu(permissions: list):
    """সেটিংস সাব-মেনু (নির্দিষ্ট পারমিশন ভিত্তিক)"""
    buttons = []

    # রো ১: নতুন রোল ও পারমিশন
    row1 = []
    if "create_new_role" in permissions: row1.append(KeyboardButton(text="➕ নতুন রোল"))
    if "create_new_permission" in permissions: row1.append(KeyboardButton(text="➕ নতুন পারমিশন"))
    if row1: buttons.append(row1)

    # রো ২: লিস্ট ও জিএ ফিল্টার
    row2 = []
    if "manage_role_and_permission_list" in permissions: row2.append(KeyboardButton(text="📋 রোল ও পারমিশন লিস্ট"))
    if "manage_ga_filter" in permissions: row2.append(KeyboardButton(text="⚙️ জিএ ফিল্টার"))
    if row2: buttons.append(row2)

    # রো ৩: ডাটা সেন্টার ও মেলা সেটিংস
    row3 = []
    if "manage_data_center" in permissions: row3.append(KeyboardButton(text="💾 ডাটা সেন্টার"))
    if "manage_mela_settings" in permissions: row3.append(KeyboardButton(text="⚙️ মেলার সেটিংস"))
    if row3: buttons.append(row3)

    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_data_center_menu(permissions: list):
    """ডাটা সেন্টার সাব-মেনু (এক্সেল আপলোডের জন্য) ✅"""
    buttons = []
    
    # এখানে আপনার ৬টি টেবিলের বাটন আসবে। আপাতত 'এক্টিভেশন' শুরু করছি।
    if "manage_data_center" in permissions:
        buttons.append([KeyboardButton(text="📈 এক্টিভেশন")])
        # ভবিষ্যতে এখানে বাকি ৫টি বাটন যোগ হবে
    
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)



def get_reports_mgmt_menu(permissions: list):
    """রিপোর্টস সাব-মেনু (Reply Keyboard)"""
    buttons = []
    row = []
    
    # জিএ লাইভ বাটনটি এখানে আসবে
    if "view_ga_live" in permissions:
        row.append(KeyboardButton(text="📡 জিএ লাইভ"))
    
    # ভবিষ্যতে আরও রিপোর্ট (যেমন সেলস রিপোর্ট) এখানে যোগ করা যাবে
    
    if row:
        buttons.append(row)

    # সব সময় প্রধান মেনুতে ফেরার বাটন থাকবে
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)




def get_field_force_menu(permissions: list):
    """ফিল্ড ফোর্স সাব-মেনু (পারমিশন ফিল্টারসহ)"""
    buttons = []
    row1 = []

    if "create_field_force" in permissions:
        row1.append(KeyboardButton(text="➕ নতুন মেম্বার"))
    
    if "view_field_force" in permissions:
        row1.append(KeyboardButton(text="📋 মেম্বার লিস্ট") )

    if row1:
        buttons.append(row1)

    # নেভিগেশন বাটন সবসময় থাকবে যদি সাব-মেনুতে ঢোকার অনুমতি থাকে
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    
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




def get_ff_mgmt_menu(permissions: list):
    """ফিল্ড ফোর্স ম্যানেজমেন্ট সাব-মেনু (নতুন)"""
    buttons = []
    row = []
    if "create_field_force" in permissions:
        row.append(KeyboardButton(text="➕ নতুন মেম্বার"))
    if "view_field_force" in permissions:
        row.append(KeyboardButton(text="📋 মেম্বার লিস্ট"))

    if row: buttons.append(row)
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)





def get_retailer_mgmt_menu(permissions: list):
    """রিটেইলার ম্যানেজমেন্ট সাব-মেনু (নতুন)"""
    buttons = []
    row = []
    if "find_retailers" in permissions:
        row.append(KeyboardButton(text="🔍 রিটেইলার সার্চ"))
    if "view_retailers" in permissions:
        row.append(KeyboardButton(text="📋 রিটেইলার লিস্ট"))

    if row: buttons.append(row)
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)




def get_mela_settings_menu(permissions: list):
    """মেলার সেটিংস সাব-মেনু (Reply Keyboard) ✅"""
    buttons = []
    
    if "manage_mela_settings" in permissions:
        # ১ম রো: ধরণ এবং এক্টিভিটি
        buttons.append([
            KeyboardButton(text="➕ নতুন মেলার ধরণ"),
            KeyboardButton(text="➕ নতুন এক্টিভিটি")
        ])
        
        # ২য় রো: এলিজিবল বিটিএস
        buttons.append([
            KeyboardButton(text="📤 এলিজিবল বিটিএস আপলোড")
        ])
    
    # সব সময় প্রধান মেনুতে ফেরার বাটন থাকবে
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)










