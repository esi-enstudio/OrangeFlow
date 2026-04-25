import asyncio
import re
import logging
from datetime import datetime
from app.Core.session_manager import session_manager
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Utils.helpers import bn_num

# লগিং কনফিগারেশন
logger = logging.getLogger("app.Services.Automation.Tasks")

# ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
ISSUE_URL = "https://blkdms.banglalink.net/IssueSimToRetailer/IssueSim"

async def run_sim_issue_status(serials: list, credentials: dict):
    """
    ধাপ ১: সিমগুলোর বর্তমান অবস্থা চেক করা।
    এটি সেশন ম্যানেজার ব্যবহার করে সচল পেজ নিশ্চিত করবে।
    """
    house_name = credentials.get('house_name', 'N/A')
    logger.info(f"🚀 [{house_name}] সিম ইস্যু এনালাইসিস শুরু হচ্ছে...")

    # ১. সেশন ম্যানেজার থেকে সচল পেজ সংগ্রহ (এটি অটো-লগইন হ্যান্ডেল করবে)
    page, context = await session_manager.get_valid_page(credentials)
    
    try:
        # ২. স্মার্ট সার্চ পেজে যাওয়া
        logger.info(f"🔍 [{house_name}] স্মার্ট সার্চ পেজে নেভিগেট করা হচ্ছে...")
        await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#SearchType", timeout=30000)
        
        # ৩. সার্চ ফরম পূরণ ও সাবমিট
        await page.select_option("#SearchType", "1") # SIM Serial নির্বাচন
        await page.fill("#SearchValue", "\n".join(serials))
        await page.click("button.btn-success")
        logger.info(f"📡 সার্চ রিকোয়েস্ট পাঠানো হয়েছে, রেজাল্ট স্ক্র্যাপ করছি...")

        # ৪. সেন্ট্রাল স্ক্র্যাপার কল করা (Error, Card, Table হ্যান্ডেল করবে)
        scanned_data, error = await get_smart_search_results(page)
        return scanned_data, error
        
    except Exception as e:
        logger.error(f"❌ এনালাইসিস ক্র্যাশ: {str(e)}", exc_info=True)
        return None, f"❌ স্ট্যাটাস চেক এরর: {str(e)}"
    finally:
        # ৫. শুধু ট্যাব বন্ধ করা হবে যাতে প্রোফাইলটি মেমোরিতে সচল থাকে ✅
        if page:
            await page.close()
            logger.info(f"🚪 [{house_name}] এনালাইসিস ট্যাব বন্ধ হয়েছে।")

async def run_finalize_issue(serials: list, retailer_code: str, credentials: dict):
    """
    ধাপ ২: চূড়ান্তভাবে ডিএমএস-এ সিম ইস্যু সাবমিট করা।
    এটিও সেশন ম্যানেজার ব্যবহার করবে যাতে সেশন ফেইল না করে। ✅
    """
    house_name = credentials.get('house_name', 'N/A')
    logger.info(f"📤 [{house_name}] রিটেইলার `{retailer_code}` এর জন্য সাবমিশন শুরু...")

    # ১. সেশন ম্যানেজার থেকে পেজ সংগ্রহ (এটি নিশ্চিত করবে সেশন এখনো সচল আছে)
    page, context = await session_manager.get_valid_page(credentials)
    
    try:
        # ২. ইস্যু পেজে যাওয়া
        logger.info(f"🌐 ইস্যু পেজে যাওয়া হচ্ছে...")
        await page.goto(ISSUE_URL, wait_until="domcontentloaded", timeout=60000)
        
        # ৩. তারিখ সেট করা (আজকের তারিখ)
        await page.wait_for_selector("#IssueDate", timeout=30000)
        today = datetime.now().strftime('%Y-%m-%d')
        await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")
        logger.info(f"📅 তারিখ সেট করা হয়েছে: {today}")

        # ৪. রিটেইলার ড্রপডাউন হ্যান্ডলিং (Attached স্টেট ব্যবহার করা হয়েছে কারণ এটি অনেক সময় লুকানো থাকে)
        await page.wait_for_selector("#Retailer", state="attached", timeout=30000)
        
        # নিখুঁত সিলেকশন লজিক (jQuery ও Native ইভেন্টসহ)
        js_select = """
            (code) => {
                let select = document.getElementById('Retailer');
                if (!select) return false;
                for (let i = 0; i < select.options.length; i++) {
                    if (select.options[i].text.includes(code)) {
                        select.selectedIndex = i;
                        if (typeof window.jQuery !== 'undefined') {
                            window.jQuery(select).trigger('chosen:updated').change();
                        } else {
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return true;
                    }
                }
                return false;
            }
        """
        selection_success = await page.evaluate(js_select, retailer_code)
        if not selection_success:
            logger.error(f"❌ রিটেইলার `{retailer_code}` ড্রপডাউনে পাওয়া যায়নি!")
            return f"❌ এরর: রিটেইলার কোড `{retailer_code}` ড্রপডাউনে পাওয়া যায়নি।"

        await asyncio.sleep(1.5) # ড্রপডাউন প্রসেসিং এর জন্য বিরতি

        # ৫. সিম লিস্ট ইনপুট ও অ্যাড বাটনে ক্লিক
        logger.info(f"📝 সিম লিস্ট ইনপুট দেওয়া হচ্ছে...")
        await page.fill("#SimList", "\n".join(serials), force=True)
        await page.click("#AddBtn")
        logger.info(f"➕ সিম লিস্ট অ্যাড করা হয়েছে। প্রসেসিং বাফার...")

        await asyncio.sleep(1) # এই ছোট বিরতিটি দিলে বাটন ক্লিক অনেক বেশি স্ট্যাবল হবে ✅



        # ৬. ডিএমএস ওয়ার্নিং মোডাল (SweetAlert2) হ্যান্ডলিং
        try:
            confirm_btn = "button.swal2-confirm"
            await page.wait_for_selector(confirm_btn, state="visible", timeout=8000)
            await page.click(confirm_btn)
            await asyncio.sleep(1)
        except: 
            pass # মোডাল না আসলে সমস্যা নেই

        # ৭. ফাইনাল ইস্যু বাটন ক্লিক
        logger.info(f"💾 চূড়ান্ত সাবমিট বাটন খুঁজছি...")
        try:
            # বাটনটি দৃশ্যমান হওয়া পর্যন্ত অপেক্ষা
            await page.wait_for_selector("#SimIssueBtn", state="visible", timeout=90000)
            await page.click("#SimIssueBtn")
            logger.info(f"💾 সাবমিট বাটনে ক্লিক করা হয়েছে।")
        except Exception:
            return "❌ 'Issue' বাটনটি নির্দিষ্ট সময়ের মধ্যে পাওয়া যায়নি। ডিএমএস স্লো হতে পারে।"

        # ৮. সাকসেস কনফার্মেশন (okBtn) হ্যান্ডলিং
        try:
            await page.wait_for_selector("#okBtn", state="visible", timeout=25000)
            await page.click("#okBtn")
            logger.info(f"✅ [{house_name}] সিম ইস্যু সফল হয়েছে!")
            return f"✅ সফলভাবে `{retailer_code}` কোডে {bn_num(len(serials))}টি সিম ইস্যু সম্পন্ন হয়েছে।"
        except Exception as e:
            logger.warning(f"⚠️ সাকসেস কনফার্মেশন বাটন পাওয়া যায়নি: {str(e)}")
            return f"⚠️ প্রসেস শেষ হয়েছে, কিন্তু সাকসেস কনফার্মেশন পাওয়া যায়নি। ডিএমএস চেক করুন।"

    except Exception as e:
        logger.error(f"💥 ইস্যু সাবমিশন এরর: {str(e)}", exc_info=True)
        return f"❌ ইস্যু সাবমিশন এরর: {str(e)}"
    
    finally:
        # ৯. কাজ শেষে শুধু ট্যাব এবং কন্টেক্সট বন্ধ করা ✅
        # যেহেতু এটি টার্মিনাল অ্যাকশন (শেষ ধাপ), তাই এখানে কন্টেক্সট বন্ধ করা নিরাপদ।
        if page: await page.close()
        if context: await context.close()
        logger.info(f"🚪 [{house_name}] ইস্যু প্রসেস ক্লিনআপ সম্পন্ন।")

def process_issue_summary(all_data, house_info):
    """সিম ইস্যু এনালাইসিস (কোড ভিত্তিক ম্যাপিং) ✅"""
    active_map, issued_map = {}, {}
    warehouse_list, ready_serials_only, errors = [], [], []

    # হাউজ কোড (RYZBRB01)
    target_code = str(house_info.get('code', '')).strip().upper()
    target_name = str(house_info.get('house_name', '')).strip()

    for d in all_data:
        sim = d.get("SIM No", "").strip().replace("'", "")
        dms_distro = str(d.get("Distributor", "N/A")).strip().upper()
        
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", d.get("Mobile No", "N/A"))

        # ১. হাউজ ভ্যালিডেশন (কোড দিয়ে) ✅
        if target_code not in dms_distro:
            errors.append(f"❌ <code>{sim}</code>: এটি অন্য হাউসের সিম।")
            continue

        if act_date:
            if act_date not in active_map: active_map[act_date] = []
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🔴 {sim}\n📱 {clean_msisdn} (এক্টিভ)")

        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
        
        else:
            warehouse_list.append(f"⚪ {sim}")
            ready_serials_only.append(sim)

    # --- রিপোর্ট ফরম্যাটিং ---
    final_output = ["📝 <b>সিম ইস্যু এনালাইসিস রিপোর্ট:</b>\n"]
    if active_map:
        for date, lines in active_map.items():
            final_output.append("\n".join(lines) + f"\n📅 {date}\n")
    if issued_map:
        final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims) + f"\n••••••••••••••••••••••\n🏪 {ret} (ইতিমধ্যে ইস্যু করা)\n")
    if warehouse_list:
        final_output.append("\n".join(warehouse_list))
        final_output.append(f"✅ এই <b>{bn_num(len(warehouse_list))}টি</b> সিম ইস্যু করা সম্ভব।\n")
    if errors:
        final_output.append("\n" + "\n".join(errors))

    return "\n".join(final_output) if len(final_output) > 1 else "⚠️ কোনো তথ্য পাওয়া যায়নি。", ready_serials_only