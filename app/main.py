from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.database import engine, Base, SessionLocal
from app.seed import seed_database
from app.routers import auth, masters, production


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
app.add_middleware(SessionMiddleware, secret_key="dev-secret-key-change-in-prod")

app.include_router(auth.router)
app.include_router(masters.router)
app.include_router(production.router)