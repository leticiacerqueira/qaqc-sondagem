"""
QA/QC das análises de carbono grafítico (Cg %): padrões certificados, brancos e duplicatas.

Pergunta: os teores de grafita deste banco são confiáveis o suficiente para entrar
numa estimativa de recurso? Quais lotes precisam ser reanalisados?

Critérios usados (referências comuns na indústria, ajustáveis no topo do script):
  Padrão  : falha se fora de ±3 DP do valor certificado, ou 2 seguidos fora de ±2 DP do mesmo lado,
            ou se a média dos padrões do lote ficar além de ±1,5 DP (viés do laboratório)
  Branco  : falha se Cg > 10 x limite de detecção (0,20% Cg)
  Duplicata de polpa : 90% dos pares com HARD <= 10%
  Duplicata de campo : 90% dos pares com HARD <= 20%
HARD = metade da diferença relativa absoluta = |A - B| / (A + B).
Pares com média abaixo de 10 x LD ficam fora da precisão (perto do LD o erro relativo explode).
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[1]
TR, SAI = RAIZ / "dados/tratados", RAIZ / "saida"
FIG = SAI / "figuras"; FIG.mkdir(parents=True, exist_ok=True)
LD = 0.02  # % Cg
LIM_BRANCO = 10 * LD
CRIT_HARD = {"DUP_POLPA": 10, "DUP_CAMPO": 20}

AZUL, LARANJA, VERMELHO = "#2a78d6", "#eb6834", "#e34948"
TINTA, TINTA2, GRADE = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": TINTA2, "axes.labelcolor": TINTA2,
                     "xtick.color": TINTA2, "ytick.color": TINTA2, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 110, "savefig.dpi": 160,
                     "axes.titleweight": "bold", "axes.titlesize": 11})

ctrl = pd.read_csv(TR / "controle.csv")
amostras = pd.read_csv(TR / "amostras.csv")
padroes = pd.read_csv(RAIZ / "dados/brutos/padroes_certificados.csv").set_index("padrao")
laudo = pd.read_csv(RAIZ / "dados/brutos/laudo_laboratorio.csv", dtype={"cg_pct": str})
ordem = {a: i for i, a in enumerate(laudo.amostra.drop_duplicates())}   # ordem de análise
ctrl["ordem"] = ctrl.amostra.map(ordem)
amostras["ordem"] = amostras.amostra.map(ordem)

# ================================================================ PADRÕES
pad = ctrl[ctrl.tipo == "PADRAO"].sort_values("ordem").copy()
pad["certificado"] = pad.referencia.map(padroes.valor_certificado)
pad["dp"] = pad.referencia.map(padroes.desvio_padrao)
pad["z"] = (pad.cg - pad.certificado) / pad.dp
pad["situacao"] = "OK"
pad.loc[pad.z.abs() > 2, "situacao"] = "ALERTA_2DP"
pad.loc[pad.z.abs() > 3, "situacao"] = "FALHA_3DP"

# troca de padrão: fora de 3 DP do esperado, mas dentro de 3 DP de outro padrão
def outro_padrao(r):
    for nome, p in padroes.iterrows():
        if nome != r.referencia and abs(r.cg - p.valor_certificado) <= 3 * p.desvio_padrao:
            return nome
    return None
falhas = pad.situacao == "FALHA_3DP"
pad.loc[falhas, "provavel_padrao"] = pad[falhas].apply(outro_padrao, axis=1)
pad.loc[pad.provavel_padrao.notna(), "situacao"] = "TROCA_DE_PADRAO"

# dois seguidos fora de 2 DP do mesmo lado (mesmo padrão): marca o segundo
pad["seq_2dp"] = False
for nome, g in pad.groupby("referencia"):
    lado = pd.Series(np.where(g.z > 2, 1, np.where(g.z < -2, -1, 0)), index=g.index)
    pad.loc[g.index, "seq_2dp"] = (lado != 0) & (lado == lado.shift())

vies = (pad.groupby("referencia").apply(lambda g: (g.cg.mean() / g.certificado.iloc[0] - 1) * 100,
        include_groups=False)).rename("vies_pct")

# ================================================================ BRANCOS
br = ctrl[ctrl.tipo == "BRANCO"].copy()
seq_lab = pd.concat([amostras[["amostra", "ordem", "cg"]], ctrl[["amostra", "ordem", "cg"]]]).sort_values("ordem")
seq_lab["cg_anterior"] = seq_lab.cg.shift()
br = br.merge(seq_lab[["amostra", "cg_anterior"]], on="amostra", how="left")
br["falha"] = br.cg > LIM_BRANCO

# ================================================================ DUPLICATAS
dup = ctrl[ctrl.tipo.isin(["DUP_CAMPO", "DUP_POLPA"])].merge(
    amostras[["amostra", "cg"]].rename(columns={"amostra": "referencia", "cg": "cg_original"}),
    on="referencia", how="left").rename(columns={"cg": "cg_duplicata"})
dup["media"] = (dup.cg_original + dup.cg_duplicata) / 2
dup["hard"] = (dup.cg_original - dup.cg_duplicata).abs() / (dup.cg_original + dup.cg_duplicata) * 100
dup_val = dup[dup.media >= 10 * LD].copy()
prec = []
for tipo, g in dup_val.groupby("tipo"):
    lim = CRIT_HARD[tipo]
    pct = (g.hard <= lim).mean() * 100
    prec.append(dict(tipo=tipo, pares_validos=len(g), criterio=f"90% com HARD <= {lim}%",
                     pct_dentro=round(pct, 1), hard_p90=round(g.hard.quantile(0.9), 1),
                     resultado="APROVADO" if pct >= 90 else "REPROVADO"))
prec = pd.DataFrame(prec)

# ================================================================ DECISÃO POR LOTE
lotes = []
for lote in sorted(set(ctrl.lote)):
    p = pad[pad.lote == lote]; b = br[br.lote == lote]
    motivos = []
    for r in p[p.situacao == "FALHA_3DP"].itertuples():
        motivos.append(f"{r.referencia} {r.z:+.1f} DP ({r.amostra})")
    for r in p[p.seq_2dp].itertuples():
        motivos.append(f"{r.referencia} 2 seguidos > 2 DP ({r.amostra})")
    for r in b[b.falha].itertuples():
        motivos.append(f"branco {r.cg:.2f}% Cg após amostra de {r.cg_anterior:.1f}% ({r.amostra})")
    obs = [f"etiqueta {r.referencia} com valor de {r.provavel_padrao} ({r.amostra}): corrigir cadastro, não reprova o lote"
           for r in p[p.situacao == "TROCA_DE_PADRAO"].itertuples()]
    vies_lote = (p[p.situacao != "TROCA_DE_PADRAO"].z.mean() if len(p) else np.nan)
    if vies_lote >= 1.5 or vies_lote <= -1.5:
        motivos.insert(0, f"viés: padrões do lote em média {vies_lote:+.1f} DP")
    lotes.append(dict(lote=lote, padroes=len(p), brancos=len(b), z_medio_padroes=round(vies_lote, 2),
                      decisao="REANALISAR" if motivos else "APROVADO",
                      motivo="; ".join(dict.fromkeys(motivos)), observacao="; ".join(obs)))
lotes = pd.DataFrame(lotes)

pad.to_csv(SAI / "qaqc_padroes.csv", index=False)
br.to_csv(SAI / "qaqc_brancos.csv", index=False)
dup.to_csv(SAI / "qaqc_duplicatas.csv", index=False)
prec.to_csv(SAI / "qaqc_precisao.csv", index=False)
lotes.to_csv(SAI / "qaqc_lotes.csv", index=False)

# ================================================================ FIGURAS
# 1) cartas de controle dos padrões (uma por padrão)
fig, axs = plt.subplots(3, 1, figsize=(10, 8.2), sharex=True)
for ax, (nome, p) in zip(axs, padroes.iterrows()):
    g = pad[pad.referencia == nome]
    c, s = p.valor_certificado, p.desvio_padrao
    ax.axhline(c, color=TINTA2, lw=1)
    for k, ls in [(2, (0, (4, 3))), (3, "-")]:
        for sg in (1, -1):
            ax.axhline(c + sg * k * s, color="#a3a29c" if k == 2 else TINTA2, lw=0.9, ls=ls)
    x = g.ordem
    gv = g[g.situacao != "TROCA_DE_PADRAO"]
    ax.plot(gv.ordem, gv.cg, color=AZUL, lw=1.2, marker="o", ms=4, zorder=3)
    ruins = g[g.situacao.isin(["FALHA_3DP"]) | g.seq_2dp]
    ax.scatter(ruins.ordem, ruins.cg, s=60, facecolor="none", edgecolor=VERMELHO, lw=1.8, zorder=4,
               label="falha (reanalisar lote)")
    tr = g[g.situacao == "TROCA_DE_PADRAO"]
    for r in tr.itertuples():
        ax.scatter([r.ordem], [c + 4.2 * s], marker="^", s=40, color=TINTA2, zorder=4, clip_on=False)
        ax.annotate(f"valor {r.cg:.2f} fora da escala: troca de padrão", (r.ordem, c + 4.2 * s),
                    xytext=(8, 0), textcoords="offset points", fontsize=8, color=TINTA2, va="center",
                    bbox=dict(boxstyle="square,pad=0.2", fc="white", ec="none"))
    lo, hi = c - 4.5 * s, c + 4.5 * s
    ax.set_ylim(lo, hi)
    ax.set_title(f"{nome}  ·  certificado {c:.2f} ± {s:.2f}% Cg  ·  viés médio {vies[nome]:+.1f}%", loc="left")
    ax.set_ylabel("Cg (%)")
    ax.text(1.005, c + 3 * s, "+3 DP", transform=ax.get_yaxis_transform(), fontsize=8, color=TINTA2, va="center")
    ax.text(1.005, c - 3 * s, "−3 DP", transform=ax.get_yaxis_transform(), fontsize=8, color=TINTA2, va="center")
    ax.grid(axis="y", color=GRADE, lw=0.6)
# faixa dos lotes com deriva
rep = lotes[lotes.decisao == "REANALISAR"].lote
for ax in axs:
    for l in rep:
        o = ctrl.loc[ctrl.lote == l, "ordem"]
        ax.axvspan(o.min(), o.max(), color=VERMELHO, alpha=0.07, lw=0)
axs[0].legend(loc="upper left", frameon=False, fontsize=8)
axs[-1].set_xlabel("Ordem de análise no laboratório (faixas = lotes reprovados)")
fig.tight_layout(); fig.savefig(FIG / "cartas_controle_padroes.png"); plt.close(fig)

# 2) brancos
fig, ax = plt.subplots(figsize=(10, 3.4))
ok = br[~br.falha]; ruim = br[br.falha]
ax.scatter(ok.amostra.map(ordem), ok.cg, s=12, color=AZUL, label="branco")
ax.scatter(ruim.amostra.map(ordem), ruim.cg, s=50, facecolor="none", edgecolor=VERMELHO, lw=1.8,
           label="acima do limite")
for r in ruim.itertuples():
    ax.annotate(f"{r.cg:.2f}% Cg, logo após amostra de {r.cg_anterior:.1f}%",
                (ordem[r.amostra], r.cg), xytext=(8, 0), textcoords="offset points", fontsize=8,
                color=TINTA2, va="center")
ax.axhline(LIM_BRANCO, color=TINTA2, lw=1, ls=(0, (4, 3)))
ax.text(1.005, LIM_BRANCO, "10 × LD", transform=ax.get_yaxis_transform(), fontsize=8, color=TINTA2, va="center")
ax.set_yscale("log"); ax.set_ylabel("Cg (%, log)")
ax.set_xlabel("Ordem de análise no laboratório")
ax.set_title("Brancos: contaminação aparece só depois de lentes de grafita maciça", loc="left")
ax.legend(frameon=False, fontsize=8, loc="upper left"); ax.grid(axis="y", color=GRADE, lw=0.6)
fig.tight_layout(); fig.savefig(FIG / "brancos.png"); plt.close(fig)

# 3) duplicatas: dispersão e curva HARD
fig, axs = plt.subplots(1, 2, figsize=(10, 4.2))
ax = axs[0]
for tipo, cor, rot in [("DUP_CAMPO", LARANJA, "campo"), ("DUP_POLPA", AZUL, "polpa")]:
    g = dup_val[dup_val.tipo == tipo]
    ax.scatter(g.cg_original, g.cg_duplicata, s=14, color=cor, alpha=0.8, label=f"duplicata de {rot}",
               edgecolor="white", lw=0.4)
lim = [0.15, 50]
ax.plot(lim, lim, color=TINTA2, lw=1)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
ax.set_xlabel("Cg original (%)"); ax.set_ylabel("Cg duplicata (%)")
ax.set_title("Original x duplicata", loc="left"); ax.legend(frameon=False, fontsize=8)
ax.grid(color=GRADE, lw=0.6)
ax = axs[1]
for tipo, cor, rot in [("DUP_CAMPO", LARANJA, "campo"), ("DUP_POLPA", AZUL, "polpa")]:
    g = np.sort(dup_val[dup_val.tipo == tipo].hard.values)
    p90 = np.percentile(g, 90)
    ax.plot(np.arange(1, len(g) + 1) / len(g) * 100, g, color=cor, lw=2,
            label=f"{rot}: 90% dos pares até {p90:.0f}% (limite {CRIT_HARD[tipo]}%)")
    ax.scatter([90], [p90], color=cor, s=30, zorder=3, edgecolor="white", lw=1)
    ax.plot([60, 100], [CRIT_HARD[tipo]] * 2, color=cor, lw=1, ls=(0, (2, 2)))
ax.axvline(90, color="#a3a29c", lw=0.9, ls=(0, (4, 3)))
ax.set_xlabel("% dos pares (ordenados)"); ax.set_ylabel("HARD (%)")
ax.set_title("Precisão (HARD)", loc="left"); ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_ylim(0, 60); ax.grid(axis="y", color=GRADE, lw=0.6)
fig.tight_layout(); fig.savefig(FIG / "duplicatas.png"); plt.close(fig)

# ================================================================ RESUMO
print("Viés dos padrões (%):"); print(vies.round(1).to_string())
print(pad.situacao.value_counts().to_string()); print("seq 2DP:", pad.seq_2dp.sum())
print(f"Brancos: {len(br)}, falhas: {br.falha.sum()}")
print(prec.to_string(index=False))
print(lotes[lotes.decisao != "APROVADO"].to_string(index=False))
print(lotes[lotes.observacao != ""][["lote", "observacao"]].to_string(index=False))
