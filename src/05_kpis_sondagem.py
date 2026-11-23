"""
KPIs operacionais da campanha de sondagem a partir dos boletins diários das sondas:
avanço x meta, produtividade e disponibilidade por sonda, recuperação de testemunho
e causas de parada. Os boletins passam por validação antes (log em saida/kpis/).
Gera as tabelas em saida/kpis/ (prontas para Power BI) e o painel saida/figuras/painel_sondagem.png.
"""
from pathlib import Path
import re
import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates
import matplotlib.ticker

RAIZ = Path(__file__).resolve().parents[1]
BR, TR, SAI = RAIZ / "dados/brutos", RAIZ / "dados/tratados", RAIZ / "saida"
OUT = SAI / "kpis"; OUT.mkdir(parents=True, exist_ok=True)
META_MENSAL = 560           # m/mês planejados para as 3 sondas
META_REC = 0.90             # recuperação mínima na zona mineralizada

man = pd.read_csv(BR / "boletim_manobras.csv")
tur = pd.read_csv(BR / "boletim_turnos.csv")
collar = pd.read_csv(TR / "collar.csv")
lit = pd.read_csv(TR / "litologia.csv")
# zona mineralizada = intercepts significativos (>= 3% Cg em >= 2 m) calculados em 04_consultas_sql.py
zona = pd.read_csv(SAI / "sql/01_intercepts_significativos.csv")[["furo", "de", "ate"]]

# ================================================================ validação dos boletins
log = []
comp = man.ate - man.de
for r in man[man.recuperado_m > comp + 1e-6].itertuples():
    log.append(dict(tabela="manobras", chave=f"{r.furo} {r.de}-{r.ate} m", regra="Recuperação acima de 100%",
                    detalhe=f"{r.recuperado_m} m recuperados em {r.ate - r.de:.1f} m perfurados", acao="REVISAR"))
man = man.sort_values(["furo", "de"])
ant = man.groupby("furo").ate.shift()
for r in man[(ant.notna()) & ((man.de - ant).abs() > 1e-6)].itertuples():
    log.append(dict(tabela="manobras", chave=r.furo, regra="Manobras não contínuas", detalhe=f"em {r.de} m", acao="REVISAR"))
fim = man.groupby("furo").ate.max()
for f, pf in collar.set_index("furo").prof_final.items():
    if abs(fim.get(f, 0) - pf) > 1e-6:
        log.append(dict(tabela="manobras", chave=f, regra="Fim das manobras x profundidade final",
                        detalhe=f"manobras até {fim.get(f, 0)} m, collar {pf} m", acao="REVISAR"))
soma_h = tur.horas_operacao + tur.horas_parada
for r in tur[soma_h > 12 + 1e-6].itertuples():
    log.append(dict(tabela="turnos", chave=f"{r.sonda} {r.data} {r.turno}", regra="Turno com mais de 12 h",
                    detalhe=f"{r.horas_operacao} h operando + {r.horas_parada} h parada", acao="REVISAR"))
m_turno = man.groupby(["furo", "data", "turno"]).apply(lambda g: (g.ate - g.de).sum(), include_groups=False)
chk = tur.set_index(["furo", "data", "turno"]).metros_perfurados
dif = (chk - m_turno.reindex(chk.index).fillna(0)).abs()
for (f, d, t), v in dif[dif > 1e-6].items():
    log.append(dict(tabela="turnos", chave=f"{f} {d} {t}", regra="Metros do turno x manobras",
                    detalhe=f"diferença de {v:.1f} m", acao="REVISAR"))
log = pd.DataFrame(log, columns=["tabela", "chave", "regra", "detalhe", "acao"])
log.to_csv(OUT / "log_boletins.csv", index=False)
print(f"Boletins: {len(man)} manobras, {len(tur)} turnos, {len(log)} ocorrências")
print(log.to_string(index=False))

# ================================================================ meta mensal (plano da campanha)
ini = pd.Timestamp(tur.data.min())
total = collar.prof_final.sum()
meses = pd.period_range(ini, pd.Timestamp(tur.data.max()), freq="M")
meta, acum = [], 0.0
for i, m in enumerate(meses):
    v = META_MENSAL * ((m.days_in_month - ini.day + 1) / m.days_in_month if i == 0 else 1)
    v = max(0.0, min(v, total - acum)); acum += v
    meta.append(dict(mes=str(m), meta_m=round(v)))
meta = pd.DataFrame(meta)

# ================================================================ SQL
db = TR / "sondagem.db"
con = sqlite3.connect(db)
for nome, df in [("manobras", man), ("turnos", tur), ("litologia", lit), ("zona_mineralizada", zona), ("meta", meta)]:
    df.to_sql(nome, con, index=False, if_exists="replace")
sql = (RAIZ / "sql/kpis_sondagem.sql").read_text(encoding="utf-8")
blocos = re.split(r"^-- name: (\S+)\s*$", sql, flags=re.M)[1:]
k = {}
for nome, corpo in zip(blocos[::2], blocos[1::2]):
    k[nome] = pd.read_sql_query(corpo, con)
    k[nome].to_csv(OUT / f"{nome}.csv", index=False)
    print(f"\n== {nome}"); print(k[nome].to_string(index=False))
con.close()
# tabelas fato/dimensão para um painel em Power BI
man.to_csv(OUT / "fato_manobras.csv", index=False)
tur.to_csv(OUT / "fato_turnos.csv", index=False)
meta.to_csv(OUT / "dim_meta_mensal.csv", index=False)

# ================================================================ painel
AZUL, CINZA, TINTA2, GRADE, VERMELHO = "#2a78d6", "#a3a29c", "#52514e", "#e4e3df", "#e34948"
plt.rcParams.update({"font.size": 9.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
                     "axes.labelcolor": TINTA2, "savefig.dpi": 160, "axes.titleweight": "bold",
                     "axes.titlesize": 10.5})
fig, axs = plt.subplots(2, 2, figsize=(11, 7.6))

# 1) curva S: realizado x meta (acumulado)
ax = axs[0, 0]
k1 = k["k1_avanco_mensal_x_meta"]
dia = tur.groupby("data").metros_perfurados.sum().cumsum()
dia.index = pd.to_datetime(dia.index)
plano = pd.Series({ini + pd.Timedelta(days=d): min(total, META_MENSAL * 12 / 365 * (d + 1))
                   for d in range((dia.index.max() - ini).days + 1)})
ax.plot(plano.index, plano.values, color=CINZA, lw=2, ls=(0, (4, 3)), label=f"meta ({META_MENSAL} m/mês)")
ax.plot(dia.index, dia.values, color=AZUL, lw=2, label="realizado")
fim_plano = plano[plano >= total].index.min(); fim_real = dia[dia >= total].index.min()
ax.annotate(f"meta: fim em {fim_plano:%d/%m/%Y}", (fim_plano, total), xytext=(-8, 6), textcoords="offset points",
            ha="right", fontsize=8, color=TINTA2)
ax.set_ylim(0, total * 1.12)
ax.annotate(f"realizado em {fim_real:%d/%m/%Y}\n({(fim_real - fim_plano).days} dias de atraso)", (fim_real, total),
            xytext=(-4, -150), textcoords="offset points", ha="right", fontsize=8, color=TINTA2,
            arrowprops=dict(arrowstyle="-", color=CINZA, lw=0.8))
ax.set_title("Avanço acumulado da campanha (m)", loc="left"); ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.grid(axis="y", color=GRADE, lw=0.6)
MES = "jan fev mar abr mai jun jul ago set out nov dez".split()
ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=[1, 4, 7, 10]))
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{MES[matplotlib.dates.num2date(x).month - 1]}/{matplotlib.dates.num2date(x):%y}"))
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}".replace(",", ".")))

# 2) produtividade por sonda
ax = axs[0, 1]
k2 = k["k2_produtividade_por_sonda"].sort_values("sonda")
bars = ax.bar(k2.sonda, k2.metros_por_hora, color=AZUL, width=0.55)
for b, r in zip(bars, k2.itertuples()):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.04,
            f"{r.metros_por_hora:.2f} m/h\ndisponível {r.disponibilidade_pct:.0f}%".replace(".", ","), ha="center", va="bottom", fontsize=8, color=TINTA2)
ax.set_ylim(0, k2.metros_por_hora.max() * 1.35)
ax.set_title("Produtividade por sonda (m por hora operando)", loc="left"); ax.grid(axis="y", color=GRADE, lw=0.6)

# 3) recuperação na zona mineralizada por sonda
ax = axs[1, 0]
k5b = k["k5b_recuperacao_minerio_por_sonda"].sort_values("sonda")
bars = ax.bar(k5b.sonda, k5b.recuperacao_minerio_pct, color=AZUL, width=0.55)
for b, r in zip(bars, k5b.itertuples()):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() - 9, f"{r.recuperacao_minerio_pct:.1f}%".replace(".", ","),
            ha="center", va="top", fontsize=9, color="white", fontweight="bold")
ax.axhline(META_REC * 100, color=TINTA2, lw=1, ls=(0, (4, 3)))
ax.text(-0.42, META_REC * 100 + 1.2, "meta 90%", fontsize=8, color=TINTA2, ha="left")
ax.set_ylim(0, 108); ax.set_title("Recuperação na zona mineralizada (Cg ≥ 3%), por sonda", loc="left")
ax.grid(axis="y", color=GRADE, lw=0.6)

# 4) pareto de paradas
ax = axs[1, 1]
k6 = k["k6_pareto_paradas"].sort_values("horas")
ax.barh(k6.motivo_parada, k6.horas, color=AZUL, height=0.55)
for y, r in enumerate(k6.itertuples()):
    ax.text(r.horas + 3, y, f"{r.horas:.0f} h ({r.pct:.0f}%)", va="center", fontsize=8, color=TINTA2)
ax.set_xlim(0, k6.horas.max() * 1.3); ax.set_title("Horas paradas por motivo", loc="left")
ax.grid(axis="x", color=GRADE, lw=0.6)
for a in axs.flat:
    a.set_axisbelow(True)
fig.tight_layout(h_pad=2.2, w_pad=2.5); fig.savefig(SAI / "figuras" / "painel_sondagem.png"); plt.close(fig)
