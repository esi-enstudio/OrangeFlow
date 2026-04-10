import os
import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)
PROFILES_DIR = "browser_profiles"

class AutomationEngine:
    def __init__(self):
        self.playwright = None
        self.browser = None # এটি আসলে কাজে লাগছে না launch_persistent_context এ
        self.contexts = {} 

    async def start(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            if not os.path.exists(PROFILES_DIR):
                os.makedirs(PROFILES_DIR)
            logger.info("🚀 [Engine] Automation Engine Ready.")

    async def get_house_page(self, house_code: str):
        """হাউজ ভিত্তিক পারসিস্টেন্ট কন্টেক্সট থেকে পেজ দিবে"""
        if not self.playwright: await self.start()
        
        profile_path = os.path.abspath(os.path.join(PROFILES_DIR, f"profile_{house_code}"))

        # যদি কন্টেক্সট আগে থেকে না থাকে বা বন্ধ হয়ে যায়, তবে নতুন করে তৈরি করবে ✅
        if house_code not in self.contexts:
            logger.info(f"📁 [Engine] Launching Persistent Context for: {house_code}")
            context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                ]
            )
            self.contexts[house_code] = context
        
        # নতুন ট্যাব তৈরি
        try:
            page = await self.contexts[house_code].new_page()
            return page, self.contexts[house_code]
        except Exception:
            # যদি কন্টেক্সট কোনো কারণে ক্র্যাশ করে থাকে, তবে সেটি ডিলিট করে আবার ট্রাই করবে
            del self.contexts[house_code]
            return await self.get_house_page(house_code)

    async def stop(self):
        """বট বন্ধের সময় সব প্রোফাইল ক্লিনলি বন্ধ করবে"""
        for code, ctx in list(self.contexts.items()):
            try:
                await ctx.close()
            except: pass
        if self.playwright:
            await self.playwright.stop()
        logger.info("✅ [Engine] All browser profiles closed.")

engine = AutomationEngine()