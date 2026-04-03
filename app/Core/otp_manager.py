import time

class OTPManager:
    def __init__(self):
        self.latest_otp = None
        self.received_at = 0
        self.is_used = True

    def update_otp(self, code: str):
        self.latest_otp = str(code)
        self.received_at = time.time()
        self.is_used = False
    
    async def wait_for_fresh_otp(self, house_name: str, timeout=120):
        """ওটিপি আসার জন্য ১২০ সেকেন্ড অপেক্ষা করবে"""
        start_wait = time.time()
        # এখন আর শুরুতে ওটিপি রিসেট করবো না, যাতে আগে আসা ওটিপি পাওয়া যায়
        
        print(f"⏳ [OTP] {house_name} এর জন্য ওটিপি-র অপেক্ষা... (Timeout: {timeout}s)")
        
        import asyncio
        while time.time() - start_wait < timeout:
            # চেক: ওটিপি যদি অব্যবহৃত হয় এবং সেটি যদি ১৫ সেকেন্ড আগে বা তার পরে এসে থাকে
            if not self.is_used and self.latest_otp:
                # স্লাইট বাফার (১৫ সেকেন্ড) যোগ করা হলো যাতে আগে রিসিভ হওয়া ওটিপি মিস না হয়
                if time.time() - self.received_at < 135: 
                    otp = self.latest_otp
                    self.is_used = True 
                    print(f"✅ [OTP] {house_name} এর জন্য ওটিপি গ্রহণ করা হয়েছে: {otp}")
                    return otp
            await asyncio.sleep(2)
        
        print(f"❌ [OTP] {house_name} এর জন্য ওটিপি পাওয়া যায়নি!")
        return None

otp_manager = OTPManager()