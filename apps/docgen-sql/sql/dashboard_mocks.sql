CREATE SCHEMA IF NOT EXISTS mock;

CREATE OR REPLACE TABLE mock.clientes AS
SELECT *
FROM (
    VALUES
        (1, 'Norte', 'Premium', DATE '2024-01-15', TRUE),
        (2, 'Norte', 'Masivo', DATE '2024-02-20', TRUE),
        (3, 'Centro', 'PyME', DATE '2024-03-02', TRUE),
        (4, 'Centro', 'Premium', DATE '2024-03-18', TRUE),
        (5, 'Sur', 'Masivo', DATE '2024-04-10', FALSE),
        (6, 'Sur', 'PyME', DATE '2024-05-22', TRUE),
        (7, 'Occidente', 'Premium', DATE '2024-06-30', TRUE),
        (8, 'Occidente', 'Masivo', DATE '2024-07-19', TRUE)
) AS t(cliente_id, region, segmento, fecha_alta, activo);

CREATE OR REPLACE TABLE mock.cuentas AS
SELECT *
FROM (
    VALUES
        (1001, 1, 'Ahorro', 'Activa', DATE '2026-05-01', 152340.25),
        (1002, 1, 'Nomina', 'Activa', DATE '2026-05-01', 28450.10),
        (1003, 2, 'Ahorro', 'Activa', DATE '2026-05-01', 9840.45),
        (1004, 3, 'Corriente', 'Bloqueada', DATE '2026-05-01', 214500.00),
        (1005, 4, 'Inversion', 'Activa', DATE '2026-05-01', 530200.40),
        (1006, 6, 'Ahorro', 'Activa', DATE '2026-05-01', 18765.00),
        (1007, 7, 'Nomina', 'Activa', DATE '2026-05-01', 44210.25),
        (1008, 8, 'Corriente', 'Cancelada', DATE '2026-05-01', 0.00)
) AS t(cuenta_id, cliente_id, producto, estatus, fecha_corte, saldo_actual);

CREATE OR REPLACE TABLE mock.saldos_diarios AS
SELECT *
FROM (
    VALUES
        (DATE '2026-05-08', 1001, 150100.25),
        (DATE '2026-05-09', 1001, 151450.00),
        (DATE '2026-05-10', 1001, 152340.25),
        (DATE '2026-05-08', 1005, 521340.10),
        (DATE '2026-05-09', 1005, 526875.55),
        (DATE '2026-05-10', 1005, 530200.40),
        (DATE '2026-05-08', 1007, 43000.00),
        (DATE '2026-05-09', 1007, 43875.25),
        (DATE '2026-05-10', 1007, 44210.25)
) AS t(fecha, cuenta_id, saldo_fin_dia);

CREATE OR REPLACE VIEW mock.v_dashboard_resumen AS
SELECT
    c.region,
    c.segmento,
    count(DISTINCT c.cliente_id) AS clientes,
    count(DISTINCT a.cuenta_id) AS cuentas,
    sum(CASE WHEN a.estatus = 'Activa' THEN 1 ELSE 0 END) AS cuentas_activas,
    round(sum(a.saldo_actual), 2) AS saldo_total
FROM mock.clientes c
LEFT JOIN mock.cuentas a USING (cliente_id)
GROUP BY 1, 2
ORDER BY saldo_total DESC;

CREATE OR REPLACE VIEW mock.v_top_cuentas AS
SELECT
    a.cuenta_id,
    c.region,
    c.segmento,
    a.producto,
    a.estatus,
    a.saldo_actual
FROM mock.cuentas a
JOIN mock.clientes c USING (cliente_id)
ORDER BY a.saldo_actual DESC
LIMIT 10;
