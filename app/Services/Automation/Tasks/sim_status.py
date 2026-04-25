import asyncio
import logging
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Core.session_manager import session_manager

# লগিং সেটআপ
logger = logging.getLogger("app.Services.Automation.Tasks")

# ইউআরএল
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"

async def run_sim_status_check(serials: list, credentials: dict):
    """
    সেশন ম্যানেজার (JSON Storage State) ব্যবহার করে সিম স্ট্যাটাস চেক।
    এটি প্রতিটি কাজের জন্য আলাদা কনটেক্সট তৈরি করে এবং শেষে ক্লিনআপ করে।
    """
    house_name = credentials.get('house_name', 'N/A')
    h_code = credentials.get('code', 'N/A')
    
    # ১. সেশন ম্যানেজার থেকে সচল পেজ ও কন্টেক্সট নেওয়া
    try:
        page, context = await session_manager.get_valid_page(credentials)
    except Exception as e:
        logger.error(f"❌ [Task Error] {house_name} সেশন পেতে ব্যর্থ: {str(e)}")
        return f"{str(e)}"
    
    final_report = "" # চূড়ান্ত রিপোর্টের জন্য ভেরিয়েবল

    try:
        logger.info(f"🔍 [Task] {house_name} ({h_code}) এর জন্য {len(serials)}টি সিম চেক শুরু...")
        
        # ২. স্মার্ট সার্চ পেজে যাওয়া (domcontentloaded বেশি স্ট্যাবল) ✅
        await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=60000) 

        # এলিমেন্ট আসা পর্যন্ত অপেক্ষা
        await page.wait_for_selector("#SearchType", timeout=30000)
        
        # ৩. ইনপুট প্রদান
        await page.select_option("#SearchType", "1") # SIM Serial
        await page.fill("#SearchValue", "\n".join(serials))
        
        # ৪. সার্চ বাটনে ক্লিক এবং রেজাল্টের অপেক্ষা
        await page.click("button.btn-success")
        logger.info(f"📡 {house_name}: সার্চ সাবমিট হয়েছে, ডাটা সংগ্রহের অপেক্ষা...")

        # ৫. সেন্ট্রাল স্ক্র্যাপার ব্যবহার করে ডাটা সংগ্রহ ✅
        scanned_data, error = await get_smart_search_results(page)

        if error:
            logger.warning(f"⚠️ {house_name}: {error}")
            final_report = error
        else:
            # ডাটা পাওয়া গেলে সামারি জেনারেট করা
            final_report = generate_sim_summary(scanned_data, credentials)

    except Exception as e:
        logger.error(f"❌ [Task Error] {house_name} ক্র্যাশ: {str(e)}", exc_info=True)
        final_report = f"❌ অটোমেশন এরর: {str(e).replace('_', ' ')}"
    
    finally:
        # ৬. কাজ শেষে ট্যাব এবং কন্টেক্সট বন্ধ করা (RAM সাশ্রয়ের জন্য) ✅
        try:
            if page: await page.close()
            if context: await context.close()
            logger.info(f"🚪 [{house_name}] টাস্ক ট্যাব ও সেশন ক্লোজ করা হয়েছে।")
        except:
            pass

    # চূড়ান্ত রেজাল্ট রিটার্ন করা
    return final_report

def generate_sim_summary(all_data, credentials):
    """হাউজ কোড দিয়ে ভ্যালিডেশন এবং সামারি জেনারেশন ✅"""
    active_map, issued_map = {}, {}
    warehouse_list, errors = [], []
    
    # ১. টার্গেট হাউজ কোড বের করা (যেমন: RYZBRB01)
    target_code = str(credentials.get('code', '')).strip().upper()
    house_name = credentials.get('house_name', 'N/A')

    for d in all_data:
        sim = d.get("SIM No", "").strip().replace("'", "")
        # ডিএমএস থেকে প্রাপ্ত ডিস্ট্রিবিউটর ডাটাকে বড় হাতের করা
        dms_distro = str(d.get("Distributor", "")).strip().upper()
        
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", d.get("Mobile No", ""))

        # ২. হাউজ ভ্যালিডেশন (কোড ভিত্তিক) ✅
        if target_code not in dms_distro:
            errors.append(f"❌ <code>{sim}</code>: এটি অন্য হাউসের সিম। ({d.get('Distributor')})")
            continue

        if act_date:
            if act_date not in active_map: active_map[act_date] = []
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🟢 {sim}\n📱 {clean_msisdn}")
            
        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
            
        else:
            warehouse_list.append(f"⚪ {sim}")

    # --- ৩. মেসেজ ফরম্যাটিং ---
    output = [f"📊 <b>সিম স্ট্যাটাস রিপোর্ট</b>", f"🏢 হাউজ: <b>{house_name}</b>\n"]

    for date, lines in active_map.items():
        output.append("\n".join(lines) + f"\n📅 {date}\n")

    if issued_map:
        output.append("----------------------------")
        for ret, sims in issued_map.items():
            output.append("\n".join(sims) + f"\n••••••••••••••••••••••\n🏪 {ret}\n")

    if warehouse_list: output.append("\n" + "\n".join(warehouse_list))
    if errors: output.append("\n" + "\n".join(errors))

    return "\n".join(output) if len(output) > 2 else "⚠️ কোনো তথ্য পাওয়া যায়নি।"