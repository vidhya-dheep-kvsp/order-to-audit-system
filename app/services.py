from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import StockLedger


def get_current_stock(db: Session, item_id: int) -> Decimal:
    """Returns the latest closing balance for an item from the append-only StockLedger."""
    latest = (
        db.query(StockLedger)
        .filter(StockLedger.item_id == item_id)
        .order_by(StockLedger.id.desc())
        .first()
    )
    return latest.balance_after if latest else Decimal("0.000")