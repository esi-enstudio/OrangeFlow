import asyncio
import os
from playwright.async_api import async_playwright
from app.Core.otp_manager import otp_manager

login_lock = asyncio.Lock()

class DMSLoginManager:
    def __init__(self):
        self.login_url = "https://blkdms.banglalink.net/Account/Login"

    async def is_session_valid(self, page):
        """সেশন সচল আছে কি না তা একটি সুরক্ষিত পেজে গিয়ে চেক করা"""
        try:
            print("🔍 [Session] সেশন ভ্যালিডিটি চেক করা হচ্ছে...")

            # সরাসরি স্মার্ট সার্চ রিপোর্টে যাওয়ার চেষ্টা করবো (এটি শুধুমাত্র লগইন থাকলেই ওপেন হয়)
            await page.goto("https://blkdms.banglalink.net/SmartSearchReport", timeout=15000)

            # ছোট বিরতি যাতে রিডাইরেক্ট হওয়ার সুযোগ পায়
            await asyncio.sleep(2)

            current_url = page.url.lower()

            # চেক: যদি URL এ 'login' শব্দটি না থাকে, তার মানে আমরা সফলভাবে ভেতরে ঢুকে গেছি
            if "login" not in current_url:
                # আরও নিশ্চিত হওয়ার জন্য পেজে কোনো এলিমেন্ট আছে কি না দেখা (ঐচ্ছিক)
                if await page.query_selector("#SearchType"):
                    print("✅ [Session] সেশন সচল আছে। লগইন করার প্রয়োজন নেই।")
                    return True
            
            print("⚠️ [Session] সেশন এক্সপায়ার হয়েছে। নতুন লগইন প্রয়োজন...")
            return False

        except Exception as e:
            print(f"❌ [Session Error] চেক করার সময় এরর: {str(e)}")
            return False

    async def perform_login(self, page, credentials: dict, session_path: str):
        """ডাইনামিক ড্রপডাউন পপুলেশন হ্যান্ডেল করে লগইন"""
        async with login_lock:
            try:
                print(f"🚀 [Login] লগইন শুরু: {credentials['house_name']}")
                await page.goto(self.login_url)
                
                print("⏳ [Login] ৩ সেকেন্ড পেজ লোড বাফার...")
                await asyncio.sleep(3) 
                
                # ১. ইউজারনেম এবং পাসওয়ার্ড ইনপুট (এটি ড্রপডাউন পপুলেট হওয়া ট্রিগার করবে)
                print(f"📝 [Login] ইউজারনেম ও পাসওয়ার্ড ইনপুট দিচ্ছি...")
                await page.fill("#Email", str(credentials['user']))
                await page.fill("#Password", str(credentials['pass']))
                
                # ২. ড্রপডাউনে ডাটা আসার জন্য অপেক্ষা করা
                house_id = str(credentials['house_id'])
                print(f"⏳ [Login] ড্রপডাউনে হাউজ কোড '{house_id}' আসার জন্য অপেক্ষা করছি...")
                
                # টার্গেট হাউজ অপশনটি ড্রপডাউনের ভেতরে না আসা পর্যন্ত ৩০ সেকেন্ড ওয়েট করবে
                target_option_selector = f"select#Distributor option[value='{house_id}']"
                try:
                    await page.wait_for_selector(target_option_selector, state="attached", timeout=20000)
                    print(f"✅ [Login] হাউজ কোড '{house_id}' পাওয়া গেছে!")
                except Exception as e:
                    print(f"❌ [Error] নির্ধারিত সময়ের মধ্যে ড্রপডাউনে ডাটা আসেনি।")
                    return False

                # ৩. আপনার লজিক অনুযায়ী ডাটা আসার পর ১-২ সেকেন্ড বিরতি
                await asyncio.sleep(2) 


                # ৪. হাউজ সিলেকশন (Select2 ফিক্সড লজিক)
                print(f"🟡 [Login] হাউজ সিলেক্ট করছি...")
                await page.evaluate(f"""
                    (function() {{
                        let select = document.getElementById('Distributor');
                        if (select) {{
                            select.value = '{house_id}';
                            // ইভেন্ট ট্রিগার যাতে সাইট ডাটা কনফার্ম করতে পারে
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            if (window.jQuery) {{
                                window.jQuery(select).val('{house_id}').trigger('change');
                            }}
                        }}
                    }})();
                """)
                
                await asyncio.sleep(2) # সিলেকশন নিশ্চিত করতে বিরতি
                
                # সিলেকশন চেক করা
                current_val = await page.evaluate("document.getElementById('Distributor').value")
                # print(f"🔍 [Debug] বর্তমানে সিলেক্টেড ভ্যালু: {current_val}")

                # ৫. লগইন বাটনে ক্লিক
                await page.click("#btnSubmit")
                print("🔵 [Login] সাবমিট বাটনে ক্লিক করা হয়েছে।")
                
                await asyncio.sleep(5)
                
                # ওটিপি হ্যান্ডেলিং
                if await page.query_selector("#OTP"):
                    print("⏳ [Login] ওটিপি পেজ পাওয়া গেছে। ওটিপি রিসিভ করছি...")
                    otp = await otp_manager.wait_for_fresh_otp()

                    if otp:
                        await page.fill("#OTP", str(otp))
                        await page.click("#submitButton")
                        print("🟡 [Login] সাবমিট হয়েছে, রিডাইরেক্টের অপেক্ষা করছি...")

                        # networkidle এর বদলে URL পরিবর্তন হওয়া পর্যন্ত অপেক্ষা করবে (সর্বোচ্চ ১৫ সেকেন্ড)
                        try:
                            await page.wait_for_function(
                                "() => !window.location.href.toLowerCase().includes('login')",
                                timeout=15000
                            )
                        except:
                            print("⚠️ [Warning] রিডাইরেক্টে সময় নিচ্ছে, তবুও সেশন চেক করছি...")

                        # await asyncio.sleep(3)
                        # await page.wait_for_load_state("networkidle")
                    else:
                        print("❌ [Login] ওটিপি সংগ্রহ ব্যর্থ হয়েছে (Timeout)।")
                        return False

                if "login" not in page.url.lower():
                    # সেশন ডিরেক্টরি নিশ্চিত করা
                    os.makedirs(os.path.dirname(session_path), exist_ok=True)

                    await page.context.storage_state(path=session_path)
                    print(f"✅ [Login] সফলভাবে লগইন সম্পন্ন এবং সেশন সেভ হয়েছে।")
                    return True
                
                return False

            except Exception as e:
                print(f"❌ [Critical Error] {str(e)}")
                return False

dms_login = DMSLoginManager()