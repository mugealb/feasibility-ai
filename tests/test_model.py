"""Nakit akışı ve kredi modelinin testleri.

Beklenen değerler Konya 10 MWp GES örnek vakasından elle doğrulandı.
"""

import pytest

from engine.assumptions import konya_example
from engine.cashflow import build_cash_flows, project_returns
from engine.debt import build_levered_cash_flows, equity_returns, loan_schedule


@pytest.fixture
def ges():
    return konya_example()


# --- Nakit akışı ---

def test_ilk_yil_degerleri(ges):
    yil1 = build_cash_flows(ges).loc[1]
    assert yil1["revenue"] == pytest.approx(1_155_000)   # 16.500 MWh x 70 USD
    assert yil1["ebitda"] == pytest.approx(1_035_000)    # gelir - 120.000 OPEX
    assert yil1["tax"] == pytest.approx(83_750)          # (1.035.000 - 700.000) x %25
    assert yil1["fcff"] == pytest.approx(951_250)


def test_sifirinci_yil_yatirim(ges):
    assert build_cash_flows(ges).loc[0, "fcff"] == pytest.approx(-7_000_000)


def test_proje_getirisi(ges):
    r = project_returns(ges)
    assert r["project_npv"] == pytest.approx(1_940_040, abs=1)
    assert r["project_irr"] == pytest.approx(0.1344, abs=0.0001)


# --- Kredi ---

def test_kredi_ilk_yil(ges):
    yil1 = loan_schedule(ges).loc[1]
    assert yil1["interest"] == pytest.approx(441_000)          # 4,9M x %9
    assert yil1["debt_service"] == pytest.approx(763_518, abs=1)


def test_kredi_vade_sonunda_biter(ges):
    plan = loan_schedule(ges)
    assert plan.loc[ges.loan_tenor_years, "closing_balance"] == pytest.approx(0, abs=1)
    assert plan["principal"].sum() == pytest.approx(ges.debt_amount)


def test_min_dscr(ges):
    r = equity_returns(ges)
    assert r["min_dscr"] == pytest.approx(1.3556, abs=0.001)
    assert r["min_dscr_year"] == 1


def test_ozkaynak_irr(ges):
    assert equity_returns(ges)["equity_irr"] == pytest.approx(0.1903, abs=0.0001)


def test_kaldirac_ozkaynak_getirisini_artirir(ges):
    assert equity_returns(ges)["equity_irr"] > project_returns(ges)["project_irr"]


def test_kredisiz_ozkaynak_irr_proje_irr_esit(ges):
    kredisiz = ges.model_copy(update={"debt_ratio": 0.0})
    assert equity_returns(kredisiz)["equity_irr"] == pytest.approx(
        project_returns(kredisiz)["project_irr"]
    )