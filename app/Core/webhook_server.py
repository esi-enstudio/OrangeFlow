import logging
import asyncio
from aiohttp import web
from pyngrok import ngrok, conf
from app.Core.otp_manager import otp_manager
from config import settings

# লগিং কনফিগারেশন
logging.getLogger("pyngrok").setLevel(logging.ERROR)

# লাইভ বটের জন্য এটি লাগবে, কিন্তু ডেভ বটের জন্য এটি খালি রাখা ভালো বা আলাদা ডোমেইন দিতে হবে
STATIC_DOMAIN = "unselfconscious-drusilla-subcommissarial.ngrok-free.dev"

async def handle_otp_webhook(request):
    """ম্যাক্রোড্রয়েড থেকে আসা ওটিপি হ্যান্ডেল করা"""
    try:
        data = await request.json()
        otp_code = data.get("otp_code")

        # MacroDroid এ আপনি house_code ফিল্ডটি ব্যবহার করবেন
        h_id = data.get("house_code") or data.get("house_name") or "UNKNOWN"

        if otp_code and len(str(otp_code)) == 6:

            # এখানে house_name সহ আপডেট করা হচ্ছে
            otp_manager.update_otp(str(otp_code), h_id)
            
            # টার্মিনালে হাউজের নামসহ সুন্দরভাবে প্রিন্ট করা
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"📥 [Webhook] ওটিপি রিসিভ হয়েছে!")
            print(f"🏢 হাউজ: {h_id}")
            print(f"🔑 ওটিপি: {otp_code}")
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
            return web.Response(text=f"OTP for {h_id} Received", status=200)
        
        return web.Response(text="Invalid Data Format", status=400)
    except Exception as e:
        print(f"❌ [Webhook Error] {str(e)}")
        return web.Response(text=str(e), status=500)

async def start_webhook_server(port=8080):
    """সার্ভার এবং এনগ্রোক স্টার্ট করার প্রফেশনাল লজিক"""

    # ১. পোর্ট নির্ধারণ (প্যারামিটার না থাকলে সেটিংস থেকে নিবে) ✅
    current_port = port if port else settings.WEBHOOK_PORT
    
    # এনগ্রোক ক্লিনআপ
    ngrok.kill() 
    
    if not settings.NGROK_AUTH_TOKEN:
        print("❌ [Ngrok] এরর: NGROK_AUTH_TOKEN নেই!")
        return

    try:
        conf.get_default().auth_token = settings.NGROK_AUTH_TOKEN

        # ডাইনামিক এনগ্রোক কানেকশন ✅
        # ডেভ বটের জন্য যদি স্ট্যাটিক ডোমেইন কাজ না করে (একই সাথে ২ বার ব্যবহার করা যায় না), 
        # তবে সেটি র্যান্ডম ইউআরএল তৈরি করবে।
        try:
            ngrok.connect(current_port, domain=STATIC_DOMAIN)
            print(f"✅ [System] Ngrok Tunnel Active: {STATIC_DOMAIN}")
        except Exception:
            # যদি স্ট্যাটিক ডোমেইন বিজি থাকে (যেমন লাইভ বটে চলছে), তবে র্যান্ডম ইউআরএল নিবে
            public_url = ngrok.connect(current_port)
            print(f"✅ [System] Ngrok Random Tunnel Active: {public_url.public_url}")

    except Exception as e:
        if "already bound" not in str(e):
            print(f"❌ [System Error] {e}")

    # aiohttp সার্ভার সেটআপ
    app = web.Application()
    app.add_routes([web.post('/receive-otp', handle_otp_webhook)])
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    try:
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"🚀 [Webhook] সার্ভার পোর্ট {port}-এ ওটিপি-র জন্য প্রস্তুত।")
    except OSError:
        print(f"❌ [Error] পোর্ট {port} দখল হয়ে আছে!")