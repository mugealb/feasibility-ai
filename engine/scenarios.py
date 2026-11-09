"""Senaryo ve duyarlılık analizi.

Excel karşılıkları:
- Senaryolar  -> Senaryo Yöneticisi (Scenario Manager)
- Duyarlılık  -> Veri Tablosu (Data Table)

Not: Kredi oranı sabit olduğu için CAPEX artınca kredi tutarı da artar.
"""

import pandas as pd

from engine.assumptions import SolarAssumptions
from engine.cashflow import project_returns
from engine.debt import equity_returns

SCENARIOS = {
    "Kotumser": {"price": -0.10, "production": -0.05, "capex": 0.10, "opex": 0.10},
    "Baz": {},
    "Iyimser": {"price": 0.10, "production": 0.05, "capex": -0.05, "opex": -0.05},
}


def apply_changes(a: SolarAssumptions, price=0.0, production=0.0, capex=0.0, opex=0.0) -> SolarAssumptions:
    """Varsayımları yüzdesel olarak değiştirilmiş yeni bir kopya döndürür."""
    return a.model_copy(update={
        "electricity_price_per_mwh": a.electricity_price_per_mwh * (1 + price),
        "specific_yield_mwh_per_mwp": a.specific_yield_mwh_per_mwp * (1 + production),
        "capex_per_mwp": a.capex_per_mwp * (1 + capex),
        "opex_per_mwp_year": a.opex_per_mwp_year * (1 + opex),
    })


def key_metrics(a: SolarAssumptions) -> dict:
    """Bir varsayım setinin temel sonuçları."""
    p = project_returns(a)
    e = equity_returns(a)
    return {
        "Proje NPV (USD)": p["project_npv"],
        "Proje IRR": p["project_irr"],
        "Ozkaynak IRR": e["equity_irr"],
        "Min DSCR": e["min_dscr"],
    }


def scenario_table(a: SolarAssumptions) -> pd.DataFrame:
    """Kötümser / baz / iyimser senaryo sonuçları."""
    rows = {name: key_metrics(apply_changes(a, **changes)) for name, changes in SCENARIOS.items()}
    return pd.DataFrame(rows).T


def sensitivity_grid(a: SolarAssumptions, metric: str,
                     price_steps=(-0.20, -0.10, 0.0, 0.10, 0.20),
                     capex_steps=(-0.10, 0.0, 0.10, 0.20)) -> pd.DataFrame:
    """Elektrik fiyatı x CAPEX iki boyutlu duyarlılık tablosu."""
    data = {}
    for c in capex_steps:
        data[f"CAPEX {c:+.0%}"] = [
            key_metrics(apply_changes(a, price=p, capex=c))[metric] for p in price_steps
        ]
    return pd.DataFrame(data, index=[f"Fiyat {p:+.0%}" for p in price_steps])


if __name__ == "__main__":
    from engine.assumptions import konya_example

    a = konya_example()

    table = scenario_table(a)
    formats = {"Proje NPV (USD)": "{:,.0f}", "Proje IRR": "{:.1%}",
               "Ozkaynak IRR": "{:.1%}", "Min DSCR": "{:.2f}"}
    for col, f in formats.items():
        table[col] = table[col].map(f.format)

    print(f"{a.project_name}\n")
    print("=== SENARYOLAR ===")
    print(table)

    print("\n=== OZKAYNAK IRR: elektrik fiyati x yatirim maliyeti ===")
    print(sensitivity_grid(a, "Ozkaynak IRR").map("{:.1%}".format))

    print("\n=== MIN DSCR: elektrik fiyati x yatirim maliyeti ===")
    print(sensitivity_grid(a, "Min DSCR").map("{:.2f}".format))