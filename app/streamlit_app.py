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

ORNEK_METIN = (
    "Konya Karapınar'da 12 MWp kapasiteli bir güneş enerjisi santrali kurmayı planlıyoruz. "
    "Toplam yatırım bütçesi yaklaşık 8,1 milyon dolar. Bölgede yıllık üretimin 20.400 MWh "
    "civarında olması bekleniyor. Elektriği 25 yıl boyunca 0,072 $/kWh fiyatla satmayı "
    "hedefliyoruz. Finansmanın %65'i bankadan, %9,5 faizle 12 yıl vadeli krediyle sağlanacak. "
    "Yıllık işletme ve bakım gideri 140 bin dolar civarında."
)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def values_from(a: SolarAssumptions) -> dict:
    """Varsayımları kenar çubuğundaki kutucukların değerlerine çevirir."""
    return {
        "capacity": float(clamp(a.capacity_mwp, 1.0, 500.0)),
        "life": int(clamp(a.project_life_years, 10, 40)),
        "capex": int(clamp(round(a.capex_per_mwp), 100_000, 2_000_000)),
        "yield": int(clamp(round(a.specific_yield_mwh_per_mwp), 500, 3_000)),
        "degradation": round(clamp(a.degradation_rate * 100, 0.0, 2.0), 2),
        "price": float(round(clamp(a.electricity_price_per_mwh, 10.0, 300.0), 2)),
        "price_esc": round(clamp(a.price_escalation * 100, -5.0, 10.0), 2),
        "opex": int(clamp(round(a.opex_per_mwp_year), 0, 100_000)),
        "tax": round(clamp(a.tax_rate * 100, 0.0, 50.0), 2),
        "debt": round(clamp(a.debt_ratio * 100, 0.0, 90.0), 2),
        "interest": round(clamp(a.interest_rate * 100, 0.0, 25.0), 2),
        "tenor": int(clamp(a.loan_tenor_years, 1, 20)),
        "discount": round(clamp(a.discount_rate * 100, 1.0, 30.0), 2),
    }


# İlk açılışta örnek değerler
for key, value in values_from(base).items():
    st.session_state.setdefault(key, value)
st.session_state.setdefault("project_text", ORNEK_METIN)


def run_extraction():
    """'Varsayımları çıkar' düğmesi: Claude metni okur, Python dönüştürür."""
    from ai.extract import extract_assumptions

    st.session_state["extract_error"] = None
    text = st.session_state.get("project_text", "").strip()
    if not text:
        st.session_state["extract_error"] = "Önce bir proje metni yazın."
        return
    try:
        with st.spinner("Claude metni okuyor..."):
            a, report, notes = extract_assumptions(text)
    except Exception as err:
        st.session_state["extract_error"] = f"Varsayımlar çıkarılamadı: {err}"
        return
    for key, value in values_from(a).items():
        st.session_state[key] = value
    st.session_state["extract_report"] = report
    st.session_state["extract_notes"] = notes


def reset_to_example():
    for key, value in values_from(base).items():
        st.session_state[key] = value
    st.session_state["extract_report"] = None
    st.session_state["extract_error"] = None


def fmt_value(v):
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.4g}"


# ---------------- Başlık ----------------
st.title("☀️ FeasibilityAI — GES Fizibilite Analizi")
st.caption("Tüm rakamlar test edilmiş Python hesap motorundan gelir. "
           "Örnek varsayımlar hayalidir; bu araç yatırım tavsiyesi değildir.")

# ---------------- Yapay zeka: metinden varsayım çıkarma ----------------
with st.expander("🤖 Proje metninden varsayımları çıkar (yapay zeka)", expanded=True):
    st.text_area("Proje açıklaması", key="project_text", height=140)
    b1, b2, _ = st.columns([1, 1, 3])
    b1.button("Varsayımları çıkar", type="primary", on_click=run_extraction)
    b2.button("Örnek varsayımlara dön", on_click=reset_to_example)

    if st.session_state.get("extract_error"):
        st.error(st.session_state["extract_error"])

    report = st.session_state.get("extract_report")
    if report is not None:
        st.success("Varsayımlar soldaki menüye aktarıldı. Lütfen kontrol edin ve gerekirse düzeltin. "
                   "'Varsayılan' satırları metinde bulunamadı, örnek değerlerle dolduruldu.")
        shown = report.copy()
        shown["Deger"] = shown["Deger"].map(fmt_value)
        st.dataframe(shown, width="stretch")
        if st.session_state.get("extract_notes"):
            st.info(f"Claude'un notu: {st.session_state['extract_notes']}")
        st.caption("Birim dönüşümleri ve bütün hesaplar Python'da yapılır; yapay zeka yalnızca metni okur.")

# ---------------- Kenar çubuğu: varsayımlar ----------------
with st.sidebar:
    st.header("Varsayımlar")

    st.subheader("Proje")
    capacity = st.number_input("Kurulu güç (MWp)", 1.0, 500.0, step=1.0, key="capacity")
    life = st.slider("İşletme süresi (yıl)", 10, 40, key="life")
    capex = st.number_input("Yatırım maliyeti (USD/MWp)", 100_000, 2_000_000, step=10_000, key="capex")

    st.subheader("Üretim ve gelir")
    yield_ = st.number_input("İlk yıl üretim (MWh/MWp)", 500, 3_000, step=10, key="yield")
    degradation = st.slider("Yıllık verim kaybı (%)", 0.0, 2.0, step=0.1, key="degradation")
    price = st.number_input("Elektrik fiyatı (USD/MWh)", 10.0, 300.0, step=1.0, key="price")
    price_esc = st.slider("Yıllık fiyat artışı (%)", -5.0, 10.0, step=0.1, key="price_esc")

    st.subheader("Gider ve vergi")
    opex = st.number_input("OPEX (USD/MWp/yıl)", 0, 100_000, step=500, key="opex")
    tax = st.slider("Kurumlar vergisi (%)", 0.0, 50.0, step=0.5, key="tax")

    st.subheader("Finansman")
    debt = st.slider("Kredi oranı (%)", 0.0, 90.0, step=1.0, key="debt")
    interest = st.slider("Kredi faizi (%)", 0.0, 25.0, step=0.1, key="interest")
    tenor = st.slider("Kredi vadesi (yıl)", 1, 20, key="tenor")
    discount = st.slider("İskonto oranı / WACC (%)", 1.0, 30.0, step=0.1, key="discount")

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

# ---------------- Ana göstergeler ----------------
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
    shown_sc = pd.DataFrame({
        "Proje NPV (USD)": sc["Proje NPV (USD)"].map(lambda v: f"{v:,.0f}"),
        "Proje IRR": sc["Proje IRR"].map(lambda v: f"{v:.1%}"),
        "Ozkaynak IRR": sc["Ozkaynak IRR"].map(lambda v: f"{v:.1%}"),
        "Min DSCR": sc["Min DSCR"].map(lambda v: "-" if pd.isna(v) else f"{v:.2f}"),
    })
    st.subheader("Kötümser / baz / iyimser")
    st.dataframe(shown_sc, width="stretch")

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

# ---------------- Yatırım Komitesi Notu (yapay zeka) ----------------
st.divider()
st.header("📝 Yatırım Komitesi Notu")
st.caption("Rakamlar hesap motorundan alınır; yapay zeka yalnızca yorumlar ve yazar. "
           "Nottaki her sayı otomatik olarak kontrol edilir.")

if st.button("Notu yaz", type="primary", key="memo_button"):
    from ai.memo import build_facts, check_numbers, write_memo

    facts = build_facts(a)
    try:
        with st.spinner("Claude notu yazıyor... (yaklaşık 30-60 saniye)"):
            memo = write_memo(facts)
        st.session_state["memo_text"] = memo
        st.session_state["memo_unknown"] = check_numbers(memo, facts)
        st.session_state["memo_for"] = a.model_dump_json()
    except Exception as err:
        st.error(f"Not yazılamadı: {err}")

if st.session_state.get("memo_text"):
    if st.session_state.get("memo_for") != a.model_dump_json():
        st.info("Varsayımlar değişti. Güncel not için 'Notu yaz' düğmesine tekrar basın.")
    unknown = st.session_state.get("memo_unknown", [])
    if unknown:
        st.warning("⚠️ Rakam kontrolü: Notta hesap motorundan gelmeyen sayılar var: "
                   + ", ".join(unknown) + ". Bu kısımları dikkatle inceleyin.")
    else:
        st.success("✅ Rakam kontrolü: Nottaki tüm sayılar hesap motorundan geliyor.")
    st.markdown(st.session_state["memo_text"])
    st.download_button("Notu indir (.md)", st.session_state["memo_text"],
                       file_name="yatirim_komitesi_notu.md", mime="text/markdown")

# ---------------- İndirmeler ----------------
st.divider()
st.header("📥 İndir")
from export.excel import build_excel
from export.word import build_word

d1, d2 = st.columns(2)
d1.download_button(
    "Excel modelini indir (.xlsx)", build_excel(a),
    file_name="fizibilite_modeli.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
if st.session_state.get("memo_text"):
    d2.download_button(
        "Notu Word olarak indir (.docx)",
        build_word(st.session_state["memo_text"], a.project_name),
        file_name="yatirim_komitesi_notu.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
else:
    d2.info("Word belgesi için önce yukarıdan 'Notu yaz' düğmesine basın.")