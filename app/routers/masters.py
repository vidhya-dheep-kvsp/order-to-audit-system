from decimal import Decimal
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Item, BOMHeader, Customer, Supplier
from app.auth import require_role
from app.services import get_current_stock

router = APIRouter(prefix="/masters")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def view_masters(
    request: Request,
    user: User = Depends(require_role("admin", "production", "salesman", "auditor", "owner")),
    db: Session = Depends(get_db),
):
    items = db.query(Item).order_by(Item.category, Item.name).all()
    stock_map = {item.id: get_current_stock(db, item.id) for item in items}
    boms = db.query(BOMHeader).all()
    customers = db.query(Customer).all()
    suppliers = db.query(Supplier).all()

    return templates.TemplateResponse(
        "masters.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "stock_map": stock_map,
            "boms": boms,
            "customers": customers,
            "suppliers": suppliers,
        },
    )


@router.post("/customers")
def add_customer(
    name: str = Form(...),
    customer_type: str = Form(...),
    state: str = Form(...),
    gstin: str = Form(""),
    address: str = Form(""),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    db.add(Customer(
        name=name.strip(),
        customer_type=customer_type,
        state=state.strip(),
        gstin=gstin.strip() or None,
        address=address.strip() or None,
    ))
    db.commit()
    return RedirectResponse("/masters", status_code=303)