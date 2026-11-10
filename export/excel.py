"""Formülleri çalışan Excel modeli (openpyxl).

- 'Varsayimlar': girdiler (mavi yazı = değiştirilebilir girdi)
- 'Model': yıllara göre nakit akışı ve kredi tablosu; hücrelerin hepsi Excel formülü
- 'Ozet': Excel formülü sonuçları ile Python hesap motoru sonuçlarının karşılaştırması
Not: Yıl sütunları dosya oluşturulurken proje ömrüne göre açılır.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from engine.assumptions import SolarAssumptions
from engine.cashflow import project_returns
from engine.debt import equity_returns

INPUT_FONT = Font(color="0000FF")
BOLD = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
MONEY = "#,##0"
PCT = "0.0%"
PCT2 = "0.00%"

INPUT_ROWS = [  # (etiket, alan adı, birim, biçim)
    ("Kurulu güç", "capacity_mwp", "MWp", "0.0"),
    ("İşletme süresi", "project_life_years", "yıl", "0"),
    ("Yatırım maliyeti", "capex_per_mwp", "USD/MWp", MONEY),
    ("İlk yıl üretim", "specific_yield_mwh_per_mwp", "MWh/MWp", MONEY),
    ("Yıllık verim kaybı", "degradation_rate", "", PCT2),
    ("Elektrik fiyatı (ilk yıl)", "electricity_price_per_mwh", "USD/MWh", "0.00"),
    ("Yıllık fiyat artışı", "price_escalation", "", PCT),
    ("OPEX", "opex_per_mwp_year", "USD/MWp/yıl", MONEY),
    ("Yıllık OPEX artışı", "opex_escalation", "", PCT),
    ("Kurumlar vergisi", "tax_rate", "", PCT),
    ("Amortisman süresi", "depreciation_years", "yıl", "0"),
    ("Kredi oranı", "debt_ratio", "", PCT),
    ("Kredi faizi", "interest_rate", "", PCT2),
    ("Kredi vadesi", "loan_tenor_years", "yıl", "0"),
    ("İskonto oranı (WACC)", "discount_rate", "", PCT),
]


def _header(ws, values):
    ws.append(values)
    for cell in ws[ws.max_row]:
        cell.font = BOLD
        cell.fill = HEADER_FILL


def _inputs_sheet(wb: Workbook, a: SolarAssumptions) -> dict:
    ws = wb.active
    ws.title = "Varsayimlar"
    _header(ws, ["Varsayım", "Değer", "Birim"])

    refs = {}
    for row, (label, field, unit, fmt) in enumerate(INPUT_ROWS, start=2):
        ws.cell(row, 1, label)
        cell = ws.cell(row, 2, getattr(a, field))
        cell.font = INPUT_FONT
        cell.number_format = fmt
        ws.cell(row, 3, unit)
        refs[field] = f"$B${row}"

    r = len(INPUT_ROWS) + 3
    derived = [
        ("total", "Toplam yatırım", f"={refs['capacity_mwp']}*{refs['capex_per_mwp']}"),
        ("debt", "Kredi tutarı", f"=B{r}*{refs['debt_ratio']}"),
        ("equity", "Öz kaynak", f"=B{r}-B{r + 1}"),
        ("payment", "Yıllık kredi taksiti",
         f"=IF(B{r + 1}=0,0,PMT({refs['interest_rate']},{refs['loan_tenor_years']},-B{r + 1}))"),
    ]
    for i, (key, label, formula) in enumerate(derived):
        ws.cell(r + i, 1, label).font = BOLD
        ws.cell(r + i, 2, formula).number_format = MONEY
        ws.cell(r + i, 3, "USD")
        refs[key] = f"$B${r + i}"

    ws.cell(r + 6, 1, "Mavi hücreler girdidir; değiştirdiğinizde Model ve Ozet sayfaları güncellenir.")
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 14
    return {k: "Varsayimlar!" + v for k, v in refs.items()}


LINES = [
    "Yıl", "Üretim (MWh)", "Elektrik fiyatı (USD/MWh)", "Gelir", "OPEX", "FAVÖK (EBITDA)",
    "Amortisman", "FVÖK (EBIT)", "Vergi (proje)", "Yatırım (CAPEX)", "FCFF (proje nakit akışı)", "",
    "Faiz", "Anapara", "Borç servisi", "Kredi bakiyesi (dönem sonu)", "Vergi (kredili)",
    "CFADS", "DSCR", "FCFE (öz kaynak nakit akışı)",
]
BOLD_ROWS = {1, 6, 11, 15, 18, 20}


def _model_sheet(wb: Workbook, a: SolarAssumptions, R: dict) -> str:
    ws = wb.create_sheet("Model")
    for row, label in enumerate(LINES, start=1):
        ws.cell(row, 1, label).font = BOLD if row in BOLD_ROWS else Font()

    for t in range(a.project_life_years + 1):
        c = get_column_letter(t + 2)
        p = get_column_letter(t + 1)
        y = f"{c}$1"
        ws[f"{c}1"] = t
        if t == 0:
            f = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
                 10: f"={R['total']}", 11: f"=-{c}10",
                 13: 0, 14: 0, 15: 0, 16: f"={R['debt']}", 17: 0, 18: 0,
                 20: f"=-{R['equity']}"}
        else:
            f = {
                2: f"={R['capacity_mwp']}*{R['specific_yield_mwh_per_mwp']}*(1-{R['degradation_rate']})^({y}-1)",
                3: f"={R['electricity_price_per_mwh']}*(1+{R['price_escalation']})^({y}-1)",
                4: f"={c}2*{c}3",
                5: f"={R['capacity_mwp']}*{R['opex_per_mwp_year']}*(1+{R['opex_escalation']})^({y}-1)",
                6: f"={c}4-{c}5",
                7: f"=IF({y}<={R['depreciation_years']},{R['total']}/{R['depreciation_years']},0)",
                8: f"={c}6-{c}7",
                9: f"=MAX({c}8,0)*{R['tax_rate']}",
                10: 0,
                11: f"={c}6-{c}9",
                13: f"=IF({y}<={R['loan_tenor_years']},{p}16*{R['interest_rate']},0)",
                14: f"=IF({y}<={R['loan_tenor_years']},{R['payment']}-{c}13,0)",
                15: f"={c}13+{c}14",
                16: f"={p}16-{c}14",
                17: f"=MAX({c}8-{c}13,0)*{R['tax_rate']}",
                18: f"={c}6-{c}17",
                19: f'=IF({c}15>0,{c}18/{c}15,"")',
                20: f"={c}18-{c}15",
            }
        for row, value in f.items():
            cell = ws[f"{c}{row}"]
            cell.value = value
            cell.number_format = "0.00" if row in (3, 19) else MONEY
            if row in BOLD_ROWS:
                cell.font = BOLD
        ws.column_dimensions[c].width = 13

    ws.column_dimensions["A"].width = 32
    ws.freeze_panes = "B2"
    return get_column_letter(a.project_life_years + 2)


def _summary_sheet(wb: Workbook, a: SolarAssumptions, R: dict, last: str):
    ws = wb.create_sheet("Ozet")
    p = project_returns(a)
    e = equity_returns(a)
    _header(ws, ["Gösterge", "Excel formülü", "Python hesap motoru", "Fark"])

    rows = [
        ("Proje NPV (USD)", f"=Model!B11+NPV({R['discount_rate']},Model!C11:{last}11)",
         p["project_npv"], MONEY, "#,##0.00"),
        ("Proje IRR", f"=IRR(Model!B11:{last}11)", p["project_irr"], PCT2, "0.0000%"),
        ("Öz kaynak IRR", f"=IRR(Model!B20:{last}20)", e["equity_irr"], PCT2, "0.0000%"),
    ]
    if e["min_dscr"] is not None:
        rows += [
            ("Minimum DSCR", f"=MIN(Model!C19:{last}19)", e["min_dscr"], "0.00", "0.0000"),
            ("Ortalama DSCR", f"=AVERAGE(Model!C19:{last}19)", e["avg_dscr"], "0.00", "0.0000"),
        ]

    for i, (label, formula, py_value, fmt, diff_fmt) in enumerate(rows, start=2):
        ws.cell(i, 1, label)
        ws.cell(i, 2, formula).number_format = fmt
        ws.cell(i, 3, py_value).number_format = fmt
        ws.cell(i, 4, f"=B{i}-C{i}").number_format = diff_fmt

    n = len(rows) + 3
    ws.cell(n, 1, "Fark sütunu sıfıra eşitse, Excel modeli ile Python hesap motoru aynı sonucu veriyor demektir.")
    ws.cell(n + 1, 1, "Örnek varsayımlar hayalidir; bu dosya yatırım tavsiyesi değildir.")
    for col, width in zip("ABCD", (22, 18, 22, 14)):
        ws.column_dimensions[col].width = width


def build_excel(a: SolarAssumptions) -> bytes:
    """Varsayımlardan formüllü Excel modeli üretir, dosya içeriğini (bytes) döndürür."""
    wb = Workbook()
    refs = _inputs_sheet(wb, a)
    last = _model_sheet(wb, a, refs)
    _summary_sheet(wb, a, refs, last)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


if __name__ == "__main__":
    from engine.assumptions import konya_example

    path = "examples/ornek_ges_modeli.xlsx"
    with open(path, "wb") as f:
        f.write(build_excel(konya_example()))
    print(f"{path} olusturuldu")