import asyncio
import re
from datetime import datetime
from app.Core.session_manager import session_manager
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Utils.helpers import bn_num

# ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
ISSUE_URL = "https://blkdms.banglalink.net/IssueSimToRetailer/IssueSim"

async def run_sim_issue_status(serials: list, credentials: dict):
    """ধাপ ১: সিমগুলোর বর্তমান অবস্থা চেক করা (সেশন ম্যানেজার ব্যবহার করে)"""
    # ১. সেশন ম্যানেজার থেকে সরাসরি সচল পেজ সংগ্রহ করা (এটি অটো-লগইন হ্যান্ডেল করবে)
    page, context = await session_manager.get_valid_page(credentials)
    
    try:
        # ২. স্মার্ট সার্চ পেজে যাওয়া
        await page.goto(SMART_SEARCH_URL, wait_until="commit", timeout=40000)
        await page.wait_for_selector("#SearchType", timeout=30000)
        
        # ৩. সার্চ ফরম পূরণ ও সাবমিট
        await page.select_option("#SearchType", "1") # SIM Serial
        await page.fill("#SearchValue", "\n".join(serials))
        await page.click("button.btn-success")

        # ৪. সেন্ট্রাল স্ক্র্যাপার কল করা (এটি Card, Table, Error সব হ্যান্ডেল করবে)
        scanned_data, error = await get_smart_search_results(page)
        return scanned_data, error
        
    except Exception as e:
        return None, f"❌ স্ট্যাটাস চেক এরর: {str(e)}"
    finally:
        # কাজ শেষে ট্যাব এবং কন্টেক্সট বন্ধ করা
        await page.close()
        await context.close()

async def run_finalize_issue(serials: list, retailer_code: str, credentials: dict):
    """ধাপ ২: চূড়ান্তভাবে ডিএমএস-এ সিম ইস্যু সম্পন্ন করা"""
    page, context = await session_manager.get_valid_page(credentials)
    
    try:
        await page.goto(ISSUE_URL, wait_until="networkidle", timeout=40000)
        await page.wait_for_selector("#IssueDate", timeout=30000)

        # ১. তারিখ সেট করা (আজকের তারিখ)
        today = datetime.now().strftime('%Y-%m-%d')
        await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")

        # ২. রিটেইলার সিলেকশন (JS Chosen Dropdown লজিক)
        js_select = """
            (code) => {
                let select = document.getElementById('Retailer');
                if (!select) return false;
                for (let i = 0; i < select.options.length; i++) {
                    if (select.options[i].text.includes(code)) {
                        select.selectedIndex = i;
                        // jQuery ট্রিগার বা স্ট্যান্ডার্ড ইভেন্ট ট্রিগার
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
            return f"❌ এরর: রিটেইলার কোড `{retailer_code}` ড্রপডাউনে পাওয়া যায়নি।"

        await asyncio.sleep(1.5) # ড্রপডাউন প্রসেসিং এর জন্য বিরতি

        # ৩. সিম লিস্ট ইনপুট ও অ্যাড বাটনে ক্লিক
        await page.fill("#SimList", "\n".join(serials))
        await page.click("#AddBtn")

        # ৪. ওয়ার্নিং মোডাল (যদি থাকে) হ্যান্ডলিং
        try:
            # ১০ সেকেন্ড ওয়েট করবে মোডাল আসার জন্য
            await page.wait_for_selector("button.swal2-confirm", state="visible", timeout=10000)
            await page.click("button.swal2-confirm")
            await asyncio.sleep(1.5)
        except:
            pass

        # ৫. ফাইনাল ইস্যু বাটন ক্লিক
        await page.wait_for_selector("#SimIssueBtn", state="visible", timeout=10000)
        await page.click("#SimIssueBtn")

        # ৬. সাকসেস মোডাল (okBtn) হ্যান্ডলিং
        try:
            await page.wait_for_selector("#okBtn", state="visible", timeout=20000)
            await page.click("#okBtn")
            # বাংলা সংখ্যা হেল্পার ব্যবহার করে মেসেজ
            return f"✅ সফলভাবে `{retailer_code}` কোডে {bn_num(len(serials))}টি সিম ইস্যু সম্পন্ন হয়েছে।"
        except:
            return f"⚠️ প্রসেস শেষ হয়েছে, কিন্তু সাকসেস কনফার্মেশন পাওয়া যায়নি। ডিএমএস ড্যাশবোর্ড চেক করুন।"

    except Exception as e:
        return f"❌ ইস্যু সাবমিশন এরর: {str(e)}"
    finally:
        await page.close()

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