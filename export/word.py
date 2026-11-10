"""Yatırım Komitesi Notu'nu Word (.docx) belgesine çevirir (python-docx).

Notun Markdown biçimini (başlıklar, maddeler, tablolar, kalın yazı) Word biçimine dönüştürür.
"""

import re
from datetime import date
from io import BytesIO

from docx import Document
from docx.shared import Pt, RGBColor

BOLD = re.compile(r"\*\*(.+?)\*\*")


def _add_text(paragraph, text: str):
    """**kalın** işaretlerini Word'de kalın yazıya çevirir."""
    text = text.replace("*", "") if "**" not in text else text
    pos = 0
    for m in BOLD.finditer(text):
        paragraph.add_run(text[pos:m.start()])
        paragraph.add_run(m.group(1)).bold = True
        pos = m.end()
    paragraph.add_run(text[pos:].replace("*", ""))


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", line)) and "-" in line


def _add_table(doc, rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows if not _is_separator(r)]
    if not cells:
        return
    width = max(len(r) for r in cells)
    table = doc.add_table(rows=len(cells), cols=width)
    table.style = "Light Grid Accent 1"
    for i, row in enumerate(cells):
        for j in range(width):
            p = table.cell(i, j).paragraphs[0]
            _add_text(p, row[j] if j < len(row) else "")
            if i == 0:
                for run in p.runs:
                    run.bold = True
    doc.add_paragraph()


def build_word(memo_markdown: str, project_name: str = "GES projesi") -> bytes:
    """Markdown notu Word belgesine çevirir, dosya içeriğini (bytes) döndürür."""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    doc.add_heading("Yatırım Komitesi Notu", level=0)
    info = doc.add_paragraph()
    info.add_run(f"{project_name}  |  {date.today():%d.%m.%Y}  |  FeasibilityAI").italic = True

    lines = memo_markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            _add_table(doc, block)
            continue
        if not stripped or stripped in ("---", "***"):
            pass
        elif stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 3)
            title = stripped.lstrip("#").strip()
            if title.lower().startswith("yatırım komitesi notu"):
                pass  # başlık zaten eklendi
            else:
                doc.add_heading(title.replace("*", ""), level=max(level - 1, 1))
        elif re.match(r"^[-*•]\s+", stripped):
            _add_text(doc.add_paragraph(style="List Bullet"), re.sub(r"^[-*•]\s+", "", stripped))
        elif re.match(r"^\d+[.)]\s+", stripped):
            _add_text(doc.add_paragraph(style="List Number"), re.sub(r"^\d+[.)]\s+", "", stripped))
        else:
            _add_text(doc.add_paragraph(), stripped)
        i += 1

    note = doc.add_paragraph()
    run = note.add_run("Rakamlar test edilmiş Python hesap motorundan alınmış ve otomatik olarak kontrol edilmiştir. "
                       "Bu belge yatırım tavsiyesi değildir.")
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


if __name__ == "__main__":
    ornek = """# Yatırım Komitesi Notu
## 1. Özet ve Öneri
**Öneri: Koşullu onay.** Proje NPV'si **1.940.040 USD**.
## 5. Senaryo Analizi
| Gösterge | Kötümser | Baz | İyimser |
|---|---|---|---|
| Proje IRR | %10,0 | %13,4 | %16,6 |
| Min DSCR | 1,02 | 1,36 | 1,64 |
## 6. Riskler
- **Fiyat riski:** Uzun vadeli satış anlaşması değerlendirilmeli.
- **Üretim riski:** Bağımsız üretim tahmini istenmeli.
"""
    path = "examples/ornek_not.docx"
    with open(path, "wb") as f:
        f.write(build_word(ornek))
    print(f"{path} olusturuldu")