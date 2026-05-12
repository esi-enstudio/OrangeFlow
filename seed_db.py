import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from app.Services.db_service import async_session
from app.Models.house import House
from app.Models.user import User
from app.Models.role import Role, Permission
from app.Models.subscription import SubscriptionPackage, SubscriptionTier

async def seed_data():
    async with async_session() as session:
        print("Data seeding started...")

        # --- ১. পারমিশন সিডিং ---
        permissions_list = [
            "view_houses",
            "create_house",
            "renew_subscription",
            "view_users", 
            "create_user",
            "edit_user",
            "delete_user",
            "itopup_replace",
            "dms_access",
            "sim_status_check", 
            "sim_issue",
            "sim_return",
            "report_access",
            "view_ga_live",
            "search_retailer",
            "create_field_force",
            "view_field_force",
            "edit_field_force",
            "delete_field_force",
            "manage_field_force",
            "upload_retailer_excel",
            "manage_retailers",
            "create_retailers",
            "view_retailers",
            "edit_retailers",
            "delete_retailers",
            "create_bts",
            "view_bts",
            "edit_bts",
            "delete_bts",
            "create_mela",
            "view_mela",
            "edit_mela",
            "delete_mela",
            "create_new_role",
            "create_new_permission",
            "manage_role_and_permission_list",
            "manage_ga_filter",
            "manage_data_center",
            "manage_mela_settings",
            "manage_settings",
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
        print("[OK] Permission seeding completed.")

        # --- ২. রোল সিডিং ---
        roles_list = ["Manager", "Zonal Manager", "Distributor", "Supervisor", "Rso", "Bp", "Accoutant", "DMS Operator"]
        db_roles = {}
        for r_name in roles_list:
            role_res = await session.execute(select(Role).where(Role.name == r_name))
            role = role_res.scalar_one_or_none()
            if not role:
                role = Role(name=r_name)
                # ম্যানেজারের সব পারমিশন থাকবে (renew_subscription বাদে - শুধু সুপার এডমিনের জন্য)
                if r_name == "Manager":
                    role.permissions = [p for p in db_perms.values() if p.name != "renew_subscription"]
                session.add(role)
            db_roles[r_name] = role
        
        await session.flush()
        print("[OK] Role seeding completed.")

        # --- ২.৫ সাবস্ক্রিপশন প্যাকেজ সিডিং ---
        packages_data = [
            {
                "name": "বেসিক",
                "tier": SubscriptionTier.BASIC,
                "duration_days": 30,
                "price": 5000.00,
                "description": "ছোট দলের জন্য মৌলিক সুবিধা",
                "features": "হাউজ ম্যানেজমেন্ট, রিটেইলার ম্যানেজমেন্ট, বেসিক রিপোর্ট"
            },
            {
                "name": "স্ট্যান্ডার্ড",
                "tier": SubscriptionTier.STANDARD,
                "duration_days": 30,
                "price": 10000.00,
                "description": "মাঝারি দলের জন্য উন্নত সুবিধা",
                "features": "বেসিক সব + ফিল্ড ফোর্স ম্যানেজমেন্ট, এক্সেল ইমপোর্ট, এসএমএস সিঙ্ক"
            },
            {
                "name": "প্রিমিয়াম",
                "tier": SubscriptionTier.PREMIUM,
                "duration_days": 30,
                "price": 20000.00,
                "description": "বড় দলের জন্য পূর্ণ সুবিধা",
                "features": "স্ট্যান্ডার্ড সব + ডিএমএস ইন্টিগ্রেশন, অটোমেশন, প্রিমিয়াম সাপোর্ট"
            },
        ]

        db_packages = {}
        for pkg_data in packages_data:
            pkg_res = await session.execute(
                select(SubscriptionPackage).where(SubscriptionPackage.tier == pkg_data["tier"])
            )
            pkg = pkg_res.scalar_one_or_none()
            if not pkg:
                pkg = SubscriptionPackage(**pkg_data)
                session.add(pkg)
            db_packages[pkg_data["tier"].value] = pkg

        await session.flush()
        print("[OK] Subscription packages seeding completed.")

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
        print("[OK] House seeding completed.")

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
        print("[OK] User seeding completed.")
        print("[DONE] Data seeding finished successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())