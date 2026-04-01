import asyncio
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from app.Core.login_manager import dms_login

# ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
RECEIVE_URL = "https://blkdms.banglalink.net/ReceiveSimsFromRetailersSubmit"

async def run_sim_return_task(serials: list, credentials: dict, bot, chat_id):
    """প্লে-রাইট সিম রিটার্ন মডিউল (সিম স্ট্যাটাস মডিউলের আদলে তৈরি)"""
    scanned_data = []
    scanned_sims = set()
    house_name = credentials.get('house_name', 'N/A')
    session_file = f"sessions/session_{credentials['user']}.json"

    async with async_playwright() as p:
        # ব্রাউজার লঞ্চ
        browser = await p.chromium.launch(headless=False)
        
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
                    return "❌ লগইন ব্যর্থ হয়েছে। ওটিপি চেক করুন।"

            # ২. স্মার্ট সার্চ - সিরিয়ালগুলোর বর্তমান অবস্থা যাচাই
            await page.goto(SMART_SEARCH_URL)
            await page.wait_for_selector("#SearchType", timeout=30000)
            
            await page.select_option("#SearchType", "1") # SIM Serial
            await page.fill("#SearchValue", "\n".join(serials))
            await page.click("button.btn-success")
            
            await page.wait_for_selector(".card-body, #dataTable_Smart_Search_Report", timeout=20000)
            
            # ডেটা স্ক্র্যাপিং লুপ (স্ট্যাটাস মডিউলের মতো)
            while True:
                soup = BeautifulSoup(await page.content(), 'html.parser')
                
                # --- কার্ড ভিউ ---
                single_card = soup.find("h3", string=lambda x: x and "Sim Information" in x)
                if single_card:
                    data = {}
                    table = single_card.find_parent("div", class_="card-body").find("table")
                    if table:
                        for tr in table.find_all("tr"):
                            ths, tds = tr.find_all("th"), tr.find_all("td")
                            for i in range(len(ths)):
                                key = ths[i].get_text(strip=True).replace(":", "")
                                data[key] = tds[i].get_text(strip=True)
                        
                        sim = data.get("SIM No", "").strip()
                        if sim and sim not in scanned_sims:
                            scanned_sims.add(sim)
                            scanned_data.append(data)
                    break

                # --- টেবিল ভিউ ---
                multi_table = soup.find("table", id="dataTable_Smart_Search_Report")
                if multi_table:
                    rows = multi_table.find("tbody").find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) < 9 or "No data" in cols[0].text: continue
                        sim = cols[0].text.strip().replace("o", "").replace("'", "")
                        if sim not in scanned_sims:
                            scanned_sims.add(sim)
                            scanned_data.append({
                                "SIM No": sim,
                                "Distributor": cols[1].text.strip(),
                                "Retailer": cols[2].text.strip(),
                                "Activation Date": cols[8].text.strip()
                            })

                # পেজিনেশন
                next_btn = await page.query_selector("#dataTable_Smart_Search_Report_next")
                if next_btn and "disabled" not in (await next_btn.get_attribute("class") or ""):
                    await next_btn.click()
                    await asyncio.sleep(2)
                else:
                    break

            # ৩. স্ক্র্যাপ করা ডেটা এনালাইসিস এবং সামারি পাঠানো
            if not scanned_data:
                return "⚠️ কোনো সিরিয়ালের তথ্য পাওয়া যায়নি।"

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
                    await bot.send_message(chat_id, f"✅ `{retailer_code}` এর {len(sims)}টি সিম সফলভাবে রিটার্ন সম্পন্ন।")
                except:
                    await bot.send_message(chat_id, f"⚠️ `{retailer_code}` এর সাবমিশন কনফার্ম করা যায়নি।")

            return "🏁 **সকল রিটার্ন প্রসেস সফলভাবে সম্পন্ন হয়েছে।**"

        except Exception as e:
            return f"❌ অটোমেশন এরর: {str(e)}"
        finally:
            await browser.close()

def process_return_summary(scanned_data, target_house):
    """রিটার্নযোগ্য সিমগুলোকে রিটেইলার কোড অনুযায়ী গ্রুপ করে এবং সামারি মেসেজ তৈরি করে"""
    grouped_data = {} # Retailer Code -> List of SIMs
    output_lines = ["📝 **রিটার্ন প্রসেস এনালাইসিস:**\n"]
    
    for d in scanned_data:
        sim = d.get("SIM No", "")
        house = d.get("Distributor", "")
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")

        # হাউজ ভ্যালিডেশন
        if target_house and target_house not in house:
            output_lines.append(f"❌ `{sim}`: এটি {house} হাউসের সিম।")
            continue

        if act_date:
            output_lines.append(f"❌ `{sim}`: একটিভ। (রিটার্ন সম্ভব নয়)")
        elif retailer and "Select" not in retailer and retailer.strip():
            # রিটেইলার কোড এক্সট্রাক্ট করা (R12345)
            match = re.search(r'R\d+', retailer)
            code = match.group(0) if match else retailer
            
            if code not in grouped_data: grouped_data[code] = []
            grouped_data[code].append(sim)
            output_lines.append(f"⚠️ `{sim}`: ইস্যু করা আছে। (রিটার্ন করা হবে)")
        else:
            output_lines.append(f"✅ `{sim}`: ওয়্যারহাউসে আছে। (রিটার্ন প্রয়োজন নেই)")

    return "\n".join(output_lines), grouped_data