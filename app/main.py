from fastapi import FastAPI

app = FastAPI(title="Order-to-Audit System")

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Order-to-Audit System is running"}