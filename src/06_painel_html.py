"""
Gera o painel interativo da campanha de sondagem (HTML único, sem dependências):
painel/index.html. Os dados vêm dos boletins validados e da litologia tratada.
"""
from pathlib import Path
import json
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
BR, TR, SAI = RAIZ / "dados/brutos", RAIZ / "dados/tratados", RAIZ / "saida"
man = pd.read_csv(BR / "boletim_manobras.csv")
tur = pd.read_csv(BR / "boletim_turnos.csv")
lit = pd.read_csv(TR / "litologia.csv")
collar = pd.read_csv(TR / "collar.csv")
meta = pd.read_csv(SAI / "kpis" / "dim_meta_mensal.csv")
lotes = pd.read_csv(SAI / "qaqc_lotes.csv")
ints = pd.read_csv(SAI / "sql" / "01_intercepts_significativos.csv")
log = pd.read_csv(SAI / "log_validacao.csv")

# litologia no ponto médio de cada manobra
def lito(r):
    g = lit[(lit.furo == r.furo) & (lit.de <= (r.de + r.ate) / 2) & (lit.ate > (r.de + r.ate) / 2)]
    return g.litologia.iloc[0] if len(g) else "SEM DESCRIÇÃO"
man["litologia"] = man.apply(lito, axis=1)
man["valida"] = man.recuperado_m <= (man.ate - man.de) + 1e-9
# zona mineralizada = manobra com ponto médio dentro de um intercepto significativo (>= 3% Cg em >= 2 m)
def na_zona(r):
    m = (r.de + r.ate) / 2
    return int(((ints.furo == r.furo) & (ints.de <= m) & (ints.ate > m)).any())
man["zona"] = man.apply(na_zona, axis=1)
tur["valido"] = (tur.horas_operacao + tur.horas_parada) <= 12 + 1e-9

LITS = ["SOLO RESIDUAL", "SAPROLITO", "GNAISSE KINZIGÍTICO GRAFITOSO", "VEIO PEGMATÓIDE", "SEM DESCRIÇÃO"]
furos = sorted(collar.furo)
dados = {
    "furos": [dict(id=r.furo, sonda=r.sonda, prof=r.prof_final) for r in collar.sort_values("furo").itertuples()],
    "lits": LITS,
    "metaMensal": int(meta.meta_m.max()), "inicio": str(tur.data.min()),
    "meta": dict(zip(meta.mes, meta.meta_m.astype(int))),
    "turnos": [[r.data, r.turno, r.sonda, r.furo, r.horas_operacao, r.horas_parada, r.motivo_parada if isinstance(r.motivo_parada, str) else "",
                r.metros_perfurados, int(r.valido)] for r in tur.itertuples()],
    # [furo_idx, de, ate, recuperado, lit_idx, data, valida, zona_mineralizada]
    "manobras": [[furos.index(r.furo), r.de, r.ate, r.recuperado_m, LITS.index(r.litologia), r.data, int(r.valida), r.zona]
                 for r in man.itertuples()],
    "qaqc": dict(lotes=int(len(lotes)), reprovados=int((lotes.decisao == "REANALISAR").sum()),
                 interceptos=int(len(ints)), provisorios=int((ints.status_qaqc == "PROVISORIO").sum()),
                 ocorrencias=int(len(log)), corrigidas=int((log.acao == "CORRIGIDO").sum())),
}
js = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
tpl = (RAIZ / "src" / "painel_template.html").read_text(encoding="utf-8")
corpo = tpl.replace("/*__DADOS__*/null", js)
(RAIZ / "painel").mkdir(exist_ok=True)
pagina = ('<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
          '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
          '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
          'body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n</head>\n<body>\n'
          + corpo + "\n</body>\n</html>\n")
(RAIZ / "painel" / "index.html").write_text(pagina, encoding="utf-8")
(SAI / "painel_fragmento.html").write_text(corpo, encoding="utf-8")
print(f"painel/index.html: {len(pagina)/1024:.0f} KB")
