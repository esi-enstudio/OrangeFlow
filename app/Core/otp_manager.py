import time
import asyncio
import logging

logger = logging.getLogger(__name__)

class OTPManager:
    def __init__(self):
        # ওটিপি পুলে ডাটা রাখার তালিকা
        self.otp_pool = []

    def update_otp(self, code: str, house_identifier: str):
        """ম্যাক্রোড্রয়েড থেকে ওটিপি আসলে এই পুলে যোগ হবে"""
        new_otp = {
            "code": str(code),
            "identifier": str(house_identifier).strip().upper(),
            "received_at": time.time(),
            "is_used": False
        }
        self.otp_pool.append(new_otp)
        logger.info(f"🆕 [OTP Pool] New OTP: {code} for {house_identifier}")
        
        # ৫ মিনিটের বেশি পুরনো ওটিপি পরিষ্কার করা
        self._cleanup_old_otps()

    async def wait_for_fresh_otp(self, target_id: str, request_time: float, timeout=110):
        """
        ওটিপি-র জন্য অপেক্ষা করবে। 
        target_id: হাউজ কোড (যেমন: MYMVAI01)
        request_time: ব্রাউজারে লগইন বাটনে ক্লিক করার সময় (লগইন ম্যানেজার থেকে পাঠানো হয়)
        """
        start_wait = time.time()
        target_id = str(target_id).strip().upper()
        
        logger.info(f"⏳ [OTP] {target_id} এর ওটিপি খুঁজছি...")
        
        while time.time() - start_wait < timeout:
            # পুলের সব ওটিপি চেক করা
            for otp_data in self.otp_pool:
                # নিখুঁত ম্যাচিং লজিক:
                # ১. আগে ব্যবহৃত হয়নি (is_used == False)
                # ২. হাউজ আইডি মিলেছে (identifier == target_id)
                # ৩. ওটিপিটি ২ মিনিটের বেশি পুরনো নয়
                # ৪. ওটিপিটি অবশ্যই লগইন রিকোয়েস্ট শুরু হওয়ার পর (বা সামান্য আগে) এসেছে ✅
                if not otp_data["is_used"] and \
                   otp_data["identifier"] == target_id and \
                   (time.time() - otp_data["received_at"] < 120) and \
                   (otp_data["received_at"] >= request_time - 2): # ২ সেকেন্ড বাফার

                    otp_code = otp_data["code"]
                    otp_data["is_used"] = True 
                    
                    logger.info(f"✅ [OTP] {target_id} এর জন্য ম্যাচ পাওয়া গেছে: {otp_code}")
                    return otp_code
            
            await asyncio.sleep(1) # ১ সেকেন্ড পর পর চেক করবে
        
        logger.error(f"❌ [OTP] ওটিপি পাওয়ার সময় শেষ (Timeout) হাউজ: {target_id}")
        return None

    def _cleanup_old_otps(self):
        """৫ মিনিটের বেশি পুরনো ওটিপিগুলো লিস্ট থেকে মুছে ফেলবে"""
        current_time = time.time()
        self.otp_pool = [otp for otp in self.otp_pool if current_time - otp["received_at"] < 300]

# গ্লোবাল অবজেক্ট
otp_manager = OTPManager()