import csv
import io
from decimal import Decimal
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import (
    User, Item, StockLedger, Purchase, ProductionRun,
    ProductionConsumption, Invoice, AuditLog
)
from app.auth import require_role
from app.services import get_current_stock

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def reports_dashboard(
    request: Request,
    user: User = Depends(require_role("owner", "auditor", "admin")),
    db: Session = Depends(get_db),
):
    items = db.query(Item).order_by(Item.category, Item.name).all()
    stock_map = {item.id: get_current_stock(db, item.id) for item in items}
    low_stock_items = [item for item in items if stock_map[item.id] <= item.reorder_level]

    invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    purchases = db.query(Purchase).order_by(Purchase.id.desc()).all()
    runs = db.query(ProductionRun).order_by(ProductionRun.id.desc()).all()
    ledger_entries = db.query(StockLedger).order_by(StockLedger.id.desc()).limit(100).all()
    audit_logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(50).all()
    user_map = {u.id: f"{u.full_name} ({u.role})" for u in db.query(User).all()}

    # Owner KPIs (Strict Decimal math)
    total_sales = sum((inv.total_amount for inv in invoices if not inv.is_cancelled), Decimal("0.00"))
    total_tax = sum((inv.cgst + inv.sgst + inv.igst for inv in invoices if not inv.is_cancelled), Decimal("0.00"))
    total_purchases = sum((p.total_amount for p in purchases), Decimal("0.00"))

    invoice_stats = {}
    total_outstanding = Decimal("0.00")
    for inv in invoices:
        paid = sum((p.amount for p in inv.payments), Decimal("0.00"))
        outstanding = inv.total_amount - paid
        invoice_stats[inv.id] = {"paid": paid, "outstanding": outstanding}
        if not inv.is_cancelled:
            total_outstanding += outstanding

    flagged_runs = sum(1 for r in runs if r.yield_flagged)
    flagged_materials = db.query(ProductionConsumption).filter(ProductionConsumption.is_flagged == True).count()

    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "user": user,
            "low_stock_items": low_stock_items,
            "stock_map": stock_map,
            "invoices": invoices,
            "invoice_stats": invoice_stats,
            "purchases": purchases,
            "runs": runs,
            "ledger_entries": ledger_entries,
            "audit_logs": audit_logs,
            "user_map": user_map,
            "kpis": {
                "total_sales": total_sales,
                "total_tax": total_tax,
                "total_outstanding": total_outstanding,
                "total_purchases": total_purchases,
                "flagged_count": flagged_runs + flagged_materials,
            },
        },
    )


@router.get("/export/excel")
def export_audit_excel(
    user: User = Depends(require_role("owner", "auditor", "admin")),
    db: Session = Depends(get_db),
):
    wb = Workbook()

    # Sheet 1: Sales & GST Register
    ws_sales = wb.active
    ws_sales.title = "Sales_GST_Register"
    ws_sales.append([
        "Invoice No", "Date", "Customer", "State", "GSTIN",
        "Taxable Value", "CGST", "SGST", "IGST", "Grand Total", "Paid", "Outstanding", "Dispatched"
    ])
    for inv in db.query(Invoice).order_by(Invoice.id.asc()).all():
        paid = sum((p.amount for p in inv.payments), Decimal("0.00"))
        ws_sales.append([
            inv.invoice_number,
            inv.invoice_date.strftime("%Y-%m-%d"),
            inv.customer.name,
            inv.customer.state,
            inv.customer.gstin or "",
            inv.taxable_value,
            inv.cgst,
            inv.sgst,
            inv.igst,
            inv.total_amount,
            paid,
            inv.total_amount - paid,
            "Yes" if inv.is_dispatched else "No",
        ])

    # Sheet 2: Purchase Register
    ws_purch = wb.create_sheet("Purchase_Register")
    ws_purch.append(["Purchase ID", "Date", "Supplier", "Item", "Qty", "Unit Rate", "Total Amount"])
    for p in db.query(Purchase).order_by(Purchase.id.asc()).all():
        ws_purch.append([
            p.id,
            p.purchase_date.strftime("%Y-%m-%d"),
            p.supplier.name,
            p.item.name,
            p.qty,
            p.unit_rate,
            p.total_amount,
        ])

    # Sheet 3: Stock Ledger
    ws_ledger = wb.create_sheet("Stock_Ledger")
    ws_ledger.append([
        "Ledger ID", "Timestamp", "Item", "Movement Type", "Qty Change",
        "Balance After", "Unit Cost", "Source Type", "Source ID", "Notes"
    ])
    for row in db.query(StockLedger).order_by(StockLedger.id.asc()).all():
        ws_ledger.append([
            row.id,
            row.timestamp.strftime("%Y-%m-%d %H:%M"),
            row.item.name,
            row.movement_type,
            row.qty_change,
            row.balance_after,
            row.unit_cost,
            row.source_type,
            row.source_id or "",
            row.notes or "",
        ])

    # Sheet 4: Production & Variances
    ws_prod = wb.create_sheet("Production_Variances")
    ws_prod.append([
        "Run ID", "Date", "Product", "Expected Output", "Actual Output",
        "Yield Var %", "Yield Flagged", "Material Cost", "Labour Cost", "Overhead Cost", "Cost/Packet"
    ])
    for r in db.query(ProductionRun).order_by(ProductionRun.id.asc()).all():
        ws_prod.append([
            r.id,
            r.run_date.strftime("%Y-%m-%d"),
            r.bom.finished_item.name,
            r.expected_output,
            r.actual_output,
            r.yield_variance_pct,
            "FLAGGED" if r.yield_flagged else "OK",
            r.material_cost,
            r.labour_cost,
            r.overhead_cost,
            r.cost_per_packet,
        ])

    # Sheet 5: Audit Trail
    ws_audit = wb.create_sheet("Audit_Trail")
    ws_audit.append(["Log ID", "Timestamp", "User", "Action", "Entity Type", "Entity ID", "Details"])
    user_map = {u.id: u.username for u in db.query(User).all()}
    for log in db.query(AuditLog).order_by(AuditLog.id.asc()).all():
        ws_audit.append([
            log.id,
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            user_map.get(log.user_id, str(log.user_id)),
            log.action,
            log.entity_type,
            log.entity_id,
            log.details or "",
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=order_to_audit_report.xlsx"},
    )


@router.get("/export/ledger-csv")
def export_ledger_csv(
    user: User = Depends(require_role("owner", "auditor", "admin")),
    db: Session = Depends(get_db),
):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Ledger ID", "Timestamp", "Item", "Movement Type", "Qty Change",
        "Balance After", "Unit Cost", "Source Type", "Source ID", "Notes"
    ])
    for row in db.query(StockLedger).order_by(StockLedger.id.asc()).all():
        writer.writerow([
            row.id,
            row.timestamp.strftime("%Y-%m-%d %H:%M"),
            row.item.name,
            row.movement_type,
            row.qty_change,
            row.balance_after,
            row.unit_cost,
            row.source_type,
            row.source_id or "",
            row.notes or "",
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=stock_ledger.csv"},
    )