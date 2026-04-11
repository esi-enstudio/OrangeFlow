import asyncio
import re
import logging
from datetime import datetime
from app.Core.session_manager import session_manager
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Utils.helpers import bn_num

# লগিং সেটআপ
logger = logging.getLogger("app.Services.Automation.Tasks")

# ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
ISSUE_URL = "https://blkdms.banglalink.net/IssueSimToRetailer/IssueSim"

async def run_sim_issue_status(serials: list, credentials: dict):
    """ধাপ ১: সিমগুলোর বর্তমান অবস্থা চেক করা (সেশন ম্যানেজার ব্যবহার করে)"""
    house_name = credentials.get('house_name', 'N/A')
    
    logger.info(f"🚀 [{house_name}] সিম ইস্যু এনালাইসিস শুরু হচ্ছে...")
    # ১. সচল পেজ সংগ্রহ
    page, context = await session_manager.get_valid_page(credentials)
    
    try:
        # ২. স্মার্ট সার্চ পেজে যাওয়া (domcontentloaded দ্রুত এবং স্ট্যাবল)
        logger.info(f"🔍 [{house_name}] স্মার্ট সার্চ পেজে যাওয়া হচ্ছে...")
        await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#SearchType", timeout=30000)
        
        # ৩. সার্চ ফরম পূরণ
        await page.select_option("#SearchType", "1") 
        await page.fill("#SearchValue", "\n".join(serials))
        await page.click("button.btn-success")
        logger.info(f"📡 সার্চ সাবমিট হয়েছে, ডাটা সংগ্রহের অপেক্ষা...")

        # ৪. স্ক্র্যাপার কল করে রেজাল্ট সংগ্রহ
        scanned_data, error = await get_smart_search_results(page)
        return scanned_data, error
        
    except Exception as e:
        logger.error(f"❌ এনালাইসিস এরর: {str(e)}")
        return None, f"❌ স্ট্যাটাস চেক এরর: {str(e)}"
    finally:
        # ৫. পরিবর্তন: শুধু ট্যাব বন্ধ করা হবে, context নয়! ✅
        if page:
            await page.close()
            logger.info(f"🚪 [{house_name}] এনালাইসিস ট্যাব বন্ধ করা হয়েছে।")

async def run_finalize_issue(serials: list, retailer_code: str, credentials: dict):
    """ধাপ ২: চূড়ান্তভাবে ডিএমএস-এ সিম ইস্যু সম্পন্ন করা"""
    house_name = credentials.get('house_name', 'N/A')
    
    logger.info(f"📤 [{house_name}] রিটেইলার `{retailer_code}` এর জন্য ফাইনাল ইস্যু শুরু...")
    # ১. নতুন পেজ সংগ্রহ
    page, context = await session_manager.get_valid_page(credentials)
    
    try:
        # ২. ইস্যু পেজে যাওয়া (networkidle পরিহার করা হয়েছে)
        logger.info(f"🌐 ইস্যু পেজে যাওয়া হচ্ছে...")
        await page.goto(ISSUE_URL, wait_until="domcontentloaded", timeout=60000)
        
        # ৩. তারিখ সেট করা
        await page.wait_for_selector("#IssueDate", timeout=30000)
        today = datetime.now().strftime('%Y-%m-%d')
        await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")
        logger.info(f"📅 তারিখ সেট: {today}")

        # ৪. রিটেইলার ড্রপডাউন হ্যান্ডলিং (Attached স্টেট ব্যবহার করা হয়েছে কারণ এটি লুকানো থাকে)
        await page.wait_for_selector("#Retailer", state="attached", timeout=30000)
        
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
        if not await page.evaluate(js_select, retailer_code):
            logger.error(f"❌ রিটেইলার `{retailer_code}` পাওয়া যায়নি।")
            return f"❌ এরর: রিটেইলার কোড `{retailer_code}` ড্রপডাউনে পাওয়া যায়নি।"

        await asyncio.sleep(1.5) 

        # ৫. সিম লিস্ট ইনপুট ও অ্যাড বাটনে ক্লিক (force=True ব্যবহার করা হয়েছে নিরাপদ ইনপুটের জন্য)
        await page.fill("#SimList", "\n".join(serials), force=True)
        await page.click("#AddBtn")
        logger.info(f"➕ সিম লিস্ট অ্যাড করা হয়েছে।")

        # ৬. ডিএমএস ওয়ার্নিং মোডাল হ্যান্ডলিং
        try:
            confirm_btn = "button.swal2-confirm"
            await page.wait_for_selector(confirm_btn, state="visible", timeout=8000)
            await page.click(confirm_btn)
            await asyncio.sleep(1)
        except: pass

        # ৭. ফাইনাল ইস্যু বাটন ক্লিক
        logger.info(f"💾 ফাইনাল সাবমিট করা হচ্ছে...")
        await page.wait_for_selector("#SimIssueBtn", state="visible", timeout=15000)
        await page.click("#SimIssueBtn")

        # ৮. সাকসেস কনফার্মেশন (okBtn)
        try:
            await page.wait_for_selector("#okBtn", state="visible", timeout=20000)
            await page.click("#okBtn")
            logger.info(f"✅ ইস্যু সফল!")
            return f"✅ সফলভাবে `{retailer_code}` কোডে {bn_num(len(serials))}টি সিম ইস্যু সম্পন্ন হয়েছে।"
        except Exception as e:
            logger.warning(f"⚠️ সাকসেস বাটন পাওয়া যায়নি: {str(e)}")
            return f"⚠️ প্রসেস শেষ হয়েছে, কিন্তু সাকসেস কনফার্মেশন পাওয়া যায়নি। ডিএমএস চেক করুন।"

    except Exception as e:
        logger.error(f"💥 ইস্যু সাবমিশন ক্র্যাশ: {str(e)}", exc_info=True)
        return f"❌ ইস্যু সাবমিশন এরর: {str(e)}"
    
    finally:
        if page:
            await page.close()
        if context:
            await context.close() # ✅ এটি এখন অবশ্যই করতে হবে
        logger.info(f"🚪 [{house_name}] টাস্ক ক্লিনআপ সম্পন্ন।")




def process_issue_summary(all_data, target_house):
    """সিম ইস্যু এনালাইসিস সামারি জেনারেটর (আইকন আপডেট সহ)"""
    active_map = {}
    issued_map = {}
    warehouse_list = []
    ready_serials_only = []
    errors = []

    for d in all_data:
        sim = d.get("SIM No", "").strip()
        house = d.get("Distributor", "N/A")
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", d.get("Mobile No", "N/A"))

        # ১. হাউজ ভ্যালিডেশন
        if target_house and target_house not in house:
            errors.append(f"❌ `{sim}`: এটি {house} হাউসের সিম।")
            continue

        # ২. এক্টিভ সিম (🔴) - যা ইস্যু করা যাবে না
        if act_date:
            if act_date not in active_map: active_map[act_date] = []
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🔴 {sim}\n📱 {clean_msisdn} (এক্টিভ)")

        # ৩. ইতিমধ্যে ইস্যু করা সিম (🟡)
        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")

        # ৪. রেডি সিম (⚪) - যা নতুন করে ইস্যু করা যাবে
        else:
            warehouse_list.append(f"⚪ {sim}")
            ready_serials_only.append(sim)

    # --- মেসেজ ফরম্যাটিং ---
    final_output = ["📝 **সিম ইস্যু এনালাইসিস রিপোর্ট:**\n"]

    # এক্টিভ সিম সেকশন
    if active_map:
        for date, lines in active_map.items():
            final_output.append("\n".join(lines))
            final_output.append(f"📅 {date}\n")

    # ইতিমধ্যে ইস্যু করা সিম সেকশন
    if issued_map:
        if len(final_output) > 1: final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims))
            final_output.append(f"••••••••••••••••••••••\n🏪 {ret} (ইতিমধ্যে ইস্যু করা)\n")

    # নতুন ইস্যুযোগ্য সিম সেকশন
    if warehouse_list:
        final_output.append("\n".join(warehouse_list))
        final_output.append(f"✅ এই {bn_num(len(warehouse_list))}টি সিম ইস্যু করা সম্ভব।\n")

    # অন্য হাউসের এরর সেকশন
    if errors:
        final_output.append("\n" + "\n".join(errors))

    report_text = "\n".join(final_output) if len(final_output) > 1 else "⚠️ কোনো তথ্য পাওয়া যায়নি।"
    return report_text, ready_serials_only