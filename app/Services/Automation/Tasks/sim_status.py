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
                                results.append(format_sim_data(data, house_name))
                    break

                # --- কেস ২: টেবিল ভিউ ---
                multi_table = soup.find("table", id="dataTable_Smart_Search_Report")
                if multi_table:
                    rows = multi_table.find("tbody").find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) < 9 or "No data" in cols[0].text: continue
                        
                        sim = cols[0].text.strip().replace("'", "")
                        if sim in scanned_sims: continue
                        
                        scanned_sims.add(sim)
                        temp_data = {
                            "SIM No": sim,
                            "Distributor": cols[1].text.strip(),
                            "Retailer": cols[2].text.strip(),
                            "Activation Date": cols[8].text.strip(),
                            "Activation Status": "Active" if cols[8].text.strip() else ""
                        }
                        results.append(format_sim_data(temp_data, house_name))

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

    return "\n\n".join(results) if results else "⚠️ কোনো তথ্য পাওয়া যায়নি।"

def format_sim_data(data: dict, target_house: str):
    """মেসেজ ফরম্যাটিং লজিক"""
    sim = data.get("SIM No", "").strip()
    house = data.get("Distributor", "N/A")
    ret = data.get("Retailer", "").strip()
    act_date = data.get("Activation Date", "").strip()
    status = data.get("Activation Status", "").strip()

    if target_house and target_house not in house:
        return f"❌ `{sim}`: এটি {house} হাউসের সিম। আপনার হাউস {target_house}-এ এটি প্রসেস করা সম্ভব নয়।"
    
    if status == "Active" or act_date:
        return f"❌ `{sim}`: একটিভ।\n👤 রিটেইলার: {ret}\n🏠 হাউস: {house}\n📅 তারিখ: {act_date}"
    elif ret and ret != "" and "Select" not in ret:
        return f"⚠️ `{sim}`: ইস্যু করা আছে।\n👤 রিটেইলার: {ret}\n🏠 হাউস: {house}"
    else:
        return f"✅ `{sim}`: ইস্যু করার জন্য প্রস্তুত।\n🏠 হাউস: {house}"