from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from app.models import (
    Item, StockLedger, Purchase, BOMHeader,
    ProductionRun, ProductionConsumption, AuditLog
)

VARIANCE_TOLERANCE_PCT = Decimal("3.00")


def round2(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_current_stock(db: Session, item_id: int) -> Decimal:
    """Returns the latest closing balance for an item from the append-only StockLedger."""
    latest = (
        db.query(StockLedger)
        .filter(StockLedger.item_id == item_id)
        .order_by(StockLedger.id.desc())
        .first()
    )
    return latest.balance_after if latest else Decimal("0.000")


def record_stock_movement(
    db: Session,
    item_id: int,
    movement_type: str,
    qty_change: Decimal,
    unit_cost: Decimal,
    source_type: str,
    source_id: int | None,
    notes: str = "",
) -> StockLedger:
    """Appends a new row to StockLedger. Never overwrites stock balances."""
    current_bal = get_current_stock(db, item_id)
    new_bal = current_bal + qty_change
    entry = StockLedger(
        item_id=item_id,
        movement_type=movement_type,
        qty_change=qty_change,
        balance_after=new_bal,
        unit_cost=round2(unit_cost),
        source_type=source_type,
        source_id=source_id,
        notes=notes,
    )
    db.add(entry)
    db.flush()
    return entry


def log_audit(db: Session, user_id: int, action: str, entity_type: str, entity_id: int, details: str):
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    ))


def record_purchase(
    db: Session,
    supplier_id: int,
    item_id: int,
    qty: Decimal,
    unit_rate: Decimal,
    user_id: int,
) -> Purchase:
    item = db.query(Item).filter(Item.id == item_id).first()
    old_qty = get_current_stock(db, item_id)
    old_val = old_qty * item.current_rate
    new_val = qty * unit_rate
    total_qty = old_qty + qty

    # Weighted Average Cost update
    if total_qty > 0:
        item.current_rate = round2((old_val + new_val) / total_qty)

    purchase = Purchase(
        supplier_id=supplier_id,
        item_id=item_id,
        qty=qty,
        unit_rate=round2(unit_rate),
        total_amount=round2(new_val),
        created_by=user_id,
    )
    db.add(purchase)
    db.flush()

    record_stock_movement(
        db=db,
        item_id=item_id,
        movement_type="PURCHASE",
        qty_change=qty,
        unit_cost=unit_rate,
        source_type="PURCHASE",
        source_id=purchase.id,
        notes=f"Purchase #{purchase.id} @ ₹{unit_rate}",
    )
    log_audit(db, user_id, "CREATE_PURCHASE", "PURCHASE", purchase.id, f"Purchased {qty} of {item.name} @ ₹{unit_rate}")
    db.commit()
    return purchase


def record_production_run(
    db: Session,
    bom_id: int,
    batch_count: Decimal,
    actual_output: Decimal,
    consumptions_data: list[dict],
    labour_cost: Decimal,
    overhead_cost: Decimal,
    user_id: int,
) -> ProductionRun:
    bom = db.query(BOMHeader).filter(BOMHeader.id == bom_id).first()
    expected_output = bom.expected_yield * batch_count

    yield_var_pct = round2(((actual_output - expected_output) / expected_output) * Decimal("100"))
    yield_flagged = abs(yield_var_pct) > VARIANCE_TOLERANCE_PCT

    run = ProductionRun(
        bom_id=bom.id,
        batch_count=batch_count,
        expected_output=expected_output,
        actual_output=actual_output,
        yield_variance_pct=yield_var_pct,
        yield_flagged=yield_flagged,
        labour_cost=round2(labour_cost),
        overhead_cost=round2(overhead_cost),
        created_by=user_id,
    )
    db.add(run)
    db.flush()

    total_material_cost = Decimal("0.00")

    for row in consumptions_data:
        item = db.query(Item).filter(Item.id == row["item_id"]).first()
        planned_qty = row["planned_qty"]
        actual_qty = row["actual_qty"]
        damaged_qty = row["damaged_qty"]
        total_deducted = actual_qty + damaged_qty

        # Variance compares total consumed (actual + damaged) against planned BOM
        var_pct = round2(((total_deducted - planned_qty) / planned_qty) * Decimal("100")) if planned_qty > 0 else Decimal("0.00")
        is_flagged = abs(var_pct) > VARIANCE_TOLERANCE_PCT

        line_cost = round2(total_deducted * item.current_rate)
        total_material_cost += line_cost

        db.add(ProductionConsumption(
            run_id=run.id,
            item_id=item.id,
            planned_qty=planned_qty,
            actual_qty=actual_qty,
            damaged_qty=damaged_qty,
            variance_pct=var_pct,
            is_flagged=is_flagged,
            unit_cost=item.current_rate,
        ))

        record_stock_movement(
            db=db,
            item_id=item.id,
            movement_type="PRODUCTION_ISSUE",
            qty_change=-total_deducted,
            unit_cost=item.current_rate,
            source_type="PRODUCTION_RUN",
            source_id=run.id,
            notes=f"Run #{run.id}: {actual_qty} used + {damaged_qty} damaged",
        )

    run.material_cost = round2(total_material_cost)
    total_run_cost = run.material_cost + run.labour_cost + run.overhead_cost
    run.cost_per_packet = round2(total_run_cost / actual_output) if actual_output > 0 else Decimal("0.00")

    # Update finished good stock and cost rate
    finished_item = bom.finished_item
    finished_item.current_rate = run.cost_per_packet

    record_stock_movement(
        db=db,
        item_id=finished_item.id,
        movement_type="PRODUCTION_OUTPUT",
        qty_change=actual_output,
        unit_cost=run.cost_per_packet,
        source_type="PRODUCTION_RUN",
        source_id=run.id,
        notes=f"Run #{run.id} output ({actual_output} good packets)",
    )

    log_audit(db, user_id, "CREATE_PRODUCTION_RUN", "PRODUCTION_RUN", run.id, f"Output {actual_output}/{expected_output} (Var: {yield_var_pct}%)")
    db.commit()
    return run


def update_run_overheads(
    db: Session,
    run_id: int,
    labour_cost: Decimal,
    overhead_cost: Decimal,
    user_id: int,
) -> ProductionRun:
    run = db.query(ProductionRun).filter(ProductionRun.id == run_id).first()
    run.labour_cost = round2(labour_cost)
    run.overhead_cost = round2(overhead_cost)
    total_run_cost = run.material_cost + run.labour_cost + run.overhead_cost
    run.cost_per_packet = round2(total_run_cost / run.actual_output) if run.actual_output > 0 else Decimal("0.00")

    # Update finished good cost rate
    run.bom.finished_item.current_rate = run.cost_per_packet

    log_audit(
        db, user_id, "UPDATE_OVERHEADS", "PRODUCTION_RUN", run.id,
        f"Updated labour=₹{run.labour_cost}, overhead=₹{run.overhead_cost}, cost/pkt=₹{run.cost_per_packet}"
    )
    db.commit()
    return run