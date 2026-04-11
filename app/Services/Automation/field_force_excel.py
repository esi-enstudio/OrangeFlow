import pandas as pd
import os
from app.Models.field_force import FieldForce
from app.Services.db_service import async_session

async def process_field_force_excel(file_path, house_id):
    try:
        # এক্সেল ফাইল রিড করা
        df = pd.read_excel(file_path, dtype=str).fillna("")
        
        async with async_session() as session:
            new_entries = []
            for _, row in df.iterrows():
                field_force = FieldForce(
                    house_id=house_id,
                    code=row.get('CODE'),
                    name=row.get('NAME'),
                    type=row.get('TYPE'),
                    phone_number=row.get('PHONE_NUMBER'),
                    personal_number=row.get('PERSONAL_NUMBER'),
                    pool_number=row.get('POOL_NUMBER'),
                    salary=row.get('SALARY'),
                    # ... একইভাবে অন্য সকল ৩৮টি কলাম এখানে ম্যাপ করতে হবে
                    status="Active"
                )
                new_entries.append(field_force)
            
            if new_entries:
                session.add_all(new_entries)
                await session.commit()
                return len(new_entries), None
        return 0, "ফাইলটি খালি।"
    except Exception as e:
        return 0, str(e)