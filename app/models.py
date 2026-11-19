from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    # Roles: salesman, admin, production, auditor, owner
    role = Column(String(20), nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    customer_type = Column(String(20), nullable=False)  # retailer, distributor
    state = Column(String(50), nullable=False)          # e.g., Tamil Nadu, Karnataka
    gstin = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    state = Column(String(50), nullable=False)
    gstin = Column(String(20), nullable=True)


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    # Category: raw_material, packaging, finished_good
    category = Column(String(20), nullable=False)
    base_unit = Column(String(20), nullable=False)  # kg, litre, piece, packet
    hsn_code = Column(String(20), nullable=True)
    gst_rate = Column(Numeric(5, 2), default=Decimal("0.00"))
    selling_price = Column(Numeric(12, 2), default=Decimal("0.00"))
    current_rate = Column(Numeric(12, 2), default=Decimal("0.00"))  # Weighted avg / latest cost
    reorder_level = Column(Numeric(12, 3), default=Decimal("0.000"))


class BOMHeader(Base):
    __tablename__ = "bom_headers"

    id = Column(Integer, primary_key=True, index=True)
    finished_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    expected_yield = Column(Numeric(12, 3), nullable=False)  # e.g., 200 packets per batch
    notes = Column(String(255), nullable=True)

    finished_item = relationship("Item")
    lines = relationship("BOMLine", back_populates="bom", cascade="all, delete-orphan")


class BOMLine(Base):
    __tablename__ = "bom_lines"

    id = Column(Integer, primary_key=True, index=True)
    bom_id = Column(Integer, ForeignKey("bom_headers.id"), nullable=False)
    component_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    standard_qty = Column(Numeric(12, 3), nullable=False)  # Qty per 1 batch
    unit = Column(String(20), nullable=False)

    bom = relationship("BOMHeader", back_populates="lines")
    component_item = relationship("Item")


class StockLedger(Base):
    """Append-only ledger. Current stock is always derived from the latest balance_after."""
    __tablename__ = "stock_ledger"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    # OPENING, PURCHASE, PRODUCTION_ISSUE, PRODUCTION_OUTPUT, SALES_DISPATCH, ADJUSTMENT
    movement_type = Column(String(30), nullable=False)
    qty_change = Column(Numeric(12, 3), nullable=False)
    balance_after = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(12, 2), default=Decimal("0.00"))
    source_type = Column(String(30), nullable=False)  # OPENING, PURCHASE, PRODUCTION_RUN, INVOICE, ADJUSTMENT
    source_id = Column(Integer, nullable=True)
    notes = Column(String(255), nullable=True)

    item = relationship("Item")


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_rate = Column(Numeric(12, 2), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    purchase_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    supplier = relationship("Supplier")
    item = relationship("Item")


class ProductionRun(Base):
    __tablename__ = "production_runs"

    id = Column(Integer, primary_key=True, index=True)
    bom_id = Column(Integer, ForeignKey("bom_headers.id"), nullable=False)
    batch_count = Column(Numeric(10, 2), default=Decimal("1.00"), nullable=False)
    expected_output = Column(Numeric(12, 3), nullable=False)
    actual_output = Column(Numeric(12, 3), nullable=False)
    yield_variance_pct = Column(Numeric(6, 2), nullable=False)
    yield_flagged = Column(Boolean, default=False)
    material_cost = Column(Numeric(12, 2), default=Decimal("0.00"))
    labour_cost = Column(Numeric(12, 2), default=Decimal("0.00"))
    overhead_cost = Column(Numeric(12, 2), default=Decimal("0.00"))
    cost_per_packet = Column(Numeric(12, 2), default=Decimal("0.00"))
    run_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    bom = relationship("BOMHeader")
    consumptions = relationship("ProductionConsumption", back_populates="run", cascade="all, delete-orphan")


class ProductionConsumption(Base):
    __tablename__ = "production_consumptions"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    planned_qty = Column(Numeric(12, 3), nullable=False)
    actual_qty = Column(Numeric(12, 3), nullable=False)
    damaged_qty = Column(Numeric(12, 3), default=Decimal("0.000"))
    variance_pct = Column(Numeric(6, 2), nullable=False)
    is_flagged = Column(Boolean, default=False)
    unit_cost = Column(Numeric(12, 2), default=Decimal("0.00"))

    run = relationship("ProductionRun", back_populates="consumptions")
    item = relationship("Item")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    salesman_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # SUBMITTED, APPROVED, INVOICED, DISPATCHED, REJECTED
    status = Column(String(20), default="SUBMITTED", nullable=False)
    order_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(String(255), nullable=True)

    customer = relationship("Customer")
    salesman = relationship("User")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    item = relationship("Item")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(30), unique=True, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    invoice_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    taxable_value = Column(Numeric(12, 2), nullable=False)
    cgst = Column(Numeric(12, 2), default=Decimal("0.00"))
    sgst = Column(Numeric(12, 2), default=Decimal("0.00"))
    igst = Column(Numeric(12, 2), default=Decimal("0.00"))
    total_amount = Column(Numeric(12, 2), nullable=False)
    is_dispatched = Column(Boolean, default=False)
    is_cancelled = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    order = relationship("Order")
    customer = relationship("Customer")
    payments = relationship("Payment", back_populates="invoice")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    payment_mode = Column(String(30), default="BANK_TRANSFER")
    reference_no = Column(String(50), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    invoice = relationship("Invoice", back_populates="payments")
    customer = relationship("Customer")


class AuditLog(Base):
    """Logs edits to invoices, production runs, and key actions with user and timestamp."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)
    details = Column(Text, nullable=True)