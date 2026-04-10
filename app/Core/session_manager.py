import os
import asyncio
import logging
from sqlalchemy import select
from app.Core.automation_engine import engine
from app.Core.login_manager import dms_login
from app.Services.db_service import async_session
from app.Models.house import House

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        self._locks = {}

    def _get_house_lock(self, house_code):
        if house_code not in self._locks:
            self._locks[house_code] = asyncio.Lock()
        return self._locks[house_code]

    async def get_valid_page(self, credentials: dict):
        """টাস্ক ফাইলগুলোর জন্য সচল পেজ নিশ্চিত করবে।"""
        h_code = credentials['code']
        
        async with self._get_house_lock(h_code):
            page, context = await engine.get_house_page(h_code)
            
            # সেশন চেক
            if await dms_login.is_session_valid(page):
                return page, context
            else:
                logger.warning(f"⚠️ [Manager] {h_code} সেশন মৃত। মেরামত হচ্ছে...")
                success = await dms_login.perform_login(page, credentials)
                if success:
                    return page, context
                
                await page.close()
                # প্রোফাইল কন্টেক্সট বন্ধ করবো না, যাতে পরবর্তীতে অটো-রিকভার করতে পারে
                raise Exception(f"DMS Login failed for {h_code}")

    async def background_watcher(self):
        """সেশন পাহারাদার (হার্টবিট সিস্টেম)"""
        await asyncio.sleep(20) 
        logger.info("💓 [Watcher] Session Heartbeat Started.")
        
        while True:
            try:
                async with async_session() as session:
                    houses = (await session.execute(select(House).where(House.dms_user != None))).scalars().all()

                for house in houses:
                    credentials = {
                        "user": house.dms_user, "pass": house.dms_pass,
                        "house_id": house.dms_house_id, "house_name": house.name, "code": house.code
                    }
                    
                    async with self._get_house_lock(house.code):
                        page = None
                        try:
                            # ১. পেজ নেওয়া
                            page, context = await engine.get_house_page(house.code)
                            
                            logger.info(f"🔄 [Watcher] Checking: {house.name}")

                            # ২. সেশন ভ্যালিডেশন
                            if await dms_login.is_session_valid(page):
                                # ৩. ডামি সার্চ হার্টবিট
                                try:
                                    await page.goto("https://blkdms.banglalink.net/SmartSearchReport", wait_until="commit", timeout=30000)
                                    await page.select_option("#SearchType", "1")
                                    await page.fill("#SearchValue", "898800000000000000")
                                    await page.click("button.btn-success")
                                    await asyncio.sleep(3)
                                    logger.info(f"✅ [Watcher] {house.name} হার্টবিট সফল।")
                                except Exception as e:
                                    logger.error(f"⚠️ [Watcher] {house.name} হার্টবিট ফেইল: {e}")
                            else:
                                # ৪. অটো-লগইন
                                logger.info(f"🔄 [Watcher] {house.name} সেশন মৃত। লগইন শুরু...")
                                await dms_login.perform_login(page, credentials)

                        except Exception as e:
                            logger.error(f"❌ [Watcher Error] {house.name}: {e}")
                        finally:
                            # শুধুমাত্র ট্যাব বন্ধ করবো, কন্টেক্সট নয়! ✅
                            if page: await page.close()
                    
                    await asyncio.sleep(5)

                logger.info("💤 [Watcher] Next cycle in 4 minutes...")
                await asyncio.sleep(240) 

            except Exception as e:
                logger.error(f"❌ [Watcher Loop Error] {e}")
                await asyncio.sleep(60)

session_manager = SessionManager()