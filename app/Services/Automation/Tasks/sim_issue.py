import re
import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from app.Core.login_manager import dms_login
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Utils.helpers import bn_num

ISSUE_URL = "https://blkdms.banglalink.net/IssueSimToRetailer/IssueSim"

async def run_sim_issue_status(serials: list, credentials: dict):
    """ধাপ ১: সিমগুলোর বর্তমান অবস্থা চেক করা (স্ক্র্যাপার ব্যবহার করে)"""
    session_file = f"sessions/session_{credentials['user']}.json"
    
    async with async_playwright() as p:
        browser, context = await dms_login.get_browser_context(p, session_file)
        page = await context.new_page()
        
        try:
            if not await dms_login.is_session_valid(page):
                await dms_login.perform_login(page, credentials, session_file)

            await page.goto("https://blkdms.banglalink.net/SmartSearchReport")
            await page.select_option("#SearchType", "1")
            await page.fill("#SearchValue", "\n".join(serials))
            await page.click("button.btn-success")

            # আমাদের সেন্ট্রাল স্ক্র্যাপার কল করা
            scanned_data, error = await get_smart_search_results(page)
            return scanned_data, error
        finally:
            await browser.close()

async def run_finalize_issue(serials: list, retailer_code: str, credentials: dict):
    """ধাপ ২: রিটেইলার কোড পাওয়ার পর ডিএমএস-এ সিম ইস্যু সম্পন্ন করা"""
    session_file = f"sessions/session_{credentials['user']}.json"
    
    async with async_playwright() as p:
        browser, context = await dms_login.get_browser_context(p, session_file)
        page = await context.new_page()
        
        try:
            if not await dms_login.is_session_valid(page):
                await dms_login.perform_login(page, credentials, session_file)

            await page.goto(ISSUE_URL)
            await page.wait_for_selector("#IssueDate")

            # তারিখ সেট (আজকের তারিখ)
            today = datetime.now().strftime('%Y-%m-%d')
            await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")

            # রিটেইলার সিলেকশন (JS Chosen)
            js_select = f"""
                (code) => {{
                    let select = document.getElementById('Retailer');
                    for (let i = 0; i < select.options.length; i++) {{
                        if (select.options[i].text.includes(code)) {{
                            select.selectedIndex = i;
                            $(select).trigger('chosen:updated').change();
                            return true;
                        }}
                    }}
                    return false;
                }}
            """
            if not await page.evaluate(js_select, retailer_code):
                return f"❌ এরর: রিটেইলার কোড `{retailer_code}` ড্রপডাউনে পাওয়া যায়নি।"

            await asyncio.sleep(1)
            await page.fill("#SimList", "\n".join(serials))
            await page.click("#AddBtn")

            # Warning Modal (Swal2)
            try:
                await page.wait_for_selector("button.swal2-confirm", timeout=5000)
                await page.click("button.swal2-confirm")
            except: pass

            # Issue Button Click
            await asyncio.sleep(1.5)
            await page.click("#SimIssueBtn")

            # Success Modal
            await page.wait_for_selector("#okBtn", timeout=10000)
            await page.click("#okBtn")
            
            return f"✅ সফলভাবে `{retailer_code}` কোডে {bn_num(len(serials))}টি সিম ইস্যু সম্পন্ন হয়েছে।"

        except Exception as e:
            return f"❌ অটোমেশন এরর: {str(e)}"
        finally:
            await browser.close()

def process_issue_summary(all_data, target_house):
    """সিম ইস্যু এনালাইসিস সামারি (স্ট্যাটাস মডিউলের স্টাইলে)"""
    active_map = {}   # Date -> List of strings
    issued_map = {}   # Retailer -> List of strings
    ready_list = []   # ইস্যুর জন্য প্রস্তুত সিমের বর্ণনা
    ready_serials_only = [] # শুধুমাত্র সিরিয়াল লিস্ট (অটোমেশনের জন্য)
    errors = []

    for d in all_data:
        sim = d.get("SIM No", "").strip()
        house = d.get("Distributor", "N/A")
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", d.get("Mobile No", "N/A"))

        # ১. হাউজ চেক
        if target_house and target_house not in house:
            errors.append(f"❌ `{sim}`: এটি {house} হাউসের সিম।")
            continue

        # ২. এক্টিভ সিম (🟢)
        if act_date:
            if act_date not in active_map: active_map[act_date] = []
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🟢 {sim}\n📱 {clean_msisdn}")

        # ৩. ইতিমধ্যে ইস্যু করা সিম (🟡)
        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")

        # ৪. ইস্যু হয় নাই বা রেডি সিম (⚪)
        else:
            ready_list.append(f"⚪ {sim}")
            ready_serials_only.append(sim)

    # --- মেসেজ ফরম্যাটিং শুরু ---
    final_output = ["📝 **সিম ইস্যু এনালাইসিস রিপোর্ট:**\n"]

    # এক্টিভ সিম সেকশন (তারিখ অনুযায়ী)
    for date, lines in active_map.items():
        final_output.append("\n".join(lines))
        final_output.append(f"📅 {date}\n")

    # ইস্যু করা সিম সেকশন (রিটেইলার অনুযায়ী)
    if issued_map:
        if len(final_output) > 1: final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims))
            final_output.append(f"••••••••••••••••••••••\n🏪 {ret} (ইতিমধ্যে ইস্যু করা)\n")

    # রেডি সিম সেকশন
    if ready_list:
        final_output.append("\n".join(ready_list))
        final_output.append("✅ এই সিমগুলো ইস্যু করা সম্ভব।\n")

    # এরর সেকশন
    if errors:
        final_output.append("\n" + "\n".join(errors))

    report_text = "\n".join(final_output) if final_output else "⚠️ কোনো তথ্য পাওয়া যায়নি।"
    
    # আমরা রিপোর্ট টেক্সট এবং শুধুমাত্র ইস্যুযোগ্য সিরিয়ালের লিস্ট—উভয়ই রিটার্ন করছি
    return report_text, ready_serials_only