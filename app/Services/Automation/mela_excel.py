import pandas as pd
from datetime import datetime
from app.Models.mela import Mela, MelaAssignment
from app.Services.db_service import async_session

async def process_mela_excel(file_path, house_id):
    try:
        # এক্সেল রিড করা
        df = pd.read_excel(file_path, dtype=str).fillna("0")
        df.columns = df.columns.str.strip()

        async with async_session() as session:
            for _, row in df.iterrows():
                # ১. তারিখ ফরম্যাট ঠিক করা
                raw_date = row.get('Activity Date (MM-DD-YYYY)')
                act_date = datetime.strptime(raw_date, '%m-%d-%y').date()

                # ২. বিটিএস কোডগুলো জড়ো করা
                bts_list = [row.get(f'BTS Code {i}') for i in range(1, 6) if row.get(f'BTS Code {i}') != "0"]
                
                # ৩. নতুন মেলা এন্ট্রি
                new_mela = Mela(
                    house_id=house_id,
                    activity_date=act_date,
                    thana=row.get('Thana'),
                    location=row.get('Event Location Address'),
                    event_type=row.get('Event Type'),
                    activity_type=row.get('Activity Selection ( Only for Zoom IN)'),
                    bts_codes=",".join(bts_list)
                )
                session.add(new_mela)
                await session.flush() # আইডি জেনারেট করার জন্য

                # ৪. এসাইনমেন্ট প্রসেসিং (RSO, BP, SSO/Shopkeeper)
                assignments = []
                
                # RSO Codes (1-5)
                for i in range(1, 6):
                    code = row.get(f'RSO Assisted Code {i}')
                    if code and code != "0":
                        assignments.append(MelaAssignment(mela_id=new_mela.id, retailer_code=code, role_type='RSO'))
                
                # BP Codes (1-4)
                for i in range(1, 5):
                    code = row.get(f'BP Assisted Code {i}')
                    if code and code != "0":
                        assignments.append(MelaAssignment(mela_id=new_mela.id, retailer_code=code, role_type='BP'))
                
                # SSO/Shopkeeper Codes (1-5)
                for i in range(1, 6):
                    code = row.get(f'SSO Code {i}')
                    if code and code != "0":
                        assignments.append(MelaAssignment(mela_id=new_mela.id, retailer_code=code, role_type='SHOPKEEPER'))

                session.add_all(assignments)
            
            await session.commit()
            return len(df), None
    except Exception as e:
        return 0, str(e)