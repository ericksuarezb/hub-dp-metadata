# Charts

Guia rapida para crear cards personalizados en Redash usando `Chart -> Custom`.

## Requisitos

- Redash `25.8.0`
- Feature flag habilitada:

```env
REDASH_FEATURE_ALLOW_CUSTOM_JS_VISUALIZATIONS=true
```

En este proyecto ya quedo conectada en:

- `.env`
- [docker-compose.yml](docker-compose.yml)

## Importante

En Redash `25.8.0`, esta feature **no** habilita un renderer HTML libre con `container.innerHTML`.

Lo que habilita es el tipo:

- `Chart`
- `Chart Type = Custom`

El runtime disponible en ese modo es:

- `x`
- `ys`
- `element`
- `Plotly`

No usar:

- `queryResult`
- `container`

porque en este modo no existen.

## Patron recomendado para cards KPI

Para que `ys` llegue bien poblado, la query debe devolver:

- una columna eje, por ejemplo `eje`
- una sola fila
- una columna por metrica

Ejemplo:

```sql
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
```

## Como crear el card

1. Abre la query en Redash.
2. Crea una nueva visualizacion.
3. Selecciona `Chart`.
4. En `Chart Type`, selecciona `Custom`.
5. En `X Column`, usa `eje`.
6. Asegurate de que las series disponibles incluyan:
   - `total_actual`
   - `total_anterior`
   - `variacion_pct`
7. Pega el codigo JS de abajo en `Custom code`.
8. Guarda la visualizacion.

## Codigo JS del card

```js
const totalActual = Number(ys.total_actual?.[0] ?? 0);
const totalAnterior = Number(ys.total_anterior?.[0] ?? 0);
const variacion = Number(ys.variacion_pct?.[0] ?? 0);

const arrow = variacion >= 0 ? "▲" : "▼";
const pctColor = variacion >= 0 ? "#6dae45" : "#c0392b";
const bgColor = variacion >= 0 ? "#e6f1d7" : "#f8dddd";

const formatNumber = value => new Intl.NumberFormat("en-US").format(value);

const layout = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "#ffffff",
  height: 150,
  margin: { l: 0, r: 0, t: 0, b: 0 },
  xaxis: { visible: false, fixedrange: true },
  yaxis: { visible: false, fixedrange: true },
  shapes: [
    {
      type: "rect",
      xref: "paper",
      yref: "paper",
      x0: 0,
      x1: 1,
      y0: 0,
      y1: 1,
      line: { color: "#222", width: 2 },
      fillcolor: "#ffffff",
      layer: "below",
    },
    {
      type: "rect",
      xref: "paper",
      yref: "paper",
      x0: 0.84,
      x1: 1,
      y0: 0,
      y1: 1,
      line: { color: "#222", width: 0 },
      fillcolor: bgColor,
      layer: "below",
    },
  ],
  annotations: [
    {
      xref: "paper",
      yref: "paper",
      x: 0.03,
      y: 0.84,
      text: "Total de cuentas acumuladas",
      showarrow: false,
      xanchor: "left",
      yanchor: "top",
      font: { family: "Arial, Helvetica, sans-serif", size: 22, color: "#111" },
    },
    {
      xref: "paper",
      yref: "paper",
      x: 0.42,
      y: 0.48,
      text: `<b>${formatNumber(totalActual)}</b>`,
      showarrow: false,
      xanchor: "center",
      yanchor: "middle",
      font: { family: "Arial, Helvetica, sans-serif", size: 30, color: "#111" },
    },
    {
      xref: "paper",
      yref: "paper",
      x: 0.03,
      y: 0.15,
      text: `<i><b>${formatNumber(totalAnterior)} vs año anterior</b></i>`,
      showarrow: false,
      xanchor: "left",
      yanchor: "bottom",
      font: { family: "Arial, Helvetica, sans-serif", size: 16, color: "#888" },
    },
    {
      xref: "paper",
      yref: "paper",
      x: 0.92,
      y: 0.5,
      text: `<b>${arrow} ${Math.abs(variacion).toFixed(2)}%</b>`,
      showarrow: false,
      xanchor: "center",
      yanchor: "middle",
      font: { family: "Arial, Helvetica, sans-serif", size: 18, color: pctColor },
    },
  ],
};

Plotly.newPlot(element, [], layout, {
  displayModeBar: false,
  responsive: true,
});
```

## Diagnostico rapido

Si el card renderiza pero sale en `0`:

- la visualizacion si esta corriendo
- pero `ys.total_actual`, `ys.total_anterior` o `ys.variacion_pct` vienen vacios

Las causas tipicas son:

- la query no trae columna eje
- la visualizacion no tiene `X Column = eje`
- las metricas no quedaron reconocidas como series

## Consulta de validacion

Antes de pegar el JS, la query debe devolver algo como:

```text
eje           | total_actual | total_anterior | variacion_pct
Total cuentas | 1577911      | 1183210        | 33.36
```

## Recomendacion

Para cards KPI de una sola fila:

- usar una fila unica
- usar una columna eje fija
- usar columnas numericas separadas por metrica

Ese patron es el mas estable para `Chart -> Custom` en Redash `25.8.0`.

## CAP Cards

Estas cards estan pensadas para el dataset replicado en:

- `mock_real.cd_cap_portafolio_cuentas_activas`

Y usan como referencia la query:

- `CAP | Total Cuentas Acumuladas`

### Tipografia recomendada

Para una apariencia mas editorial y menos generica, usar:

```js
const CARD_FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif';
```

Si el equipo quiere un look mas premium y con mas contraste visual:

```js
const CARD_FONT = '"Avenir Next", "Optima", "Segoe UI", "Helvetica Neue", Arial, sans-serif';
```

### Query 1

`CAP | Total Cuentas Acumuladas`

```sql
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
```

### Query 2

`CAP | Saldo Total Estimado`

```sql
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
```

### Query 3

`CAP | Saldo Promedio`

```sql
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
```

### Diseño base

Este layout se usa como base para las tres cards:

```js
const totalActual = Number(ys.total_actual?.[0] ?? 0);
const totalAnterior = Number(ys.total_anterior?.[0] ?? 0);
const variacion = Number(ys.variacion_pct?.[0] ?? 0);

const CARD_FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif';
const arrow = variacion >= 0 ? "▲" : "▼";
const pctColor = variacion >= 0 ? "#73b63f" : "#c0392b";
const bgColor = variacion >= 0 ? "#e7f2d7" : "#f8dddd";

const layout = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "#ffffff",
  height: 148,
  margin: { l: 0, r: 0, t: 0, b: 0 },
  xaxis: { visible: false, fixedrange: true },
  yaxis: { visible: false, fixedrange: true },
  shapes: [
    {
      type: "rect",
      xref: "paper",
      yref: "paper",
      x0: 0,
      x1: 1,
      y0: 0,
      y1: 1,
      line: { color: "#1b1b1b", width: 2 },
      fillcolor: "#ffffff",
      layer: "below",
    },
    {
      type: "rect",
      xref: "paper",
      yref: "paper",
      x0: 0.75,
      x1: 1,
      y0: 0.5,
      y1: 1,
      line: { color: "rgba(0,0,0,0)", width: 0 },
      fillcolor: bgColor,
      layer: "below",
    },
  ],
};
```

### Card 1

`CAP | Total Cuentas Acumuladas`

```js
const totalActual = Number(ys.total_actual?.[0] ?? 0);
const totalAnterior = Number(ys.total_anterior?.[0] ?? 0);
const variacion = Number(ys.variacion_pct?.[0] ?? 0);

const CARD_FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif';
const arrow = variacion >= 0 ? "▲" : "▼";
const pctColor = variacion >= 0 ? "#73b63f" : "#c0392b";
const bgColor = variacion >= 0 ? "#e7f2d7" : "#f8dddd";
const formatInt = value => new Intl.NumberFormat("en-US").format(Math.round(value));

const layout = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "#ffffff",
  height: 148,
  margin: { l: 0, r: 0, t: 0, b: 0 },
  xaxis: { visible: false, fixedrange: true },
  yaxis: { visible: false, fixedrange: true },
  shapes: [
    { type: "rect", xref: "paper", yref: "paper", x0: 0, x1: 1, y0: 0, y1: 1, line: { color: "#1b1b1b", width: 2 }, fillcolor: "#ffffff", layer: "below" },
    { type: "rect", xref: "paper", yref: "paper", x0: 0.75, x1: 1, y0: 0.5, y1: 1, line: { color: "rgba(0,0,0,0)", width: 0 }, fillcolor: bgColor, layer: "below" },
  ],
  annotations: [
    { xref: "paper", yref: "paper", x: 0.05, y: 0.82, text: "Total de cuentas acumuladas", showarrow: false, xanchor: "left", yanchor: "middle", font: { family: CARD_FONT, size: 20, color: "#111111" } },
    { xref: "paper", yref: "paper", x: 0.40, y: 0.38, text: `<b>${formatInt(totalActual)}</b>`, showarrow: false, xanchor: "center", yanchor: "middle", font: { family: CARD_FONT, size: 30, color: "#111111" } },
    { xref: "paper", yref: "paper", x: 0.05, y: 0.10, text: `<i><b>${formatInt(totalAnterior)} vs año anterior</b></i>`, showarrow: false, xanchor: "left", yanchor: "middle", font: { family: CARD_FONT, size: 15, color: "#8a8a8a" } },
    { xref: "paper", yref: "paper", x: 0.875, y: 0.74, text: `<b>${arrow} ${Math.abs(variacion).toFixed(2)}%</b>`, showarrow: false, xanchor: "center", yanchor: "middle", font: { family: CARD_FONT, size: 16, color: pctColor } },
  ],
};

Plotly.newPlot(element, [], layout, { displayModeBar: false, responsive: true });
```

### Card 2

`CAP | Saldo Total Estimado`

```js
const totalActual = Number(ys.total_actual?.[0] ?? 0);
const totalAnterior = Number(ys.total_anterior?.[0] ?? 0);
const variacion = Number(ys.variacion_pct?.[0] ?? 0);

const CARD_FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif';
const arrow = variacion >= 0 ? "▲" : "▼";
const pctColor = variacion >= 0 ? "#73b63f" : "#c0392b";
const bgColor = variacion >= 0 ? "#e7f2d7" : "#f8dddd";
const formatCurrency = value =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 }).format(value);

const layout = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "#ffffff",
  height: 148,
  margin: { l: 0, r: 0, t: 0, b: 0 },
  xaxis: { visible: false, fixedrange: true },
  yaxis: { visible: false, fixedrange: true },
  shapes: [
    { type: "rect", xref: "paper", yref: "paper", x0: 0, x1: 1, y0: 0, y1: 1, line: { color: "#1b1b1b", width: 2 }, fillcolor: "#ffffff", layer: "below" },
    { type: "rect", xref: "paper", yref: "paper", x0: 0.75, x1: 1, y0: 0.5, y1: 1, line: { color: "rgba(0,0,0,0)", width: 0 }, fillcolor: bgColor, layer: "below" },
  ],
  annotations: [
    { xref: "paper", yref: "paper", x: 0.05, y: 0.82, text: "Saldo total estimado", showarrow: false, xanchor: "left", yanchor: "middle", font: { family: CARD_FONT, size: 20, color: "#111111" } },
    { xref: "paper", yref: "paper", x: 0.40, y: 0.38, text: `<b>${formatCurrency(totalActual)}</b>`, showarrow: false, xanchor: "center", yanchor: "middle", font: { family: CARD_FONT, size: 26, color: "#111111" } },
    { xref: "paper", yref: "paper", x: 0.05, y: 0.10, text: `<i><b>${formatCurrency(totalAnterior)} vs año anterior</b></i>`, showarrow: false, xanchor: "left", yanchor: "middle", font: { family: CARD_FONT, size: 15, color: "#8a8a8a" } },
    { xref: "paper", yref: "paper", x: 0.875, y: 0.74, text: `<b>${arrow} ${Math.abs(variacion).toFixed(2)}%</b>`, showarrow: false, xanchor: "center", yanchor: "middle", font: { family: CARD_FONT, size: 16, color: pctColor } },
  ],
};

Plotly.newPlot(element, [], layout, { displayModeBar: false, responsive: true });
```

### Card 3

`CAP | Saldo Promedio`

```js
const totalActual = Number(ys.total_actual?.[0] ?? 0);
const totalAnterior = Number(ys.total_anterior?.[0] ?? 0);
const variacion = Number(ys.variacion_pct?.[0] ?? 0);

const CARD_FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif';
const arrow = variacion >= 0 ? "▲" : "▼";
const pctColor = variacion >= 0 ? "#73b63f" : "#c0392b";
const bgColor = variacion >= 0 ? "#e7f2d7" : "#f8dddd";
const formatCurrency = value =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 }).format(value);

const layout = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "#ffffff",
  height: 148,
  margin: { l: 0, r: 0, t: 0, b: 0 },
  xaxis: { visible: false, fixedrange: true },
  yaxis: { visible: false, fixedrange: true },
  shapes: [
    { type: "rect", xref: "paper", yref: "paper", x0: 0, x1: 1, y0: 0, y1: 1, line: { color: "#1b1b1b", width: 2 }, fillcolor: "#ffffff", layer: "below" },
    { type: "rect", xref: "paper", yref: "paper", x0: 0.75, x1: 1, y0: 0.5, y1: 1, line: { color: "rgba(0,0,0,0)", width: 0 }, fillcolor: bgColor, layer: "below" },
  ],
  annotations: [
    { xref: "paper", yref: "paper", x: 0.05, y: 0.82, text: "Saldo promedio", showarrow: false, xanchor: "left", yanchor: "middle", font: { family: CARD_FONT, size: 20, color: "#111111" } },
    { xref: "paper", yref: "paper", x: 0.40, y: 0.38, text: `<b>${formatCurrency(totalActual)}</b>`, showarrow: false, xanchor: "center", yanchor: "middle", font: { family: CARD_FONT, size: 26, color: "#111111" } },
    { xref: "paper", yref: "paper", x: 0.05, y: 0.10, text: `<i><b>${formatCurrency(totalAnterior)} vs año anterior</b></i>`, showarrow: false, xanchor: "left", yanchor: "middle", font: { family: CARD_FONT, size: 15, color: "#8a8a8a" } },
    { xref: "paper", yref: "paper", x: 0.875, y: 0.74, text: `<b>${arrow} ${Math.abs(variacion).toFixed(2)}%</b>`, showarrow: false, xanchor: "center", yanchor: "middle", font: { family: CARD_FONT, size: 16, color: pctColor } },
  ],
};

Plotly.newPlot(element, [], layout, { displayModeBar: false, responsive: true });
```
