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
    if "manage_field_force" in permissions: 
        row3.append(KeyboardButton(text="👥 ফিল্ড ফোর্স"))
    if "manage_retailers" in permissions: 
        row3.append(KeyboardButton(text="🏪 রিটেইলারস"))
    if row3: 
        buttons.append(row3)
    
    # ৪র্থ রো: মেলা এবং বিটিএস
    row4 = []
    if "manage_mela" in permissions: 
        row4.append(KeyboardButton(text="🎪 মেলা ম্যানেজমেন্ট"))
    if "manage_bts" in permissions: 
        row4.append(KeyboardButton(text="📡 বিটিএস লিস্ট"))
    if row4: 
        buttons.append(row4)
    
    # ৫তম রো: সেটিংস (একাকী)
    if "manage_settings" in permissions:
        buttons.append([KeyboardButton(text="⚙️ সেটিংস")])
        
    # যদি কোনো পারমিশন না থাকে
    if not buttons:
        return None
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)






def get_report_menu(permissions: list):
    """রিপোর্টস সাব-মেনু"""
    buttons = []

    row1 = []
    if "view_ga_live" in permissions:
        row1.append(KeyboardButton(text="📡 জিএ লাইভ"))
        # ভবিষ্যতে অন্য কোনো রিপোর্টের জন্য জায়গা
        # row1.append(KeyboardButton(text="📈 সেলস রিপোর্ট"))
    
    if row1: buttons.append(row1)
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





def get_retailer_menu(permissions: list):
    """রিটেইলার সাব-মেনু (পারমিশন ফিল্টারসহ)"""
    buttons = []
    row1 = []

    if "upload_retailer_excel" in permissions:
        row1.append(KeyboardButton(text="📤 এক্সেল আপলোড"))
    
    if "search_retailer" in permissions:
        row1.append(KeyboardButton(text="🔍 রিটেইলার সার্চ"))

    if row1:
        buttons.append(row1)

    # নেভিগেশন বাটন
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





def get_settings_menu(permissions: list):
    """সেটিংস সাব-মেনু (রোল, পারমিশন এবং জিএ ফিল্টার)"""
    buttons = []

    if "manage_settings" in permissions:
        # রোল ও পারমিশন
        buttons.append([
            KeyboardButton(text="➕ নতুন রোল"), 
            KeyboardButton(text="➕ নতুন পারমিশন")
        ])

        # লিস্ট ও ফিল্টার
        buttons.append([
            KeyboardButton(text="📋 রোল ও পারমিশন লিস্ট"), 
            KeyboardButton(text="⚙️ জিএ ফিল্টার")
        ])
    
    buttons.append([KeyboardButton(text="🔙 প্রধান মেনু")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)