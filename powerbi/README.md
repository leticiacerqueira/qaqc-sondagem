# Painel de sondagem em Power BI

Este é o mesmo painel da campanha (avanço, sondas, recuperação e QA/QC), montado no Power BI Desktop com um modelo estrela e medidas DAX. Os dados saem de `python src/07_exportar_powerbi.py` e ficam em `saida/powerbi/`.

## Atalho: abrir o projeto pronto
A pasta [`Painel Sondagem/`](Painel%20Sondagem/) é um projeto do Power BI (formato PBIP), gerado por [`gerar_pbip.py`](gerar_pbip.py). Ele já vem com:
- as tabelas, que leem os CSVs direto deste repositório no GitHub;
- as relações e as medidas DAX;
- as 3 páginas.

Como abrir:
1. Baixe a pasta inteira.
2. No Power BI Desktop, vá em **Arquivo > Abrir** e escolha `Painel Sondagem.pbip`.
3. Clique em **Atualizar**. Se ele pedir credencial para os CSVs, escolha **Anônimo**.
4. Para gerar um `.pbix` único, use **Arquivo > Salvar como**.

Se o Power BI não abrir o PBIP, ative em **Opções > Recursos de visualização** os itens **Salvar projetos do Power BI (.pbip)** e **Formato de armazenamento TMDL**. Também dá para montar tudo à mão seguindo os passos abaixo.

## 1. Importar os dados
1. Abra o Power BI Desktop e vá em **Obter dados > Texto/CSV**. Importe os 6 arquivos de `saida/powerbi/`: `fato_turnos`, `fato_manobras`, `dim_furo`, `dim_sonda`, `dim_meta_mensal` e `dim_lote_qaqc`.
2. Clique em **Transformar dados**. Os CSVs usam **ponto como separador decimal**. Se o seu Power BI estiver em português, em cada coluna numérica use **Alterar tipo > Usando a localidade > Decimal / Inglês (Estados Unidos)**. Sem isso, 2.35 vira 235.
   - Colunas numéricas: `de`, `ate`, `recuperado_m`, `metros_perfurados`, `horas_operacao`, `horas_parada`, `este`, `norte`, `cota`, `prof_final`, `teor_cg_pct`, `pct_metro`, `espessura_m` e `z_medio_padroes`.
   - Colunas de data (mesma localidade): `data` e `data_inicio`.
3. Clique em **Fechar e aplicar**.

## 2. Modelo
1. Crie a tabela calendário: **Modelagem > Nova tabela** e cole o bloco `dCalendario` de [`medidas.dax`](medidas.dax). Em seguida, marque-a como tabela de datas.
2. Crie estas relações na exibição de **Modelo**. Todas são de um para muitos, com filtro em direção única:

| De (1) | Para (*) |
|---|---|
| `dCalendario[Date]` | `fato_turnos[data]`, `fato_manobras[data]`, `dim_meta_mensal[data]` |
| `dim_sonda[sonda]` | `fato_turnos[sonda]`, `fato_manobras[sonda]` |
| `dim_furo[furo]` | `fato_turnos[furo]`, `fato_manobras[furo]` |

`dim_lote_qaqc` fica sem relação: ela só alimenta os cartões de QA/QC.

3. Crie uma tabela vazia `_Medidas` (**Página Inicial > Inserir dados > Carregar**) e cole as medidas de [`medidas.dax`](medidas.dax), uma por vez, em **Nova medida**. Formatos:
   - `%`: **Recuperação %**, **Disponibilidade %**, **% da Meta** e **% das Horas Paradas**.
   - Número com 2 casas: **Produtividade (m/h)**.

## 3. Páginas
Use uma barra lateral escura com 3 botões de navegação (**Inserir > Botões > Navegador > Navegador de páginas**). Coloque segmentações de **Sonda** (`dim_sonda[sonda]`) e **Período** (`dCalendario[Date]`, estilo Entre) no topo de cada página, sincronizadas entre as páginas (**Exibir > Sincronizar segmentações**).

**Página 1 · Resumo da campanha**
- 5 cartões: Metros Perfurados, % da Meta, Produtividade (m/h), Disponibilidade % e Recuperação Zona Mineralizada %.
- Gráfico de linhas: eixo `dCalendario[Mes]`, valores Metros Acumulados e Meta Acumulada (linha da meta tracejada e cinza).
- Gráfico de colunas agrupadas: Metros Perfurados x Meta (m) por mês.

**Página 2 · Sondas**
- Gráfico de linhas: Produtividade (m/h) por mês, com legenda `dim_sonda[sonda]`. Mostra a queda da SD-03 a partir de abr/25.
- Matriz por sonda com Metros Perfurados, Produtividade (m/h), Disponibilidade %, Horas Paradas e Metros por Turno.
- Barras horizontais: Horas Paradas por `fato_turnos[motivo_parada]` (filtro: diferente de "Sem parada"), ordenadas de forma decrescente. Use % das Horas Paradas na dica de ferramenta.
- Cartão: Principal Parada.

**Página 3 · Recuperação e QA/QC**
- Colunas: Recuperação Zona Mineralizada % por sonda, com linha constante de 90% (**Análise > Linha constante**).
- Barras: Recuperação % por `fato_manobras[litologia]`.
- Tabela: furo, sonda, Metros na Zona Mineralizada e Recuperação Zona Mineralizada %, com filtro do visual Recuperação Zona Mineralizada % < 0,9. Use a cor de fundo pela medida **Cor Recuperação**.
- Cartões: Furos Abaixo da Meta, Lotes Reprovados (de Lotes) e Furos com Melhor Intercepto Provisório.
- Opcional: um gráfico de dispersão com `dim_furo[este]` x `dim_furo[norte]`, tamanho `pct_metro` e legenda `status_qaqc`, que funciona como mapa dos furos.

## 4. Conferência
Sem filtros, os números têm que bater com o painel HTML e com o README do projeto:

| Medida | Valor |
|---|---|
| Metros Perfurados | 12.920 |
| Produtividade (m/h) | 1,98 |
| Disponibilidade % | 88,7% |
| Recuperação Zona Mineralizada % | 91,5% |
| Furos Abaixo da Meta | 20 (todos da SD-01) |
| Lotes Reprovados | 8 de 72 |
| Principal Parada | Manutenção mecânica (41%) |
| Produtividade da SD-03 | 1,55 m/h |

## 5. Levar para o portfólio
- Para publicar na web pelo **Publicar na Web** do Power BI, é preciso uma conta de trabalho ou de estudante (e-mail de Gmail não entra no serviço do Power BI). Com essa conta, o link de incorporação vai num `<iframe>`, como o painel HTML.
- Sem essa conta, exporte cada página como imagem (**Arquivo > Exportar > PDF** e depois recorte cada página, ou capture a tela) e salve o `.pbix` no repositório. O portfólio mostra as páginas numa galeria com o link do arquivo.
