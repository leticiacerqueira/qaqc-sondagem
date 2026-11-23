"""
Gera um banco de sondagem SIMULADO de um projeto de grafita fictício,
no formato em que os dados costumam chegar de campo e do laboratório:

  collar.csv            boca dos furos (coordenadas UTM, profundidade, atitude)
  survey.csv            desvio do furo (azimute e mergulho por profundidade)
  litologia.csv         descrição geológica por intervalo
  amostragem.csv        intervalos amostrados e número da amostra (folha de campo)
  insercao_controle.csv amostras de controle inseridas no lote (padrões, brancos, duplicatas)
  laudo_laboratorio.csv carbono grafítico (Cg %) e carbono total (CT %) devolvidos pelo laboratório, por lote
  padroes_certificados.csv valores certificados dos materiais de referência

Problemas foram inseridos de propósito (como acontece na vida real) para
serem encontrados pelas etapas seguintes. A lista fica em
dados/brutos/_gabarito_problemas.txt, que só serve para conferir a validação.
"""
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
RAIZ = Path(__file__).resolve().parents[1]
OUT = RAIZ / "dados" / "brutos"
OUT.mkdir(parents=True, exist_ok=True)
LD = 0.02  # limite de detecção do método (% Cg)
gabarito = []

# ---------------------------------------------------------------- collar
furos = []
n = 0
for linha in range(8):            # 8 seções N-S, espaçadas 50 m
    for col in range(5):          # 5 furos por seção, espaçados 50 m
        n += 1
        furos.append(dict(
            furo=f"FD-{n:03d}",
            este=round(381000 + col * 50 + rng.normal(0, 3), 2),
            norte=round(8805000 + linha * 50 + rng.normal(0, 3), 2),
            cota=round(612 + col * 4 - linha * 1.5 + rng.normal(0, 1), 2),
            prof_final=float(rng.integers(12, 26) * 10),
            azimute=90.0,
            mergulho=-60.0,
            data_inicio=None,
            sonda=f"SD-0{1 + n % 3}",
        ))
collar = pd.DataFrame(furos)
datas = pd.date_range("2025-03-03", periods=len(collar), freq="5D")
collar["data_inicio"] = datas.strftime("%Y-%m-%d")

# ---------------------------------------------------------------- geologia e teor "verdadeiro"
def zona_minerio(r):
    """Camada de xisto grafitoso que mergulha para leste: fica mais funda nos furos a leste."""
    col = (r.este - 381000) / 50
    topo = 45 + col * 22 + rng.normal(0, 4)
    esp = max(2.0, rng.normal(9, 3.5))
    return topo, topo + esp

registros_lit, teor_real = [], {}
for r in collar.itertuples():
    sap = float(rng.integers(8, 22))
    z0, z1 = zona_minerio(r)
    z0, z1 = round(z0), round(z1)
    gran = r.prof_final - float(rng.integers(15, 40)) if rng.random() < 0.5 else None
    lims = [(0, sap, "SAPROLITO"), (sap, z0, "XISTO"), (z0, z1, "XISTO GRAFITOSO")]
    if gran and gran > z1 + 5:
        lims += [(z1, gran, "XISTO"), (gran, r.prof_final, "GNAISSE")]
    else:
        lims += [(z1, r.prof_final, "XISTO")]
    for de, ate, lit in lims:
        if ate > de and de < r.prof_final:
            registros_lit.append(dict(furo=r.furo, de=float(de), ate=float(min(ate, r.prof_final)), litologia=lit))
    centro = 1 - abs((r.norte - 8805175) / 250)  # teor maior no meio do corpo
    teor_real[r.furo] = (z0, z1, 4.5 + 6.0 * max(centro, 0))
lit = pd.DataFrame(registros_lit)

# ---------------------------------------------------------------- amostragem (1 m) e teor verdadeiro
am = []
for r in collar.itertuples():
    z0, z1, media = teor_real[r.furo]
    for de in np.arange(0, r.prof_final, 1.0):
        meio = de + 0.5
        if z0 <= meio < z1:
            g = min(rng.lognormal(np.log(media), 0.45), 35)
        elif z0 - 4 <= meio < z1 + 4:          # halo
            g = rng.lognormal(np.log(0.9), 0.5)
        else:
            g = rng.lognormal(np.log(0.10), 0.7)
        am.append(dict(furo=r.furo, de=de, ate=de + 1.0, g=g))
am = pd.DataFrame(am)
# algumas lentes de grafita maciça (teor muito alto)
idx = am.index[am.g > 6].to_series().sample(6, random_state=1)
am.loc[idx, "g"] = [24.6, 27.9, 31.4, 26.2, 29.0, 33.5]

# ---------------------------------------------------------------- lotes e inserção de controles
padroes = pd.DataFrame([
    dict(padrao="PAD-BAIXO", valor_certificado=2.10, desvio_padrao=0.06),
    dict(padrao="PAD-MEDIO", valor_certificado=6.45, desvio_padrao=0.15),
    dict(padrao="PAD-ALTO", valor_certificado=14.80, desvio_padrao=0.30),
])
pmap = padroes.set_index("padrao")

fluxo = []        # amostras na ordem em que vão para o laboratório
num = 100000
lote_n, no_lote = 1, 0
ciclo_pad = ["PAD-BAIXO", "PAD-MEDIO", "PAD-ALTO"]
k_pad = 0
def novo_num():
    global num
    num += 1
    return f"AM{num}"

am = am.sort_values(["furo", "de"]).reset_index(drop=True)
am["amostra"] = None
for i, r in am.iterrows():
    sid = novo_num()
    am.at[i, "amostra"] = sid
    fluxo.append(dict(amostra=sid, lote=lote_n, tipo="ROTINA", ref=None, g=r.g))
    no_lote += 1
    if r.g > 20:                                # grafita maciça: geólogo insere branco logo depois
        fluxo.append(dict(amostra=novo_num(), lote=lote_n, tipo="BRANCO", ref="BRANCO-QZ", g=None))
    if no_lote % 20 == 0:                       # 1 padrão a cada 20 amostras
        p = ciclo_pad[k_pad % 3]; k_pad += 1
        fluxo.append(dict(amostra=novo_num(), lote=lote_n, tipo="PADRAO", ref=p, g=None))
    if no_lote % 25 == 0:                       # 1 branco a cada 25
        fluxo.append(dict(amostra=novo_num(), lote=lote_n, tipo="BRANCO", ref="BRANCO-QZ", g=None))
    # duplicatas: 1 a cada 30 no estéril e 1 a cada 6 na zona mineralizada (onde a precisão importa)
    zona = r.g > 1.0
    if no_lote % 30 == 0 or (zona and no_lote % 6 == 0):   # duplicata de campo (metade do testemunho)
        fluxo.append(dict(amostra=novo_num(), lote=lote_n, tipo="DUP_CAMPO", ref=sid, g=r.g))
    if no_lote % 30 == 15 or (zona and no_lote % 6 == 3):  # duplicata de polpa (mesmo pó, reanálise)
        fluxo.append(dict(amostra=novo_num(), lote=lote_n, tipo="DUP_POLPA", ref=sid, g=r.g))
    if no_lote >= 180:
        lote_n += 1; no_lote = 0
fl = pd.DataFrame(fluxo)
fl["lote"] = fl["lote"].map(lambda x: f"L{x:03d}")
lotes = sorted(fl.lote.unique())

# ---------------------------------------------------------------- "laboratório"
vies = {l: 1.0 for l in lotes}
for l in lotes[20:24]:                          # deriva do laboratório: +4 a +5,5%
    vies[l] = 1.04 + 0.005 * (int(l[1:]) - 21)
gabarito.append(f"Deriva do laboratório (viés positivo) nos lotes {', '.join(lotes[20:24])}")

res = []
prev_g = 0.0
for r in fl.itertuples():
    b = vies[r.lote]
    if r.tipo == "ROTINA":
        v = r.g * np.exp(rng.normal(0, 0.03)) * b
    elif r.tipo == "DUP_CAMPO":
        v = r.g * np.exp(rng.normal(0, 0.16)) * b
    elif r.tipo == "DUP_POLPA":
        v = r.g * np.exp(rng.normal(0, 0.04)) * b
    elif r.tipo == "PADRAO":
        c, s = pmap.loc[r.ref]
        v = rng.normal(c, s * 0.9) * b
    else:  # branco
        v = abs(rng.normal(0.008, 0.006)) + (prev_g * 0.011 if prev_g > 20 and rng.random() < 0.1 else 0)
    prev_g = r.g if r.tipo == "ROTINA" else 0.0
    res.append(v)
fl["v"] = res

# troca de padrão: etiqueta diz MEDIO, mas o pó enviado era o ALTO
ip = fl.index[(fl.tipo == "PADRAO") & (fl.ref == "PAD-MEDIO") & (fl.lote == "L010")][0]
fl.at[ip, "v"] = rng.normal(14.8, 0.2)
gabarito.append(f"Troca de padrão: {fl.at[ip,'amostra']} (L010) etiquetado PAD-MEDIO com valor de PAD-ALTO")
# falha pontual de padrão (> 3 DP) num lote sem deriva
ip2 = fl.index[(fl.tipo == "PADRAO") & (fl.ref == "PAD-BAIXO") & (fl.lote == "L031")][0]
fl.at[ip2, "v"] = 2.33
gabarito.append(f"Padrão fora de 3 DP: {fl.at[ip2,'amostra']} (L031)")
gabarito.append("Contaminação de branco após lentes de grafita maciça (> 20% Cg)")

def formata(v):
    if v < LD:
        return f"<{LD}"
    return f"{v:.2f}"
fl["cg_pct"] = fl.v.map(formata)
# carbono total = carbono grafítico + carbono de carbonatos (o Cg nunca pode passar do CT)
fl["ct"] = fl.v + rng.lognormal(np.log(0.25), 0.6, len(fl)) + rng.normal(0, 0.02, len(fl))
fl["ct_pct"] = fl.ct.map(formata)

# ---------------------------------------------------------------- problemas de banco inseridos
# 1) resultado em ppb (sem conversão) para uma amostra
i = fl.index[(fl.tipo == "ROTINA") & (fl.v > 3.0)][40]
fl.at[i, "cg_pct"] = f"{fl.at[i,'v']*10000:.0f}"
gabarito.append(f"Valor em ppm no lugar de %: {fl.at[i,'amostra']}")
# 1b) Cg e CT trocados pelo laboratório em 3 amostras mineralizadas (Cg > CT é impossível)
for i in fl.index[(fl.tipo == "ROTINA") & (fl.v > 3.0)][[90, 170, 230]]:
    fl.at[i, "cg_pct"], fl.at[i, "ct_pct"] = fl.at[i, "ct_pct"], fl.at[i, "cg_pct"]
    gabarito.append(f"Cg e CT trocados: {fl.at[i,'amostra']}")
# 2) códigos de sem resultado
for k, cod in zip([500, 1500, 2600], ["-", "IS", "NR"]):  # IS = amostra insuficiente, NR = não recebida
    j = fl.index[fl.tipo == "ROTINA"][k]
    fl.at[j, "cg_pct"] = cod; fl.at[j, "ct_pct"] = cod
    gabarito.append(f"Sem resultado ({cod}): {fl.at[j,'amostra']}")
# 3) valor negativo (código antigo de abaixo do LD)
j = fl.index[fl.tipo == "ROTINA"][3100]
fl.at[j, "cg_pct"] = "-0.02"
gabarito.append(f"Valor negativo -0.02: {fl.at[j,'amostra']}")
# 4) amostra repetida no laudo
dup = fl.iloc[[4000]].copy()
fl = pd.concat([fl.iloc[:4001], dup, fl.iloc[4001:]], ignore_index=True)
gabarito.append(f"Amostra repetida no laudo: {dup.amostra.iloc[0]}")
# 5) amostra enviada que não voltou do laboratório
perdida = fl[fl.tipo == "ROTINA"].iloc[5200].amostra
fl = fl[fl.amostra != perdida]
gabarito.append(f"Amostra sem laudo: {perdida}")

# collar
collar.loc[collar.furo == "FD-017", ["este", "norte"]] = collar.loc[collar.furo == "FD-017", ["norte", "este"]].values
gabarito.append("FD-017 com este/norte trocados")
collar.loc[collar.furo == "FD-029", "cota"] = np.nan
gabarito.append("FD-029 sem cota")
collar.loc[collar.furo == "FD-033", "mergulho"] = 60.0
gabarito.append("FD-033 com mergulho positivo no collar")

# survey: leituras a cada 30 m com pequeno desvio
sv = []
for r in collar.itertuples():
    az, dip = 90.0, -60.0
    for p in np.arange(0, r.prof_final + 1, 30.0):
        sv.append(dict(furo=r.furo, prof=float(min(p, r.prof_final)), azimute=round(az, 1), mergulho=round(dip, 1)))
        az += rng.normal(0.6, 0.5); dip += rng.normal(0.25, 0.2)
sv = pd.DataFrame(sv).drop_duplicates(["furo", "prof"])
k = sv.index[(sv.furo == "FD-008") & (sv.prof == 90)][0]
sv.at[k, "azimute"] = sv.at[k, "azimute"] + 38
gabarito.append("Survey FD-008 a 90 m: salto de azimute (~38°)")

# litologia: grafias diferentes e intervalos com problema
for f, nome in [("FD-004", "Xisto"), ("FD-021", "xisto "), ("FD-036", "XISTO GRAF."), ("FD-012", "Saprolito")]:
    m = lit.index[(lit.furo == f)][[1, 2, 0, 0][["FD-004", "FD-021", "FD-036", "FD-012"].index(f)]]
    lit.at[m, "litologia"] = nome
gabarito.append("Grafias diferentes de litologia (Xisto, 'xisto ', XISTO GRAF., Saprolito)")
m = lit.index[lit.furo == "FD-014"][1]
lit.at[m, "de"] = lit.at[m, "de"] - 2
gabarito.append("FD-014: sobreposição de 2 m na litologia")
m = lit.index[lit.furo == "FD-025"][2]
lit.at[m, "de"] = lit.at[m, "de"] + 1.5
gabarito.append("FD-025: lacuna de 1,5 m na litologia")
m = lit.index[lit.furo == "FD-038"][-1]
lit.at[m, "ate"] = lit.at[m, "ate"] + 6
gabarito.append("FD-038: litologia passa da profundidade final")

amostragem = am[["furo", "de", "ate", "amostra"]].copy()
# intervalo invertido e sobreposição na amostragem
j = amostragem.index[amostragem.furo == "FD-019"][55]
de0, ate0 = amostragem.at[j, "de"], amostragem.at[j, "ate"]
amostragem.at[j, "de"], amostragem.at[j, "ate"] = ate0, de0
gabarito.append("FD-019: intervalo de amostragem com de > ate")
j = amostragem.index[amostragem.furo == "FD-027"][70]
amostragem.at[j, "ate"] = amostragem.at[j, "ate"] + 0.5
gabarito.append("FD-027: sobreposição de 0,5 m na amostragem")
# furo amostrado que não existe no collar (erro de digitação)
j = amostragem.index[amostragem.furo == "FD-040"][:3]
amostragem.loc[j, "furo"] = "FD-40"
gabarito.append("Amostras com furo 'FD-40' (não existe no collar)")

# ---------------------------------------------------------------- salvar
ctrl = fl[fl.tipo != "ROTINA"][["amostra", "lote", "tipo", "ref"]].rename(columns={"ref": "referencia"})
laudo = fl[["lote", "amostra", "cg_pct", "ct_pct"]]
collar.to_csv(OUT / "collar.csv", index=False)
sv.to_csv(OUT / "survey.csv", index=False)
lit.to_csv(OUT / "litologia.csv", index=False)
amostragem.to_csv(OUT / "amostragem.csv", index=False)
ctrl.to_csv(OUT / "insercao_controle.csv", index=False)
laudo.to_csv(OUT / "laudo_laboratorio.csv", index=False)
padroes.to_csv(OUT / "padroes_certificados.csv", index=False)
(OUT / "_gabarito_problemas.txt").write_text("\n".join(gabarito) + "\n", encoding="utf-8")

print(f"{len(collar)} furos, {collar.prof_final.sum():.0f} m perfurados")
print(f"{len(amostragem)} amostras de rotina, {len(ctrl)} de controle, {len(lotes)} lotes")
print(ctrl.tipo.value_counts().to_string())
