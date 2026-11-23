-- KPIs de sondagem a partir dos boletins diários (SQLite).
-- Tabelas: manobras, turnos, litologia, zona_mineralizada (intercepts >= 3% Cg), meta. Cada bloco "-- name:" vira um CSV em saida/kpis/.

-- name: k1_avanco_mensal_x_meta
-- Metros perfurados por mês contra a meta, com acumulado (SUM OVER) e aderência.
WITH mensal AS (
    SELECT substr(data, 1, 7) AS mes, SUM(metros_perfurados) AS realizado
    FROM turnos GROUP BY 1
)
SELECT m.mes,
       m.realizado,
       t.meta_m AS meta,
       CASE WHEN t.meta_m >= 0.5 * MAX(t.meta_m) OVER ()          -- meses de plano parcial ficam sem aderência
            THEN ROUND(100.0 * m.realizado / t.meta_m, 1) END AS aderencia_pct,
       SUM(m.realizado) OVER (ORDER BY m.mes) AS realizado_acum,
       SUM(t.meta_m)    OVER (ORDER BY m.mes) AS meta_acum
FROM mensal m JOIN meta t ON t.mes = m.mes
ORDER BY m.mes;

-- name: k2_produtividade_por_sonda
SELECT sonda,
       SUM(metros_perfurados)                                              AS metros,
       COUNT(*)                                                            AS turnos,
       ROUND(SUM(metros_perfurados) / COUNT(*), 1)                         AS metros_por_turno,
       ROUND(SUM(metros_perfurados) / SUM(horas_operacao), 2)              AS metros_por_hora,
       ROUND(100.0 * SUM(horas_operacao) / SUM(horas_operacao + horas_parada), 1) AS disponibilidade_pct,
       ROUND(SUM(CASE WHEN motivo_parada = 'Manutenção mecânica' THEN horas_parada ELSE 0 END), 1) AS horas_manutencao
FROM turnos
WHERE horas_operacao + horas_parada <= 12      -- turnos com horas inconsistentes ficam fora até a correção
GROUP BY sonda
ORDER BY metros_por_hora DESC;

-- name: k3_produtividade_mensal_por_sonda
-- Variação mês a mês (LAG) para achar queda de desempenho.
WITH m AS (
    SELECT sonda, substr(data, 1, 7) AS mes,
           ROUND(SUM(metros_perfurados) / SUM(horas_operacao), 2) AS metros_por_hora
    FROM turnos GROUP BY sonda, mes
)
SELECT sonda, mes, metros_por_hora,
       ROUND(100.0 * (metros_por_hora / LAG(metros_por_hora) OVER (PARTITION BY sonda ORDER BY mes) - 1), 1) AS variacao_pct
FROM m ORDER BY sonda, mes;

-- name: k4_recuperacao_por_litologia
-- Recuperação de testemunho = metros recuperados / metros perfurados. Meta: >= 90% na zona mineralizada.
WITH man AS (
    SELECT mb.*, (mb.de + mb.ate) / 2.0 AS meio, mb.ate - mb.de AS perfurado
    FROM manobras mb
    WHERE mb.recuperado_m <= mb.ate - mb.de      -- recuperação acima de 100% é erro de boletim
)
SELECT CASE WHEN z.furo IS NOT NULL THEN 'ZONA MINERALIZADA (Cg >= 3%)'
            ELSE COALESCE(l.litologia, 'SEM DESCRIÇÃO') END AS litologia,
       COUNT(*) AS manobras,
       ROUND(100.0 * SUM(man.recuperado_m) / SUM(man.perfurado), 1) AS recuperacao_pct,
       ROUND(100.0 * SUM(CASE WHEN man.recuperado_m / man.perfurado < 0.9 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_manobras_abaixo_90
FROM man
LEFT JOIN litologia l ON l.furo = man.furo AND man.meio >= l.de AND man.meio < l.ate
LEFT JOIN zona_mineralizada z ON z.furo = man.furo AND man.meio >= z.de AND man.meio < z.ate
GROUP BY 1
ORDER BY recuperacao_pct;

-- name: k5_furos_abaixo_meta_zona_mineralizada
-- Furos em que a recuperação na zona mineralizada ficou abaixo de 90%: o teor desses trechos pode estar enviesado.
WITH man AS (
    SELECT mb.*, (mb.de + mb.ate) / 2.0 AS meio, mb.ate - mb.de AS perfurado
    FROM manobras mb WHERE mb.recuperado_m <= mb.ate - mb.de
)
SELECT man.furo, man.sonda,
       ROUND(SUM(man.perfurado), 1) AS metros_minerio,
       ROUND(100.0 * SUM(man.recuperado_m) / SUM(man.perfurado), 1) AS recuperacao_pct
FROM man
JOIN zona_mineralizada z ON z.furo = man.furo AND man.meio >= z.de AND man.meio < z.ate
GROUP BY man.furo, man.sonda
HAVING SUM(man.recuperado_m) / SUM(man.perfurado) < 0.9
ORDER BY recuperacao_pct;

-- name: k5b_recuperacao_minerio_por_sonda
-- Recuperação na zona mineralizada por sonda x velocidade de perfuração.
WITH man AS (
    SELECT mb.*, (mb.de + mb.ate) / 2.0 AS meio, mb.ate - mb.de AS perfurado
    FROM manobras mb WHERE mb.recuperado_m <= mb.ate - mb.de
),
rec AS (
    SELECT man.sonda,
           ROUND(100.0 * SUM(man.recuperado_m) / SUM(man.perfurado), 1) AS recuperacao_minerio_pct,
           COUNT(DISTINCT man.furo) AS furos
    FROM man JOIN zona_mineralizada z ON z.furo = man.furo AND man.meio >= z.de AND man.meio < z.ate
    GROUP BY man.sonda
),
vel AS (
    SELECT sonda, ROUND(SUM(metros_perfurados) / SUM(horas_operacao), 2) AS metros_por_hora
    FROM turnos GROUP BY sonda
)
SELECT rec.sonda, rec.furos, vel.metros_por_hora, rec.recuperacao_minerio_pct
FROM rec JOIN vel USING (sonda)
ORDER BY rec.recuperacao_minerio_pct;

-- name: k6_pareto_paradas
WITH p AS (
    SELECT motivo_parada, SUM(horas_parada) AS horas
    FROM turnos WHERE motivo_parada IS NOT NULL GROUP BY motivo_parada
)
SELECT motivo_parada, ROUND(horas, 1) AS horas,
       ROUND(100.0 * horas / SUM(horas) OVER (), 1) AS pct,
       ROUND(100.0 * SUM(horas) OVER (ORDER BY horas DESC) / SUM(horas) OVER (), 1) AS acumulado_pct
FROM p ORDER BY horas DESC;
