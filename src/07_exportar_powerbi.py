"""
Exporta o modelo estrela do painel de sondagem para o Power BI (saida/powerbi/):
fatos de manobras e turnos, dimensões de furo, sonda, meta mensal e lotes de QA/QC.
As medidas DAX e o passo a passo ficam em powerbi/.
"""
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
BR, TR, SAI = RAIZ / "dados/brutos", RAIZ / "dados/tratados", RAIZ / "saida"
OUT = SAI / "powerbi"; OUT.mkdir(parents=True, exist_ok=True)

man = pd.read_csv(BR / "boletim_manobras.csv")
tur = pd.read_csv(BR / "boletim_turnos.csv")
lit = pd.read_csv(TR / "litologia.csv")
collar = pd.read_csv(TR / "collar.csv")
ints = pd.read_csv(SAI / "sql/01_intercepts_significativos.csv")
melhor = pd.read_csv(SAI / "sql/02_melhor_intercepto_por_furo.csv")
meta = pd.read_csv(SAI / "kpis/dim_meta_mensal.csv")
lotes = pd.read_csv(SAI / "qaqc_lotes.csv")

# ---------- fato_manobras: litologia e zona mineralizada no ponto médio, flag de boletim válido
meio = (man.de + man.ate) / 2
def no_intervalo(tab, furo, m, col):
    g = tab[(tab.furo == furo) & (tab.de <= m) & (tab.ate > m)]
    return g[col].iloc[0] if len(g) else None
man["litologia"] = [no_intervalo(lit, f, m, "litologia") or "SEM DESCRIÇÃO" for f, m in zip(man.furo, meio)]
man["zona_mineralizada"] = [int(no_intervalo(ints, f, m, "furo") is not None) for f, m in zip(man.furo, meio)]
man["metros_perfurados"] = man.ate - man.de
man["boletim_valido"] = (man.recuperado_m <= man.metros_perfurados + 1e-9).astype(int)
man.to_csv(OUT / "fato_manobras.csv", index=False)

# ---------- fato_turnos: flag de turno com horas consistentes
tur["motivo_parada"] = tur.motivo_parada.fillna("Sem parada")
tur["turno_valido"] = ((tur.horas_operacao + tur.horas_parada) <= 12 + 1e-9).astype(int)
tur.to_csv(OUT / "fato_turnos.csv", index=False)

# ---------- dim_furo: collar + melhor intercepto
dim = collar.merge(melhor[["furo", "de", "espessura_m", "teor_cg_pct", "pct_metro", "status_qaqc"]]
                   .rename(columns={"de": "intercepto_de_m"}), on="furo", how="left")
dim["status_qaqc"] = dim.status_qaqc.fillna("SEM INTERCEPTO")
dim.to_csv(OUT / "dim_furo.csv", index=False)

pd.DataFrame({"sonda": ["SD-01", "SD-02", "SD-03"]}).to_csv(OUT / "dim_sonda.csv", index=False)
meta.assign(data=pd.to_datetime(meta.mes + "-01")).to_csv(OUT / "dim_meta_mensal.csv", index=False)
lotes.to_csv(OUT / "dim_lote_qaqc.csv", index=False)
for f in sorted(OUT.glob("*.csv")):
    print(f"{f.name}: {sum(1 for _ in open(f, encoding='utf-8')) - 1} linhas")
