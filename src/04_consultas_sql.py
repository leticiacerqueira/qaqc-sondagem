"""
Monta um banco SQLite com as tabelas tratadas e o resultado do QA/QC,
roda as consultas de sql/consultas.sql e gera o mapa de furos.
"""
from pathlib import Path
import re
import sqlite3
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[1]
TR, SAI = RAIZ / "dados/tratados", RAIZ / "saida"
(SAI / "sql").mkdir(parents=True, exist_ok=True)
db = TR / "sondagem.db"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
pd.read_csv(TR / "collar.csv").to_sql("collar", con, index=False)
pd.read_csv(TR / "amostras.csv").to_sql("amostras", con, index=False)
pd.read_csv(SAI / "qaqc_lotes.csv").to_sql("lotes_qaqc", con, index=False)

sql = (RAIZ / "sql/consultas.sql").read_text(encoding="utf-8")
blocos = re.split(r"^-- name: (\S+)\s*$", sql, flags=re.M)[1:]
res = {}
for nome, corpo in zip(blocos[::2], blocos[1::2]):
    df = pd.read_sql_query(corpo, con)
    res[nome] = df
    df.to_csv(SAI / "sql" / f"{nome}.csv", index=False)
    if nome.startswith("01_"):
        df.to_sql("resultado_01", con, index=False)   # reaproveitado pela consulta 02
    print(f"\n== {nome} ({len(df)} linhas)"); print(df.head(8).to_string(index=False))
con.close()

# ---------------------------------------------------------------- mapa de furos
AZUL, TINTA2 = "#2a78d6", "#52514e"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
                     "axes.labelcolor": TINTA2, "savefig.dpi": 160, "axes.titleweight": "bold"})
collar = pd.read_csv(TR / "collar.csv")
best = res["02_melhor_intercepto_por_furo"]
fig, ax = plt.subplots(figsize=(7.5, 6.2))
ax.scatter(collar.este, collar.norte, s=14, color="#c3c2b7", zorder=2, label="furo")
val = best[best.status_qaqc == "VALIDADO"]; prov = best[best.status_qaqc == "PROVISORIO"]
esc = 6
ax.scatter(val.este, val.norte, s=val.grama_metro * esc, color=AZUL, alpha=0.75, edgecolor="white",
           lw=1, zorder=3, label="melhor intercepto, validado")
ax.scatter(prov.este, prov.norte, s=prov.grama_metro * esc, facecolor="none", edgecolor=AZUL,
           lw=1.6, ls=(0, (2, 1.5)), zorder=3, label="provisório (lote a reanalisar)")
for r in best.head(5).itertuples():
    ax.annotate(f"{r.furo}\n{r.espessura_m:.0f} m @ {r.teor_g_t:.2f} g/t", (r.este, r.norte),
                xytext=(10, 6), textcoords="offset points", fontsize=8, color=TINTA2)
ax.set_aspect("equal"); ax.ticklabel_format(useOffset=False, style="plain")
ax.set_xlabel("Este (m, UTM)"); ax.set_ylabel("Norte (m, UTM)")
ax.set_xlim(collar.este.min() - 40, collar.este.max() + 70)
ax.set_title("Melhor intercepto por furo (tamanho = grama x metro)", loc="left", fontsize=11)
ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3,
          markerscale=0.5)
fig.tight_layout(); fig.savefig(SAI / "figuras" / "mapa_intercepts.png"); plt.close(fig)
