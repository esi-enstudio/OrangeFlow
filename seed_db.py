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
            "sim_status_check", "sim_issue", "sim_return", "ga_live", "itopup_replace", "dms_access", "task_sim_status", "task_sim_issue", "task_sim_return"
        ]
        
        db_perms = {}
        for p_name in permissions_list:
            perm = (await session.execute(select(Permission).where(Permission.name == p_name))).scalar_one_or_none()
            if not perm:
                perm = Permission(name=p_name)
                session.add(perm)
            db_perms[p_name] = perm
        
        await session.flush() # আইডি জেনারেট করার জন্য
        print("✅ পারমিশন সিডিং সম্পন্ন।")

        # --- ২. রোল সিডিং ---
        roles_list = ["Manager", "Zonal Manager", "Distributor", "Supervisor", "Rso", "Bp", "Accoutant", "DMS Operator"]
        db_roles = {}
        for r_name in roles_list:
            role = (await session.execute(select(Role).where(Role.name == r_name))).scalar_one_or_none()
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

        db_houses = []
        for h_data in houses_to_create:
            house = (await session.execute(select(House).where(House.code == h_data['code']))).scalar_one_or_none()
            if not house:
                house = House(
                    **h_data,
                    subscription_date=datetime.now() + timedelta(days=7),
                    is_active=True
                )
                session.add(house)
            db_houses.append(house)
        
        await session.flush()
        print("✅ হাউজ সিডিং সম্পন্ন।")

        # --- ৪. ইউজার সিডিং ---
        # এমিল (Patwary Telecom এর আন্ডারে)
        patwary_house = (await session.execute(select(House).where(House.code == "MYMVAI01"))).scalar_one()
        
        users_to_create = [
            {
                "telegram_id": 8653346171, "name": "এমিল", "phone_number": "01732547755", 
                "house_id": patwary_house.id, "role_name": "Manager"
            }
        ]

        # আরও ১০ টি ডেমো ইউজার যোগ করা
        for i in range(1, 11):
            users_to_create.append({
                "telegram_id": 1000000 + i, "name": f"Demo User {i}", "phone_number": f"018000000{i:02d}",
                "house_id": db_houses[i % len(db_houses)].id, "role_name": "Rso"
            })

        for u_data in users_to_create:
            user = (await session.execute(select(User).where(User.telegram_id == u_data['telegram_id']))).scalar_one_or_none()
            if not user:
                role = db_roles[u_data['role_name']]
                user = User(
                    telegram_id=u_data['telegram_id'],
                    name=u_data['name'],
                    phone_number=u_data['phone_number'],
                    house_id=u_data['house_id'],
                    roles=[role] # Many-to-Many রিলেশন
                )
                session.add(user)

        await session.commit()
        print("✅ ইউজার সিডিং সম্পন্ন।")
        print("🏁 ডাটা সিডিং সফলভাবে শেষ হয়েছে!")

if __name__ == "__main__":
    asyncio.run(seed_data())