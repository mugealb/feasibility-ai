"""GES nakit akışı tablosu (proje seviyesi, kredi hariç).

Excel'deki ana model sekmesinin karşılığı: her satır bir yıl.
0. yıl = yatırım, 1..N. yıllar = işletme.

Şimdilik basitleştirmeler (ileride geliştirilecek):
- İşletme sermayesi ve yenileme yatırımı yok
- Vergi zararı devri yok (EBIT negatifse vergi 0)
"""

import pandas as pd

from engine.assumptions import SolarAssumptions
from engine.metrics import irr, npv


def build_cash_flows(a: SolarAssumptions) -> pd.DataFrame:
    """Varsayımlardan yıllık nakit akışı tablosunu üretir."""
    rows = [{
        "year": 0, "production_mwh": 0.0, "revenue": 0.0, "opex": 0.0,
        "ebitda": 0.0, "depreciation": 0.0, "ebit": 0.0, "tax": 0.0,
        "capex": a.total_capex, "fcff": -a.total_capex,
    }]
    annual_depreciation = a.total_capex / a.depreciation_years

    for year in range(1, a.project_life_years + 1):
        production = a.first_year_production_mwh * (1 - a.degradation_rate) ** (year - 1)
        price = a.electricity_price_per_mwh * (1 + a.price_escalation) ** (year - 1)
        revenue = production * price
        opex = a.capacity_mwp * a.opex_per_mwp_year * (1 + a.opex_escalation) ** (year - 1)
        ebitda = revenue - opex
        depreciation = annual_depreciation if year <= a.depreciation_years else 0.0
        ebit = ebitda - depreciation
        tax = max(ebit, 0.0) * a.tax_rate
        fcff = ebitda - tax

        rows.append({
            "year": year, "production_mwh": production, "revenue": revenue,
            "opex": opex, "ebitda": ebitda, "depreciation": depreciation,
            "ebit": ebit, "tax": tax, "capex": 0.0, "fcff": fcff,
        })

    return pd.DataFrame(rows).set_index("year")


def project_returns(a: SolarAssumptions) -> dict:
    """Proje seviyesi (kredisiz) NPV ve IRR."""
    fcff = build_cash_flows(a)["fcff"].tolist()
    return {"project_npv": npv(a.discount_rate, fcff), "project_irr": irr(fcff)}


if __name__ == "__main__":
    from engine.assumptions import konya_example

    a = konya_example()
    table = build_cash_flows(a)
    pd.set_option("display.float_format", "{:,.0f}".format)

    print(a.project_name)
    print(table[["revenue", "opex", "ebitda", "depreciation", "tax", "fcff"]].head(6))

    r = project_returns(a)
    print(f"\nProje NPV (iskonto %{a.discount_rate * 100:.0f}): {r['project_npv']:,.0f} USD")
    print(f"Proje IRR: %{r['project_irr'] * 100:.2f}")
    