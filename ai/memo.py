"""Yatırım Komitesi Notu (LLM ile yazım + otomatik rakam kontrolü).

Prensip:
- Bütün rakamlar Python hesap motorundan gelir ve Claude'a HAZIR METİN olarak verilir.
- Claude sadece yorumlar ve yazar; yeni rakam hesaplamaz.
- check_numbers(): Nottaki her sayıyı verilen rakamlarla karşılaştırır,
  listede olmayan sayıları "doğrulanamadı" olarak raporlar.
  Harfle bitişik sayılar (P50, P90 gibi sektör terimleri) kontrol dışıdır.
"""

import json
import re

from ai.client import MODEL, get_client
from engine.assumptions import SolarAssumptions
from engine.cashflow import project_returns
from engine.debt import equity_returns
from engine.scenarios import scenario_table


# --- Türkçe sayı biçimleri ---
def tr_money(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def tr_pct(v: float) -> str:
    return "%" + f"{v * 100:.1f}".replace(".", ",")


def tr_dec(v: float, digits: int = 2) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def build_facts(a: SolarAssumptions) -> dict:
    """Notta kullanılabilecek BÜTÜN rakamlar (hepsi Python'dan)."""
    p = project_returns(a)
    e = equity_returns(a)
    sc = scenario_table(a)
    has_debt = e["min_dscr"] is not None

    scenarios = {}
    for name, row in sc.iterrows():
        scenarios[name] = {
            "Proje NPV": f"{tr_money(row['Proje NPV (USD)'])} USD",
            "Proje IRR": tr_pct(row["Proje IRR"]),
            "Öz kaynak IRR": tr_pct(row["Ozkaynak IRR"]),
            "Min DSCR": tr_dec(row["Min DSCR"]) if has_debt else "Kredi yok",
        }

    return {
        "Proje adı": a.project_name,
        "Kurulu güç": f"{tr_dec(a.capacity_mwp, 1)} MWp",
        "İşletme süresi": f"{a.project_life_years} yıl",
        "Toplam yatırım": f"{tr_money(a.total_capex)} USD",
        "Kredi tutarı": f"{tr_money(a.debt_amount)} USD",
        "Öz kaynak tutarı": f"{tr_money(a.equity_amount)} USD",
        "Kredi oranı": tr_pct(a.debt_ratio),
        "Kredi faizi": tr_pct(a.interest_rate),
        "Kredi vadesi": f"{a.loan_tenor_years} yıl",
        "Kredi geri ödeme yapısı": "Eşit taksitli (anüite)",
        "İlk yıl üretim": f"{tr_money(a.first_year_production_mwh)} MWh",
        "Yıllık üretim kaybı (panel degradasyonu)": tr_pct(a.degradation_rate),
        "Elektrik fiyatı (ilk yıl)": f"{tr_dec(a.electricity_price_per_mwh, 1)} USD/MWh",
        "Yıllık elektrik fiyatı artışı": tr_pct(a.price_escalation),
        "Yıllık işletme gideri (OPEX, ilk yıl)": f"{tr_money(a.capacity_mwp * a.opex_per_mwp_year)} USD",
        "Yıllık OPEX artışı": tr_pct(a.opex_escalation),
        "Kurumlar vergisi oranı": tr_pct(a.tax_rate),
        "Amortisman süresi": f"{a.depreciation_years} yıl",
        "İskonto oranı (WACC)": tr_pct(a.discount_rate),
        "Proje NPV": f"{tr_money(p['project_npv'])} USD",
        "Proje IRR": tr_pct(p["project_irr"]),
        "Öz kaynak IRR": tr_pct(e["equity_irr"]),
        "Minimum DSCR": tr_dec(e["min_dscr"]) if has_debt else "Kredi yok",
        "Minimum DSCR yılı": f"{e['min_dscr_year']}. yıl" if has_debt else "-",
        "Ortalama DSCR": tr_dec(e["avg_dscr"]) if has_debt else "Kredi yok",
        "Banka DSCR alt sınırı": "1,20",
        "Senaryolar (kötümser: fiyat -%10, üretim -%5, CAPEX +%10, OPEX +%10; iyimser: fiyat +%10, üretim +%5, CAPEX -%5, OPEX -%5)": scenarios,
    }


SYSTEM_PROMPT = """Sen deneyimli bir proje finansmanı analistisin. Verilen rakamlarla Türkçe,
profesyonel bir Yatırım Komitesi Notu yazacaksın.

KESİN KURALLAR:
1. SADECE verilen JSON'daki rakamları kullan; rakamları AYNEN, verildiği biçimde yaz.
2. Yeni rakam HESAPLAMA (fark, oran, toplam, yüzde dahil). Karşılaştırmayı sözle yap
   (ör. "proje getirisi sermaye maliyetinin üzerinde").
3. Verilmeyen bir bilgiyi uydurma; gerekiyorsa "ek analiz gerektirir" de.
4. Önerilerde bile yeni sayı, oran veya hedef değer yazma (ör. hedef kredi oranı, faiz artışı miktarı).
   Önerileri sözle ifade et (ör. "kredi oranının düşürülmesi değerlendirilmeli").

YAPI (Markdown başlıklarıyla):
## 1. Özet ve Öneri  (2-3 cümle; net bir öneri: Onay / Koşullu onay / Ret)
## 2. Proje ve Temel Varsayımlar
## 3. Getiri Analizi
## 4. Finansman ve Borç Ödeme Kapasitesi (DSCR)
## 5. Senaryo Analizi
## 6. Başlıca Riskler ve Önerilen Önlemler
## 7. Sonuç

Notun sonuna şu cümleyi ekle: "Bu not otomatik üretilmiştir ve yatırım tavsiyesi değildir." """


def write_memo(facts: dict) -> str:
    """Claude'a rakamları verip notu yazdırır."""
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": "Rakamlar (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=2),
        }],
    )
    return "".join(b.text for b in response.content if b.type == "text")


# --- Rakam kontrolü ---
# Önünde harf olan sayılar (P50, P90, O&M gibi terimler) yakalanmaz.
NUMBER = re.compile(r"(?<![A-Za-zÇĞİÖŞÜçğıöşü])\d+(?:[.,]\d+)*")


def _normalize(token: str) -> str:
    return token.replace(".", "").replace(",", "")


def _collect_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _collect_strings(v)
    else:
        yield str(obj)


def check_numbers(memo: str, facts: dict) -> list:
    """Notta geçen ama verilen rakamlarda OLMAYAN sayıları döndürür.

    40 ve altındaki tam sayılara izin verilir (yıl sayıları, madde numaraları gibi).
    """
    allowed = {_normalize(t) for s in _collect_strings(facts) for t in NUMBER.findall(s)}
    unknown = set()
    for token in NUMBER.findall(memo):
        n = _normalize(token)
        if n in allowed:
            continue
        if token.isdigit() and int(token) <= 40:
            continue
        unknown.add(token)
    return sorted(unknown)


if __name__ == "__main__":
    from engine.assumptions import konya_example

    a = konya_example()
    facts = build_facts(a)
    print("Claude notu yaziyor...\n")
    memo = write_memo(facts)
    print(memo)

    unknown = check_numbers(memo, facts)
    print("\n" + "=" * 60)
    if unknown:
        print(f"RAKAM KONTROLU: Dogrulanamayan sayilar var: {unknown}")
    else:
        print("RAKAM KONTROLU: Nottaki tum sayilar hesap motorundan geliyor. OK")