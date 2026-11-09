"""Temel yatırım değerlendirme metrikleri: NPV, IRR, geri ödeme süresi."""

import numpy_financial as npf


def npv(rate, cash_flows):
    """Net Bugünkü Değer.

    cash_flows[0] = bugünkü yatırım (iskonto edilmez),
    sonrakiler = yıl sonu nakit akışları.

    Not: Excel'in NPV() fonksiyonu ilk değeri de iskonto eder.
    Bu yüzden Excel karşılığı: =CF0 + NPV(oran; CF1:CFn)
    """
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))


def irr(cash_flows):
    """İç Verim Oranı (Excel'deki IRR ile aynı)."""
    return float(npf.irr(cash_flows))


def payback_period(cash_flows):
    """Basit geri ödeme süresi (yıl). Yatırım hiç geri dönmüyorsa None."""
    cumulative = cash_flows[0]
    for year in range(1, len(cash_flows)):
        previous = cumulative
        cumulative += cash_flows[year]
        if cumulative >= 0:
            return (year - 1) + (-previous / cash_flows[year])
    return None