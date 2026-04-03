import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from app.Services.db_service import async_session
from app.Models.house import House
from app.Models.user import User
from app.Models.role import Role, Permission

async def seed_data():
    async with async_session() as session:
        print("🚀 ডাটা সিডিং শুরু হচ্ছে...")

        # --- ১. পারমিশন সিডিং ---
        permissions_list = [
            "view_houses", "create_house", "renew_subscription", "view_users", 
            "create_user", "edit_user", "delete_user", "manage_settings", 
            "ga_live", "itopup_replace", "dms_access", "sim_status_check", 
            "sim_issue", "sim_return"
        ]
        
        db_perms = {}
        for p_name in permissions_list:
            perm_res = await session.execute(select(Permission).where(Permission.name == p_name))
            perm = perm_res.scalar_one_or_none()
            if not perm:
                perm = Permission(name=p_name)
                session.add(perm)
            db_perms[p_name] = perm
        
        await session.flush() 
        print("✅ পারমিশন সিডিং সম্পন্ন।")

        # --- ২. রোল সিডিং ---
        roles_list = ["Manager", "Zonal Manager", "Distributor", "Supervisor", "Rso", "Bp", "Accoutant", "DMS Operator"]
        db_roles = {}
        for r_name in roles_list:
            role_res = await session.execute(select(Role).where(Role.name == r_name))
            role = role_res.scalar_one_or_none()
            if not role:
                role = Role(name=r_name)
                # ম্যানেজারের সব পারমিশন থাকবে
                if r_name == "Manager":
                    role.permissions = list(db_perms.values())
                session.add(role)
            db_roles[r_name] = role
        
        await session.flush()
        print("✅ রোল সিডিং সম্পন্ন।")

        # --- ৩. হাউজ সিডিং ---
        houses_to_create = [
            {
                "cluster": "East", "region": "Brahmanbaria", "name": "Patwary Telecom", "code": "MYMVAI01",
                "email": "patwarytelecom@gmail.com", "contact": "01917747555",
                "address": "Kisukkhon Patwary Complex, Bongobondhu road, Bhairab, Kishoreganj."
            },
            {
                "cluster": "North East", "region": "Mymensingh", "name": "M/s Modina Store", "code": "MYMVAI02",
                "email": "blmodinastore@gmail.com", "contact": "01911636262",
                "address": "Lonchghat, Mithamoin, Kishoreganj."
            }
        ]

        # আরও ১০ টি ডেমো হাউজ যোগ করা
        for i in range(3, 13):
            houses_to_create.append({
                "cluster": "Demo Cluster", "region": f"Region {i}", "name": f"Demo House {i}", "code": f"MYMVAI{i:02d}",
                "email": f"demo{i}@gmail.com", "contact": f"019000000{i:02d}", "address": f"Address of House {i}"
            })

        db_houses_map = {} # কোড অনুযায়ী হাউজ অবজেক্ট রাখার জন্য
        for h_data in houses_to_create:
            h_res = await session.execute(select(House).where(House.code == h_data['code']))
            house = h_res.scalar_one_or_none()
            if not house:
                house = House(
                    **h_data,
                    subscription_date=datetime.now() + timedelta(days=365), # ১ বছর মেয়াদ
                    is_active=True
                )
                session.add(house)
            db_houses_map[h_data['code']] = house
        
        await session.flush()
        print("✅ হাউজ সিডিং সম্পন্ন।")

        # --- ৪. ইউজার সিডিং ---
        # এমিল (সুপার এডমিন হিসেবে তাকে Patwary Telecom এবং Modina Store দুটিতেই রাখা হলো)
        patwary_h = db_houses_map["MYMVAI01"]
        modina_h = db_houses_map["MYMVAI02"]
        
        users_to_create = [
            {
                "telegram_id": 6906339644, "name": "এমিল", "phone_number": "01732547755", 
                "house_codes": ["MYMVAI01", "MYMVAI02"], "role_name": "Manager"
            }
        ]

        # আরও কিছু ডেমো ইউজার
        for i in range(1, 6):
            users_to_create.append({
                "telegram_id": 1000000 + i, "name": f"Demo User {i}", "phone_number": f"018000000{i:02d}",
                "house_codes": ["MYMVAI01"], "role_name": "DMS Operator"
            })

        for u_data in users_to_create:
            u_res = await session.execute(select(User).where(User.telegram_id == u_data['telegram_id']))
            user = u_res.scalar_one_or_none()
            
            if not user:
                # রোল অবজেক্ট নেওয়া
                role = db_roles[u_data['role_name']]
                
                # হাউজ অবজেক্টগুলোর লিস্ট তৈরি করা (Many-to-Many এর জন্য)
                assigned_houses = [db_houses_map[code] for code in u_data['house_codes']]
                
                user = User(
                    telegram_id=u_data['telegram_id'],
                    name=u_data['name'],
                    phone_number=u_data['phone_number'],
                    roles=[role],      # Many-to-Many রিলেশন (লিস্ট হিসেবে দিতে হবে)
                    houses=assigned_houses # Many-to-Many রিলেশন (লিস্ট হিসেবে দিতে হবে) ✅
                )
                session.add(user)

        await session.commit()
        print("✅ ইউজার সিডিং সম্পন্ন।")
        print("🏁 ডাটা সিডিং সফলভাবে শেষ হয়েছে!")

if __name__ == "__main__":
    asyncio.run(seed_data())