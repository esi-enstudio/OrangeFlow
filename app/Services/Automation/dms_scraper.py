import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import Page

async def get_smart_search_results(page: Page):
    """
    DMS স্মার্ট সার্চ রিপোর্টের রেজাল্ট স্ক্র্যাপ করার গ্লোবাল ফাংশন।
    এটি Error, Card View এবং Table View (Pagination সহ) হ্যান্ডেল করে।
    রিটার্ন করে: (data_list, error_message)
    """
    results = []
    scanned_sims = set()

    try:
        # ১. ৩টি জিনিসের জন্য একসাথে অপেক্ষা করা (Card, Table, Error)
        try:
            await page.wait_for_selector(".card-body, #dataTable_Smart_Search_Report, #errorMessage", timeout=20000)
        except:
            return None, "⚠️ ডিএমএস থেকে রেসপন্স পেতে দেরি হচ্ছে বা কোনো ডাটা পাওয়া যায়নি।"

        # ২. শুরুতেই এরর মেসেজ (Data not found) চেক করা
        error_element = await page.query_selector("#errorMessage")
        if error_element:
            error_text = (await error_element.inner_text()).strip()
            if "Data not found" in error_text:
                return None, "⚠️ ডিএমএস থেকে জানানো হয়েছে: **ডাটা পাওয়া যায়নি (Data not found)**।"
            
            # যদি এটি পজিটিভ কনফার্মেশন হয় (Found/Success), তবে এটিকে এরর হিসেবে ধরবো না
            elif "Sim Details Information Found By Sim Serial" in error_text or "successfully" in error_text.lower():
                # এটি কোনো এরর নয়, তাই প্রসেস চালিয়ে যাবে
                pass

            # অন্য কোনো আননোন এরর থাকলে সেটি দেখাবে
            elif error_text:
                return None, f"❌ ডিএমএস এরর: {error_text}"

        # ৩. যদি এরর না থাকে, তবে ডাটা স্ক্র্যাপিং লুপ শুরু
        while True:
            soup = BeautifulSoup(await page.content(), 'html.parser')

            # --- কেস ১: সিঙ্গেল কার্ড ভিউ (Single Result) ---
            single_card = soup.find("h3", string=lambda x: x and "Sim Information" in x)
            if single_card:
                data = {}
                card_div = single_card.find_parent("div", class_="card-body")
                if card_div:
                    table = card_div.find("table")
                    if table:
                        for tr in table.find_all("tr"):
                            ths, tds = tr.find_all("th"), tr.find_all("td")
                            for i in range(len(ths)):
                                key = ths[i].get_text(strip=True).replace(":", "")
                                data[key] = tds[i].get_text(strip=True)
                        
                        sim = data.get("SIM No", "").strip()
                        if sim and sim not in scanned_sims:
                            scanned_sims.add(sim)
                            # MSISDN কী ইউনিফর্ম করা
                            data['MSISDN'] = data.get("MSISDN", data.get("Mobile No", "N/A"))
                            results.append(data)
                break # কার্ড ভিউতে পেজিনেশন থাকে না

            # --- কেস ২: টেবিল ভিউ (Multiple Results) ---
            multi_table = soup.find("table", id="dataTable_Smart_Search_Report")
            if multi_table:
                rows = multi_table.find("tbody").find_all("tr")
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) < 10 or "No data" in cols[0].text: continue
                    
                    sim = cols[0].text.strip().replace("'", "")
                    if sim not in scanned_sims:
                        scanned_sims.add(sim)
                        results.append({
                            "SIM No": sim,
                            "Distributor": cols[1].text.strip(),
                            "Retailer": cols[2].text.strip(),
                            "Activation Date": cols[8].text.strip(),
                            "MSISDN": cols[9].text.strip()
                        })

            # --- ৪. পেজিনেশন (Next Button) হ্যান্ডেল করা ---
            next_btn = await page.query_selector("#dataTable_Smart_Search_Report_next")
            if next_btn:
                btn_class = await next_btn.get_attribute("class") or ""
                if "disabled" not in btn_class:
                    await next_btn.click()
                    await asyncio.sleep(2) # ডাটা রেন্ডার হওয়ার সময়
                    continue # লুপের শুরুতে গিয়ে পরবর্তী পেজ স্ক্র্যাপ করবে
            
            break # আর পেজ না থাকলে লুপ থেকে বের হবে

        return results, None

    except Exception as e:
        return None, f"❌ স্ক্র্যাপিং এরর: {str(e)}"