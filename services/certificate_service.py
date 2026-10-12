from __future__ import annotations

from pathlib import Path

from database.features import get_certificate, issue_certificate

BASE_DIR = Path(__file__).resolve().parent.parent
CERT_DIR = BASE_DIR / "certificates"


def _font_path() -> Path | None:
    candidates = [
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def build_certificate_pdf(telegram_id: int, display_name: str) -> tuple[dict, Path]:
    record = issue_certificate(telegram_id, display_name)
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    output = CERT_DIR / f"{record['id']}.pdf"
    if output.is_file():
        return record, output

    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    font_file = _font_path()
    if font_file is not None:
        pdf.add_font("UI", "", str(font_file))
        pdf.set_font("UI", size=22)
    else:
        pdf.set_font("Helvetica", size=22)
    pdf.set_text_color(10, 30, 60)
    pdf.cell(0, 18, "CyberUstozBot", ln=True, align="C")
    if font_file is not None:
        pdf.set_font("UI", size=16)
    else:
        pdf.set_font("Helvetica", size=16)
    pdf.ln(8)
    pdf.cell(0, 12, "Ta'lim sertifikati / Educational certificate", ln=True, align="C")
    pdf.ln(10)
    pdf.cell(0, 12, record["display_name"], ln=True, align="C")
    pdf.ln(6)
    pdf.set_font("Helvetica" if font_file is None else "UI", size=12)
    pdf.multi_cell(
        0,
        8,
        "Kiberxavfsizlik asoslari kursi (ta'limiy, davlat diplomi emas).\n"
        f"Sana: {record['issued_at']}\nID: {record['id']}",
        align="C",
    )
    pdf.output(str(output))
    return record, output


def verify_certificate(cert_id: str) -> dict | None:
    return get_certificate(cert_id)
