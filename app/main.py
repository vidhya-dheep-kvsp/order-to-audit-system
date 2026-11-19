from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import engine, Base, SessionLocal
from app.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Order-to-Audit System", lifespan=lifespan)


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Order-to-Audit System is running with seeded DB"}