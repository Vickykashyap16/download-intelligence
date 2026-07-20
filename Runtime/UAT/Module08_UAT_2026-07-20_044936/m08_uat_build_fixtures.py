from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image, ImageDraw
import pypdf
from pathlib import Path

D = Path("/tmp/uat_m08_downloads")

def make_pdf(path, lines):
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 750
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()

# 1. Clean invoice, every field present
make_pdf(D / "Invoice_CloudHosting_Vendor.pdf", [
    "INVOICE",
    "Vendor: NimbusHost Cloud Services",
    "Invoice Date: 2026-07-15",
    "Invoice Number: NH-88213",
    "Amount: 249.00",
    "Currency: USD",
    "Tax Type: VAT",
    "Thank you for your business.",
])

# 2. Resume, candidate name present
make_pdf(D / "Resume_Morgan_Taylor.pdf", [
    "Morgan Taylor",
    "Senior Product Designer",
    "Experience: 8 years in UX/UI design across fintech and healthcare.",
    "Skills: Figma, user research, design systems.",
    "Contact: morgan.taylor@example.com",
])

# 3. Sparse receipt - only required fields, optional fields absent
make_pdf(D / "Receipt_Coffee_Shop.pdf", [
    "RECEIPT",
    "Vendor: Corner Coffee Co",
    "Date: 2026-07-16",
    "Thanks for stopping by!",
])

# 4. Screenshot - drawn image, no EXIF, error dialog look
img = Image.new("RGB", (800, 500), color=(240, 240, 245))
draw = ImageDraw.Draw(img)
draw.rectangle([200, 150, 600, 350], fill=(255, 255, 255), outline=(200, 0, 0), width=3)
draw.text((230, 180), "Error: Connection timed out", fill=(200, 0, 0))
draw.text((230, 220), "Unable to reach sync server.", fill=(50, 50, 50))
draw.rectangle([450, 300, 560, 330], fill=(220, 220, 220), outline=(100, 100, 100))
draw.text((480, 308), "Retry", fill=(0, 0, 0))
img.save(D / "Screenshot_ErrorDialog.png")

# 5. Locked/password-protected contract
tmp_unlocked = D / "_tmp_contract.pdf"
make_pdf(tmp_unlocked, [
    "MUTUAL NON-DISCLOSURE AGREEMENT",
    "Between Northwind Partners and Vega Analytics",
    "Effective Date: 2026-07-10",
    "Confidential.",
])
reader = pypdf.PdfReader(str(tmp_unlocked))
writer = pypdf.PdfWriter()
for page in reader.pages:
    writer.add_page(page)
writer.encrypt(user_password="secret123")
with open(D / "Locked_NDA_Contract.pdf", "wb") as f:
    writer.write(f)
tmp_unlocked.unlink()

# 6. Exact duplicate text pair
notes = "Meeting Notes - Q3 Planning\n\nAttendees: Sam, Priya, Deon\nDecisions: ship v2 by Aug 1.\nAction items: finalize budget, confirm vendor.\n"
(D / "Old_Meeting_Notes.txt").write_text(notes)
(D / "Old_Meeting_Notes_backup.txt").write_text(notes)

# 7. Version chain - similar filenames, related but different content
make_pdf(D / "Budget_Plan_v1.pdf", [
    "BUDGET PLAN - DRAFT 1",
    "Department: Marketing",
    "Total: $45,000",
    "Status: draft, pending review",
])
make_pdf(D / "Budget_Plan_v2.pdf", [
    "BUDGET PLAN - DRAFT 2",
    "Department: Marketing",
    "Total: $52,000",
    "Status: revised after stakeholder feedback",
])

print("Built", len(list(D.iterdir())), "files:")
for p in sorted(D.iterdir()):
    print(" -", p.name, p.stat().st_size, "bytes")
