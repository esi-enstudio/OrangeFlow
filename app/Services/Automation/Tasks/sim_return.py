import asyncio
import re
import logging
from datetime import datetime
from app.Services.Automation.dms_scraper import get_smart_search_results
from app.Core.session_manager import session_manager # সেশন ম্যানেজার ব্যবহার করা হয়েছে ✅
from app.Utils.helpers import bn_num

# লগিং সেটআপ
logger = logging.getLogger("app.Services.Automation.Tasks")

# ইউআরএল সমূহ
SMART_SEARCH_URL = "https://blkdms.banglalink.net/SmartSearchReport"
RECEIVE_URL = "https://blkdms.banglalink.net/ReceiveSimsFromRetailersSubmit"

async def run_sim_return_task(serials: list, credentials: dict, bot, chat_id):
    """সেশন ম্যানেজার ব্যবহার করে সিম রিটার্ন অটোমেশন"""
    house_name = credentials.get('house_name', 'N/A')
    
    # ১. সেশন ম্যানেজার থেকে সচল পেজ সংগ্রহ (এটি অটো-লগইন হ্যান্ডেল করবে)
    logger.info(f"🚀 [{house_name}] সিম রিটার্ন টাস্ক শুরু হচ্ছে...")
    try:
        page, context = await session_manager.get_valid_page(credentials)
    except Exception as e:
        logger.error(f"❌ সেশন পেতে ব্যর্থ: {e}")
        return f"❌ ডিএমএস সেশন তৈরি করা সম্ভব হয়নি: {str(e)}"
    
    try:
        # ২. স্মার্ট সার্চ - সিরিয়ালগুলোর বর্তমান অবস্থা যাচাই
        logger.info(f"🔍 [{house_name}] স্মার্ট সার্চ রিপোর্টে স্ট্যাটাস চেক করা হচ্ছে...")
        await page.goto(SMART_SEARCH_URL, wait_until="commit", timeout=60000)
        await page.wait_for_selector("#SearchType", timeout=30000)
        
        await page.select_option("#SearchType", "1") # SIM Serial
        await page.fill("#SearchValue", "\n".join(serials))
        await page.click("button.btn-success")
        logger.info(f"📡 সার্চ সাবমিট করা হয়েছে, রেজাল্টের অপেক্ষা করছি...")

        # ৩. সেন্ট্রাল স্ক্র্যাপার ব্যবহার করে রেজাল্ট সংগ্রহ
        scanned_data, error = await get_smart_search_results(page)

        if error:
            logger.error(f"❌ স্ক্র্যাপিং এরর: {error}")
            return error 

        # ৪. স্ক্র্যাপ করা ডাটা এনালাইসিস করে সামারি তৈরি
        summary_msg, grouped_return_data = process_return_summary(scanned_data, credentials)
        
        # ইউজারকে টেলিগ্রামে এনালাইসিস রিপোর্ট পাঠানো
        await bot.send_message(chat_id, summary_msg, parse_mode="Markdown")

        if not grouped_return_data:
            logger.info("🏁 কোনো রিটার্নযোগ্য সিরিয়াল পাওয়া যায়নি।")
            return "🏁 রিটার্নযোগ্য (ইস্যু করা) কোনো সিরিয়াল পাওয়া যায়নি। প্রসেস শেষ।"

        # ৫. সিম রিটার্ন সাবমিশন প্রসেস (Action Phase)
        total_retailers = len(grouped_return_data)
        logger.info(f"🛠 মোট {bn_num(total_retailers)}টি রিটেইলারের সাবমিশন শুরু হচ্ছে...")
        
        count = 1
        for retailer_code, sims in grouped_return_data.items():
            logger.info(f"🔄 [{bn_num(count)}/{bn_num(total_retailers)}] রিটেইলার `{retailer_code}` এর কাজ চলছে...")
            
            # ১. রিটার্ন পেজে যাওয়া
            await page.goto(RECEIVE_URL, wait_until="domcontentloaded", timeout=60000)
            
            # ২. পরিবর্তন: দৃশ্যমান (visible) হওয়ার বদলে শুধু যুক্ত (attached) হওয়ার অপেক্ষা করা ✅
            try:
                await page.wait_for_selector("#Retailer", state="attached", timeout=30000)
                logger.info(f"✅ রিটার্ন পেজ এবং রিটেইলার ড্রপডাউন পাওয়া গেছে।")
            except Exception as e:
                logger.error(f"❌ ড্রপডাউন পাওয়া যায়নি: {str(e)}")
                await bot.send_message(chat_id, f"❌ এরর: `{retailer_code}` এর জন্য পেজ লোড হচ্ছে না।")
                continue

            # ৩. তারিখ সেট করা
            today = datetime.now().strftime('%Y-%m-%d')
            await page.evaluate(f"document.getElementById('IssueDate').value = '{today}';")

            # ৪. JS এর মাধ্যমে রিটেইলার সিলেক্ট (এটি লুকানো এলিমেন্টেও কাজ করে)
            js_select = """
                (code) => {
                    let select = document.getElementById('Retailer');
                    if(!select) return false;
                    
                    let found = false;
                    for (let i = 0; i < select.options.length; i++) {
                        if (select.options[i].text.includes(code)) {
                            select.selectedIndex = i;
                            found = true;
                            break;
                        }
                    }
                    
                    if(found) {
                        // অরিজিনাল এলিমেন্টটি লুকানো থাকলেও ইভেন্ট ট্রিগার করলে কাজ হবে
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        if(window.jQuery) {
                            window.jQuery(select).trigger('chosen:updated').change();
                        }
                        return true;
                    }
                    return false;
                }
            """
            
            selection_success = await page.evaluate(js_select, retailer_code)
            if not selection_success:
                logger.error(f"❌ রিটেইলার `{retailer_code}` ড্রপডাউনে পাওয়া যায়নি!")
                await bot.send_message(chat_id, f"❌ এরর: `{retailer_code}` ড্রপডাউনে নেই।")
                continue

            # ৫. সিম লিস্ট ইনপুট
            await asyncio.sleep(1.5) # ড্রপডাউন সিলেকশন প্রসেস হওয়ার জন্য বিরতি
            
            # সিম লিস্ট বক্সটিও অনেক সময় লুকানো থাকতে পারে, তাই 'force=True' ব্যবহার করা নিরাপদ
            await page.fill("#SimList", "\n".join(sims), force=True) 
            
            # ৬. সেভ বাটনে ক্লিক (বাটনটি সাধারণত দৃশ্যমান থাকে)
            await page.wait_for_selector("#SaveBtn", state="visible", timeout=10000)
            await page.click("#SaveBtn")
            logger.info(f"💾 সাবমিট করা হয়েছে। কনফার্মেশন মোডালের অপেক্ষা...")

            # ৯. সাকসেস কনফার্মেশন মোডাল (SweetAlert2)
            try:
                # মোডাল বাটন আসা পর্যন্ত ১৫ সেকেন্ড অপেক্ষা
                confirm_btn = "button.swal2-confirm"
                await page.wait_for_selector(confirm_btn, state="visible", timeout=15000)
                await page.click(confirm_btn)
                
                logger.info(f"✅ `{retailer_code}` রিটার্ন সফল।")
                status_text = f"✅ [{count}/{total_retailers}] `{retailer_code}` এর {bn_num(len(sims))}টি সিম রিটার্ন সফল।"
                await bot.send_message(chat_id, status_text)
            except Exception as e:
                logger.warning(f"⚠️ `{retailer_code}` এর জন্য সাকসেস মোডাল পাওয়া যায়নি।")
                await bot.send_message(chat_id, f"⚠️ `{retailer_code}` এর কনফার্মেশন পাওয়া যায়নি। ডিএমএস চেক করুন।")
            
            count += 1
            await asyncio.sleep(2) # সার্ভার লোড কমাতে বিরতি

        logger.info(f"🏁 [{house_name}] সিম রিটার্ন প্রসেস সম্পন্ন।")
        return "🏁 **সিম রিটার্ন প্রসেস সফলভাবে সম্পন্ন হয়েছে।**"

    except Exception as e:
        logger.error(f"💥 ক্রিকাল এরর: {str(e)}", exc_info=True)
        return f"❌ অটোমেশন এরর: {str(e).replace('_', ' ')}"
    
    finally:
        if page:
            await page.close()
        if context:
            await context.close() # ✅ এটি এখন অবশ্যই করতে হবে
        logger.info(f"🚪 [{house_name}] টাস্ক ক্লিনআপ সম্পন্ন।")


def process_return_summary(scanned_data, credentials):
    """
    হাউজ কোড (RYZBRB01) ব্যবহার করে নিখুঁত ভ্যালিডেশন এবং 
    রিটার্নযোগ্য সিম গ্রুপিং লজিক।
    """
    import re
    
    active_map = {}   # এক্টিভ সিম (তারিখ অনুযায়ী)
    issued_map = {}   # ইস্যু করা সিম (রিটেইলার অনুযায়ী)
    warehouse_list = [] # ওয়্যারহাউসে থাকা সিম
    errors = []       # অন্য হাউজের সিম
    grouped_return_data = {} # অটোমেশন সাবমিশনের জন্য ডাটা

    # ১. ডাটাবেজ থেকে আমাদের হাউজ কোড এবং নাম সংগ্রহ ✅
    target_code = str(credentials.get('code', '')).strip().upper() 
    target_name = credentials.get('house_name', 'N/A')

    for d in scanned_data:
        sim = d.get("SIM No", "").strip()
        # ডিএমএস থেকে পাওয়া হাউজ তথ্য (উদা: RYZBRB01-M/S Patwary Telecom)
        dms_house_info = str(d.get("Distributor", "")).strip().upper() 
        retailer = d.get("Retailer", "")
        act_date = d.get("Activation Date", "")
        msisdn = d.get("MSISDN", d.get("Mobile No", "N/A"))

        # ২. শক্তিশালী হাউজ ভ্যালিডেশন (কোড দিয়ে চেক) ✅
        # এটি চেক করবে RYZBRB01 শব্দটি ডিএমএস এর ডিস্ট্রিবিউটর নামের ভেতর আছে কিনা
        if target_code not in dms_house_info:
            errors.append(f"❌ `{sim}`: এটি {d.get('Distributor')} হাউসের সিম।")
            continue

        # ৩. সিমের অবস্থা অনুযায়ী গ্রুপিং
        if act_date:
            # এক্টিভ সিম (রিটার্ন সম্ভব নয়)
            if act_date not in active_map: active_map[act_date] = []
            clean_msisdn = f"0{msisdn}" if len(msisdn) == 10 else msisdn
            active_map[act_date].append(f"🔴 {sim}\n📱 {clean_msisdn} (এক্টিভ)")

        elif retailer and retailer.strip() and "Select" not in retailer:
            # ইস্যু করা সিম (এগুলো রিটার্ন হবে)
            if retailer not in issued_map: issued_map[retailer] = []
            issued_map[retailer].append(f"🟡 {sim}")
            
            # রিটেইলার কোড (উদা: R123456) আলাদা করে ডিকশনারিতে রাখা
            match = re.search(r'R\d+', retailer)
            code = match.group(0) if match else retailer
            if code not in grouped_return_data: grouped_return_data[code] = []
            grouped_return_data[code].append(sim)
        else:
            # ইস্যু হয়নি এমন সিম (ওয়্যারহাউস)
            warehouse_list.append(f"⚪ {sim} (ওয়্যারহাউসে আছে)")

    # ৪. রিপোর্ট টেক্সট ফরম্যাটিং ✅
    final_output = [
        f"📝 **সিম রিটার্ন এনালাইসিস রিপোর্ট**",
        f"🏢 হাউজ: **{target_name}** (`{target_code}`)\n"
    ]

    # এক্টিভ সেকশন
    if active_map:
        for date, lines in active_map.items():
            final_output.append("\n".join(lines))
            final_output.append(f"📅 {date}\n")

    # ইস্যু করা সেকশন (যাদের রিটার্ন প্রসেস শুরু হবে)
    if issued_map:
        if len(final_output) > 2: final_output.append("----------------------------")
        for ret, sims in issued_map.items():
            final_output.append("\n".join(sims))
            final_output.append(f"••••••••••••••••••••••\n🏪 {ret} (রিটার্ন করা হবে)\n")

    # ওয়্যারহাউস সেকশন
    if warehouse_list:
        final_output.append("\n".join(warehouse_list))

    # এরর সেকশন (অন্য হাউজের ডাটা)
    if errors:
        final_output.append("\n" + "\n".join(errors))

    return "\n".join(final_output), grouped_return_data