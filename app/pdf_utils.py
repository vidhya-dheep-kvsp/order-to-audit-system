from fpdf import FPDF
from app.models import Invoice


def generate_invoice_pdf(invoice: Invoice) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "TAX INVOICE", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "SnackFactory Foods Pvt. Ltd. | Madurai, Tamil Nadu | GSTIN: 33AABCS1234F1Z5", ln=True, align="C")
    pdf.ln(5)

    # Invoice & Customer Details
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(95, 6, f"Invoice No: {invoice.invoice_number}")
    pdf.cell(95, 6, f"Date: {invoice.invoice_date.strftime('%Y-%m-%d')}", ln=True, align="R")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 6, f"Customer: {invoice.customer.name} ({invoice.customer.customer_type.title()})")
    pdf.cell(95, 6, f"State: {invoice.customer.state}", ln=True, align="R")
    pdf.cell(95, 6, f"GSTIN: {invoice.customer.gstin or 'Unregistered'}")
    pdf.cell(95, 6, f"Order Ref: #{invoice.order_id}", ln=True, align="R")
    pdf.ln(6)

    # Line Items Table Header
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(70, 8, "Item", border=1, fill=True)
    pdf.cell(25, 8, "HSN", border=1, fill=True, align="C")
    pdf.cell(25, 8, "Qty", border=1, fill=True, align="R")
    pdf.cell(35, 8, "Rate (Rs.)", border=1, fill=True, align="R")
    pdf.cell(35, 8, "Amount (Rs.)", border=1, fill=True, align="R", ln=True)

    # Line Items Rows
    pdf.set_font("Helvetica", "", 10)
    for line in invoice.order.items:
        line_total = line.qty * line.unit_price
        pdf.cell(70, 8, line.item.name, border=1)
        pdf.cell(25, 8, line.item.hsn_code or "-", border=1, align="C")
        pdf.cell(25, 8, f"{line.qty:.0f}", border=1, align="R")
        pdf.cell(35, 8, f"{line.unit_price:.2f}", border=1, align="R")
        pdf.cell(35, 8, f"{line_total:.2f}", border=1, align="R", ln=True)

    pdf.ln(4)

    # Tax Breakdown
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(155, 7, "Taxable Value:", align="R")
    pdf.cell(35, 7, f"Rs. {invoice.taxable_value:.2f}", align="R", ln=True)

    if invoice.igst > 0:
        pdf.cell(155, 7, "IGST (Inter-State):", align="R")
        pdf.cell(35, 7, f"Rs. {invoice.igst:.2f}", align="R", ln=True)
    else:
        pdf.cell(155, 7, "CGST (Intra-State):", align="R")
        pdf.cell(35, 7, f"Rs. {invoice.cgst:.2f}", align="R", ln=True)
        pdf.cell(155, 7, "SGST (Intra-State):", align="R")
        pdf.cell(35, 7, f"Rs. {invoice.sgst:.2f}", align="R", ln=True)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(155, 9, "Grand Total:", align="R")
    pdf.cell(35, 9, f"Rs. {invoice.total_amount:.2f}", align="R", ln=True)

    return bytes(pdf.output())