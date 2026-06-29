-- CAP cards basadas en mock_real.cd_cap_portafolio_cuentas_activas

-- CAP | Total Cuentas Acumuladas
WITH actual AS (
  SELECT COUNT(*) AS total_actual
  FROM mock_real.cd_cap_portafolio_cuentas_activas
),
anterior AS (
  SELECT COUNT(*) AS total_anterior
  FROM mock_real.cd_cap_portafolio_cuentas_activas
  WHERE fec_apertura <= CURRENT_DATE - INTERVAL '1 year'
)
SELECT
  'Total cuentas' AS eje,
  actual.total_actual::numeric AS total_actual,
  anterior.total_anterior::numeric AS total_anterior,
  ROUND(
    (
      (actual.total_actual - anterior.total_anterior)::numeric
      / NULLIF(anterior.total_anterior, 0)
    ) * 100,
    2
  ) AS variacion_pct
FROM actual, anterior;

-- CAP | Saldo Total Estimado
WITH actual AS (
  SELECT COALESCE(SUM(sld_actual), 0) AS total_actual
  FROM mock_real.cd_cap_portafolio_cuentas_activas
),
anterior AS (
  SELECT COALESCE(SUM(sld_actual), 0) AS total_anterior
  FROM mock_real.cd_cap_portafolio_cuentas_activas
  WHERE fec_apertura <= CURRENT_DATE - INTERVAL '1 year'
)
SELECT
  'Saldo total' AS eje,
  actual.total_actual::numeric AS total_actual,
  anterior.total_anterior::numeric AS total_anterior,
  ROUND(
    (
      (actual.total_actual - anterior.total_anterior)::numeric
      / NULLIF(anterior.total_anterior, 0)
    ) * 100,
    2
  ) AS variacion_pct
FROM actual, anterior;

-- CAP | Saldo Promedio
WITH actual AS (
  SELECT COALESCE(AVG(sld_actual), 0) AS total_actual
  FROM mock_real.cd_cap_portafolio_cuentas_activas
),
anterior AS (
  SELECT COALESCE(AVG(sld_actual), 0) AS total_anterior
  FROM mock_real.cd_cap_portafolio_cuentas_activas
  WHERE fec_apertura <= CURRENT_DATE - INTERVAL '1 year'
)
SELECT
  'Saldo promedio' AS eje,
  ROUND(actual.total_actual::numeric, 2) AS total_actual,
  ROUND(anterior.total_anterior::numeric, 2) AS total_anterior,
  ROUND(
    (
      (actual.total_actual - anterior.total_anterior)::numeric
      / NULLIF(anterior.total_anterior, 0)
    ) * 100,
    2
  ) AS variacion_pct
FROM actual, anterior;
