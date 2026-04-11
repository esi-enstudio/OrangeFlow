import asyncio
import logging
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Core.session_manager import session_manager

# লগিং কনফিগারেশন
logger = logging.getLogger(__name__)

# ইউআরএল
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"

async def run_sim_status_check(serials: list, credentials: dict):
    """
    সেশন ম্যানেজার ব্যবহার করে সিম স্ট্যাটাস চেক টাস্ক।
    এটি Persistent Profile ব্যবহার করে, ফলে সেশন অনেক বেশি স্থায়ী হয়।
    """
    house_name = credentials.get('house_name', 'N/A')
    h_code = credentials.get('code', 'N/A')
    
    # ১. সেশন ম্যানেজার থেকে সরাসরি একটি সচল পেজ এবং কন্টেক্সট সংগ্রহ করা ✅
    # এটি নিজে থেকেই সেশন ভ্যালিডিটি চেক করবে এবং প্রোফাইল ফোল্ডার থেকে ডাটা লোড করবে।
    try:
        page, context = await session_manager.get_valid_page(credentials)
    except Exception as e:
        logger.error(f"❌ [Task Error] সেশন পেতে ব্যর্থ: {str(e)}")
        return f"❌ ডিএমএস সেশন তৈরি করা সম্ভব হয়নি: {str(e)}"
    
    try:
        logger.info(f"🔍 [Task] {house_name} ({h_code}) এর জন্য স্ট্যাটাস চেক শুরু...")
        
        # ২. সরাসরি স্মার্ট সার্চ পেজে যাওয়া
        # wait_until="commit" দ্রুত কাজ করার জন্য ব্যবহার করা হয়েছে
        await page.goto(SMART_SEARCH_URL, wait_until="commit", timeout=40000) 

        # পেজ লোড নিশ্চিত করতে একটি কি-এলিমেন্টের জন্য অপেক্ষা
        await page.wait_for_selector("#SearchType", timeout=30000)
        
        # ৩. ইনপুট প্রদান এবং সাবমিট
        # সার্চ টাইপ 'SIM Serial' (Value: 1) সিলেক্ট করা
        await page.select_option("#SearchType", "1")
        
        # সিরিয়ালগুলো ফিল করা
        await page.fill("#SearchValue", "\n".join(serials))
        
        # সার্চ বাটনে ক্লিক
        await page.click("button.btn-success")

        # ৪. সেন্ট্রাল স্ক্র্যাপার ব্যবহার করে রেজাল্ট সংগ্রহ করা ✅
        # এটি এরর মেসেজ, কার্ড ভিউ এবং টেবিল ভিউ (পেজিনেশনসহ) হ্যান্ডেল করে।
        scanned_data, error = await get_smart_search_results(page)

        if error:
            return error # "Data not found" বা অন্য কোনো এরর থাকলে সেটি সরাসরি রিটার্ন হবে

    except Exception as e:
        logger.error(f"❌ [Task Error] {house_name} স্ট্যাটাস চেক এরর: {str(e)}")
        return f"❌ অটোমেশন এরর: {str(e)}"
    
    finally:
        if page:
            await page.close()
        if context:
            await context.close() # ✅ এটি এখন অবশ্যই করতে হবে
        logger.info(f"🚪 [{house_name}] টাস্ক ক্লিনআপ সম্পন্ন।")


    # ৬. স্ক্র্যাপ করা ডাটা থেকে সামারি রিপোর্ট জেনারেট করে রিটার্ন করা
    return generate_sim_summary(scanned_data, house_name)

def generate_sim_summary(all_data, target_house):
    """স্ক্র্যাপ করা ডাটা থেকে সুন্দর টেলিগ্রাম মেসেজ জেনারেট করার লজিক"""
    active_map = {} # Date -> List of strings
    issued_map = {} # Retailer -> List of strings
    ready_list = []
    errors = []

    for d in all_data:
        sim = d.get("SIM No", "")
        house = d.get("Distributor", "")
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", "")

        # ১. হাউজ ভ্যালিডেশন চেক
        if target_house and target_house not in house:
            errors.append(f"❌ `{sim}`: এটি {house} হাউসের সিম।")
            continue

        # ২. এক্টিভ সিম ক্যাটাগরি (🟢)
        if act_date:
            if act_date not in active_map: 
                active_map[act_date] = []
            # নাম্বার ফরম্যাট ঠিক করা
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🟢 {sim}\n📱 {clean_msisdn}")
            
        # ৩. ইস্যু করা সিম ক্যাটাগরি (🟡)
        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: 
                issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
            
        # ৪. রেডি সিম/ওয়্যারহাউস ক্যাটাগরি (⚪)
        else:
            ready_list.append(f"⚪ {sim}")

    # --- মেসেজ ফরম্যাটিং ---
    final_output = []

    # এক্টিভ সিম সেকশন (তারিখ অনুযায়ী সাজানো)
    for date, lines in active_map.items():
        final_output.append("\n".join(lines))
        final_output.append(f"📅 {date}\n")

    # ইস্যু করা সিম সেকশন (রিটেইলার অনুযায়ী সাজানো)
    if issued_map:
        if final_output: 
            final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims))
            final_output.append(f"••••••••••••••••••••••\n🏪 {ret}\n")

    # রেডি সিম সেকশন
    if ready_list:
        if final_output: 
            final_output.append("")
        final_output.append("\n".join(ready_list))

    # এরর সেকশন (অন্য হাউসের সিম)
    if errors:
        final_output.append("\n" + "\n".join(errors))

    return "\n".join(final_output) if final_output else "⚠️ কোনো তথ্য পাওয়া যায়নি।"