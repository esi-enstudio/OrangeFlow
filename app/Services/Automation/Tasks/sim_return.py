import asyncio
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Core.login_manager import dms_login
from app.Utils.helpers import bn_num

# ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
RECEIVE_URL = "https://blkdms.banglalink.net/ReceiveSimsFromRetailersSubmit"

async def run_sim_return_task(serials: list, credentials: dict, bot, chat_id):
    """প্লে-রাইট সিম রিটার্ন মডিউল (সিম স্ট্যাটাস মডিউলের আদলে তৈরি)"""
    house_name = credentials.get('house_name', 'N/A')
    session_file = f"sessions/session_{credentials['user']}.json"

    async with async_playwright() as p:
        # ব্রাউজার লঞ্চ
        browser = await p.chromium.launch(headless=True)
        
        # সেশন লোড করা
        if os.path.exists(session_file):
            context = await browser.new_context(storage_state=session_file)
        else:
            context = await browser.new_context()
            
        page = await context.new_page()
        
        try:
            # ১. লগইন ভ্যালিডেশন
            if not await dms_login.is_session_valid(page):
                if not await dms_login.perform_login(page, credentials, session_file):
                    return "❌ DMS লগইন ব্যর্থ হয়েছে। ওটিপি চেক করুন।"

            # ২. স্মার্ট সার্চ - সিরিয়ালগুলোর বর্তমান অবস্থা যাচাই
            await page.goto(SMART_SEARCH_URL)
            await page.wait_for_selector("#SearchType", timeout=30000)
            
            await page.select_option("#SearchType", "1") # SIM Serial
            await page.fill("#SearchValue", "\n".join(serials))
            await page.click("button.btn-success")

            scanned_data, error = await get_smart_search_results(page)

            if error:
                return error # "Data not found" বা অন্য এরর থাকলে এখানেই শেষ
            
            # ৪. স্ক্র্যাপ করা ডাটা এনালাইসিস করে সামারি তৈরি
            summary_msg, grouped_return_data = process_return_summary(scanned_data, house_name)
            await bot.send_message(chat_id, summary_msg, parse_mode="Markdown")

            if not grouped_return_data:
                return "🏁 রিটার্নযোগ্য কোনো সিরিয়াল নেই। প্রসেস শেষ।"
            
            # ৪. সিম রিটার্ন সাবমিশন প্রসেস (Action Phase)
            await page.goto(RECEIVE_URL)            
            
            for retailer_code, sims in grouped_return_data.items():
                # তারিখ সেট (আজকের তারিখ)
                today = datetime.now().strftime('%Y-%m-%d')
                await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")

                # JS Chosen ড্রপডাউন হ্যান্ডলিং
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
                    await bot.send_message(chat_id, f"❌ এরর: `{retailer_code}` ড্রপডাউনে পাওয়া যায়নি।")
                    continue

                await asyncio.sleep(1)
                await page.fill("#SimList", "\n".join(sims))
                await page.click("#SaveBtn")

                # কনফার্মেশন মোডাল
                try:
                    await page.wait_for_selector("button.swal2-confirm", timeout=10000)
                    await page.click("button.swal2-confirm")
                    await bot.send_message(chat_id, f"✅ `{retailer_code}` এর {bn_num(len(sims))}টি সিম সফলভাবে রিটার্ন সম্পন্ন।")
                except:
                    await bot.send_message(chat_id, f"⚠️ `{retailer_code}` এর সাবমিশন কনফার্ম করা যায়নি।")

            # return "🏁 **সকল রিটার্ন প্রসেস সফলভাবে সম্পন্ন হয়েছে।**"

        except Exception as e:
            return f"❌ অটোমেশন এরর: {str(e)}"
        finally:
            await browser.close()

def process_return_summary(scanned_data, target_house):
    """সিম রিটার্ন এনালাইসিস সামারি জেনারেটর (স্ট্যাটাস মডিউলের স্টাইলে)"""
    active_map = {}   # Date -> List of strings
    issued_map = {}   # Retailer -> List of strings
    warehouse_list = []
    errors = []
    
    # এটি মূলত অটোমেশন সাবমিশনের জন্য ব্যবহৃত হবে
    grouped_return_data = {} # Retailer Code -> List of Serials

    for d in scanned_data:
        sim = d.get("SIM No", "").strip()
        house = d.get("Distributor", "N/A")
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", d.get("Mobile No", "N/A"))

        # ১. হাউজ ভ্যালিডেশন
        if target_house and target_house not in house:
            errors.append(f"❌ `{sim}`: এটি {house} হাউসের সিম।")
            continue

        # ২. এক্টিভ সিম চেক (রিটার্ন সম্ভব নয়)
        if act_date:
            if act_date not in active_map: active_map[act_date] = []
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🔴 {sim}\n📱 {clean_msisdn} (এক্টিভ)")

        # ৩. ইস্যু করা সিম চেক (এগুলোই রিটার্ন করা হবে)
        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
            
            # সাবমিশনের জন্য রিটেইলার কোড (R12345) এক্সট্রাক্ট করা
            match = re.search(r'R\d+', retailer)
            code = match.group(0) if match else retailer
            if code not in grouped_return_data: grouped_return_data[code] = []
            grouped_return_data[code].append(sim)

        # ৪. ওয়্যারহাউসে আছে এমন সিম (রিটার্ন প্রয়োজন নেই)
        else:
            warehouse_list.append(f"⚪ {sim} (ওয়্যারহাউসে আছে)")

    # --- মেসেজ ফরম্যাটিং ---
    final_output = ["📝 **সিম রিটার্ন এনালাইসিস রিপোর্ট:**\n"]

    # এক্টিভ সিম সেকশন (তারিখ অনুযায়ী)
    if active_map:
        for date, lines in active_map.items():
            final_output.append("\n".join(lines))
            final_output.append(f"📅 {date}\n")

    # ইস্যু করা সিম সেকশন (রিটেইলার অনুযায়ী) - এই অংশটিই রিটার্ন হবে
    if issued_map:
        if len(final_output) > 1: final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims))
            final_output.append(f"••••••••••••••••••••••\n🏪 {ret} (রিটার্ন করা হবে)\n")

    # রেডি সিম/ওয়্যারহাউস সেকশন
    if warehouse_list:
        final_output.append("\n".join(warehouse_list))

    # এরর সেকশন (অন্য হাউসের সিম)
    if errors:
        final_output.append("\n" + "\n".join(errors))

    return "\n".join(final_output), grouped_return_data