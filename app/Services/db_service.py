from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config.settings import DATABASE_URL
from app.Models.base import Base
import app.Models.user # টেবিল তৈরির জন্য ইম্পোর্ট জরুরি
import app.Models.house
import app.Models.role
import app.Models.live_activation
import app.Models.retailer
import app.Models.field_force
import app.Models.bts
import app.Models.ga_filter
import app.Models.mela

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        # এটি এখন সকল নতুন টেবিলগুলো তৈরি করবে
        await conn.run_sync(Base.metadata.create_all)