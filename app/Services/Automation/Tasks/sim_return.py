import asyncio
import re
import os
import logging
from datetime import datetime
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Core.session_manager import session_manager
from app.Utils.helpers import bn_num

# লগিং কনফিগারেশন
logger = logging.getLogger("app.Services.Automation.Tasks")

# ডিএমএস ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
RECEIVE_URL = "https://blkdms.banglalink.net/ReceiveSimsFromRetailersSubmit"

async def run_sim_return_task(serials: list, credentials: dict, bot, chat_id):
    """
    সেশন ম্যানেজার ব্যবহার করে সিম রিটার্ন অটোমেশন।
    এটি প্রথমে সিমগুলোর স্ট্যাটাস চেক করে এবং পরে রিটেইলার অনুযায়ী সাবমিট করে।
    """
    house_name = credentials.get('house_name', 'N/A')
    
    # ১. সেশন ম্যানেজার থেকে সচল ব্রাউজার পেজ এবং কন্টেক্সট নেওয়া
    logger.info(f"🚀 [{house_name}] সিম রিটার্ন প্রসেস শুরু হচ্ছে...")
    try:
        page, context = await session_manager.get_valid_page(credentials)
    except Exception as e:
        logger.error(f"❌ সেশন তৈরি করতে ব্যর্থ: {e}")
        return f"❌ এরর: {str(e)}"
    
    try:
        # ২. স্মার্ট সার্চ পেজে নেভিগেট করা
        logger.info(f"🌐 [{house_name}] স্মার্ট সার্চ রিপোর্টে যাওয়া হচ্ছে...")
        await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        
        # ৩. সার্চ ফরম পূরণ করা (সিম সিরিয়াল অপশন সিলেক্ট)
        await page.wait_for_selector("#SearchType", timeout=30000)
        await page.select_option("#SearchType", "1") 
        await page.fill("#SearchValue", "\n".join(serials))
        
        # ৪. সার্চ বাটনে ক্লিক এবং রেজাল্টের অপেক্ষা
        await page.click("button.btn-success")
        logger.info(f"📡 সার্চ সাবমিট করা হয়েছে, ডাটা স্ক্র্যাপ করা হচ্ছে...")

        # ৫. সেন্ট্রাল স্ক্র্যাপার (dms_scraper.py) কল করা
        scanned_data, error = await get_smart_search_results(page)

        if error:
            logger.error(f"❌ ডিএমএস স্ক্র্যাপিং এরর: {error}")
            return error 

        # ৬. স্ক্র্যাপ করা ডাটা এনালাইসিস করে রিপোর্ট এবং গ্রুপিং তৈরি করা
        summary_msg, grouped_return_data = process_return_summary(scanned_data, credentials)
        
        # ইউজারকে টেলিগ্রামে এনালাইসিস সামারি পাঠানো (HTML মোডে)
        await bot.send_message(chat_id, summary_msg, parse_mode="HTML")

        # যদি কোনো সিম রিটার্ন করার যোগ্য না থাকে
        if not grouped_return_data:
            logger.info("🏁 কোনো রিটার্নযোগ্য (ইস্যু করা) সিম পাওয়া যায়নি।")
            return "🏁 <b>রিটার্নযোগ্য কোনো সিরিয়াল পাওয়া যায়নি। প্রসেস শেষ।</b>"

        # ৭. রিটেইলার ভিত্তিক সাবমিশন শুরু (অ্যাকশন ফেজ)
        total_retailers = len(grouped_return_data)
        logger.info(f"🛠 মোট {bn_num(total_retailers)}টি রিটেইলারের জন্য সাবমিশন শুরু হচ্ছে...")
        
        count = 1
        for retailer_code, sims in grouped_return_data.items():
            logger.info(f"🔄 [{bn_num(count)}/{bn_num(total_retailers)}] রিটেইলার `{retailer_code}` প্রসেস হচ্ছে...")
            
            # রিটার্ন সাবমিশন পেজে যাওয়া
            await page.goto(RECEIVE_URL, wait_until="domcontentloaded", timeout=60000)
            
            # ৮. রিটেইলার ড্রপডাউন নিশ্চিত করা (Attached স্টেট ব্যবহার করা হয়েছে কারণ এটি লুকানো থাকে)
            try:
                await page.wait_for_selector("#Retailer", state="attached", timeout=30000)
            except:
                logger.error(f"❌ ড্রপডাউন পাওয়া যায়নি রিটেইলার: {retailer_code}")
                await bot.send_message(chat_id, f"❌ এরর: <b>{retailer_code}</b> এর জন্য ড্রপডাউন লোড হয়নি।")
                continue

            # ৯. তারিখ ইনপুট (আজকের তারিখ)
            today = datetime.now().strftime('%Y-%m-%d')
            await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")

            # ১০. জাভাস্ক্রিপ্টের মাধ্যমে 'Chosen' ড্রপডাউন থেকে রিটেইলার সিলেক্ট করা
            js_select = """
                (code) => {
                    let select = document.getElementById('Retailer');
                    if(!select) return false;
                    for (let i = 0; i < select.options.length; i++) {
                        if (select.options[i].text.includes(code)) {
                            select.selectedIndex = i;
                            if(window.jQuery) {
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
                logger.warning(f"⚠️ রিটেইলার {retailer_code} ড্রপডাউনে নেই।")
                await bot.send_message(chat_id, f"⚠️ রিটেইলার কোড <code>{retailer_code}</code> ড্রপডাউনে পাওয়া যায়নি।")
                continue

            # ১১. সিম সিরিয়াল ইনপুট এবং সেভ বাটনে ক্লিক
            await asyncio.sleep(1.5) # সিলেকশন প্রসেস হওয়ার বিরতি
            await page.fill("#SimList", "\n".join(sims), force=True) 
            await page.click("#SaveBtn")
            logger.info(f"💾 {retailer_code} এর জন্য সাবমিট বাটনে ক্লিক করা হয়েছে।")

            # ১২. SweetAlert2 কনফার্মেশন মোডাল হ্যান্ডলিং
            try:
                confirm_btn = "button.swal2-confirm"
                await page.wait_for_selector(confirm_btn, state="visible", timeout=15000)
                await page.click(confirm_btn)
                
                logger.info(f"✅ {retailer_code} রিটার্ন সফল।")
                status_text = f"✅ [{bn_num(count)}/{bn_num(total_retailers)}] <b>{retailer_code}</b> এর {bn_num(len(sims))}টি সিম রিটার্ন সফল।"
                await bot.send_message(chat_id, status_text, parse_mode="HTML")
            except:
                logger.warning(f"⚠️ {retailer_code} এর কনফার্মেশন মোডাল আসেনি।")
                await bot.send_message(chat_id, f"⚠️ <b>{retailer_code}</b> এর রিটার্ন কনফার্মেশন পাওয়া যায়নি। ডিএমএস চেক করুন।")
            
            count += 1
            await asyncio.sleep(2) # সার্ভার লোড ব্যালেন্স করতে বিরতি

        logger.info(f"🏁 [{house_name}] সকল কাজ সফলভাবে সম্পন্ন।")
        return "🏁 <b>সিম রিটার্ন প্রসেস সফলভাবে সম্পন্ন হয়েছে।</b>"

    except Exception as e:
        logger.error(f"💥 ক্রিকাল এরর: {str(e)}", exc_info=True)
        return f"❌ অটোমেশন এরর: {str(e).replace('_', ' ')}"
    
    finally:
        # ১৩. কাজ শেষে পেজ এবং সেশন কন্টেক্সট বন্ধ করা (মেমোরি সেভ করার জন্য)
        if page: await page.close()
        if context: await context.close()
        logger.info(f"🚪 [{house_name}] টাস্ক সেশন ক্লোজ করা হয়েছে।")


def process_return_summary(scanned_data, credentials):
    """হাউজ কোড দিয়ে রিটার্নযোগ্য সিম ফিল্টারিং ✅"""
    active_map, issued_map = {}, {}
    warehouse_list, errors = [], []
    grouped_return_data = {} 

    # টার্গেট হাউজ কোড
    target_code = str(credentials.get('code', '')).strip().upper() 
    target_name = credentials.get('house_name', 'N/A')

    for d in scanned_data:
        sim = d.get("SIM No", "").strip().replace("'", "")
        dms_distro = str(d.get("Distributor", "")).strip().upper() 
        
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
            active_map[act_date].append(f"🔴 {sim} | 📱 {clean_msisdn} (এক্টিভ)")

        elif retailer and retailer.strip() and "Select" not in retailer:
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
            
            match = re.search(r'R\d+', retailer)
            code = match.group(0) if match else retailer
            if code not in grouped_return_data: grouped_return_data[code] = []
            grouped_return_data[code].append(sim)
        else:
            warehouse_list.append(f"⚪ {sim} (ওয়্যারহাউসে আছে)")

    # ২. রিপোর্ট টেক্সট ফরম্যাটিং (HTML)
    output = [f"📊 <b>সিম রিটার্ন এনালাইসিস রিপোর্ট</b>", f"🏢 হাউজ: <b>{target_name}</b>\n"]

    if active_map:
        for date, lines in active_map.items():
            output.append("\n".join(lines) + f"\n📅 {date}\n")

    if issued_map:
        if len(output) > 2: output.append("----------------------------")
        for ret, sims in issued_map.items():
            output.append("\n".join(sims) + f"\n••••••••••••••••••••••\n🏪 {ret} (রিটার্ন হবে)\n")

    if warehouse_list: output.append("\n".join(warehouse_list))
    if errors: output.append("\n" + "\n".join(errors))

    return "\n".join(output), grouped_return_data