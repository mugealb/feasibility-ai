"""GES projesi varsayımları.

Excel'deki 'Varsayımlar' sekmesinin Python karşılığı.
Pydantic, Excel'deki 'Veri Doğrulama' gibi çalışır:
mantıksız bir değer girilirse (ör. %150 kredi oranı) hata verir.
Böylece LLM'in metinden çıkardığı varsayımlar da modele girmeden kontrol edilir.
"""

from pydantic import BaseModel, Field, model_validator


class SolarAssumptions(BaseModel):
    """Güneş enerjisi santrali (GES) fizibilite varsayımları. Tutarlar USD."""

    # Proje
    project_name: str = Field(description="Proje adı")
    capacity_mwp: float = Field(gt=0, description="Kurulu güç (MWp)")
    project_life_years: int = Field(ge=1, le=50, description="İşletme süresi (yıl)")

    # Yatırım
    capex_per_mwp: float = Field(gt=0, description="MWp başına yatırım maliyeti (USD)")

    # Üretim ve gelir
    specific_yield_mwh_per_mwp: float = Field(gt=0, description="MWp başına ilk yıl üretimi (MWh/yıl)")
    degradation_rate: float = Field(ge=0, le=0.05, description="Yıllık panel verim kaybı (0.005 = %0,5)")
    electricity_price_per_mwh: float = Field(gt=0, description="İlk yıl elektrik satış fiyatı (USD/MWh)")
    price_escalation: float = Field(ge=-0.10, le=0.20, description="Yıllık fiyat artışı")

    # Giderler ve vergi
    opex_per_mwp_year: float = Field(ge=0, description="MWp başına yıllık işletme gideri (USD)")
    opex_escalation: float = Field(ge=-0.10, le=0.20, description="Yıllık OPEX artışı")
    tax_rate: float = Field(ge=0, le=0.5, description="Kurumlar vergisi oranı")
    depreciation_years: int = Field(ge=1, le=50, description="Doğrusal amortisman süresi (yıl)")

    # Finansman
    debt_ratio: float = Field(ge=0, le=0.9, description="Kredi / toplam yatırım")
    interest_rate: float = Field(ge=0, le=0.5, description="Yıllık kredi faizi")
    loan_tenor_years: int = Field(ge=1, le=30, description="Kredi vadesi (yıl)")
    discount_rate: float = Field(gt=0, le=0.5, description="İskonto oranı / WACC")

    @model_validator(mode="after")
    def check_periods(self):
        if self.loan_tenor_years > self.project_life_years:
            raise ValueError("Kredi vadesi proje ömründen uzun olamaz")
        if self.depreciation_years > self.project_life_years:
            raise ValueError("Amortisman süresi proje ömründen uzun olamaz")
        return self

    # Türetilen değerler (Excel'deki formül hücreleri gibi)
    @property
    def total_capex(self) -> float:
        return self.capacity_mwp * self.capex_per_mwp

    @property
    def debt_amount(self) -> float:
        return self.total_capex * self.debt_ratio

    @property
    def equity_amount(self) -> float:
        return self.total_capex - self.debt_amount

    @property
    def first_year_production_mwh(self) -> float:
        return self.capacity_mwp * self.specific_yield_mwh_per_mwp


def konya_example() -> SolarAssumptions:
    """Örnek vaka: Konya'da 10 MWp GES. Rakamlar hayalidir, yalnızca gösterim içindir."""
    return SolarAssumptions(
        project_name="Konya 10 MWp GES (örnek)",
        capacity_mwp=10,
        project_life_years=25,
        capex_per_mwp=700_000,
        specific_yield_mwh_per_mwp=1_650,
        degradation_rate=0.005,
        electricity_price_per_mwh=70,
        price_escalation=0.02,
        opex_per_mwp_year=12_000,
        opex_escalation=0.02,
        tax_rate=0.25,
        depreciation_years=10,
        debt_ratio=0.70,
        interest_rate=0.09,
        loan_tenor_years=10,
        discount_rate=0.10,
    )