# Order-to-Audit System (Small Food Manufacturer ERP Prototype)

A containerized, relational B2B Manufacturing ERP built with **FastAPI**, **MySQL 8.0**, **SQLAlchemy**, and **Tailwind CSS**. Designed to connect the **Production Loop** (Purchases, BOM Consumption, Yield Variances, Costing) and the **Sales Loop** (Mobile Field Orders, GST Invoicing, Dispatch, Receivables) through a single **append-only Stock Ledger** and **Audit Trail**.

## Key Features
- **Strict `DECIMAL` Financial & Inventory Math:** Zero floating-point arithmetic (`Numeric(12, 2)` for currency, `Numeric(12, 3)` for quantities).
- **Append-Only `StockLedger`:** Current stock is never overwritten; every balance is derived from ledger rows traced back to a source document (`OPENING`, `PURCHASE`, `PRODUCTION_RUN`, `INVOICE`).
- **Weighted Average Costing & Variance Engine:** Automatically recalculates raw material rates on purchase, flags production yield and material variances exceeding `±3%`, and computes exact cost per packet including labour and overheads.
- **GST Tax Compliance:** Automatic **CGST/SGST** (intra-state Tamil Nadu) vs. **IGST** (inter-state) calculation with downloadable PDF Tax Invoices (`fpdf2`).
- **Role-Based Access Control (RBAC):** Dedicated workspaces for 5 roles (`salesman`, `production`, `admin`, `auditor`, `owner`).
- **Audit-Ready Exports:** One-click multi-sheet Excel workbook (`.xlsx` via `openpyxl`) and CSV Stock Ledger export.

---

## Quick Start (Docker Compose)

### Prerequisites
- Docker Desktop installed and running.

### 1. Boot the Application
```bash
git clone [https://github.com/vidhya-dheep-kvsp/order-to-audit-system.git](https://github.com/vidhya-dheep-kvsp/order-to-audit-system.git)
cd order-to-audit-system
docker compose up --build
```
*(First startup initializes MySQL 8.0 and automatically seeds the Section 5 benchmark master data and opening stock balances.)*

Open **http://localhost:8000** in your browser.

### 2. Demo Credentials
All seeded accounts use the password: **`password123`**

| Username | Role | Primary Workspace |
| :--- | :--- | :--- |
| `supervisor` | Production | `/production` (Purchases, BOM Runs, Overheads) |
| `salesman_a` | Salesman | `/sales/mobile` (Mobile-first Quick Order Entry) |
| `salesman_b` | Salesman | `/sales/mobile` (Mobile-first Quick Order Entry) |
| `admin` | Factory Admin | `/sales/admin` (Approvals, GST PDFs, Dispatch, Payments) |
| `owner` | Owner | `/reports` (KPI Dashboard, Low-Stock Alerts, Exports) |
| `auditor` | Auditor | `/reports` (Read-Only Registers, Ledger, Audit Trail, Exports) |

### 3. Run the Automated Benchmark Test Suite
Executes all 9 steps of the Section 5 benchmark scenario, RBAC checks, and export endpoints against an isolated in-memory database:
```bash
docker compose exec web python -m pytest -v
```

### 4. Reset Database to Clean Opening State
To wipe all transactions and re-seed the exact opening balances:
```bash
docker compose down -v
docker compose up -d
```

---

## Project Structure
```text
order-to-audit-system/
├── app/
│   ├── routers/          # auth.py, masters.py, production.py, sales.py, reports.py
│   ├── templates/        # Jinja2 + Tailwind CSS views (mobile & desktop)
│   ├── auth.py           # Session auth & require_role() dependency
│   ├── database.py       # SQLAlchemy engine & session management
│   ├── main.py           # FastAPI entrypoint & startup seeding
│   ├── models.py         # 14 relational tables with strict DECIMAL columns
│   ├── pdf_utils.py      # GST Tax Invoice PDF generator (fpdf2)
│   ├── seed.py           # Section 5 benchmark master data & opening ledger
│   └── services.py       # Core business logic (WAC, BOM, GST, Ledger, Audit)
├── tests/
│   └── test_benchmark.py # Automated 9-step benchmark & RBAC verification
├── docker-compose.yml
├── Dockerfile
├── DESIGN_NOTE.md        # Architecture, ER diagram, and costing methodology
└── requirements.txt
```