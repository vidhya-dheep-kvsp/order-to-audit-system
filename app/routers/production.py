from decimal import Decimal
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Item, Supplier, BOMHeader, Purchase, ProductionRun
from app.auth import require_role
from app.services import (
    get_current_stock, record_purchase, record_production_run, update_run_overheads
)

router = APIRouter(prefix="/production")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def production_page(
    request: Request,
    user: User = Depends(require_role("production", "admin")),
    db: Session = Depends(get_db),
):
    raw_items = db.query(Item).filter(Item.category.in_(["raw_material", "packaging"])).all()
    suppliers = db.query(Supplier).all()
    boms = db.query(BOMHeader).all()
    purchases = db.query(Purchase).order_by(Purchase.id.desc()).limit(10).all()
    runs = db.query(ProductionRun).order_by(ProductionRun.id.desc()).all()
    stock_map = {item.id: get_current_stock(db, item.id) for item in db.query(Item).all()}

    return templates.TemplateResponse(
        "production.html",
        {
            "request": request,
            "user": user,
            "raw_items": raw_items,
            "suppliers": suppliers,
            "boms": boms,
            "purchases": purchases,
            "runs": runs,
            "stock_map": stock_map,
        },
    )


@router.post("/purchase")
def create_purchase(
    supplier_id: int = Form(...),
    item_id: int = Form(...),
    qty: str = Form(...),
    unit_rate: str = Form(...),
    user: User = Depends(require_role("production", "admin")),
    db: Session = Depends(get_db),
):
    record_purchase(
        db=db,
        supplier_id=supplier_id,
        item_id=item_id,
        qty=Decimal(qty),
        unit_rate=Decimal(unit_rate),
        user_id=user.id,
    )
    return RedirectResponse("/production", status_code=303)


@router.post("/run")
async def create_production_run(
    request: Request,
    user: User = Depends(require_role("production", "admin")),
    db: Session = Depends(get_db),
):
    form = await request.form()
    bom_id = int(form["bom_id"])
    batch_count = Decimal(form["batch_count"])
    actual_output = Decimal(form["actual_output"])
    labour_cost = Decimal(form.get("labour_cost") or "0")
    overhead_cost = Decimal(form.get("overhead_cost") or "0")

    bom = db.query(BOMHeader).filter(BOMHeader.id == bom_id).first()
    consumptions_data = []
    for line in bom.lines:
        actual_qty = Decimal(form.get(f"actual_{line.component_item_id}", str(line.standard_qty)))
        damaged_qty = Decimal(form.get(f"damaged_{line.component_item_id}") or "0")
        consumptions_data.append({
            "item_id": line.component_item_id,
            "planned_qty": line.standard_qty * batch_count,
            "actual_qty": actual_qty,
            "damaged_qty": damaged_qty,
        })

    record_production_run(
        db=db,
        bom_id=bom_id,
        batch_count=batch_count,
        actual_output=actual_output,
        consumptions_data=consumptions_data,
        labour_cost=labour_cost,
        overhead_cost=overhead_cost,
        user_id=user.id,
    )
    return RedirectResponse("/production", status_code=303)


@router.post("/run/{run_id}/overheads")
def save_overheads(
    run_id: int,
    labour_cost: str = Form(...),
    overhead_cost: str = Form(...),
    user: User = Depends(require_role("production", "admin")),
    db: Session = Depends(get_db),
):
    update_run_overheads(
        db=db,
        run_id=run_id,
        labour_cost=Decimal(labour_cost),
        overhead_cost=Decimal(overhead_cost),
        user_id=user.id,
    )
    return RedirectResponse("/production", status_code=303)