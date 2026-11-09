"""Monte Carlo risk simülasyonu.

Binlerce olası senaryo üretir ve şu sorulara cevap verir:
- NPV'nin negatif olma olasılığı nedir?
- Min DSCR'ın banka sınırının (1,20) altına düşme olasılığı nedir?

Dağılımlar (baz değere göre yüzde sapma):
- Elektrik fiyatı : Normal, std %10
- Üretim          : Normal, std %5
- OPEX            : Normal, std %10
- CAPEX           : Üçgen (-%5 / %0 / +%15), maliyet aşımına çarpık
Sabit seed kullanıldığı için sonuçlar her çalıştırmada aynıdır (tekrar üretilebilir).
"""

import numpy as np
import pandas as pd

from engine.assumptions import SolarAssumptions
from engine.scenarios import apply_changes, key_metrics


def run_monte_carlo(a: SolarAssumptions, n: int = 2000, seed: int = 42,
                    price_sd: float = 0.10, production_sd: float = 0.05, opex_sd: float = 0.10,
                    capex_low: float = -0.05, capex_mode: float = 0.0, capex_high: float = 0.15) -> pd.DataFrame:
    """n adet simülasyon çalıştırır, her biri için temel sonuçları döndürür."""
    rng = np.random.default_rng(seed)
    price = rng.normal(0, price_sd, n)
    production = rng.normal(0, production_sd, n)
    opex = rng.normal(0, opex_sd, n)
    capex = rng.triangular(capex_low, capex_mode, capex_high, n)

    rows = []
    for i in range(n):
        scenario = apply_changes(a, price=price[i], production=production[i],
                                 capex=capex[i], opex=opex[i])
        rows.append(key_metrics(scenario))
    return pd.DataFrame(rows)


def summarize(results: pd.DataFrame, dscr_covenant: float = 1.20) -> dict:
    """P10 / P50 / P90 değerleri ve risk olasılıkları."""
    cols = ["Proje NPV (USD)", "Ozkaynak IRR", "Min DSCR"]
    percentiles = results[cols].quantile([0.10, 0.50, 0.90]).T
    percentiles.columns = ["P10", "P50", "P90"]

    return {
        "percentiles": percentiles,
        "prob_npv_negative": float((results["Proje NPV (USD)"] < 0).mean()),
        "prob_dscr_below_covenant": float((results["Min DSCR"] < dscr_covenant).mean()),
        "prob_dscr_below_1": float((results["Min DSCR"] < 1.0).mean()),
    }


def format_percentiles(percentiles: pd.DataFrame) -> pd.DataFrame:
    """Ekrana basmak için sayıları okunur metne çevirir (orijinal tabloyu değiştirmez)."""
    formats = {"Proje NPV (USD)": "{:,.0f}", "Ozkaynak IRR": "{:.1%}", "Min DSCR": "{:.2f}"}
    rows = {name: [formats[name].format(v) for v in percentiles.loc[name]] for name in formats}
    return pd.DataFrame(rows, index=percentiles.columns).T


if __name__ == "__main__":
    from engine.assumptions import konya_example

    a = konya_example()
    n = 2000
    print(f"{a.project_name}")
    print(f"{n:,} simulasyon calisiyor, lutfen bekleyin...\n")

    results = run_monte_carlo(a, n=n)
    s = summarize(results)

    print("=== DAGILIM (P10 = kotu, P50 = ortanca, P90 = iyi) ===")
    print(format_percentiles(s["percentiles"]))
    print("\n=== RISK OLASILIKLARI ===")
    print(f"NPV < 0 olasiligi          : {s['prob_npv_negative']:.1%}")
    print(f"Min DSCR < 1.20 olasiligi  : {s['prob_dscr_below_covenant']:.1%}")
    print(f"Min DSCR < 1.00 olasiligi  : {s['prob_dscr_below_1']:.1%}")