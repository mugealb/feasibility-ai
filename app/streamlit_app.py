"""FeasibilityAI - Streamlit arayüzü.

Çalıştırmak için:  streamlit run app/streamlit_app.py --server.headless true
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pydantic import ValidationError

from engine.assumptions import SolarAssumptions, konya_example
from engine.cashflow import project_returns
from engine.debt import build_levered_cash_flows, equity_returns
from engine.montecarlo import format_percentiles, run_monte_carlo, summarize
from engine.scenarios import scenario_table, sensitivity_grid

st.set_page_config(page_title="FeasibilityAI", page_icon="☀️", layout="wide")

DSCR_COVENANT = 1.20
base = konya_example()

# ---------------- Kenar çubuğu: varsayımlar ----------------
with st.sidebar:
    st.header("Varsayımlar")

    st.subheader("Proje")
    capacity = st.number_input("Kurulu güç (MWp)", 1.0, 500.0, float(base.capacity_mwp), 1.0)
    life = st.slider("İşletme süresi (yıl)", 10, 40, base.project_life_years)
    capex = st.number_input("Yatırım maliyeti (USD/MWp)", 100_000, 2_000_000, int(base.capex_per_mwp), 10_000)

    st.subheader("Üretim ve gelir")
    yield_ = st.number_input("İlk yıl üretim (MWh/MWp)", 500, 3_000, int(base.specific_yield_mwh_per_mwp), 10)
    degradation = st.slider("Yıllık verim kaybı (%)", 0.0, 2.0, round(base.degradation_rate * 100, 2), 0.1)
    price = st.number_input("Elektrik fiyatı (USD/MWh)", 10.0, 300.0, float(base.electricity_price_per_mwh), 1.0)
    price_esc = st.slider("Yıllık fiyat artışı (%)", -5.0, 10.0, round(base.price_escalation * 100, 2), 0.5)

    st.subheader("Gider ve vergi")
    opex = st.number_input("OPEX (USD/MWp/yıl)", 0, 100_000, int(base.opex_per_mwp_year), 500)
    tax = st.slider("Kurumlar vergisi (%)", 0.0, 50.0, round(base.tax_rate * 100, 2), 1.0)

    st.subheader("Finansman")
    debt = st.slider("Kredi oranı (%)", 0.0, 90.0, round(base.debt_ratio * 100, 2), 5.0)
    interest = st.slider("Kredi faizi (%)", 0.0, 25.0, round(base.interest_rate * 100, 2), 0.5)
    tenor = st.slider("Kredi vadesi (yıl)", 1, 20, base.loan_tenor_years)
    discount = st.slider("İskonto oranı / WACC (%)", 1.0, 30.0, round(base.discount_rate * 100, 2), 0.5)

try:
    a = SolarAssumptions(
        project_name="GES projesi",
        capacity_mwp=capacity,
        project_life_years=life,
        capex_per_mwp=capex,
        specific_yield_mwh_per_mwp=yield_,
        degradation_rate=degradation / 100,
        electricity_price_per_mwh=price,
        price_escalation=price_esc / 100,
        opex_per_mwp_year=opex,
        opex_escalation=base.opex_escalation,
        tax_rate=tax / 100,
        depreciation_years=min(base.depreciation_years, life),
        debt_ratio=debt / 100,
        interest_rate=interest / 100,
        loan_tenor_years=tenor,
        discount_rate=discount / 100,
    )
except ValidationError as err:
    st.error(f"Varsayımlarda hata var:\n\n{err}")
    st.stop()

# ---------------- Başlık ve ana göstergeler ----------------
st.title("☀️ FeasibilityAI — GES Fizibilite Analizi")
st.caption("Tüm rakamlar test edilmiş Python hesap motorundan gelir. "
           "Örnek varsayımlar hayalidir; bu araç yatırım tavsiyesi değildir.")

p = project_returns(a)
e = equity_returns(a)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Proje NPV", f"{p['project_npv'] / 1e6:,.2f} M USD")
c2.metric("Proje IRR", f"{p['project_irr']:.1%}",
          f"{(p['project_irr'] - a.discount_rate) * 100:+.1f} puan (WACC'a göre)")
c3.metric("Öz kaynak IRR", f"{e['equity_irr']:.1%}")
if e["min_dscr"] is None:
    c4.metric("Min DSCR", "Kredi yok")
else:
    c4.metric("Min DSCR", f"{e['min_dscr']:.2f}",
              f"{e['min_dscr'] - DSCR_COVENANT:+.2f} (1,20 sınırına göre)")

dscr_ok = e["min_dscr"] is None or e["min_dscr"] >= DSCR_COVENANT
if p["project_npv"] > 0 and dscr_ok:
    st.success("Bu varsayımlarla proje fizibil: NPV pozitif ve DSCR banka sınırının üzerinde.")
elif p["project_npv"] > 0:
    st.warning("NPV pozitif ama min DSCR 1,20 banka sınırının altında: finansman yapısı gözden geçirilmeli.")
else:
    st.error("NPV negatif: bu varsayımlarla proje değer yaratmıyor.")

df = build_levered_cash_flows(a)
tab1, tab2, tab3, tab4 = st.tabs(["📊 Nakit akışı", "🏦 Kredi ve DSCR", "🔀 Senaryolar", "🎲 Monte Carlo"])

# ---------------- Nakit akışı ----------------
with tab1:
    fig = go.Figure()
    fig.add_bar(x=df.index, y=df["fcff"], name="FCFF (proje)")
    fig.add_bar(x=df.index, y=df["fcfe"], name="FCFE (öz kaynak)")
    fig.update_layout(barmode="group", xaxis_title="Yıl", yaxis_title="USD", height=420)
    st.plotly_chart(fig, width="stretch")

    cols = ["revenue", "opex", "ebitda", "tax", "fcff", "debt_service", "fcfe"]
    st.dataframe(df[cols].round(0), width="stretch")

# ---------------- Kredi ve DSCR ----------------
with tab2:
    d = df[df["debt_service"] > 0]
    if d.empty:
        st.info("Bu yapıda kredi kullanılmıyor.")
    else:
        fig2 = px.line(x=d.index, y=d["dscr"], markers=True, labels={"x": "Yıl", "y": "DSCR"})
        fig2.add_hline(y=DSCR_COVENANT, line_dash="dash", annotation_text="Banka sınırı 1,20")
        fig2.update_layout(height=420)
        st.plotly_chart(fig2, width="stretch")
        st.dataframe(d[["cfads", "interest", "principal", "debt_service", "dscr"]].round(2), width="stretch")

# ---------------- Senaryolar ----------------
with tab3:
    sc = scenario_table(a)
    shown = pd.DataFrame({
        "Proje NPV (USD)": sc["Proje NPV (USD)"].map(lambda v: f"{v:,.0f}"),
        "Proje IRR": sc["Proje IRR"].map(lambda v: f"{v:.1%}"),
        "Ozkaynak IRR": sc["Ozkaynak IRR"].map(lambda v: f"{v:.1%}"),
        "Min DSCR": sc["Min DSCR"].map(lambda v: "-" if pd.isna(v) else f"{v:.2f}"),
    })
    st.subheader("Kötümser / baz / iyimser")
    st.dataframe(shown, width="stretch")

    st.subheader("Öz kaynak IRR (%): elektrik fiyatı × yatırım maliyeti")
    g = sensitivity_grid(a, "Ozkaynak IRR")
    st.plotly_chart(px.imshow(g.values * 100, x=list(g.columns), y=list(g.index), text_auto=".1f",
                              color_continuous_scale="RdYlGn", aspect="auto"), width="stretch")

    if a.debt_ratio > 0:
        st.subheader("Min DSCR: elektrik fiyatı × yatırım maliyeti")
        g2 = sensitivity_grid(a, "Min DSCR").astype(float)
        st.plotly_chart(px.imshow(g2.values, x=list(g2.columns), y=list(g2.index), text_auto=".2f",
                                  color_continuous_scale="RdYlGn", aspect="auto"), width="stretch")

# ---------------- Monte Carlo ----------------
@st.cache_data(show_spinner=False)
def cached_monte_carlo(assumptions_json: str, n: int) -> pd.DataFrame:
    return run_monte_carlo(SolarAssumptions.model_validate_json(assumptions_json), n=n)


with tab4:
    if a.debt_ratio == 0:
        st.info("Monte Carlo şu an kredili yapılar için hazırlanmıştır.")
    else:
        st.write("Elektrik fiyatı, üretim, OPEX ve CAPEX rastgele değişir; binlerce olası gelecek simüle edilir.")
        n = st.select_slider("Simülasyon sayısı", options=[500, 1000, 2000], value=1000)
        if st.button("Simülasyonu çalıştır"):
            with st.spinner("Simülasyon çalışıyor..."):
                results = cached_monte_carlo(a.model_dump_json(), n)
            s = summarize(results, dscr_covenant=DSCR_COVENANT)

            m1, m2, m3 = st.columns(3)
            m1.metric("NPV < 0 olasılığı", f"{s['prob_npv_negative']:.1%}")
            m2.metric("Min DSCR < 1,20 olasılığı", f"{s['prob_dscr_below_covenant']:.1%}")
            m3.metric("Min DSCR < 1,00 olasılığı", f"{s['prob_dscr_below_1']:.1%}")

            fig3 = px.histogram(results, x="Proje NPV (USD)", nbins=50)
            fig3.add_vline(x=0, line_dash="dash", annotation_text="NPV = 0")
            fig3.update_layout(height=380)
            st.plotly_chart(fig3, width="stretch")
            st.dataframe(format_percentiles(s["percentiles"]), width="stretch")