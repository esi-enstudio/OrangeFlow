import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from app.Core.login_manager import dms_login
import os

# ইউআরএল
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"

async def run_sim_status_check(serials: list, credentials: dict):
    """প্লে-রাইট ভিত্তিক সিম স্ট্যাটাস চেক টাস্ক (ডাইনামিক ক্রেডেনশিয়ালসহ)"""
    results = []
    scanned_sims = set()
    house_name = credentials.get('house_name', 'N/A')
    
    # প্রতিটি হাউসের জন্য আলাদা সেশন ফাইল পাথ (যাতে কনফ্লিক্ট না হয়)
    # যেমন: sessions/session_MYMVAI01.json
    session_file = f"sessions/session_{credentials['user']}.json"

    async with async_playwright() as p:

        # ব্রাউজার লঞ্চ করা
        browser = await p.chromium.launch(headless=False) # Headless=True প্রডাকশনের জন্য

        # সেশন ফাইল থাকলে সেটি কন্টেক্সটে লোড করা
        if os.path.exists(session_file):
            context = await browser.new_context(storage_state=session_file)
        else:
            context = await browser.new_context()
            
        page = await context.new_page()
        
        try:
            # print("DEBUG: Checking session validity...")

            if not await dms_login.is_session_valid(page):
                # print("DEBUG: Performing Login process...")
                if not await dms_login.perform_login(page, credentials, session_file):
                    return "❌ লগইন ব্যর্থ হয়েছে। ওটিপি চেক করুন।"


            # লগইন শেষে স্মার্ট সার্চ পেজে যাওয়া
            # print("DEBUG: Navigating to Smart Search...")
            await page.goto(SMART_SEARCH_URL) 

            # পেজ লোড নিশ্চিত করতে একটি এলিমেন্টের জন্য অপেক্ষা
            await page.wait_for_selector("#SearchType", timeout=30000)
            
            # print("DEBUG: Filling serials and submitting...")

            # সার্চ টাইপ 'SIM Serial' (Value: 1) সিলেক্ট করা
            await page.select_option("#SearchType", "1")
            
            # সিরিয়ালগুলো ইনপুট দেওয়া
            await page.fill("#SearchValue", "\n".join(serials))
            
            # সার্চ বাটনে ক্লিক
            await page.click("button.btn-success")
            
            # ৩. রেজাল্ট আসার জন্য অপেক্ষা করা
            try:
                # print("DEBUG: Waiting for results...")
                await page.wait_for_selector(".card-body, #dataTable_Smart_Search_Report", timeout=20000)
            except:
                return "⚠️ সার্চ রেজাল্ট লোড হতে অনেক সময় নিচ্ছে অথবা কোনো ডাটা পাওয়া যায়নি।"
            
            while True:
                soup = BeautifulSoup(await page.content(), 'html.parser')
                
                # --- কেস ১: সিঙ্গেল কার্ড ভিউ ---
                single_card = soup.find("h3", string=lambda x: x and "Sim Information" in x)
                if single_card:
                    data = {}
                    card_div = single_card.find_parent("div", class_="card-body")
                    if card_div:
                        table = card_div.find("table")
                        if table:
                            for tr in table.find_all("tr"):
                                ths = tr.find_all("th")
                                tds = tr.find_all("td")
                                for i in range(len(ths)):
                                    key = ths[i].get_text(strip=True).replace(":", "")
                                    data[key] = tds[i].get_text(strip=True)
                            
                            sim = data.get("SIM No", "").strip()
                            if sim and sim not in scanned_sims:
                                scanned_sims.add(sim)
                                # আমরা পুরো ডিকশনারিটি জমা রাখবো প্রসেসিং এর জন্য
                                data['MSISDN'] = data.get("MSISDN", data.get("Mobile No", "N/A"))
                                results.append(data)
                                # results.append(format_sim_data(data, house_name))
                    break

                # --- কেস ২: টেবিল ভিউ ---
                multi_table = soup.find("table", id="dataTable_Smart_Search_Report")
                if multi_table:
                    rows = multi_table.find("tbody").find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) < 10 or "No data" in cols[0].text: continue
                        
                        sim = cols[0].text.strip().replace("'", "")
                        
                        if sim not in scanned_sims:
                            scanned_sims.add(sim)
                            temp_data = {
                                "SIM No": sim,
                                "Distributor": cols[1].text.strip(),
                                "Retailer": cols[2].text.strip(),
                                "Activation Date": cols[8].text.strip(),
                                "MSISDN": cols[9].text.strip() # MSISDN এখন ৯ নম্বর ইনডেক্সে
                            }
                            results.append(temp_data)

                # --- পেজিনেশন চেক করা ---
                next_btn = await page.query_selector("#dataTable_Smart_Search_Report_next")
                if next_btn and "disabled" not in (await next_btn.get_attribute("class") or ""):
                    await next_btn.click()
                    await asyncio.sleep(2)
                else:
                    break

        except Exception as e:
            print(f"CRITICAL DEBUG: {str(e)}")
            return f"❌ অটোমেশন এরর: {str(e)}"
        
        finally:
            await browser.close()

    # return "\n\n".join(results) if results else "⚠️ কোনো তথ্য পাওয়া যায়নি।"
    return generate_sim_summary(results, house_name)

def generate_sim_summary(all_data, target_house):
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

        # হাউজ চেক
        if target_house and target_house not in house:
            errors.append(f"❌ `{sim}`: এটি {house} হাউসের সিম।")
            continue

        if act_date: # ১. এক্টিভ সিম (🟢)
            if act_date not in active_map: active_map[act_date] = []
            # নাম্বার যদি ১০ ডিজিট হয় তবে সামনে ০ যোগ করা
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🟢 {sim}\n📱 {clean_msisdn}")
            
        elif retailer and retailer.strip(): # ২. ইস্যু করা (🟡)
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
            
        else: # ৩. ইস্যু হয় নাই (⚪)
            ready_list.append(f"⚪ {sim}")

    # --- মেসেজ ফরম্যাটিং ---
    final_output = []

    # এক্টিভ সিম সেকশন (তারিখ অনুযায়ী)
    for date, lines in active_map.items():
        final_output.append("\n".join(lines))
        final_output.append(f"📅 {date}\n")

    # ইস্যু করা সিম সেকশন (রিটেইলার অনুযায়ী)
    if issued_map:
        if final_output: final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims))
            final_output.append(f"••••••••••••••••••••••\n🏪 {ret}\n")

    # রেডি সিম সেকশন
    if ready_list:
        if final_output: final_output.append("")
        final_output.append("\n".join(ready_list))

    # এরর সেকশন
    if errors:
        final_output.append("\n" + "\n".join(errors))

    return "\n".join(final_output) if final_output else "⚠️ কোনো তথ্য পাওয়া যায়নি।"