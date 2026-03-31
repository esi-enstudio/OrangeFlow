import logging
import asyncio
from aiohttp import web
from pyngrok import ngrok, conf
from app.Core.otp_manager import otp_manager
from config import settings

logging.getLogger("pyngrok").setLevel(logging.ERROR) # pyngrok কে শান্ত করা
# logger = logging.getLogger(__name__)

STATIC_DOMAIN = "unselfconscious-drusilla-subcommissarial.ngrok-free.dev"

async def handle_otp_webhook(request):
    try:
        data = await request.json()
        otp_code = data.get("otp_code")
        if otp_code and len(str(otp_code)) == 6:
            otp_manager.update_otp(str(otp_code))
            print(f"📥 [Webhook] ওটিপি রিসিভ হয়েছে: {otp_code}")
            return web.Response(text="OTP Received", status=200)
        return web.Response(text="Invalid Data", status=400)
    except Exception as e:
        return web.Response(text=str(e), status=500)

async def start_webhook_server(port=8080):
    """সার্ভার এবং এনগ্রোক স্টার্ট করার রিফ্যাক্টরড কোড"""
    
    # ১. এনগ্রোক ক্লিনআপ (পুরনো টানেল বন্ধ করা)
    ngrok.kill() 
    
    if not settings.NGROK_AUTH_TOKEN:
        print("❌ [Ngrok] এরর: NGROK_AUTH_TOKEN নেই!")
        return

    try:
        conf.get_default().auth_token = settings.NGROK_AUTH_TOKEN
        # ২. টানেল কানেক্ট করা
        public_url = ngrok.connect(port, domain=STATIC_DOMAIN)

        # আপনার জন্য শুধু প্রয়োজনীয় মেসেজগুলো প্রিন্ট করা হচ্ছে
        print(f"✅ [System] Ngrok Tunnel Active: {STATIC_DOMAIN}")
        print(f"🚀 [System] Webhook Server is ready on port {port}")

    except Exception as e:
        # শুধু সিরিয়াস এরর হলে দেখাবে
        if "already bound" not in str(e):
            print(f"❌ [System Error] {e}")

    # ৩. aiohttp সার্ভার সেটআপ
    app = web.Application()
    app.add_routes([web.post('/receive-otp', handle_otp_webhook)])
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    try:
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"🚀 [Webhook] সার্ভার পোর্ট {port}-এ লিসেন করছে।")
    except OSError:
        print(f"❌ [Error] পোর্ট {port} দখল হয়ে আছে! অন্য কোনো প্রোগ্রাম এটি ব্যবহার করছে।")