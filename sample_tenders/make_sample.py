"""Generates two small dummy tender PDFs (with a real TOC) for testing the tool."""
from datetime import datetime, timedelta
import os
try:
    import pymupdf as fitz
except ImportError:
    import fitz

OUT = os.path.dirname(os.path.abspath(__file__))


def make(filename, days_to_deadline, equipment, pbg, emd, ld):
    close = (datetime.now() + timedelta(days=days_to_deadline)).strftime("%d-%m-%Y")
    opening = (datetime.now() + timedelta(days=days_to_deadline + 1)).strftime("%d-%m-%Y")
    sections = [
        ("Notice Inviting Tender", f"""Tender No: BEL/PKL/{filename[:6].upper()}/2026
Customer: Indian Army - Directorate of Signals
Item: {equipment}
Quantity: 24 Nos
Bid Type: Two Bid System
Bid End Date: {close}
Bid Opening Date: {opening}
Bid Validity: 180 days
Estimated Value: Rs. 4,50,00,000"""),
        ("Scope of Supply", "Scope of Work: Design, supply, installation and commissioning of the "
         "complete system including spares, documentation and operator training at user site."),
        ("Commercial Conditions", f"""EMD: {emd}
Performance Bank Guarantee of {pbg} of order value.
Liquidated Damages: {ld} per week of delay subject to maximum 10%.
Payment Terms: 90% on delivery and 10% after acceptance
Warranty: 2 years from date of acceptance"""),
        ("Special Conditions", """Non-Disclosure Agreement to be signed by the bidder.
Pre-Contract Integrity Pact (PCIP) is applicable.
Pre-dispatch inspection by DGQA at supplier works.
Delivery Period: 12 months from date of order
Consignee: Commandant, 21 Signal Regiment, Ambala Cantt, Haryana"""),
    ]
    doc = fitz.open()
    toc = []
    for i, (title, body) in enumerate(sections):
        page = doc.new_page()
        page.insert_text((50, 60), title, fontsize=16)
        page.insert_textbox(fitz.Rect(50, 90, 550, 780), body, fontsize=11)
        toc.append([1, title, i + 1])
    doc.set_toc(toc)
    doc.save(os.path.join(OUT, filename))
    doc.close()


if __name__ == "__main__":
    make("radar_tender_urgent.pdf", 4, "Low Level Light Weight Radar", "10%", "Rs. 9,00,000", "2%")
    make("comms_tender_relaxed.pdf", 75, "VHF Radio Sets", "5%", "Rs. 50,000", "0.5%")
    print("Sample tenders created in", OUT)
