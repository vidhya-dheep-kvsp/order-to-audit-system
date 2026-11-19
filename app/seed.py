from decimal import Decimal
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.models import (
    User, Customer, Supplier, Item, BOMHeader, BOMLine, StockLedger
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed_database(db: Session):
    # Skip if already seeded
    if db.query(User).first():
        return

    # 1. Users (all 5 roles with simple demo password: "password123")
    pw = pwd_context.hash("password123")
    users = [
        User(username="salesman_a", full_name="Salesman A", password_hash=pw, role="salesman"),
        User(username="salesman_b", full_name="Salesman B", password_hash=pw, role="salesman"),
        User(username="admin", full_name="Factory Admin", password_hash=pw, role="admin"),
        User(username="supervisor", full_name="Production Supervisor", password_hash=pw, role="production"),
        User(username="auditor", full_name="External Auditor", password_hash=pw, role="auditor"),
        User(username="owner", full_name="Factory Owner", password_hash=pw, role="owner"),
    ]
    db.add_all(users)

    # 2. Customers & Supplier (Factory is in Tamil Nadu)
    customers = [
        Customer(
            name="Retailer A", customer_type="retailer", state="Tamil Nadu",
            gstin="33AABCR1234A1Z5", address="Madurai, Tamil Nadu"
        ),
        Customer(
            name="Distributor B", customer_type="distributor", state="Karnataka",
            gstin="29AABCD5678B1Z2", address="Bengaluru, Karnataka"
        ),
    ]
    supplier = Supplier(name="Kaveri Agro Mills", state="Tamil Nadu", gstin="33AABCK9999C1Z1")
    db.add_all(customers)
    db.add(supplier)

    # 3. Items (Raw Materials, Packaging, Finished Goods)
    flour = Item(name="Flour", category="raw_material", base_unit="kg", current_rate=Decimal("42.00"), reorder_level=Decimal("50.000"))
    oil = Item(name="Cooking Oil", category="raw_material", base_unit="litre", current_rate=Decimal("140.00"), reorder_level=Decimal("15.000"))
    spice = Item(name="Salt and Spice Mix", category="raw_material", base_unit="kg", current_rate=Decimal("200.00"), reorder_level=Decimal("3.000"))
    pouch = Item(name="200g Pouch", category="packaging", base_unit="piece", current_rate=Decimal("2.50"), reorder_level=Decimal("200.000"))
    carton = Item(name="Carton (20 packets)", category="packaging", base_unit="piece", current_rate=Decimal("15.00"), reorder_level=Decimal("10.000"))
    murukku = Item(
        name="Murukku 200g", category="finished_good", base_unit="packet",
        hsn_code="21069099", gst_rate=Decimal("5.00"), selling_price=Decimal("50.00"),
        current_rate=Decimal("0.00"), reorder_level=Decimal("50.000")
    )
    db.add_all([flour, oil, spice, pouch, carton, murukku])
    db.flush()  # Populate item IDs

    # 4. BOM for Murukku 200g (1 batch = 200 packets expected)
    bom = BOMHeader(finished_item_id=murukku.id, expected_yield=Decimal("200.000"), notes="Standard 200-packet batch")
    db.add(bom)
    db.flush()

    bom_lines = [
        BOMLine(bom_id=bom.id, component_item_id=flour.id, standard_qty=Decimal("40.000"), unit="kg"),
        BOMLine(bom_id=bom.id, component_item_id=oil.id, standard_qty=Decimal("10.000"), unit="litre"),
        BOMLine(bom_id=bom.id, component_item_id=spice.id, standard_qty=Decimal("1.200"), unit="kg"),
        BOMLine(bom_id=bom.id, component_item_id=pouch.id, standard_qty=Decimal("200.000"), unit="piece"),
        BOMLine(bom_id=bom.id, component_item_id=carton.id, standard_qty=Decimal("10.000"), unit="piece"),
    ]
    db.add_all(bom_lines)

    # 5. Opening Stock in StockLedger (Section 5 exact balances)
    opening_entries = [
        (flour, Decimal("100.000"), Decimal("42.00")),
        (oil, Decimal("30.000"), Decimal("140.00")),
        (spice, Decimal("5.000"), Decimal("200.00")),
        (pouch, Decimal("500.000"), Decimal("2.50")),
        (carton, Decimal("30.000"), Decimal("15.00")),
        (murukku, Decimal("50.000"), Decimal("0.00")),
    ]
    for item, qty, cost in opening_entries:
        db.add(StockLedger(
            item_id=item.id,
            movement_type="OPENING",
            qty_change=qty,
            balance_after=qty,
            unit_cost=cost,
            source_type="OPENING",
            source_id=None,
            notes="Section 5 benchmark opening stock"
        ))

    db.commit()