"""Kredi geri ödeme planı, DSCR ve öz kaynak getirisi.

- Kredi eşit taksitli (anüite) geri ödenir.
- Faiz vergiden düşülür (vergi kalkanı).
- CFADS = FAVÖK - vergi      -> borç servisi için kullanılabilir nakit
- DSCR  = CFADS / borç servisi (faiz + anapara)
- FCFE  = CFADS - borç servisi -> öz kaynak sahibine kalan nakit
"""

import pandas as pd

from engine.assumptions import SolarAssumptions
from engine.cashflow import build_cash_flows
from engine.metrics import irr


def loan_schedule(a: SolarAssumptions) -> pd.DataFrame:
    """Eşit taksitli kredi geri ödeme tablosu."""
    r = a.interest_rate
    n = a.loan_tenor_years
    amount = a.debt_amount

    if r == 0:
        payment = amount / n
    else:
        payment = amount * r / (1 - (1 + r) ** -n)

    rows = []
    balance = amount
    for year in range(1, a.project_life_years + 1):
        if year <= n:
            interest = balance * r
            principal = payment - interest
            balance -= principal
        else:
            interest = principal = 0.0
        rows.append({
            "year": year,
            "interest": interest,
            "principal": principal,
            "debt_service": interest + principal,
            "closing_balance": max(balance, 0.0),
        })
    return pd.DataFrame(rows).set_index("year")


def build_levered_cash_flows(a: SolarAssumptions) -> pd.DataFrame:
    """Nakit akışı + kredi: CFADS, DSCR ve FCFE."""
    df = build_cash_flows(a).join(loan_schedule(a), how="left").fillna(0.0)

    df["tax_levered"] = (df["ebit"] - df["interest"]).clip(lower=0) * a.tax_rate
    df["cfads"] = df["ebitda"] - df["tax_levered"]
    df["dscr"] = df["cfads"] / df["debt_service"].where(df["debt_service"] > 0)
    df["fcfe"] = df["cfads"] - df["debt_service"]
    df.loc[0, "fcfe"] = -a.equity_amount  # 0. yıl: yatırımcının koyduğu öz kaynak
    return df


def equity_returns(a: SolarAssumptions) -> dict:
    """Öz kaynak IRR'ı ve DSCR özetleri."""
    df = build_levered_cash_flows(a)
    dscr = df["dscr"].dropna()
    return {
        "equity_irr": irr(df["fcfe"].tolist()),
        "min_dscr": float(dscr.min()),
        "min_dscr_year": int(dscr.idxmin()),
        "avg_dscr": float(dscr.mean()),
    }


if __name__ == "__main__":
    from engine.assumptions import konya_example

    a = konya_example()
    df = build_levered_cash_flows(a)
    pd.set_option("display.float_format", "{:,.0f}".format)

    show = df.loc[1:a.loan_tenor_years, ["cfads", "interest", "principal", "debt_service", "dscr", "fcfe"]].copy()
    show["dscr"] = show["dscr"].map("{:.2f}".format)

    print(f"{a.project_name} - kredi donemi")
    print(show)

    r = equity_returns(a)
    print(f"\nKredi: {a.debt_amount:,.0f} USD  |  Ozkaynak: {a.equity_amount:,.0f} USD")
    print(f"Minimum DSCR: {r['min_dscr']:.2f} (yil {r['min_dscr_year']})")
    print(f"Ortalama DSCR: {r['avg_dscr']:.2f}")
    print(f"Ozkaynak IRR: %{r['equity_irr'] * 100:.2f}")
    