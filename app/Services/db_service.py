from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config.settings import DATABASE_URL
from app.Models.base import Base
import app.Models.user # টেবিল তৈরির জন্য ইম্পোর্ট জরুরি
import app.Models.house

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        # এটি User এবং House টেবিল দুটোই তৈরি করবে
        await conn.run_sync(Base.metadata.create_all)