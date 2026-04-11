import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class AutomationEngine:
    def __init__(self):
        self.playwright = None
        self.browser = None

    async def start(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            # সাধারণ ব্রাউজার লঞ্চ
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=['--disable-blink-features=AutomationControlled']
            )
            logger.info("🚀 [Engine] Browser Engine Started.")

    async def get_browser(self):
        if not self.browser or not self.playwright:
            await self.start()
        return self.browser


    async def stop(self):
        """বট বন্ধের সময় সব প্রোফাইল এবং ব্রাউজার ক্লিনলি বন্ধ করবে"""
        # ১. আগে সব আলাদা কন্টেক্সট (যদি থাকে) বন্ধ করার চেষ্টা করা
        for code, ctx in list(self.contexts.items()):
            try:
                await ctx.close()
            except: pass
            
        # ২. মেইন ব্রাউজার বন্ধ করা (এরর প্রোটেকশনসহ) ✅
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                # যদি ডিসকানেক্ট হয়ে যায়, তবে এরর না দেখিয়ে সাইলেন্টলি ইগনোর করবে
                logger.debug(f"[Engine] Browser already closed or disconnected: {e}")
        
        # ৩. প্লে-রাইট ড্রাইভার বন্ধ করা
        if self.playwright:
            try:
                await self.playwright.stop()
            except: pass
            
        logger.info("✅ [Engine] All browser profiles and engine stopped.")


engine = AutomationEngine()