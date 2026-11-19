from decimal import Decimal
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Customer, Item, Order, Invoice
from app.auth import require_role
from app.services import (
    get_current_stock, create_sales_order, approve_and_invoice_order,
    dispatch_invoice, record_payment
)
from app.pdf_utils import generate_invoice_pdf

router = APIRouter(prefix="/sales")
templates = Jinja2Templates(directory="app/templates")


@router.get("/mobile", response_class=HTMLResponse)
def salesman_mobile_page(
    request: Request,
    user: User = Depends(require_role("salesman")),
    db: Session = Depends(get_db),
):
    customers = db.query(Customer).order_by(Customer.name).all()
    products = db.query(Item).filter(Item.category == "finished_good").all()
    my_orders = (
        db.query(Order)
        .filter(Order.salesman_id == user.id)
        .order_by(Order.id.desc())
        .limit(10)
        .all()
    )
    return templates.TemplateResponse(
        "sales_mobile.html",
        {
            "request": request,
            "user": user,
            "customers": customers,
            "products": products,
            "my_orders": my_orders,
        },
    )


@router.post("/mobile/order")
def submit_mobile_order(
    customer_id: int = Form(...),
    item_id: int = Form(...),
    qty: str = Form(...),
    notes: str = Form(""),
    user: User = Depends(require_role("salesman")),
    db: Session = Depends(get_db),
):
    create_sales_order(
        db=db,
        customer_id=customer_id,
        salesman_id=user.id,
        item_id=item_id,
        qty=Decimal(qty),
        notes=notes,
    )
    return RedirectResponse("/sales/mobile", status_code=303)


@router.get("/admin", response_class=HTMLResponse)
def admin_sales_page(
    request: Request,
    error: str | None = None,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    orders = db.query(Order).order_by(Order.id.desc()).all()
    invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    products = db.query(Item).filter(Item.category == "finished_good").all()
    stock_map = {p.id: get_current_stock(db, p.id) for p in products}

    # Pre-calculate paid & outstanding per invoice
    invoice_stats = {}
    for inv in invoices:
        paid = sum((p.amount for p in inv.payments), Decimal("0.00"))
        invoice_stats[inv.id] = {
            "paid": paid,
            "outstanding": inv.total_amount - paid,
        }

    return templates.TemplateResponse(
        "sales_admin.html",
        {
            "request": request,
            "user": user,
            "orders": orders,
            "invoices": invoices,
            "stock_map": stock_map,
            "invoice_stats": invoice_stats,
            "error": error,
        },
    )


@router.post("/admin/order/{order_id}/invoice")
def admin_approve_invoice(
    order_id: int,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    try:
        approve_and_invoice_order(db, order_id, user.id)
    except ValueError as e:
        return RedirectResponse(f"/sales/admin?error={e}", status_code=303)
    return RedirectResponse("/sales/admin", status_code=303)


@router.post("/admin/invoice/{invoice_id}/dispatch")
def admin_dispatch(
    invoice_id: int,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    try:
        dispatch_invoice(db, invoice_id, user.id)
    except ValueError as e:
        return RedirectResponse(f"/sales/admin?error={e}", status_code=303)
    return RedirectResponse("/sales/admin", status_code=303)


@router.post("/admin/invoice/{invoice_id}/payment")
def admin_record_payment(
    invoice_id: int,
    amount: str = Form(...),
    payment_mode: str = Form("BANK_TRANSFER"),
    reference_no: str = Form(""),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    record_payment(
        db=db,
        invoice_id=invoice_id,
        amount=Decimal(amount),
        payment_mode=payment_mode,
        reference_no=reference_no,
        user_id=user.id,
    )
    return RedirectResponse("/sales/admin", status_code=303)


@router.get("/invoice/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    user: User = Depends(require_role("admin", "auditor", "owner")),
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    pdf_bytes = generate_invoice_pdf(invoice)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={invoice.invoice_number}.pdf"},
    )