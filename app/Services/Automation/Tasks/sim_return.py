import asyncio
import re
import os
from datetime import datetime
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Core.session_manager import session_manager # নতুন ম্যানেজার ইম্পোর্ট ✅
from app.Utils.helpers import bn_num

# ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
RECEIVE_URL = "https://blkdms.banglalink.net/ReceiveSimsFromRetailersSubmit"

async def run_sim_return_task(serials: list, credentials: dict, bot, chat_id):
    """সেশন ম্যানেজার ব্যবহার করে সিম রিটার্ন অটোমেশন"""
    house_name = credentials.get('house_name', 'N/A')
    
    # ১. সেশন ম্যানেজার থেকে সরাসরি একটি সচল পেজ এবং কন্টেক্সট সংগ্রহ করা ✅
    # এটি নিজে থেকেই সেশন চেক করবে এবং প্রোফাইল থেকে ডাটা লোড করবে।
    page, context = await session_manager.get_valid_page(credentials)
    
    try:
        # ২. স্মার্ট সার্চ - সিরিয়ালগুলোর বর্তমান অবস্থা যাচাই
        logger_info(f"🔍 [SIM Return] {house_name} এর জন্য স্ট্যাটাস চেক শুরু...")
        await page.goto(SMART_SEARCH_URL, wait_until="commit", timeout=40000)
        await page.wait_for_selector("#SearchType", timeout=30000)
        
        await page.select_option("#SearchType", "1") # SIM Serial
        await page.fill("#SearchValue", "\n".join(serials))
        await page.click("button.btn-success")

        # ৩. সেন্ট্রাল স্ক্র্যাপার ব্যবহার করে রেজাল্ট সংগ্রহ ✅
        scanned_data, error = await get_smart_search_results(page)

        if error:
            return error # যেমন: Data not found বা অন্য এরর

        # ৪. স্ক্র্যাপ করা ডাটা এনালাইসিস করে সামারি তৈরি
        summary_msg, grouped_return_data = process_return_summary(scanned_data, house_name)
        
        # ইউজারকে এনালাইসিস রিপোর্ট পাঠানো
        await bot.send_message(chat_id, summary_msg, parse_mode="Markdown")

        if not grouped_return_data:
            return "🏁 রিটার্নযোগ্য (ইস্যু করা) কোনো সিরিয়াল পাওয়া যায়নি। প্রসেস শেষ।"

        # ৫. সিম রিটার্ন সাবমিশন প্রসেস (Action Phase)
        # প্রতিটি রিটেইলারের জন্য আলাদাভাবে সাবমিট করা হবে
        total_retailers = len(grouped_return_data)
        count = 1

        for retailer_code, sims in grouped_return_data.items():
            await page.goto(RECEIVE_URL, wait_until="networkidle", timeout=40000)
            
            # তারিখ সেট (আজকের তারিখ)
            today = datetime.now().strftime('%Y-%m-%d')
            await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")

            # JS Chosen ড্রপডাউন হ্যান্ডলিং (নিখুঁত সিলেকশন লজিক)
            js_select = f"""
                (code) => {{
                    let select = document.getElementById('Retailer');
                    if(!select) return false;
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
                await bot.send_message(chat_id, f"❌ এরর: `{retailer_code}` রিটেইলারটি ড্রপডাউনে পাওয়া যায়নি।")
                continue

            await asyncio.sleep(1.5) # ড্রপডাউন পরিবর্তনের পর বাফার
            await page.fill("#SimList", "\n".join(sims))
            await page.click("#SaveBtn")

            # ৬. সাকসেস কনফার্মেশন মোডাল (SweetAlert2)
            try:
                # মোডাল আসা পর্যন্ত সর্বোচ্চ ১০ সেকেন্ড অপেক্ষা
                await page.wait_for_selector("button.swal2-confirm", state="visible", timeout=10000)
                await page.click("button.swal2-confirm")
                
                status_text = f"✅ [{count}/{total_retailers}] `{retailer_code}` এর {bn_num(len(sims))}টি সিম রিটার্ন সফল।"
                await bot.send_message(chat_id, status_text)
            except:
                await bot.send_message(chat_id, f"⚠️ `{retailer_code}` এর সাবমিশন কনফার্মেশন পাওয়া যায়নি। অনুগ্রহ করে ডিএমএস চেক করুন।")
            
            count += 1
            await asyncio.sleep(1) # প্রতি সাবমিশনের মাঝে ছোট গ্যাপ

        return "🏁 **সিম রিটার্ন প্রসেস সফলভাবে সম্পন্ন হয়েছে।**"

    except Exception as e:
        import logging
        logging.error(f"❌ [Task Error] SIM Return: {str(e)}")
        return f"❌ অটোমেশন এরর: {str(e).replace('_', ' ')}"
    
    finally:
        # ৭. কাজ শেষে ট্যাব এবং কন্টেক্সট বন্ধ করা (ব্রাউজার ব্যাকগ্রাউন্ডে সচল থাকবে) ✅
        await page.close()

def process_return_summary(scanned_data, target_house):
    """রিটার্নযোগ্য সিম গ্রুপিং এবং রিপোর্ট জেনারেশন (অপরিবর্তিত)"""
    active_map = {}   
    issued_map = {}   
    warehouse_list = []
    errors = []
    grouped_return_data = {} 

    for d in scanned_data:
        sim = d.get("SIM No", "").strip()
        house = d.get("Distributor", "N/A")
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", "N/A")

        if target_house and target_house not in house:
            errors.append(f"❌ `{sim}`: এটি {house} হাউসের সিম।")
            continue

        if act_date:
            if act_date not in active_map: active_map[act_date] = []
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🔴 {sim}\n📱 {clean_msisdn} (এক্টিভ)")

        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
            
            # সাবমিশনের জন্য রিটেইলার কোড (R12345) আলাদা করা
            match = re.search(r'R\d+', retailer)
            code = match.group(0) if match else retailer
            if code not in grouped_return_data: grouped_return_data[code] = []
            grouped_return_data[code].append(sim)

        else:
            warehouse_list.append(f"⚪ {sim} (ওয়্যারহাউসে আছে)")

    # মেসেজ ফরম্যাটিং
    final_output = ["📝 **সিম রিটার্ন এনালাইসিস রিপোর্ট:**\n"]
    if active_map:
        for date, lines in active_map.items():
            final_output.append("\n".join(lines))
            final_output.append(f"📅 {date}\n")

    if issued_map:
        if len(final_output) > 1: final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims))
            final_output.append(f"••••••••••••••••••••••\n🏪 {ret} (রিটার্ন করা হবে)\n")

    if warehouse_list:
        final_output.append("\n".join(warehouse_list))

    if errors:
        final_output.append("\n" + "\n".join(errors))

    return "\n".join(final_output), grouped_return_data

def logger_info(msg):
    import logging
    logging.getLogger("app.Services.Automation.Tasks").info(msg)