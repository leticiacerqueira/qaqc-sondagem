-- Consultas sobre o banco tratado (SQLite).
-- Tabelas: collar, amostras, lotes_qaqc. Cada bloco "-- name:" vira um CSV em saida/sql/.

-- name: 01_intercepts_significativos
-- Intervalos contínuos com Cg >= 3% e pelo menos 2 m (técnica "gaps and islands").
-- Um intercepto com amostra em lote reprovado no QA/QC, ou com Cg > carbono total, fica PROVISÓRIO.
WITH base AS (
    SELECT a.furo, a.de, a.ate, a.cg, a.lote, a.status,
           CASE WHEN a.cg >= 3 THEN 1 ELSE 0 END AS mineralizada
    FROM amostras a
    WHERE a.cg IS NOT NULL
),
ilhas AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY furo ORDER BY de)
         - ROW_NUMBER() OVER (PARTITION BY furo, mineralizada ORDER BY de) AS grupo
    FROM base
),
intercepts AS (
    SELECT i.furo,
           MIN(i.de) AS de, MAX(i.ate) AS ate,
           ROUND(MAX(i.ate) - MIN(i.de), 1) AS espessura_m,
           ROUND(SUM(i.cg * (i.ate - i.de)) / SUM(i.ate - i.de), 2) AS teor_cg_pct,
           ROUND(SUM(i.cg * (i.ate - i.de)), 1) AS pct_metro,
           SUM(CASE WHEN l.decisao = 'REANALISAR' OR i.status = 'CG_MAIOR_QUE_CT' THEN 1 ELSE 0 END) AS amostras_pendentes
    FROM ilhas i
    LEFT JOIN lotes_qaqc l ON l.lote = i.lote
    WHERE i.mineralizada = 1
    GROUP BY i.furo, i.grupo
    HAVING MAX(i.ate) - MIN(i.de) >= 2
)
SELECT furo, de, ate, espessura_m, teor_cg_pct, pct_metro,
       CASE WHEN amostras_pendentes > 0 THEN 'PROVISORIO' ELSE 'VALIDADO' END AS status_qaqc
FROM intercepts
ORDER BY pct_metro DESC;

-- name: 02_melhor_intercepto_por_furo
-- Ranking dos furos pelo melhor intercepto (teor x espessura, em %·m), com RANK().
WITH ints AS (SELECT * FROM resultado_01),
melhor AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY furo ORDER BY pct_metro DESC) AS n
    FROM ints
)
SELECT RANK() OVER (ORDER BY m.pct_metro DESC) AS posicao,
       m.furo, c.este, c.norte, m.de, m.espessura_m, m.teor_cg_pct, m.pct_metro, m.status_qaqc
FROM melhor m JOIN collar c ON c.furo = m.furo
WHERE m.n = 1
ORDER BY posicao;

-- name: 03_teor_por_litologia
SELECT COALESCE(litologia, 'SEM DESCRIÇÃO (lacuna)') AS litologia,
       COUNT(*)                                          AS amostras,
       ROUND(SUM(ate - de), 0)                           AS metros,
       ROUND(SUM(cg * (ate - de)) / SUM(ate - de), 2)    AS teor_medio_cg_pct,
       ROUND(100.0 * SUM(CASE WHEN cg >= 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_acima_3
FROM amostras
WHERE cg IS NOT NULL
GROUP BY 1
ORDER BY teor_medio_cg_pct DESC;

-- name: 04_impacto_qaqc
-- Quanto do banco (e do minério) depende dos lotes que precisam ser reanalisados.
SELECT CASE WHEN l.decisao = 'REANALISAR' THEN 'Lote a reanalisar' ELSE 'Lote aprovado' END AS situacao,
       COUNT(*) AS amostras,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_amostras,
       SUM(CASE WHEN a.cg >= 3 THEN 1 ELSE 0 END) AS amostras_mineralizadas,
       ROUND(100.0 * SUM(CASE WHEN a.cg >= 3 THEN 1 ELSE 0 END)
             / SUM(SUM(CASE WHEN a.cg >= 3 THEN 1 ELSE 0 END)) OVER (), 1) AS pct_mineralizadas
FROM amostras a
JOIN lotes_qaqc l ON l.lote = a.lote
GROUP BY 1;

-- name: 05_pendencias_por_furo
-- Lista de trabalho para o geólogo: o que falta resolver em cada furo.
SELECT a.furo,
       COUNT(*) AS amostras,
       SUM(CASE WHEN a.status = 'SEM_RESULTADO' OR a.status IS NULL THEN 1 ELSE 0 END) AS sem_resultado,
       SUM(CASE WHEN a.status = 'CG_MAIOR_QUE_CT' THEN 1 ELSE 0 END) AS cg_maior_que_ct,
       SUM(CASE WHEN l.decisao = 'REANALISAR' THEN 1 ELSE 0 END) AS em_lote_reprovado,
       GROUP_CONCAT(DISTINCT CASE WHEN l.decisao = 'REANALISAR' THEN l.lote END) AS lotes
FROM amostras a
LEFT JOIN lotes_qaqc l ON l.lote = a.lote
GROUP BY a.furo
HAVING sem_resultado > 0 OR cg_maior_que_ct > 0 OR em_lote_reprovado > 0
ORDER BY em_lote_reprovado DESC, cg_maior_que_ct DESC, sem_resultado DESC;
