import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from app.Models.bts import BTS
from app.Services.db_service import async_session

# কলাম ম্যাপিং (Excel Header -> DB Column)
BTS_MAP = {
    'SITE ID': 'site_id', 'BTS CODE': 'bts_code', 'SITE TYPE': 'site_type',
    'THANA': 'thana', 'THANA BN': 'thana_bn', 'DISTRICT': 'district',
    'DISTRICT BN': 'district_bn', 'DIVISION': 'division', 'DIVISION BN': 'division_bn',
    'CLUSTER': 'cluster', 'CLUSTER BN': 'cluster_bn', 'REGION': 'region',
    'REGION BN': 'region_bn', 'NETWORK MODE': 'network_mode', 'ADDRESS': 'address',
    'ADDRESS BN': 'address_bn', 'SHORT ADDRESS': 'short_address', 'LONGITUDE': 'longitude',
    'LATITUDE': 'latitude', 'ARCHETYPE': 'archetype', 'MARKET': 'market',
    'DISTRIBUTOR CODE': 'distributor_code', '2GONAIRDATE': 'onair_date_2g',
    '3GONAIRDATE': 'onair_date_3g', '4GONAIRDATE': 'onair_date_4g',
    'URBAN_RURAL': 'urban_rural', 'PRIORITY': 'priority'
}

async def generate_bts_sample(file_path):
    """ইউজারের জন্য একটি বিটিএস স্যাম্পল এক্সেল ফাইল তৈরি করবে"""
    # বিটিএস-এর সকল ২৭টি কলামের হেডার লিস্ট
    headers = [
        'SITE ID', 'BTS CODE', 'SITE TYPE', 'THANA', 'THANA BN', 'DISTRICT',
        'DISTRICT BN', 'DIVISION', 'DIVISION BN', 'CLUSTER', 'CLUSTER BN', 'REGION',
        'REGION BN', 'NETWORK MODE', 'ADDRESS', 'ADDRESS BN', 'SHORT ADDRESS', 'LONGITUDE',
        'LATITUDE', 'ARCHETYPE', 'MARKET', 'DISTRIBUTOR CODE', '2GONAIRDATE',
        '3GONAIRDATE', '4GONAIRDATE', 'URBAN_RURAL', 'PRIORITY'
    ]
    
    # একটি খালি ডাটাফ্রেম তৈরি করে এক্সেল হিসেবে সেভ করা
    df = pd.DataFrame(columns=headers)
    df.to_excel(file_path, index=False)
    return file_path



async def process_bts_excel(file_path, house_id, progress_callback):
    try:
        df = pd.read_excel(file_path, dtype=str).fillna("N/A")
        df.columns = [c.strip().upper() for c in df.columns]
        total = len(df)

        async with async_session() as session:
            for index, row in df.iterrows():
                data = {"house_id": house_id}
                for excel_key, db_key in BTS_MAP.items():
                    data[db_key] = str(row.get(excel_key, 'N/A')).strip()

                stmt = insert(BTS).values(**data)
                stmt = stmt.on_conflict_do_update(index_elements=['bts_code'], set_=data)
                await session.execute(stmt)
                
                if (index + 1) % 10 == 0 or (index + 1) == total:
                    await progress_callback(f"⏳ বিটিএস আপলোড: {round(((index+1)/total)*100)}% ({index+1}/{total})")
            
            await session.commit()
        return total, None
    except Exception as e:
        return 0, str(e)