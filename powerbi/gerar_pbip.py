"""
Gera o projeto do Power BI (formato PBIP: modelo em TMDL + relatório) em powerbi/Painel Sondagem/.
Os dados vêm direto dos CSVs públicos do repositório no GitHub (saida/powerbi/), então o arquivo
abre em qualquer computador sem ajustar caminho de pasta.
Abrir no Power BI Desktop: Arquivo > Abrir > "Painel Sondagem.pbip" e depois Atualizar.
"""
from pathlib import Path
import json, re, shutil, uuid

AQUI = Path(__file__).resolve().parent
NOME = "Painel Sondagem"
RAIZ = AQUI / NOME
URL = "https://raw.githubusercontent.com/leticiacerqueira/qaqc-sondagem/main/saida/powerbi/"
NAVY, AZUL, CINZA, FUNDO = "#0B1F3A", "#1F6FD1", "#B8BEC6", "#F3F5F8"

def gid(*k):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "painel-sondagem/" + "/".join(k)))

def q(n):  # nome TMDL: aspas simples quando tem espaço ou símbolo
    return n if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) else "'" + n.replace("'", "''") + "'"

# ------------------------------------------------------------------ tabelas
# (nome, tipo TMDL, tipo M, formato, resumo)
T, D, I, S = "double", "dateTime", "int64", "string"
TABELAS = {
    "fato_turnos": [("data", D), ("turno", S), ("sonda", S), ("furo", S), ("horas_operacao", T), ("horas_parada", T),
                    ("motivo_parada", S), ("metros_perfurados", T), ("turno_valido", I)],
    "fato_manobras": [("furo", S), ("sonda", S), ("data", D), ("turno", S), ("de", T), ("ate", T), ("recuperado_m", T),
                      ("litologia", S), ("zona_mineralizada", I), ("metros_perfurados", T), ("boletim_valido", I)],
    "dim_furo": [("furo", S), ("este", T), ("norte", T), ("cota", T), ("prof_final", T), ("azimute", T), ("mergulho", T),
                 ("data_inicio", D), ("sonda", S), ("intercepto_de_m", T), ("espessura_m", T), ("teor_cg_pct", T),
                 ("pct_metro", T), ("status_qaqc", S)],
    "dim_sonda": [("sonda", S)],
    "dim_meta_mensal": [("mes", S), ("meta_m", I), ("data", D)],
    "dim_lote_qaqc": [("lote", S), ("padroes", I), ("brancos", I), ("z_medio_padroes", T), ("decisao", S), ("motivo", S),
                      ("observacao", S)],
}
MTIPO = {T: "type number", D: "type date", I: "Int64.Type", S: "type text"}

MEDIDAS = {
    "fato_turnos": [
        ("Metros Perfurados", "SUM ( fato_turnos[metros_perfurados] )", "#,0"),
        ("Meta (m)", """VAR m = SUM ( dim_meta_mensal[meta_m] )
RETURN IF ( ISFILTERED ( dim_sonda[sonda] ), m * DIVIDE ( COUNTROWS ( VALUES ( dim_sonda[sonda] ) ), 3 ), m )""", "#,0"),
        ("% da Meta", "DIVIDE ( [Metros Perfurados], [Meta (m)] )", "0.0%"),
        ("Metros Acumulados", """CALCULATE ( [Metros Perfurados],
    FILTER ( ALL ( dCalendario[Data] ), dCalendario[Data] <= MAX ( dCalendario[Data] ) ) )""", "#,0"),
        ("Meta Acumulada", """CALCULATE ( [Meta (m)],
    FILTER ( ALL ( dCalendario[Data] ), dCalendario[Data] <= MAX ( dCalendario[Data] ) ) )""", "#,0"),
        ("Horas Operando", "CALCULATE ( SUM ( fato_turnos[horas_operacao] ), fato_turnos[turno_valido] = 1 )", "#,0"),
        ("Horas Paradas", "CALCULATE ( SUM ( fato_turnos[horas_parada] ), fato_turnos[turno_valido] = 1 )", "#,0"),
        ("Produtividade (m/h)", """DIVIDE ( CALCULATE ( [Metros Perfurados], fato_turnos[turno_valido] = 1 ), [Horas Operando] )""", "0.00"),
        ("Disponibilidade %", "DIVIDE ( [Horas Operando], [Horas Operando] + [Horas Paradas] )", "0.0%"),
        ("Metros por Turno", """DIVIDE ( CALCULATE ( [Metros Perfurados], fato_turnos[turno_valido] = 1 ),
    CALCULATE ( COUNTROWS ( fato_turnos ), fato_turnos[turno_valido] = 1 ) )""", "0.0"),
        ("% das Horas Paradas", "DIVIDE ( [Horas Paradas], CALCULATE ( [Horas Paradas], ALL ( fato_turnos[motivo_parada] ) ) )", "0%"),
        ("Principal Parada", """VAR t = TOPN ( 1, FILTER ( VALUES ( fato_turnos[motivo_parada] ), fato_turnos[motivo_parada] <> "Sem parada" ), [Horas Paradas], DESC )
RETURN CONCATENATEX ( t, fato_turnos[motivo_parada], ", " )""", None),
    ],
    "fato_manobras": [
        ("Recuperação %", """DIVIDE ( CALCULATE ( SUM ( fato_manobras[recuperado_m] ), fato_manobras[boletim_valido] = 1 ),
    CALCULATE ( SUM ( fato_manobras[metros_perfurados] ), fato_manobras[boletim_valido] = 1 ) )""", "0.0%"),
        ("Recuperação Zona Mineralizada %", "CALCULATE ( [Recuperação %], fato_manobras[zona_mineralizada] = 1 )", "0.0%"),
        ("Metros na Zona Mineralizada", """CALCULATE ( SUM ( fato_manobras[metros_perfurados] ),
    fato_manobras[zona_mineralizada] = 1, fato_manobras[boletim_valido] = 1 )""", "#,0"),
        ("Meta Recuperação", "0.9", "0%"),
        ("Furos Abaixo da Meta", """COUNTROWS ( FILTER ( VALUES ( fato_manobras[furo] ),
    VAR r = [Recuperação Zona Mineralizada %] RETURN NOT ISBLANK ( r ) && r < [Meta Recuperação] ) )""", "0"),
    ],
    "dim_lote_qaqc": [
        ("Lotes", "COUNTROWS ( dim_lote_qaqc )", "0"),
        ("Lotes Reprovados", """CALCULATE ( [Lotes], dim_lote_qaqc[decisao] = "REANALISAR" )""", "0"),
        ("Furos com Intercepto Provisório", """CALCULATE ( COUNTROWS ( dim_furo ), dim_furo[status_qaqc] = "PROVISORIO" )""", "0"),
    ],
}

def tab_m(nome, cols):
    tipos = ", ".join(f'{{"{c}", {MTIPO[t]}}}' for c, t in cols)
    return f'''let
    Fonte = Csv.Document(Web.Contents("{URL}{nome}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Tipos = Table.TransformColumnTypes(Cabecalhos, {{{tipos}}}, "en-US")
in
    Tipos'''

def bloco(texto, nivel):
    pad = "\t" * nivel
    return "\n".join(pad + l if l.strip() else "" for l in texto.splitlines())

def tmdl_tabela(nome, cols, medidas, m, extra_cols=""):
    out = [f"table {q(nome)}", f"\tlineageTag: {gid(nome)}", ""]
    for c, t in cols:
        out += [f"\tcolumn {q(c)}", f"\t\tdataType: {t}"]
        if t == D: out.append("\t\tformatString: dd/mm/yyyy")
        if t in (T, I): out.append("\t\tsummarizeBy: none" if c in ("turno_valido", "boletim_valido", "zona_mineralizada", "este", "norte", "cota", "azimute", "mergulho") else "\t\tsummarizeBy: sum")
        else: out.append("\t\tsummarizeBy: none")
        out += [f"\t\tlineageTag: {gid(nome, c)}", f"\t\tsourceColumn: {c}", ""]
    out.append(extra_cols)
    for n, expr, fmt in medidas:
        if "\n" in expr:
            out.append(f"\tmeasure {q(n)} =")
            out.append(bloco(expr, 3))
        else:
            out.append(f"\tmeasure {q(n)} = {expr}")
        if fmt: out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tlineageTag: {gid(nome, 'm', n)}", ""]
    out += [f"\tpartition {q(nome)} = m", "\t\tmode: import", "\t\tsource =", bloco(m, 4), ""]
    return "\n".join(out) + "\n"

CAL_COLS = [("Data", D), ("Ano", I), ("Mes Num", I), ("Mes", S), ("Ano-Mes", S)]
CAL_M = '''let
    Datas = List.Dates(#date(2024, 3, 1), Duration.Days(#date(2026, 4, 30) - #date(2024, 3, 1)) + 1, #duration(1, 0, 0, 0)),
    Tabela = Table.FromList(Datas, Splitter.SplitByNothing(), {"Data"}),
    Ano = Table.AddColumn(Tabela, "Ano", each Date.Year([Data]), Int64.Type),
    MesNum = Table.AddColumn(Ano, "Mes Num", each Date.Month([Data]), Int64.Type),
    Mes = Table.AddColumn(MesNum, "Mes", each {"jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"}{Date.Month([Data]) - 1} & "/" & Text.End(Text.From(Date.Year([Data])), 2), type text),
    AnoMes = Table.AddColumn(Mes, "Ano-Mes", each Date.ToText([Data], "yyyy-MM"), type text),
    Tipos = Table.TransformColumnTypes(AnoMes, {{"Data", type date}})
in
    Tipos'''

def gerar_modelo():
    sm = RAIZ / f"{NOME}.SemanticModel"
    d = sm / "definition"; (d / "tables").mkdir(parents=True)
    (sm / "definition.pbism").write_text(json.dumps({"version": "4.0", "settings": {}}, indent=2), encoding="utf-8")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n", encoding="utf-8")
    nomes = list(TABELAS) + ["dCalendario"]
    model = ["model Model", "\tculture: pt-BR", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: pt-BR", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", ""]
    model += [f"ref table {q(n)}" for n in nomes] + ["", "ref cultureInfo pt-BR", ""]
    (d / "model.tmdl").write_text("\n".join(model), encoding="utf-8")
    (d / "cultures").mkdir()
    (d / "cultures" / "pt-BR.tmdl").write_text("cultureInfo pt-BR\n", encoding="utf-8")
    for n, cols in TABELAS.items():
        (d / "tables" / f"{n}.tmdl").write_text(tmdl_tabela(n, cols, MEDIDAS.get(n, []), tab_m(n, cols)), encoding="utf-8")
    cal = tmdl_tabela("dCalendario", CAL_COLS, [], CAL_M)
    cal = cal.replace("\tlineageTag: " + gid("dCalendario") + "\n", "\tlineageTag: " + gid("dCalendario") + "\n\tdataCategory: Time\n", 1)
    cal = cal.replace("\tcolumn Data\n", "\tcolumn Data\n\t\tisKey\n", 1)
    cal = cal.replace(f"\t\tsourceColumn: Mes\n", "\t\tsourceColumn: Mes\n\t\tsortByColumn: 'Ano-Mes'\n", 1)
    (d / "tables" / "dCalendario.tmdl").write_text(cal, encoding="utf-8")
    rel = [("fato_turnos", "data", "dCalendario", "Data"), ("fato_manobras", "data", "dCalendario", "Data"),
           ("dim_meta_mensal", "data", "dCalendario", "Data"), ("fato_turnos", "sonda", "dim_sonda", "sonda"),
           ("fato_manobras", "sonda", "dim_sonda", "sonda"), ("fato_turnos", "furo", "dim_furo", "furo"),
           ("fato_manobras", "furo", "dim_furo", "furo")]
    out = []
    for a, ca, b, cb in rel:
        out += [f"relationship {gid('rel', a, ca, b)}", f"\tfromColumn: {q(a)}.{q(ca)}", f"\ttoColumn: {q(b)}.{q(cb)}", ""]
    (d / "relationships.tmdl").write_text("\n".join(out), encoding="utf-8")

# ------------------------------------------------------------------ relatório (report.json)
def lit(v):
    return {"expr": {"Literal": {"Value": v}}}

def cor(c):
    return {"solid": {"color": lit(f"'{c}'")}}

def visual(nome, tipo, x, y, w, h, campos=None, objetos=None, vc_objetos=None, titulo=None, z=1000):
    """campos: {projeção: [(tabela, campo, 'm'|'c')]}"""
    sv = {"visualType": tipo, "drillFilterOtherVisuals": True}
    if campos:
        apelidos, frm, sel, proj = {}, [], [], {}
        for papel, lst in campos.items():
            proj[papel] = []
            for t, c, k in lst:
                if t not in apelidos:
                    apelidos[t] = f"t{len(apelidos)}"
                    frm.append({"Name": apelidos[t], "Entity": t, "Type": 0})
                ref = f"{t}.{c}"
                expr = {"Expression": {"SourceRef": {"Source": apelidos[t]}}, "Property": c}
                if k == "a":   # coluna agregada (soma), exigida em eixos numéricos do gráfico de dispersão
                    ref = f"Sum({t}.{c})"
                    item = {"Aggregation": {"Expression": {"Column": expr}, "Function": 0}}
                else:
                    item = {"Measure": expr} if k == "m" else {"Column": expr}
                if ref not in [s["Name"] for s in sel]:
                    sel.append({**item, "Name": ref, **({"NativeReferenceName": c} if k == "m" else {})})
                proj[papel].append({"queryRef": ref, **({"active": True} if papel == "Category" else {})})
        sv["projections"] = proj
        sv["prototypeQuery"] = {"Version": 2, "From": frm, "Select": sel}
    if objetos: sv["objects"] = objetos
    vco = dict(vc_objetos or {})
    if titulo:
        vco["title"] = [{"properties": {"show": lit("true"), "text": lit(f"'{titulo}'"),
                                        "fontColor": cor(NAVY), "fontSize": lit("11D"), "bold": lit("true")}}]
    if tipo not in ("textbox", "basicShape"):
        vco.setdefault("background", [{"properties": {"show": lit("true"), "color": cor("#FFFFFF"), "transparency": lit("0D")}}])
        vco.setdefault("border", [{"properties": {"show": lit("true"), "color": cor("#E3E7EC"), "radius": lit("6D")}}])
    if vco: sv["vcObjects"] = vco
    cfg = {"name": nome, "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h}}], "singleVisual": sv}
    return {"x": x, "y": y, "z": z, "width": w, "height": h, "config": json.dumps(cfg, ensure_ascii=False), "filters": "[]"}

def texto(nome, x, y, w, h, linhas, z=2000):
    paras = [{"textRuns": [{"value": t, "textStyle": {"fontWeight": "bold" if b else "normal", "fontSize": f"{s}pt", "color": c,
                                                      "fontFamily": "Segoe UI" + (" Semibold" if b else "")}}]} for t, s, c, b in linhas]
    return visual(nome, "textbox", x, y, w, h, objetos={"general": [{"properties": {"paragraphs": paras}}]}, z=z)

def forma(nome, x, y, w, h, c, z=0):
    return visual(nome, "basicShape", x, y, w, h, z=z, objetos={
        "shape": [{"properties": {"tileShape": lit("'rectangle'")}}],
        "fill": [{"properties": {"show": lit("true"), "fillColor": cor(c), "transparency": lit("0D")}}],
        "outline": [{"properties": {"show": lit("false")}}]})

def card(nome, x, y, w, rotulo, t, med):
    return visual(nome, "card", x, y, w, 92, {"Values": [(t, med, "m")]}, objetos={
        "labels": [{"properties": {"color": cor(NAVY), "fontSize": lit("22D")}}],
        "categoryLabels": [{"properties": {"show": lit("false")}}]}, titulo=rotulo)

def moldura(pagina, titulo, sub):
    """barra lateral azul-marinho + cabeçalho + filtros, igual em todas as páginas"""
    ps = ["Resumo da Campanha", "Sondas", "Recuperação e QA/QC"]
    v = [forma(f"{pagina}_lado", 0, 0, 200, 720, NAVY),
         texto(f"{pagina}_marca", 14, 22, 176, 60, [("Painel de Sondagem", 14, "#FFFFFF", True), ("Exploração de grafita · 2024–2026", 9, "#AFC3DE", False)])]
    for i, p in enumerate(ps):
        ativo = p == titulo
        v.append(forma(f"{pagina}_bt{i}", 16, 130 + i * 48, 168, 36, AZUL if ativo else "#16305A", z=10 + i))
        v.append(texto(f"{pagina}_btt{i}", 22, 134 + i * 48, 156, 30, [(p, 10, "#FFFFFF", ativo)], z=3000 + i))
    v.append(texto(f"{pagina}_rodape", 14, 640, 176, 60, [("Dados simulados · Leticia Cerqueira", 8, "#AFC3DE", False)]))
    v.append(texto(f"{pagina}_tit", 222, 12, 420, 56, [(titulo.upper(), 18, NAVY, True), (sub, 9, "#5B6675", False)]))
    v.append(visual(f"{pagina}_fs", "slicer", 900, 10, 170, 58, {"Values": [("dim_sonda", "sonda", "c")]},
                    objetos={"data": [{"properties": {"mode": lit("'Dropdown'")}}]}, titulo="Sonda"))
    v.append(visual(f"{pagina}_fp", "slicer", 1080, 10, 186, 58, {"Values": [("dCalendario", "Data", "c")]},
                    objetos={"data": [{"properties": {"mode": lit("'Between'")}}]}, titulo="Período"))
    return v

def paginas():
    L = 214  # início da área útil
    p1 = moldura("p1", "Resumo da Campanha", "Avanço contra a meta, produtividade e recuperação")
    kp = [("Metros Perfurados", "fato_turnos", "Metros Perfurados"), ("% da Meta", "fato_turnos", "% da Meta"),
          ("Produtividade (m/h)", "fato_turnos", "Produtividade (m/h)"), ("Disponibilidade", "fato_turnos", "Disponibilidade %"),
          ("Recuperação no minério", "fato_manobras", "Recuperação Zona Mineralizada %")]
    w = (1266 - L - 4 * 10) / 5
    p1 += [card(f"p1_k{i}", round(L + i * (w + 10)), 80, round(w), r, t, m) for i, (r, t, m) in enumerate(kp)]
    p1.append(visual("p1_avanco", "lineChart", L, 184, 640, 260,
                     {"Category": [("dCalendario", "Mes", "c")], "Y": [("fato_turnos", "Metros Acumulados", "m"), ("fato_turnos", "Meta Acumulada", "m")]},
                     objetos={"dataPoint": [{"properties": {"fill": cor(AZUL)}, "selector": {"metadata": "fato_turnos.Metros Acumulados"}},
                                            {"properties": {"fill": cor(CINZA)}, "selector": {"metadata": "fato_turnos.Meta Acumulada"}}],
                              "lineStyles": [{"properties": {"lineStyle": lit("'dashed'")}, "selector": {"metadata": "fato_turnos.Meta Acumulada"}}]},
                     titulo="Avanço acumulado x meta (m)"))
    p1.append(visual("p1_paradas", "barChart", L + 650, 184, 1266 - L - 650, 260,
                     {"Category": [("fato_turnos", "motivo_parada", "c")], "Y": [("fato_turnos", "Horas Paradas", "m")]},
                     objetos={"dataPoint": [{"properties": {"fill": cor(NAVY)}}], "labels": [{"properties": {"show": lit("true")}}]},
                     titulo="Horas paradas por motivo"))
    p1.append(visual("p1_mensal", "clusteredColumnChart", L, 454, 1266 - L, 256,
                     {"Category": [("dCalendario", "Mes", "c")], "Y": [("fato_turnos", "Metros Perfurados", "m"), ("fato_turnos", "Meta (m)", "m")]},
                     objetos={"dataPoint": [{"properties": {"fill": cor(AZUL)}, "selector": {"metadata": "fato_turnos.Metros Perfurados"}},
                                            {"properties": {"fill": cor(CINZA)}, "selector": {"metadata": "fato_turnos.Meta (m)"}}]},
                     titulo="Metros perfurados x meta por mês"))

    p2 = moldura("p2", "Sondas", "Produtividade, disponibilidade e paradas por sonda")
    kp2 = [("Produtividade (m/h)", "fato_turnos", "Produtividade (m/h)"), ("Metros por turno", "fato_turnos", "Metros por Turno"),
           ("Horas paradas", "fato_turnos", "Horas Paradas"), ("Principal parada", "fato_turnos", "Principal Parada")]
    w = (1266 - L - 3 * 10) / 4
    p2 += [card(f"p2_k{i}", round(L + i * (w + 10)), 80, round(w), r, t, m) for i, (r, t, m) in enumerate(kp2)]
    p2.append(visual("p2_prod", "lineChart", L, 184, 1266 - L, 270,
                     {"Category": [("dCalendario", "Mes", "c")], "Series": [("dim_sonda", "sonda", "c")], "Y": [("fato_turnos", "Produtividade (m/h)", "m")]},
                     titulo="Produtividade mensal por sonda (m por hora operando)"))
    p2.append(visual("p2_tab", "tableEx", L, 464, 620, 246,
                     {"Values": [("dim_sonda", "sonda", "c"), ("fato_turnos", "Metros Perfurados", "m"), ("fato_turnos", "Produtividade (m/h)", "m"),
                                 ("fato_turnos", "Disponibilidade %", "m"), ("fato_turnos", "Horas Paradas", "m"), ("fato_turnos", "Metros por Turno", "m")]},
                     titulo="Desempenho por sonda"))
    p2.append(visual("p2_par", "clusteredColumnChart", L + 630, 464, 1266 - L - 630, 246,
                     {"Category": [("dim_sonda", "sonda", "c")], "Y": [("fato_turnos", "Disponibilidade %", "m")]},
                     objetos={"dataPoint": [{"properties": {"fill": cor(NAVY)}}], "labels": [{"properties": {"show": lit("true")}}]},
                     titulo="Disponibilidade por sonda"))

    p3 = moldura("p3", "Recuperação e QA/QC", "Recuperação de testemunho na zona mineralizada (Cg ≥ 3%) e qualidade dos dados")
    kp3 = [("Recuperação no minério", "fato_manobras", "Recuperação Zona Mineralizada %"), ("Furos abaixo de 90%", "fato_manobras", "Furos Abaixo da Meta"),
           ("Lotes para reanálise", "dim_lote_qaqc", "Lotes Reprovados"), ("Furos com intercepto provisório", "dim_lote_qaqc", "Furos com Intercepto Provisório")]
    p3 += [card(f"p3_k{i}", round(L + i * (w + 10)), 80, round(w), r, t, m) for i, (r, t, m) in enumerate(kp3)]
    p3.append(visual("p3_rec", "clusteredColumnChart", L, 184, 420, 260,
                     {"Category": [("dim_sonda", "sonda", "c")], "Y": [("fato_manobras", "Recuperação Zona Mineralizada %", "m")]},
                     objetos={"dataPoint": [{"properties": {"fill": cor(AZUL)}}], "labels": [{"properties": {"show": lit("true")}}],
                              "valueAxis": [{"properties": {"start": lit("0D"), "end": lit("1D")}}]},
                     titulo="Recuperação na zona mineralizada por sonda (meta 90%)"))
    p3.append(visual("p3_lit", "barChart", L + 430, 184, 1266 - L - 430, 260,
                     {"Category": [("fato_manobras", "litologia", "c")], "Y": [("fato_manobras", "Recuperação %", "m")]},
                     objetos={"dataPoint": [{"properties": {"fill": cor(NAVY)}}], "labels": [{"properties": {"show": lit("true")}}]},
                     titulo="Recuperação por litologia"))
    p3.append(visual("p3_tab", "tableEx", L, 454, 640, 256,
                     {"Values": [("fato_manobras", "furo", "c"), ("fato_manobras", "sonda", "c"), ("fato_manobras", "Metros na Zona Mineralizada", "m"),
                                 ("fato_manobras", "Recuperação Zona Mineralizada %", "m")]},
                     titulo="Recuperação por furo na zona mineralizada"))
    p3.append(visual("p3_mapa", "scatterChart", L + 650, 454, 1266 - L - 650, 256,
                     {"Category": [("dim_furo", "furo", "c")], "Series": [("dim_furo", "status_qaqc", "c")],
                      "X": [("dim_furo", "este", "a")], "Y": [("dim_furo", "norte", "a")], "Size": [("dim_furo", "pct_metro", "a")]},
                     titulo="Mapa dos furos · melhor intercepto (tamanho = % Cg x metro)"))
    return [("ReportSection" + str(i + 1), n, v) for i, (n, v) in enumerate([("Resumo da Campanha", p1), ("Sondas", p2), ("Recuperação e QA/QC", p3)])]

def gerar_relatorio():
    rp = RAIZ / f"{NOME}.Report"; rp.mkdir(parents=True)
    (rp / "definition.pbir").write_text(json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOME}.SemanticModel"}}}, indent=2), encoding="utf-8")
    secoes = []
    for i, (sid, nome, vis) in enumerate(paginas()):
        cfg = {"objects": {"background": [{"properties": {"color": cor(FUNDO), "transparency": lit("0D")}}],
                           "outspace": [{"properties": {"color": cor(FUNDO)}}]}}
        secoes.append({"name": sid, "displayName": nome, "displayOption": 1, "width": 1280, "height": 720, "ordinal": i,
                       "config": json.dumps(cfg), "filters": "[]", "visualContainers": vis})
    # tema: o Power BI exige um tema base (e aceita um personalizado por cima) guardado em StaticResources
    tema = {"name": "Sondagem", "dataColors": [AZUL, "#EB6834", "#1BAF7A", NAVY, "#8A94A6", "#E0A548", "#6F4BD8", "#C93A3A"],
            "background": "#FFFFFF", "foreground": NAVY, "tableAccent": AZUL, "good": "#1D7F47", "bad": "#C93A3A", "neutral": "#8A94A6",
            "textClasses": {"callout": {"fontSize": 22, "fontFace": "Segoe UI Semibold", "color": NAVY},
                            "title": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": NAVY},
                            "header": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": NAVY},
                            "label": {"fontSize": 9, "fontFace": "Segoe UI", "color": "#5B6675"}}}
    base = rp / "StaticResources" / "SharedResources" / "BaseThemes"; base.mkdir(parents=True)
    (base / "CY24SU10.json").write_text(json.dumps({**tema, "name": "CY24SU10"}, indent=2), encoding="utf-8")
    reg = rp / "StaticResources" / "RegisteredResources"; reg.mkdir(parents=True)
    (reg / "Sondagem.json").write_text(json.dumps(tema, indent=2), encoding="utf-8")
    rep = {"config": json.dumps({"version": "5.61",
                                 "themeCollection": {"baseTheme": {"name": "CY24SU10", "version": "5.61", "type": 2},
                                                     "customTheme": {"name": "Sondagem.json", "version": "5.61", "type": 1}},
                                 "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True,
                                 "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": 1}}),
           "layoutOptimization": 0,
           "resourcePackages": [
               {"resourcePackage": {"name": "SharedResources", "type": 2, "disabled": False,
                                    "items": [{"type": 202, "path": "BaseThemes/CY24SU10.json", "name": "CY24SU10"}]}},
               {"resourcePackage": {"name": "RegisteredResources", "type": 1, "disabled": False,
                                    "items": [{"type": 201, "path": "Sondagem.json", "name": "Sondagem.json"}]}}],
           "sections": secoes, "filters": "[]"}
    (rp / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    if RAIZ.exists(): shutil.rmtree(RAIZ)
    RAIZ.mkdir()
    (RAIZ / f"{NOME}.pbip").write_text(json.dumps({"version": "1.0", "artifacts": [{"report": {"path": f"{NOME}.Report"}}],
                                                  "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")
    (RAIZ / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n", encoding="utf-8")
    gerar_modelo(); gerar_relatorio()
    for f in sorted(RAIZ.rglob("*")):
        if f.is_file(): print(f.relative_to(AQUI), f.stat().st_size)
