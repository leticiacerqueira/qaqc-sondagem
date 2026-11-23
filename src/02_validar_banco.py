"""
Validação do banco de sondagem antes de qualquer análise.

Cada problema encontrado vira uma linha em saida/log_validacao.csv, com a regra
que falhou e a ação tomada:
  CORRIGIDO  -> correção objetiva e rastreável (ex.: sinal do mergulho, ppb -> ppm)
  REVISAR    -> precisa de decisão de quem conhece o furo (não se corrige no escuro)
Os dados tratados vão para dados/tratados/.
"""
from pathlib import Path
import re
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
BR, TR, SAI = RAIZ / "dados/brutos", RAIZ / "dados/tratados", RAIZ / "saida"
TR.mkdir(parents=True, exist_ok=True); SAI.mkdir(exist_ok=True)
LD = 0.005
log = []

def registra(tabela, chave, regra, detalhe, acao):
    log.append(dict(tabela=tabela, chave=chave, regra=regra, detalhe=detalhe, acao=acao))

collar = pd.read_csv(BR / "collar.csv")
survey = pd.read_csv(BR / "survey.csv")
lit = pd.read_csv(BR / "litologia.csv")
amostragem = pd.read_csv(BR / "amostragem.csv")
laudo = pd.read_csv(BR / "laudo_laboratorio.csv", dtype={"au_ppm": str})
ctrl = pd.read_csv(BR / "insercao_controle.csv")

# ======================================================== COLLAR
# coordenadas UTM: este tem 6 dígitos, norte tem 7 (fuso 24S, ~8,8 milhões)
troca = (collar.este > 1e6) & (collar.norte < 1e6)
for f in collar.loc[troca, "furo"]:
    registra("collar", f, "Coordenadas fora da faixa", "este e norte trocados", "CORRIGIDO")
collar.loc[troca, ["este", "norte"]] = collar.loc[troca, ["norte", "este"]].values

for f in collar.loc[collar.cota.isna(), "furo"]:
    registra("collar", f, "Campo obrigatório vazio", "cota ausente", "REVISAR")

# mergulho do collar deve bater com a primeira leitura do survey
prim = survey.sort_values("prof").groupby("furo").first()
for r in collar.itertuples():
    if r.furo in prim.index and np.sign(r.mergulho) != np.sign(prim.at[r.furo, "mergulho"]):
        registra("collar", r.furo, "Collar x survey", f"mergulho {r.mergulho:+.0f} no collar e "
                 f"{prim.at[r.furo,'mergulho']:+.0f} no survey", "CORRIGIDO")
        collar.loc[collar.furo == r.furo, "mergulho"] = -abs(r.mergulho)

for f in collar.loc[collar.furo.duplicated(), "furo"]:
    registra("collar", f, "Furo duplicado", "mesmo ID duas vezes", "REVISAR")

# ======================================================== SURVEY
survey = survey.sort_values(["furo", "prof"])
for f, g in survey.groupby("furo"):
    d_az = g.azimute.diff().abs()
    d_dip = g.mergulho.diff().abs()
    for i in g.index[(d_az > 10) | (d_dip > 5)]:
        registra("survey", f, "Desvio brusco entre leituras",
                 f"a {g.at[i,'prof']:.0f} m: azimute variou {d_az[i]:.1f}°", "REVISAR")
    pf = collar.loc[collar.furo == f, "prof_final"]
    if len(pf) and g.prof.max() > pf.iloc[0]:
        registra("survey", f, "Leitura além da profundidade final", "", "REVISAR")

# ======================================================== INTERVALOS (litologia e amostragem)
def checa_intervalos(df, tabela, chave_extra=None):
    df = df.copy()
    inv = df.de >= df.ate
    for i in df.index[inv]:
        registra(tabela, df.at[i, "furo"], "de >= ate", f"{df.at[i,'de']} - {df.at[i,'ate']}", "CORRIGIDO")
    df.loc[inv, ["de", "ate"]] = df.loc[inv, ["ate", "de"]].values
    df = df.sort_values(["furo", "de"])
    ant_ate = df.groupby("furo").ate.shift()
    sob = df.de < ant_ate - 1e-6
    lac = df.de > ant_ate + 1e-6
    for i in df.index[sob]:
        registra(tabela, df.at[i, "furo"], "Sobreposição", f"{df.at[i,'de']} m começa antes de {ant_ate[i]} m", "REVISAR")
    for i in df.index[lac]:
        registra(tabela, df.at[i, "furo"], "Lacuna", f"sem registro entre {ant_ate[i]} e {df.at[i,'de']} m", "REVISAR")
    pf = df.furo.map(collar.set_index("furo").prof_final)
    passa = df.ate > pf + 1e-6
    for i in df.index[passa]:
        registra(tabela, df.at[i, "furo"], "Passa da profundidade final",
                 f"vai até {df.at[i,'ate']} m, furo tem {pf[i]} m", "CORRIGIDO")
    df.loc[passa, "ate"] = pf[passa]
    return df

# padroniza códigos de litologia antes de checar
sinonimos = {"QZ-SULFETO": "QUARTZO-SULFETO"}
lit["lit_original"] = lit.litologia
lit["litologia"] = lit.litologia.str.strip().str.upper().replace(sinonimos)
for i in lit.index[lit.litologia != lit.lit_original]:
    registra("litologia", lit.at[i, "furo"], "Código fora do padrão",
             f"'{lit.at[i,'lit_original']}' -> {lit.at[i,'litologia']}", "CORRIGIDO")
lit = checa_intervalos(lit.drop(columns="lit_original"), "litologia")

# furo na amostragem que não existe no collar: tenta normalizar o formato FD-nnn
validos = set(collar.furo)
def normaliza(f):
    m = re.match(r"^\s*FD-?(\d+)\s*$", str(f), re.I)
    return f"FD-{int(m.group(1)):03d}" if m else f
orf = ~amostragem.furo.isin(validos)
for f in amostragem.loc[orf, "furo"].unique():
    novo = normaliza(f)
    acao = "CORRIGIDO" if novo in validos else "REVISAR"
    registra("amostragem", f, "Furo não existe no collar", f"'{f}' -> {novo}" if acao == "CORRIGIDO" else "", acao)
amostragem.loc[orf, "furo"] = amostragem.loc[orf, "furo"].map(normaliza)
amostragem = checa_intervalos(amostragem, "amostragem")

# ======================================================== LAUDO
dups = laudo.amostra.duplicated(keep="first")
for a in laudo.loc[dups, "amostra"]:
    iguais = laudo.loc[laudo.amostra == a, "au_ppm"].nunique() == 1
    registra("laudo", a, "Amostra repetida no laudo", "mesmo resultado" if iguais else "resultados diferentes",
             "CORRIGIDO" if iguais else "REVISAR")
laudo = laudo[~dups].copy()

def converte(txt):
    t = str(txt).strip()
    if t.startswith("<"):
        return LD / 2, "ABAIXO_LD"
    try:
        v = float(t)
    except ValueError:
        return np.nan, "SEM_RESULTADO"
    if v < 0:
        return LD / 2, "ABAIXO_LD"
    return v, "OK"
conv = laudo.au_ppm.map(converte)
laudo["au"] = [c[0] for c in conv]
laudo["status"] = [c[1] for c in conv]
for r in laudo[laudo.status == "SEM_RESULTADO"].itertuples():
    registra("laudo", r.amostra, "Sem resultado", f"código '{r.au_ppm}'", "REVISAR")
for r in laudo[laudo.au_ppm.str.startswith("-") & (laudo.status == "ABAIXO_LD")].itertuples():
    registra("laudo", r.amostra, "Valor negativo", f"'{r.au_ppm}' tratado como abaixo do LD", "CORRIGIDO")
# Au acima de 100 g/t sem ser pepita conhecida: provável ppb
ppb = laudo.au > 100
for r in laudo[ppb].itertuples():
    registra("laudo", r.amostra, "Valor fora da faixa", f"{r.au_ppm} parece ppb -> {r.au/1000:.3f} ppm", "CORRIGIDO")
laudo.loc[ppb, "au"] /= 1000
laudo.loc[ppb, "status"] = "CONVERTIDO_PPB"

# amostras enviadas x devolvidas
enviadas = set(amostragem.amostra) | set(ctrl.amostra)
for a in sorted(enviadas - set(laudo.amostra)):
    registra("laudo", a, "Amostra sem laudo", "enviada e não devolvida", "REVISAR")
for a in sorted(set(laudo.amostra) - enviadas):
    registra("laudo", a, "Laudo sem amostra cadastrada", "", "REVISAR")

# ======================================================== TABELAS TRATADAS
amostras = amostragem.merge(laudo[["amostra", "lote", "au", "status"]], on="amostra", how="left")
amostras["meio"] = (amostras.de + amostras.ate) / 2
# litologia de cada amostra pelo ponto médio do intervalo
def lito(row, idx=lit.groupby("furo")):
    g = idx.get_group(row.furo) if row.furo in idx.groups else None
    if g is None:
        return None
    m = g[(g.de <= row.meio) & (g.ate > row.meio)]
    return m.litologia.iloc[-1] if len(m) else None
amostras["litologia"] = amostras.apply(lito, axis=1)
controle = ctrl.merge(laudo[["amostra", "au", "status"]], on="amostra", how="left")

collar.to_csv(TR / "collar.csv", index=False)
survey.to_csv(TR / "survey.csv", index=False)
lit.to_csv(TR / "litologia.csv", index=False)
amostras.drop(columns="meio").to_csv(TR / "amostras.csv", index=False)
controle.to_csv(TR / "controle.csv", index=False)

log = pd.DataFrame(log)
log.to_csv(SAI / "log_validacao.csv", index=False)
print(f"{len(log)} ocorrências ({(log.acao=='CORRIGIDO').sum()} corrigidas, {(log.acao=='REVISAR').sum()} para revisar)")
print(log.groupby(["tabela", "regra", "acao"]).size().to_string())
