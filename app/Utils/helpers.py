from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.Models.user import User
from app.Models.house import House
from app.Services.db_service import async_session

async def get_dms_credentials(house_id: int):
    """হাউজ আইডি দিয়ে ডিএমএস ক্রেডেনশিয়াল সংগ্রহ করার কমন ফাংশন"""
    async with async_session() as session:
        # সরাসরি হাউজ টেবিল থেকে আইডি দিয়ে ডাটা নেওয়া হচ্ছে
        house = await session.get(House, house_id)
        
        if not house:
            return None, "❌ হাউজটি খুঁজে পাওয়া যায়নি।"

        # প্রয়োজনীয় ডিএমএস তথ্যগুলো আছে কি না চেক করা
        if not all([house.dms_user, house.dms_pass, house.dms_house_id]):
            return None, f"❌ হাউজ '{house.name}' এর জন্য DMS Credentials সেট করা নেই।"

        return {
            "user": house.dms_user,
            "pass": house.dms_pass,
            "house_id": house.dms_house_id,
            "house_name": house.name,
            "code": house.code
        }, None

async def get_user_houses(telegram_id: int):
    """ইউজারের সাথে যুক্ত সকল হাউজ লিস্ট পাওয়ার ফাংশন"""
    async with async_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return [], "❌ ইউজার খুঁজে পাওয়া যায়নি।"
        
        if not user.houses:
            return [], "❌ আপনার সাথে কোনো হাউজ যুক্ত নেই।"

        return user.houses, None
    
def bn_num(number):
    """ইংরেজি সংখ্যাকে বাংলায় রূপান্তর করার কমন মেথড"""
    en_digits = "0123456789"
    bn_digits = "০১২৩৪৫৬৭৮৯"
    
    # কনভার্সন টেবিল তৈরি
    table = str.maketrans(en_digits, bn_digits)
    return str(number).translate(table)





def get_field_force_full_profile_text(m):
    """ফিল্ড ফোর্সের ৩৮টি ফিল্ডের ডাটা HTML ফরম্যাটে সাজিয়ে দেওয়ার ফাংশন"""
    def clean(val):
        return str(val) if val and str(val).lower() != 'nan' else "N/A"
    
    return (
        f"👥 **ফিল্ড ফোর্স বিস্তারিত প্রোফাইল**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 প্রাথমিক পরিচয় (Basic Info):</b>\n"
        f"🔹 নাম: {m.name}\n"
        f"🔹 ডিএমএস কোড: `{m.dms_code}`\n"
        f"🔹 নিজের কোড: `{clean(m.assisted_retailer_code)}`\n"
        f"🔹 আইটপ নাম্বার: {clean(m.itop_number)}\n"
        f"🔹 পার্সোনাল নং: {clean(m.personal_number)}\n"
        f"🔹 পুল নম্বর: {clean(m.pool_number)}\n"
        f"🔹 টাইপ: {clean(m.type)} | স্ট্যাটাস: {m.status}\n\n"
        
        f"<b>🏦 ব্যাংক তথ্য (Bank Details):</b>\n"
        f"🔹 ব্যাংক: {clean(m.bank_name)}\n"
        f"🔹 অ্যাকাউন্ট: {clean(m.bank_account)}\n"
        f"🔹 ব্রাঞ্চ: {clean(m.branch_name)}\n"
        f"🔹 রাউটিং নং: {clean(m.routing_number)}\n\n"
        
        f"<b>👤 ব্যক্তিগত তথ্য (Personal):</b>\n"
        f"🔹 বাবার নাম: {clean(m.fathers_name)}\n"
        f"🔹 মায়ের নাম: {clean(m.mothers_name)}\n"
        f"🔹 রক্তের গ্রুপ: {clean(m.blood_group)}\n"
        f"🔹 ধর্ম: {clean(m.religion)} | এনআইডি: {clean(m.nid)}\n"
        f"🔹 জন্মতারিখ: {clean(m.dob)}\n"
        f"🔹 হোম টাউন: {clean(m.home_town)}\n\n"
        
        f"<b>🎓 শিক্ষা ও অভিজ্ঞতা (Pro):</b>\n"
        f"🔹 শেষ শিক্ষা: {clean(m.last_education)}\n"
        f"🔹 প্রতিষ্ঠান: {clean(m.institution_name)}\n"
        f"🔹 পূর্বের কোম্পানি: {clean(m.previous_company_name)}\n"
        f"🔹 পূর্বের স্যালারি: {clean(m.previous_company_salary)}\n\n"
        
        f"<b>🛠 অফিসিয়াল ও অন্যান্য:</b>\n"
        f"🔹 জয়েনিং: {clean(m.joining_date)}\n"
        f"🔹 স্যালারি: {clean(m.salary)}\n"
        f"🔹 মার্কেট টাইপ: {clean(m.market_type)}\n"
        f"🔹 বাইক: {clean(m.motor_bike)} | সাইকেল: {clean(m.bicyle)}\n"
        f"🔹 লাইসেন্স: {clean(m.driving_license)}\n"
        f"🔹 ঠিকানা: {clean(m.present_address)}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def get_retailer_full_profile_text(r):
    """রিটেইলারের সকল ডাটা ফিল্ড ফোর্সের স্টাইলে সাজিয়ে দেওয়ার ফাংশন"""
    def clean(val):
        return str(val) if val and str(val).lower() != 'nan' else "N/A"
    
    # আরএসও (SR) এর নাম বের করা (যদি লিঙ্ক থাকে)
    sr_name = r.field_force.name if r.field_force else "অ্যাসাইন করা নেই"

    return (
        f"🏪 **রিটেইলার বিস্তারিত প্রোফাইল**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 প্রাথমিক পরিচয় (Identity):</b>\n"
        f"🔹 নাম: {r.name}\n"
        f"🔹 কোড: `{r.retailer_code}`\n"
        f"🔹 দায়িত্বপ্রাপ্ত SR: <b>{sr_name}</b>\n"
        f"🔹 রিটেইলার টাইপ: {clean(r.type)}\n"
        f"🔹 সচল (Enabled): {clean(r.enabled)}\n\n"
        
        f"<b>📞 যোগাযোগ ও মোবাইল (Contact):</b>\n"
        f"🔹 ফোন নং: {clean(r.contact_no)}\n"
        f"🔹 iTop Number: {clean(r.itop_number)}\n"
        f"🔹 iTop SR No: {clean(r.itop_sr_number)}\n"
        f"🔹 Tran Mobile: {clean(r.tran_mobile_no)}\n\n"
        
        f"<b>📍 ঠিকানা ও লোকেশন (Location):</b>\n"
        f"🔹 থানা: {clean(r.thana)}\n"
        f"🔹 জেলা: {clean(r.district)}\n"
        f"🔹 রুট: {clean(r.route)}\n"
        f"🔹 পূর্ণ ঠিকানা: {clean(r.address)}\n\n"
        
        f"<b>💼 বিজনেস ও ব্যক্তিগত (Business):</b>\n"
        f"🔹 মালিকের নাম: {clean(r.owner_name)}\n"
        f"🔹 এনআইডি (NID): {clean(r.nid)}\n"
        f"🔹 জন্ম তারিখ: {clean(r.dob)}\n"
        f"🔹 ক্যাটাগরি: {clean(r.category)}\n"
        f"🔹 সার্ভিস পয়েন্ট: {clean(r.service_point)}\n"
        f"🔹 সিম সেলার: {clean(r.sim_seller)}\n\n"
        
        f"<b>👷‍♂️ বিপি (BP) কানেকশন:</b>\n"
        f"🔹 BP কোড: {clean(r.bp_code)}\n"
        f"🔹 BP নম্বর: {clean(r.bp_number)}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    
def get_house_full_profile_text(h):
    """হাউজের সকল ডাটা রিটেইলার ও ফিল্ড ফোর্সের স্টাইলে সাজিয়ে দেওয়ার ফাংশন"""
    def clean(val):
        return str(val) if val and str(val).lower() != 'nan' else "N/A"
    
    # স্ট্যাটাস এবং সাবস্ক্রিপশন ডেট ফরম্যাটিং
    status = "Active ✅" if h.is_active else "Deactive ❌"
    sub_date = h.subscription_date.strftime('%d-%m-%Y') if h.subscription_date else "N/A"

    return (
        f"🏢 <b>হাউজ বিস্তারিত প্রোফাইল</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 প্রাথমিক পরিচয় (Identity):</b>\n"
        f"🔹 নাম: {h.name}\n"
        f"🔹 কোড: <code>{h.code}</code>\n"
        f"🔹 স্ট্যাটাস: {status}\n\n"
        
        f"<b>📍 অবস্থান ও ক্লাস্টার (Geography):</b>\n"
        f"🔹 ক্লাস্টার: {clean(h.cluster)}\n"
        f"🔹 রিজিয়ন: {clean(h.region)}\n\n"
        
        f"<b>📞 যোগাযোগ ও ঠিকানা (Contact):</b>\n"
        f"🔹 কন্টাক্ট নং: {clean(h.contact)}\n"
        f"🔹 ইমেইল: {clean(h.email)}\n"
        f"🔹 ঠিকানা: {clean(h.address)}\n\n"
        
        f"<b>🔐 ডিএমএস ক্রেডেনশিয়াল (DMS):</b>\n"
        f"🔹 ইউজারনেম: <code>{clean(h.dms_user)}</code>\n"
        f"🔹 পাসওয়ার্ড: <code>{clean(h.dms_pass)}</code>\n"
        f"🔹 হাউজ আইডি: <code>{clean(h.dms_house_id)}</code>\n\n"
        
        f"<b>📅 সাবস্ক্রিপশন (Subscription):</b>\n"
        f"🔹 মেয়াদ শেষ: <b>{sub_date}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )