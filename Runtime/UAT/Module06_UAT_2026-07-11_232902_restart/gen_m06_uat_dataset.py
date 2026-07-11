import os, zipfile, struct
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image, ImageDraw
from pypdf import PdfWriter, PdfReader
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TDRC

OUT = "/tmp/uat_m06_downloads_restart"
os.makedirs(OUT, exist_ok=True)

def make_pdf(path, lines, font_size=11):
    c = canvas.Canvas(path, pagesize=letter)
    y = 750
    for line in lines:
        if line == "<<<PAGEBREAK>>>":
            c.showPage()
            y = 750
            continue
        c.setFont("Helvetica", font_size)
        c.drawString(72, y, line)
        y -= 16
        if y < 60:
            c.showPage()
            y = 750
    c.save()

# 1. Clean invoice
make_pdf(f"{OUT}/Invoice_Northwind_Traders.pdf", [
    "INVOICE", "",
    "Northwind Traders",
    "228 Harbor Ave, Seattle, WA", "",
    "Invoice Number: INV-88213",
    "Invoice Date: 2026-06-15",
    "Bill To: Redwood Consulting LLC", "",
    "Description                Qty   Price     Total",
    "Office Supplies Bundle      1   $1,200.00  $1,200.00",
    "Consulting Services        10   $ 303.00  $3,030.00", "",
    "Subtotal: $4,230.00",
    "Tax (Sales Tax): $0.00",
    "Total Amount Due: $4,230.00 USD", "",
    "Payment due within 30 days.",
])

# 2. Sparse draft invoice
make_pdf(f"{OUT}/Invoice_Sparse_Draft.pdf", [
    "DRAFT -- NOT FINAL", "",
    "Preliminary billing note for supplies delivered last week.",
    "Amount to be confirmed once final pricing is received from procurement.",
    "Please treat as a placeholder only.", "",
    "Date: 2026-05-02",
])

# 3. Ambiguous invoice/receipt
make_pdf(f"{OUT}/Receipt_Or_Invoice_Ambiguous.pdf", [
    "THANK YOU FOR YOUR PURCHASE", "",
    "Riverside Cafe & Goods",
    "Transaction Receipt / Invoice Copy", "",
    "Item: Catering Package - Corporate Lunch (25 guests)",
    "Amount Charged: $612.50",
    "Date: 2026-06-20",
    "Payment Method: Corporate Account (Net 15 terms apply)", "",
    "This document serves as both your official invoice for",
    "accounting purposes and your receipt of payment on account.",
])

# 4. French invoice (non-English)
make_pdf(f"{OUT}/Facture_Boulangerie_Paris.pdf", [
    "FACTURE", "",
    "Boulangerie Saint-Germain",
    "15 Rue de Rivoli, 75004 Paris, France", "",
    "Facture N : FR-2026-0417",
    "Date de facturation : 12/06/2026",
    "Client : Cafe du Marche", "",
    "Designation                    Qte   Prix Unit.   Total",
    "Pain de campagne (livraison)    50   1,20          60,00",
    "Croissants au beurre           200   0,85         170,00", "",
    "Sous-total : 230,00 EUR",
    "TVA (20%) : 46,00 EUR",
    "Montant Total Du : 276,00 EUR", "",
    "Paiement a reception, merci. Nous vous remercions",
    "pour votre confiance et votre fidelite depuis de nombreuses annees.",
])

# 5. Multi-document batch invoice
make_pdf(f"{OUT}/Batch_Invoices_Merged.pdf", [
    "INVOICE #A-1001",
    "Vendor: Cascade Hardware",
    "Date: 2026-04-01",
    "Total: $340.00",
    "<<<PAGEBREAK>>>",
    "INVOICE #A-1002",
    "Vendor: Pinegrove Electric",
    "Date: 2026-04-03",
    "Total: $912.40",
    "<<<PAGEBREAK>>>",
    "INVOICE #A-1003",
    "Vendor: Cascade Hardware",
    "Date: 2026-04-05",
    "Total: $128.75",
])

# 6. Password-protected (locked) PDF
tmp_locked = f"{OUT}/_tmp_payroll.pdf"
make_pdf(tmp_locked, [
    "CONFIDENTIAL PAYROLL STATEMENT", "",
    "Employee: J. Rivera",
    "Pay Period: June 2026",
    "Net Pay: $4,102.55",
])
reader = PdfReader(tmp_locked)
writer = PdfWriter()
for p in reader.pages:
    writer.add_page(p)
writer.encrypt(user_password="letmein2026", owner_password="ownerpw2026")
with open(f"{OUT}/Confidential_Payroll_Statement.pdf", "wb") as f:
    writer.write(f)
os.remove(tmp_locked)

# 7. Blank/no-extractable-text PDF
c = canvas.Canvas(f"{OUT}/Scan_Blank_Page.pdf", pagesize=letter)
c.showPage()
c.save()

# 8/9. Resume version chain
make_pdf(f"{OUT}/Resume_Morgan_Ellis_v1.pdf", [
    "MORGAN ELLIS",
    "Software Engineer", "",
    "EXPERIENCE",
    "Junior Developer, TechCorp -- 2023-2025",
    "Built internal tooling in Python.", "",
    "EDUCATION",
    "B.S. Computer Science, State University, 2023",
])
make_pdf(f"{OUT}/Resume_Morgan_Ellis_v2.pdf", [
    "MORGAN ELLIS",
    "Senior Software Engineer", "",
    "EXPERIENCE",
    "Senior Developer, TechCorp -- 2025-Present",
    "Led migration of internal tooling to a microservices architecture.",
    "Junior Developer, TechCorp -- 2023-2025",
    "Built internal tooling in Python.", "",
    "EDUCATION",
    "B.S. Computer Science, State University, 2023", "",
    "Last Updated: 2026-05-10",
])

# 10/11. Bank statement exact-duplicate pair
bank_lines = [
    "CHASE BANK",
    "Monthly Statement", "",
    "Statement Period: June 1 - June 30, 2026",
    "Account holder: Redwood Consulting LLC",
    "Account Number ending: 4821", "",
    "Beginning Balance: $12,340.00",
    "Ending Balance: $15,102.44",
]
make_pdf(f"{OUT}/BankStatement_Chase_June2026.pdf", bank_lines)
make_pdf(f"{OUT}/BankStatement_Chase_June2026_copy.pdf", bank_lines)

# 12/13. Contract version chain WITH conflict
make_pdf(f"{OUT}/Contract_ServiceAgreement_v1.pdf", [
    "SERVICE AGREEMENT", "",
    "This Service Agreement (\"Agreement\") is entered into between",
    "Meridian Consulting Group (\"Provider\") and Oakview Retail Inc. (\"Client\").", "",
    "Contract Type: Service Agreement",
    "Counterparty: Oakview Retail Inc.",
    "Effective Date: March 1, 2026",
    "Term Length: 12 months", "",
    "Both parties agree to the terms set forth herein.",
])
make_pdf(f"{OUT}/Contract_ServiceAgreement_v2.pdf", [
    "SERVICE AGREEMENT (REVISED - CORRECTED COPY)", "",
    "This Service Agreement (\"Agreement\") is entered into between",
    "Meridian Consulting Group (\"Provider\") and Oakview Retail Inc. (\"Client\").", "",
    "Contract Type: Service Agreement",
    "Counterparty: Oakview Retail Inc.",
    "Effective Date: January 15, 2026",
    "Term Length: 12 months", "",
    "Note: This corrected copy restates the original effective date,",
    "which was misprinted in an earlier draft circulated internally.", "",
    "Both parties agree to the terms set forth herein.",
])

# 14/15. Near-duplicate images
def draw_product(path, offset=0, color=(200,120,60)):
    img = Image.new("RGB", (600, 400), (245,245,245))
    d = ImageDraw.Draw(img)
    d.rectangle([100+offset, 100, 400+offset, 300], fill=color, outline=(30,30,30), width=4)
    d.ellipse([420+offset, 140, 520+offset, 240], fill=(80,140,200), outline=(30,30,30), width=3)
    img.save(path, "JPEG")

draw_product(f"{OUT}/Product_Shot_Front.jpg", offset=0, color=(200,120,60))
draw_product(f"{OUT}/Product_Shot_Angle.jpg", offset=8, color=(205,124,64))

# 16. Document
make_pdf(f"{OUT}/Document_Employee_Handbook.pdf", [
    "EMPLOYEE HANDBOOK", "",
    "Welcome to Lighthouse Analytics. This handbook outlines company",
    "policies regarding remote work, paid time off, and code of conduct.", "",
    "Section 1: Remote Work Policy",
    "Employees may work remotely up to three days per week.", "",
    "Section 2: Paid Time Off",
    "Full-time employees accrue 15 days of PTO annually.", "",
    "Last revised: 2026-04-18",
])

# 17. Screenshot (no EXIF, screen-like dims)
img = Image.new("RGB", (1440, 900), (235,235,240))
d = ImageDraw.Draw(img)
d.rectangle([520, 340, 920, 560], fill=(255,255,255), outline=(120,120,120), width=2)
d.rectangle([540, 370, 900, 400], fill=(255,225,225), outline=(200,60,60), width=2)
d.text((550, 378), "Error: Invalid username or password", fill=(180,30,30))
d.rectangle([650, 470, 790, 505], fill=(60,110,220))
d.text((680, 480), "Try Again", fill=(255,255,255))
img.save(f"{OUT}/Screenshot_Login_Error.png", "PNG")

# 18. Application installer (deterministic filename-parsed, dummy bytes)
with open(f"{OUT}/Zoom_Installer_6.1.2.dmg", "wb") as f:
    f.write(b"DUMMY_DMG_CONTAINER_BYTES_NOT_A_REAL_DISK_IMAGE" * 10)

# 19. Archive with real member files
with zipfile.ZipFile(f"{OUT}/Project_Archive_2026.zip", "w") as z:
    z.writestr("notes.txt", "Project kickoff notes for the 2026 renovation project.\n")
    z.writestr("budget.csv", "item,cost\nlumber,1200\npermits,450\n")

# 20. Video (deterministic filename-parsed, dummy bytes)
with open(f"{OUT}/Family_Vacation_Clip.mp4", "wb") as f:
    f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200)

# 21. Audio with real ID3 tags
with open(f"{OUT}/Voice_Memo_070826.mp3", "wb") as f:
    # minimal valid-ish MP3 frame header repeated, mutagen needs a parseable mp3
    f.write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
try:
    audio = MP3(f"{OUT}/Voice_Memo_070826.mp3")
    audio["TIT2"] = TIT2(encoding=3, text="Client Call Notes")
    audio["TPE1"] = TPE1(encoding=3, text="Vicky")
    audio["TDRC"] = TDRC(encoding=3, text="2026")
    audio.save()
    print("MP3 ID3 tags written OK")
except Exception as e:
    print("MP3 tagging failed:", e)

# 22. Corrupted / malformed PDF (fails to parse)
with open(f"{OUT}/Corrupted_Invoice_Damaged.pdf", "wb") as f:
    f.write(b"%PDF-1.4\n%garbage-truncated-stream-not-a-real-pdf-body\n" + os.urandom(120))

# 23. Adversarial filename, valid content
make_pdf(f"{OUT}/invoice_\U0001F9FE_northstar_—_v2.pdf", [
    "INVOICE", "",
    "North Star Freight Co.", "",
    "Invoice Number: NS-3390",
    "Invoice Date: 2026-06-28",
    "Amount Due: $980.00 USD",
    "Tax Type: None",
])

# 24. Zero-byte (Module 01 skip path)
open(f"{OUT}/zero_byte_file.pdf", "wb").close()

# 25. Unsupported extension (Module 01 skip path)
with open(f"{OUT}/mystery_notes.xyz", "w") as f:
    f.write("not a supported file type")

print("Generated", len(os.listdir(OUT)), "files in", OUT)
for name in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, name)
    print(f"  {name}  ({os.path.getsize(p)} bytes)")
