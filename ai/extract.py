"""Metinden GES varsayımlarını çıkarma (LLM).

Prensip: LLM sadece metinde YAZANI okur, hesap yapmaz.
- Metinde olmayan değerler None döner; örnek varsayılanlarla doldurulur ve işaretlenir.
- Birim dönüşümleri (ör. toplam yatırım -> MWp başına) Python'da yapılır.
- Sonuç SolarAssumptions veri doğrulamasından geçer.
"""

import pandas as pd

from ai.client import MODEL, get_client
from engine.assumptions import SolarAssumptions, konya_example

# LLM'in aradığı alanlar: alan adı -> açıklama
FIELDS = {
    "capacity_mwp": "Kurulu güç (MWp)",
    "project_life_years": "İşletme süresi (yıl)",
    "total_capex_usd": "Toplam yatırım tutarı (USD)",
    "capex_per_mwp": "MWp başına yatırım maliyeti (USD). Sadece metinde açıkça MWp başına verilmişse.",
    "annual_production_mwh": "Toplam ilk yıl elektrik üretimi (MWh)",
    "specific_yield_mwh_per_mwp": "MWp başına yıllık üretim (MWh/MWp). Sadece metinde açıkça bu birimle verilmişse.",
    "degradation_rate": "Yıllık panel verim kaybı, ondalık (%0,5 -> 0.005)",
    "electricity_price_per_mwh": "Elektrik satış fiyatı (USD/MWh). Metinde bu birimle verilmişse.",
    "electricity_price_per_kwh": "Elektrik satış fiyatı (USD/kWh). Metinde kWh başına verilmişse.",
    "price_escalation": "Yıllık elektrik fiyatı artışı, ondalık",
    "annual_opex_usd": "Toplam yıllık işletme/bakım gideri (USD)",
    "opex_per_mwp_year": "MWp başına yıllık işletme gideri (USD). Sadece metinde açıkça bu birimle verilmişse.",
    "tax_rate": "Kurumlar vergisi oranı, ondalık",
    "debt_ratio": "Kredi / toplam yatırım oranı, ondalık (%70 -> 0.70)",
    "interest_rate": "Yıllık kredi faiz oranı, ondalık (%9 -> 0.09)",
    "loan_tenor_years": "Kredi vadesi (yıl)",
    "discount_rate": "İskonto oranı / WACC, ondalık",
}

SYSTEM_PROMPT = """Sen bir proje finansmanı analistisin. Görevin, verilen proje metninden
yatırım varsayımlarını ÇIKARMAK. Kurallar:
1. Sadece metinde açıkça yazan değerleri al. Tahmin etme, hesap yapma, birim dönüştürme.
   (Tek istisna: yüzdeleri ondalığa çevir, %70 -> 0.70.)
2. "Milyon", "bin" gibi ifadeleri sayıya çevir (8,1 milyon -> 8100000).
3. Metinde olmayan bir değer için value = null ver.
4. Para birimi USD değilse value = null ver ve notes alanında belirt.
5. Her değer için, değerin geçtiği kısa metin parçasını quote alanına yaz.
6. Cevabını MUTLAKA record_assumptions aracını çağırarak ver; düz metin cevap yazma."""


def _tool_schema() -> dict:
    field_schema = {
        "type": "object",
        "properties": {
            "value": {"type": ["number", "null"]},
            "quote": {"type": ["string", "null"], "description": "Değerin geçtiği kısa metin parçası"},
        },
        "required": ["value", "quote"],
    }
    properties = {name: {**field_schema, "description": desc} for name, desc in FIELDS.items()}
    properties["notes"] = {"type": "string", "description": "Belirsizlikler, para birimi uyarıları vb."}
    return {
        "name": "record_assumptions",
        "description": "Proje metninden çıkarılan varsayımları kaydeder.",
        "input_schema": {"type": "object", "properties": properties, "required": list(FIELDS) + ["notes"]},
    }


def extract_raw(text: str) -> dict:
    """LLM çağrısı: metinden ham değerleri ve alıntıları çıkarır."""
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=[_tool_schema()],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": text}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Claude varsayımları formata dökmedi. Lütfen tekrar deneyin.")


def build_assumptions(raw: dict, project_name: str = "Metinden çıkarılan GES projesi"):
    """Ham değerleri SolarAssumptions'a çevirir. Dönüşümleri PYTHON yapar.

    Döndürür: (SolarAssumptions, kaynak raporu DataFrame, notlar)
    """
    v = {k: (raw.get(k) or {}).get("value") for k in FIELDS}
    q = {k: (raw.get(k) or {}).get("quote") for k in FIELDS}
    defaults = konya_example()
    final, source, quote = {}, {}, {}

    def put(field, value, src, qt=None):
        final[field], source[field], quote[field] = value, src, qt

    def direct(field):
        if v.get(field) is not None:
            put(field, v[field], "Metin", q.get(field))
            return True
        return False

    direct("capacity_mwp") or put("capacity_mwp", defaults.capacity_mwp, "Varsayılan")
    cap = final["capacity_mwp"]

    # Yatırım: MWp başına yoksa toplamdan hesapla (Python)
    if not direct("capex_per_mwp"):
        if v["total_capex_usd"] is not None:
            put("capex_per_mwp", v["total_capex_usd"] / cap, "Hesaplandı: toplam / kapasite", q["total_capex_usd"])
        else:
            put("capex_per_mwp", defaults.capex_per_mwp, "Varsayılan")

    # Üretim: MWp başına yoksa toplam üretimden hesapla
    if not direct("specific_yield_mwh_per_mwp"):
        if v["annual_production_mwh"] is not None:
            put("specific_yield_mwh_per_mwp", v["annual_production_mwh"] / cap,
                "Hesaplandı: toplam üretim / kapasite", q["annual_production_mwh"])
        else:
            put("specific_yield_mwh_per_mwp", defaults.specific_yield_mwh_per_mwp, "Varsayılan")

    # Fiyat: kWh verilmişse MWh'ye çevir
    if not direct("electricity_price_per_mwh"):
        if v["electricity_price_per_kwh"] is not None:
            put("electricity_price_per_mwh", v["electricity_price_per_kwh"] * 1000,
                "Hesaplandı: USD/kWh x 1000", q["electricity_price_per_kwh"])
        else:
            put("electricity_price_per_mwh", defaults.electricity_price_per_mwh, "Varsayılan")

    # OPEX: MWp başına yoksa toplamdan hesapla
    if not direct("opex_per_mwp_year"):
        if v["annual_opex_usd"] is not None:
            put("opex_per_mwp_year", v["annual_opex_usd"] / cap, "Hesaplandı: toplam OPEX / kapasite", q["annual_opex_usd"])
        else:
            put("opex_per_mwp_year", defaults.opex_per_mwp_year, "Varsayılan")

    # Doğrudan alınan diğer alanlar
    for field in ["project_life_years", "degradation_rate", "price_escalation", "tax_rate",
                  "debt_ratio", "interest_rate", "loan_tenor_years", "discount_rate"]:
        direct(field) or put(field, getattr(defaults, field), "Varsayılan")

    for field in ["project_life_years", "loan_tenor_years"]:
        final[field] = int(round(final[field]))

    assumptions = SolarAssumptions(
        project_name=project_name,
        opex_escalation=defaults.opex_escalation,
        depreciation_years=min(defaults.depreciation_years, final["project_life_years"]),
        **final,
    )

    report = pd.DataFrame({
        "Deger": final, "Kaynak": source, "Metindeki ifade": quote,
    })
    return assumptions, report, raw.get("notes", "")


def extract_assumptions(text: str, project_name: str = "Metinden çıkarılan GES projesi"):
    """Uçtan uca: metin -> (SolarAssumptions, rapor, notlar)."""
    return build_assumptions(extract_raw(text), project_name)


if __name__ == "__main__":
    from engine.scenarios import key_metrics

    ornek_metin = (
        "Konya Karapınar'da 12 MWp kapasiteli bir güneş enerjisi santrali kurmayı planlıyoruz. "
        "Toplam yatırım bütçesi yaklaşık 8,1 milyon dolar. Bölgede yıllık üretimin 20.400 MWh "
        "civarında olması bekleniyor. Elektriği 25 yıl boyunca 0,072 $/kWh fiyatla satmayı "
        "hedefliyoruz. Finansmanın %65'i bankadan, %9,5 faizle 12 yıl vadeli krediyle sağlanacak. "
        "Yıllık işletme ve bakım gideri 140 bin dolar civarında."
    )

    print("METIN:\n" + ornek_metin + "\n")
    print("Claude metni okuyor...\n")
    a, report, notes = extract_assumptions(ornek_metin)

    pd.set_option("display.max_colwidth", 45)
    pd.set_option("display.width", 200)
    print("=== CIKARILAN VARSAYIMLAR ===")
    print(report)
    if notes:
        print(f"\nClaude'un notu: {notes}")

    m = key_metrics(a)
    print("\n=== SONUC (hesap motoru) ===")
    print(f"Proje NPV   : {m['Proje NPV (USD)']:,.0f} USD")
    print(f"Proje IRR   : {m['Proje IRR']:.1%}")
    print(f"Ozkaynak IRR: {m['Ozkaynak IRR']:.1%}")
    print(f"Min DSCR    : {m['Min DSCR']:.2f}")