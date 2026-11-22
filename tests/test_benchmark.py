from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, Customer, Supplier, Item, BOMHeader, StockLedger, AuditLog
from app.seed import seed_database
from app.services import (
    get_current_stock,
    record_purchase,
    record_production_run,
    update_run_overheads,
    create_sales_order,
    approve_and_invoice_order,
    dispatch_invoice,
    record_payment,
)

# Isolated in-memory SQLite DB so tests never touch your live MySQL data
SQLALCHEMY_TEST_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_database(db)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_full_section_5_benchmark(db_session):
    db = db_session

    # Fetch seeded master entities
    admin = db.query(User).filter_by(username="admin").first()
    supervisor = db.query(User).filter_by(username="supervisor").first()
    salesman_a = db.query(User).filter_by(username="salesman_a").first()
    salesman_b = db.query(User).filter_by(username="salesman_b").first()

    supplier = db.query(Supplier).first()
    retailer_a = db.query(Customer).filter_by(name="Retailer A").first()
    distributor_b = db.query(Customer).filter_by(name="Distributor B").first()

    flour = db.query(Item).filter_by(name="Flour").first()
    oil = db.query(Item).filter_by(name="Cooking Oil").first()
    spice = db.query(Item).filter_by(name="Salt and Spice Mix").first()
    pouch = db.query(Item).filter_by(name="200g Pouch").first()
    carton = db.query(Item).filter_by(name="Carton (20 packets)").first()
    murukku = db.query(Item).filter_by(name="Murukku 200g").first()
    bom = db.query(BOMHeader).first()

    # Step 1: Purchase 60 kg Flour @ Rs. 45/kg
    purchase = record_purchase(
        db=db,
        supplier_id=supplier.id,
        item_id=flour.id,
        qty=Decimal("60.000"),
        unit_rate=Decimal("45.00"),
        user_id=supervisor.id,
    )
    assert purchase.total_amount == Decimal("2700.00")
    assert get_current_stock(db, flour.id) == Decimal("160.000")
    # Weighted avg: (100*42 + 60*45) / 160 = 43.125 -> 43.13
    assert flour.current_rate == Decimal("43.13")

    # Step 2: Production Run (1 batch Murukku 200g -> 188 good packets)
    consumptions_data = [
        {"item_id": flour.id, "planned_qty": Decimal("40.000"), "actual_qty": Decimal("40.000"), "damaged_qty": Decimal("0.000")},
        {"item_id": oil.id, "planned_qty": Decimal("10.000"), "actual_qty": Decimal("10.500"), "damaged_qty": Decimal("0.000")},
        {"item_id": spice.id, "planned_qty": Decimal("1.200"), "actual_qty": Decimal("1.200"), "damaged_qty": Decimal("0.000")},
        {"item_id": pouch.id, "planned_qty": Decimal("200.000"), "actual_qty": Decimal("188.000"), "damaged_qty": Decimal("15.000")},
        {"item_id": carton.id, "planned_qty": Decimal("10.000"), "actual_qty": Decimal("10.000"), "damaged_qty": Decimal("0.000")},
    ]
    run = record_production_run(
        db=db,
        bom_id=bom.id,
        batch_count=Decimal("1.00"),
        actual_output=Decimal("188.000"),
        consumptions_data=consumptions_data,
        labour_cost=Decimal("0.00"),
        overhead_cost=Decimal("0.00"),
        user_id=supervisor.id,
    )

    # Verify exact post-production stock balances
    assert get_current_stock(db, flour.id) == Decimal("120.000")
    assert get_current_stock(db, oil.id) == Decimal("19.500")
    assert get_current_stock(db, spice.id) == Decimal("3.800")
    assert get_current_stock(db, pouch.id) == Decimal("297.000")
    assert get_current_stock(db, carton.id) == Decimal("20.000")
    assert get_current_stock(db, murukku.id) == Decimal("238.000")

    # Verify variance flags (>3% tolerance)
    assert run.yield_variance_pct == Decimal("-6.00")
    assert run.yield_flagged is True
    oil_cons = next(c for c in run.consumptions if c.item_id == oil.id)
    assert oil_cons.variance_pct == Decimal("5.00")
    assert oil_cons.is_flagged is True

    # Step 3 & 4: Intra-state Order (Retailer A, Tamil Nadu, 120 pkts) -> CGST/SGST
    order1 = create_sales_order(db, retailer_a.id, salesman_a.id, murukku.id, Decimal("120.000"))
    inv1 = approve_and_invoice_order(db, order1.id, admin.id)
    assert inv1.taxable_value == Decimal("6000.00")
    assert inv1.cgst == Decimal("150.00")
    assert inv1.sgst == Decimal("150.00")
    assert inv1.igst == Decimal("0.00")
    assert inv1.total_amount == Decimal("6300.00")

    # Step 5: Dispatch Invoice 1
    dispatch_invoice(db, inv1.id, admin.id)
    assert get_current_stock(db, murukku.id) == Decimal("118.000")

    # Step 6: Inter-state Order (Distributor B, Karnataka, 100 pkts) -> IGST + Dispatch
    order2 = create_sales_order(db, distributor_b.id, salesman_b.id, murukku.id, Decimal("100.000"))
    inv2 = approve_and_invoice_order(db, order2.id, admin.id)
    assert inv2.taxable_value == Decimal("5000.00")
    assert inv2.cgst == Decimal("0.00")
    assert inv2.sgst == Decimal("0.00")
    assert inv2.igst == Decimal("250.00")
    assert inv2.total_amount == Decimal("5250.00")

    dispatch_invoice(db, inv2.id, admin.id)
    assert get_current_stock(db, murukku.id) == Decimal("18.000")

    # Step 7: Partial Payments & Exact Outstanding Balance (Rs. 3,875.00)
    record_payment(db, inv1.id, Decimal("4000.00"), "BANK_TRANSFER", "UTR001", admin.id)
    record_payment(db, inv2.id, Decimal("3675.00"), "UPI", "UPI002", admin.id)

    due1 = inv1.total_amount - sum((p.amount for p in inv1.payments), Decimal("0.00"))
    due2 = inv2.total_amount - sum((p.amount for p in inv2.payments), Decimal("0.00"))
    assert due1 == Decimal("2300.00")
    assert due2 == Decimal("1575.00")
    assert (due1 + due2) == Decimal("3875.00")

    # Step 8: Overhead Allocation & Cost per Packet
    updated_run = update_run_overheads(db, run.id, Decimal("800.00"), Decimal("400.00"), supervisor.id)
    # Material: 4092.70 + Labour: 800.00 + Overhead: 400.00 = 5292.70 / 188 = 28.15
    assert updated_run.material_cost == Decimal("4092.70")
    assert updated_run.cost_per_packet == Decimal("28.15")

    # Step 9: Ledger & Audit Trail Integrity
    assert db.query(StockLedger).count() == 15  # 6 opening + 1 purchase + 6 prod + 2 dispatches
    assert db.query(AuditLog).count() >= 10


def test_rbac_and_exports(client):
    # Login as auditor (read-only)
    resp = client.post("/login", data={"username": "auditor", "password": "password123"}, follow_redirects=False)
    assert resp.status_code == 303

    # Auditor can access reports and exports
    assert client.get("/reports").status_code == 200
    assert client.get("/reports/export/excel").status_code == 200
    assert client.get("/reports/export/ledger-csv").status_code == 200

    # Auditor CANNOT access admin sales or production floor
    assert client.get("/sales/admin").status_code == 403
    assert client.get("/production").status_code == 403