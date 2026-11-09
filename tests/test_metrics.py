"""metrics.py testleri.

Beklenen değerler Excel ile hesaplandı:
  NPV : =A1+NPV(10%;A2:A6)
  IRR : =IRR(A1:A6)
"""

import pytest

from engine.metrics import irr, npv, payback_period

NAKIT_AKISI = [-1000, 200, 250, 300, 350, 400]


def test_npv_excel_ile_ayni():
    assert npv(0.10, NAKIT_AKISI) == pytest.approx(101.25, abs=0.01)


def test_irr_excel_ile_ayni():
    assert irr(NAKIT_AKISI) == pytest.approx(0.1345, abs=0.0001)


def test_irr_noktasinda_npv_sifir():
    # IRR'ın tanımı: NPV'yi sıfırlayan iskonto oranı
    assert npv(irr(NAKIT_AKISI), NAKIT_AKISI) == pytest.approx(0, abs=1e-6)


def test_geri_odeme_suresi():
    assert payback_period(NAKIT_AKISI) == pytest.approx(3.714, abs=0.001)


def test_geri_donmeyen_yatirim():
    assert payback_period([-1000, 100, 100, 100]) is None