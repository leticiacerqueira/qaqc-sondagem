# QA/QC e validação de banco de dados de sondagem (grafita)

**Pergunta:** os teores de grafita deste banco de sondagem são confiáveis para entrar numa estimativa de recurso? Se não forem, quais lotes precisam voltar ao laboratório e quais resultados ficam em espera?

Este projeto reproduz a rotina de um analista de dados geológicos num projeto de grafita: receber as planilhas de campo e os laudos do laboratório, **validar o banco** (furos, intervalos, códigos, unidades), rodar o **QA/QC** das análises de carbono grafítico (padrões certificados, brancos e duplicatas) e entregar uma **lista de ação**: o que foi corrigido, o que precisa de revisão e quais lotes devem ser reanalisados.

> Os dados são **simulados** (projeto de grafita fictício com 40 furos e 7.630 m de sondagem), porque bancos reais de empresas são confidenciais. A simulação segue o formato usual de exportação (collar, survey, litologia, amostragem, laudo com carbono grafítico **Cg** e carbono total **CT**) e inclui de propósito os problemas que aparecem na prática.

Portfólio: https://leticiacerqueira.github.io

## Ferramentas
Python (pandas, NumPy, Matplotlib) · SQL (SQLite: CTEs, window functions, gaps and islands)

## Etapas
| Script | O que faz |
|---|---|
| `src/01_gerar_dados.py` | Gera o banco simulado: 40 furos, camada de xisto grafitoso, 7.630 amostras de rotina e 1.325 amostras de controle (15% do fluxo) em 43 lotes de laboratório. |
| `src/02_validar_banco.py` | Valida e trata o banco. Cada problema vira uma linha em `saida/log_validacao.csv` com a regra que falhou e a ação: **CORRIGIDO** (correção objetiva e rastreável) ou **REVISAR** (depende de quem conhece o furo ou de confirmação do laboratório). |
| `src/03_qaqc.py` | Cartas de controle dos padrões, gráfico de brancos, precisão das duplicatas (HARD) e decisão por lote: **APROVADO** ou **REANALISAR**. |
| `src/04_consultas_sql.py` + `sql/consultas.sql` | Carrega tudo num SQLite e calcula interceptos significativos, ranking de furos, teor por litologia, impacto do QA/QC e pendências por furo. |

## 1. Validação do banco
**25 ocorrências: 12 corrigidas e 13 para revisar** ([log completo](saida/log_validacao.csv)).

| Tabela | Exemplo encontrado | Ação |
|---|---|---|
| Collar | FD-017 com este e norte trocados (detectado pela faixa de coordenadas UTM) | Corrigido |
| Collar | FD-033 com mergulho +60 no collar e −60 no survey | Corrigido |
| Collar | FD-029 sem cota | Revisar |
| Survey | FD-008: azimute muda 39° entre 60 m e 90 m e volta depois (leitura ruim) | Revisar |
| Litologia | `Xisto`, `xisto `, `XISTO GRAF.`: códigos fora do padrão | Corrigido |
| Litologia | sobreposição em FD-014, lacuna de 1,5 m em FD-025, intervalo além do fundo do furo em FD-038 | Revisar / corrigido |
| Amostragem | amostras lançadas no furo `FD-40`, que não existe (era FD-040) | Corrigido |
| Laudo | teor impossível de 219.592 (veio em ppm: 21,96% Cg), valor −0,02, códigos `-`, `IS`, `NR`, amostra repetida, amostra que não voltou | Corrigido / revisar |
| Laudo | **3 amostras com Cg maior que o carbono total**, o que é impossível (o grafítico é parte do total): provável troca de colunas no laboratório | Revisar |

A lacuna de FD-025 não é detalhe: ela cai **dentro de um intercepto de 10 m a 11,5% Cg**, e a amostra fica sem litologia nas estatísticas até o geólogo descrever o trecho.

## 2. QA/QC das análises
Critérios usados (referências comuns na indústria, ajustáveis no início de `03_qaqc.py`):
- **Padrão certificado:** falha fora de ±3 DP, ou 2 seguidos fora de ±2 DP do mesmo lado, ou média do lote além de ±1,5 DP (viés).
- **Branco:** falha acima de 10 × o limite de detecção (0,20% Cg).
- **Duplicatas:** 90% dos pares com HARD ≤ 10% (polpa) e ≤ 20% (campo). HARD = |A − B| / (A + B).

![Cartas de controle dos padrões](saida/figuras/cartas_controle_padroes.png)

- **Deriva do laboratório nos lotes L021 a L024:** os três padrões sobem juntos (média do lote de +1,6 a +2,0 DP). Poucos pontos passam de 3 DP, mas a sequência mostra que o laboratório passou a ler alto. Os 4 lotes vão para reanálise.
- **L004 e L031:** falhas pontuais (PAD-ALTO a −3,2 DP e PAD-BAIXO a +3,8 DP). Lotes reprovados.
- **L010:** amostra etiquetada como PAD-MEDIO com 14,59% Cg, que é o valor do PAD-ALTO. É **troca de padrão no envio**, não erro do laboratório: corrige-se o cadastro e o lote não é reprovado. Sem essa checagem, um lote bom seria reanalisado à toa.

![Brancos](saida/figuras/brancos.png)

- 2 brancos contaminados (0,35% e 0,23% Cg), **sempre logo depois de amostras de grafita maciça** (32,5% e 19,5% Cg). A grafita é macia e gruda no pulverizador, então o material arrasta para a amostra seguinte. L016 e L025 voltam ao laboratório, e a recomendação é limpar o pulverizador com quartzo depois de amostras de alto teor.

![Duplicatas](saida/figuras/duplicatas.png)

| Tipo | Pares válidos | Dentro do limite | Resultado |
|---|---:|---:|---|
| Duplicata de polpa | 116 | 100% | Aprovado |
| Duplicata de campo | 114 | 98,2% | Aprovado |

A precisão está boa nas duas etapas: o laboratório repete o resultado (polpa) e a metade do testemunho representa bem o intervalo (campo). Os poucos pares mais distantes estão perto do limite de detecção, onde a diferença relativa naturalmente cresce.

## 3. Resultado para o projeto (SQL)
**8 de 43 lotes precisam de reanálise** (L004, L016, L021 a L025, L031). Eles contêm 18,9% das amostras e **20,5% das amostras mineralizadas** (≥ 3% Cg).

Dos **44 interceptos significativos** (≥ 3% Cg e ≥ 2 m, calculados em SQL com a técnica *gaps and islands*), **10 ficam provisórios** até a reanálise ou a confirmação do Cg > CT, entre eles os **2 melhores furos do projeto**.

![Mapa de interceptos](saida/figuras/mapa_intercepts.png)

| Posição | Furo | Intercepto | Status |
|---:|---|---|---|
| 1 | FD-021 | 14 m @ 11,4% Cg | Provisório |
| 2 | FD-022 | 10 m @ 13,7% Cg | Provisório |
| 3 | FD-007 | 12 m @ 11,3% Cg | Validado |
| 4 | FD-012 | 13 m @ 10,2% Cg | Validado |
| 5 | FD-010 | 15 m @ 8,4% Cg | Validado |

Consultas em [`sql/consultas.sql`](sql/consultas.sql) e resultados em [`saida/sql/`](saida/sql/). A lista de pendências por furo ([`05_pendencias_por_furo.csv`](saida/sql/05_pendencias_por_furo.csv)) é o que vai para a equipe de geologia.

## Conclusão
O banco **ainda não está pronto** para estimar recurso: 8 lotes precisam voltar ao laboratório, 3 resultados de Cg precisam ser confirmados e 10 itens precisam de revisão do geólogo. A parte boa: a precisão das duplicatas está aprovada, e quase todos os problemas do banco foram corrigidos de forma rastreável, com o log mostrando o que mudou e por quê.

## Como rodar
```bash
pip install pandas numpy matplotlib
python src/01_gerar_dados.py
python src/02_validar_banco.py
python src/03_qaqc.py
python src/04_consultas_sql.py
```

## Autora
Leticia Santos Cerqueira · Geóloga e Analista de Dados · [LinkedIn](https://www.linkedin.com/in/leticiasantoscerqueira/)
