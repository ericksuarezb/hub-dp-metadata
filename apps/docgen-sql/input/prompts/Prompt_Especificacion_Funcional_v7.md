# PROMPT — Generacion de Especificacion Funcional de Producto de Datos (v7)

## OBJETIVO
A partir de un script SQL, generar un documento Word (.docx) de especificacion funcional en formato apaisado (landscape, Letter) con 9 secciones. El documento describe en lenguaje natural —sin codigo— las definiciones, criterios y logica del proceso, indicando siempre el campo y valor evaluado en cada regla y transformacion.

---

## REGLAS GENERALES

### Lenguaje y estilo
- Todo en español sin acentos en el contenido del documento (por compatibilidad de fuentes).
- No incluir codigo SQL; describir la logica en lenguaje natural.
- En cada regla y transformacion, siempre nombrar explicitamente el campo evaluado y el valor o condicion aplicada. Ejemplo: "Se excluyen cuentas cuyo campo estatuscuenta tenga el valor C (canceladas)."
- Reemplazar la palabra "patrones" por "valor" o "valores" y siempre especificar que campo se evalua y que valor tiene.

### Identificacion de capas de datos
- Las tablas que inician con `cd_` pertenecen a la capa **Crystal** y se identifican como insumos origen ya procesados.
- Las tablas que inician con `rd_` pertenecen a la capa **Raw**.
- Las tablas que inician con `cu_` pertenecen a la capa **Curada**.
- La capa Crystal se resalta visualmente en purpura (#6B21A8 texto, #F3E8FF fondo) en todas las secciones donde aparezca.

### Separacion de responsabilidades
- **Todas las transformaciones** (calculos, renombres, conversiones de tipo, clasificaciones, constantes, concatenaciones condicionales, normalizaciones, limpiezas, agregaciones, cascadas) se documentan **exclusivamente en la Seccion 5**.
- La **Seccion 7** (Proceso paso a paso) describe unicamente extraccion de datos, filtros aplicados y cruces realizados. No describe transformaciones; referencia a la Seccion 5 con frases como: "Las transformaciones sobre estos campos estan en la Seccion 5" o "ver transformacion #N en Seccion 5".
- Si un campo intermedio se genera en un paso de preparacion (ej: `prod_subprod` se calcula en el Paso 1 a partir del campo `producto`), esa transformacion debe aparecer en la Seccion 5 con su tipo real (Calculo, no Renombre). El paso solo menciona que se genera y referencia la seccion de transformaciones.

### Clasificacion correcta de transformaciones
- Un campo que cambia de nombre pero mantiene tipo y contenido es **Renombre**.
- Un campo que cambia de tipo es **Conv. tipo**.
- Un campo que cambia de nombre Y de tipo es **Conv. tipo + Renombre**.
- Un campo que se genera mediante operaciones sobre otro campo (substring, concat, LPAD, aritmetica, CASE WHEN) es **Calculo**, no Renombre.
- Un campo que resulta de una agregacion (COUNT, SUM, MIN, MAX) es **Agregacion** o **Agregacion + Conv. tipo** si ademas se convierte.
- Un campo que se limpia (TRIM) y ademas se convierte es **Limpieza + Conv. tipo**.
- Un campo que evalua multiples fuentes con COALESCE es **Cascada**.
- Un campo que asigna un valor fijo es **Constante**.
- Un campo que busca equivalencia en un catalogo es **Normalizacion**.
- Un campo que asigna valores segun condiciones evaluadas sobre otro campo es **Clasificacion**.
- Un campo que se enriquece solo cuando otro campo cumple una condicion es **Condicional**.

---

## ESTRUCTURA DEL DOCUMENTO (10 SECCIONES)

### Portada
- Titulo centrado: "ESPECIFICACION FUNCIONAL"
- Subtitulo: nombre del producto de datos
- Parrafo introductorio explicando que describe el documento
- Nota en purpura sobre tablas Crystal (cd_)
- Indice de las 10 secciones

---

### Seccion 1 — Referencia rapida y ficha del producto
**Tabla unica con tres bloques (tres encabezados de color diferente):**

**Bloque 1: FICHA DEL PRODUCTO** (encabezado azul marino #162B44)
| Campo | Contenido |
|---|---|
| Producto | Nombre del inventario/producto |
| Dominio | Area funcional |
| Responsable | Equipo encargado |
| Frecuencia | Periodicidad y parametro |
| Dia de actualizacion | Que dia de la semana se actualiza y por que (derivado del script: ej. si num_dia_sem=7, el corte es el domingo) |
| Horario esperado | Cuando se espera disponible la informacion (ej. "Lunes antes de las 08:00 hrs") |
| Granularidad | Nivel de detalle (una fila por...) |
| Proposito | Descripcion funcional completa |
| Salida | Tipo de resultado (tabla, vista, archivo) |
| Consumidores objetivo | Equipos, procesos o sistemas que consumen este producto de datos (ej: equipo de analitica, tableros BI, procesos downstream) |

**Bloque 2: TABLAS CRYSTAL DE SALIDA** (encabezado purpura #6B21A8)
| Tabla Crystal | Descripcion |
|---|---|
| cd_xxx_nombre_tabla | Descripcion corta del contenido de la tabla Crystal de salida: que contiene, granularidad, campos principales |

Nota: puede haber una o varias tablas de salida. Cada fila en fondo purpura claro (#F3E8FF).

**Bloque 3: REFERENCIA RAPIDA** (encabezado azul #2B6CB0)
| Pregunta | Respuesta |
|---|---|
| Cuantas fuentes usa | N tablas, M CTEs |
| Cuantos pasos tiene | Listado breve |
| Cuantos campos produce | N finales: X directos + Y transformados |
| Cuantas reglas lo rigen | N reglas |
| Que no hace | Limitaciones explicitas |

---

### Seccion 2 — Fuentes de datos
**Tabla con 7 columnas:**

| Alias | Tabla insumo | Capa | Campos finales que genera | Que contiene | Se usa en | Tabla Crystal destino |

- **Alias**: letra o letras usadas en el script (A, B, J, H, etc.)
- **Tabla insumo**: nombre completo con esquema
- **Capa**: Raw (rd_), Curada (cu_) o Crystal (cd_) — Crystal en fondo purpura
- **Campos finales que genera**: lista de campos del producto final que se originan en esta tabla. Si una tabla contribuye parcialmente a un campo (ej: `id_master` viene de multiples tablas), indicar "(parcial)". Si no genera campos finales directamente (ej: catalogo de fechas usado solo como filtro), indicarlo.
- **Que contiene**: descripcion funcional breve de la tabla insumo
- **Se usa en**: paso(s) donde interviene
- **Tabla Crystal destino**: nombre de la tabla Crystal final que se genera con todos estos insumos — columna entera en fondo purpura

---

### Seccion 3 — Flujo general del proceso
**Tabla con 5 columnas:**

| Paso | Accion | Depende de | Tablas nuevas | Salida |

- Cada paso en una fila con color de fondo distintivo (paleta de 7 colores)
- Indicar que pasos pueden ejecutarse en paralelo y cual necesita todos los anteriores

---

### Seccion 4 — Matriz de trazabilidad
**Tabla cruzada de campos x pasos. Con N columnas:**

| Campo | P1 | P2 | P3 | P4 | P5 | P6 | P7 |

- **NO incluir columna Clase ni columna Regla.**
- Fila de subencabezado con nombres cortos de cada paso
- Punto de color en la celda si el campo participa en ese paso
- Cada paso tiene su color distintivo
- Nota: "Para el detalle de cada transformacion, ir a la Seccion 5. Para la regla asociada, ir a la Seccion 6."

---

### Seccion 5 — Transformaciones
**Tabla unica con los N campos del producto final. 9 columnas:**

| # | Campo destino | Tipo | Subtipo | Origen | Campo origen | Que se le hace | Paso | Regla |

- **#**: numero secuencial
- **Campo destino**: nombre del campo en la salida final
- **Tipo**: D (directo, verde #15803D) o T (transformado, naranja #C2410C)
- **Subtipo**: para D es "—"; para T es el subtipo especifico (Renombre, Conv. tipo, Calculo, Cascada, Clasificacion, Condicional, Constante, Normalizacion, Limpieza, Agregacion, o combinaciones)
- **Origen**: alias de la tabla fuente o "—" para constantes
- **Campo origen**: nombre del campo en la tabla fuente. Si intervienen multiples campos, listarlos separados por " / "
- **Que se le hace**: descripcion completa de la transformacion incluyendo campos intermedios si aplica
- **Paso**: paso donde se origina el campo
- **Regla**: ID de la regla de negocio o "—"

**NO incluir columna de Valores.**

**Importante**: incluir aqui TODAS las transformaciones, incluyendo campos intermedios calculados en pasos de preparacion (ej: prod_subprod generado en Paso 1 a partir de producto es un Calculo, no un Renombre).

---

### Seccion 6 — Reglas de negocio
**Tabla con 3 columnas:**

| ID | Regla de negocio | Se aplica en |

- **ID**: RN-01, RN-02, etc.
- **Regla**: descripcion completa nombrando siempre campo y valor
- **Se aplica en**: paso donde se implementa

---

### Seccion 7 — Proceso paso a paso detallado
**Cada paso es una ficha (tabla) autocontenida:**

| Campo de la ficha | Contenido |
|---|---|
| Encabezado | "PASO N — Titulo" + objetivo (fondo de color del paso) |
| Depende de | Paso(s) previos o "Ninguno" |
| Tablas involucradas | Nombres completos. Marcar las Crystal. |
| Criterio de cruce | (si aplica) campo de A = campo de B para cada JOIN |
| Tipo de union | (si aplica) LEFT JOIN y significado |
| Que significa | (si aplica) Interpretacion funcional |
| Criterio de seleccion | (si aplica) Filtros: campo, operador, valor |
| Campos que se extraen | Lista de campos. NO describir transformaciones; referenciar Seccion 5. |
| Reglas aplicadas | IDs de reglas |
| Resultado | Que produce este paso |

**Regla critica**: Esta seccion NO describe transformaciones. Referencia a la Seccion 5.

**Flechas entre pasos**: flecha visual entre cada ficha. Salto de pagina cada 2-3 pasos.

---

### Seccion 8 — Convenciones y navegacion

**Subtabla 1: Tipos de transformacion y capas de datos**

| Tipo / Subtipo | Que significa | Ejemplo |

Incluir todos los subtipos usados mas la entrada "Crystal (cd_)".

**Subtabla 2: Como navegar este documento**
- Quiero saber como se transforma un campo -> Seccion 5
- Quiero saber en que pasos participa un campo -> Seccion 4
- Quiero saber que campos genera una tabla insumo -> Seccion 2
- Quiero entender una regla de negocio -> Seccion 6
- Quiero entender un paso del proceso -> Seccion 7
- Quiero saber que tablas Crystal se usan -> Seccion 2, columna Capa

---

## FORMATO VISUAL

### Pagina
- Orientacion: apaisada (landscape)
- Tamano: Letter (15840 x 12240 DXA)
- Margenes: 1080 DXA en los 4 lados
- Encabezado: linea con nombre del documento
- Pie: numero de pagina a la derecha

### Tipografia
- Fuente: Arial en todo el documento
- Titulos H1: 26pt, bold, azul marino (#162B44)
- Titulos H2: 21pt, bold, azul (#2B6CB0)
- Texto normal: 17pt, gris (#505050)
- Celdas de tabla: 12-16pt segun densidad

### Paleta de colores
- Azul marino (navy): #162B44
- Azul: #2B6CB0
- Purpura: #6B21A8 texto / #F3E8FF fondo — Crystal
- Verde: #15803D — campos directos (D)
- Naranja: #C2410C — campos transformados (T)
- Gris: #505050 texto, #F2F4F6 fondo alterno

### Colores de pasos (7 pasos)
| Paso | Fondo | Texto |
|---|---|---|
| 1 | #DBEAFE | #1E40AF |
| 2 | #E9D5FF | #6B21A8 |
| 3 | #FEF3C7 | #92400E |
| 4 | #D1FAE5 | #065F46 |
| 5 | #FCE7F3 | #9D174D |
| 6 | #E0E7FF | #3730A3 |
| 7 | #FEE2E2 | #991B1B |

### Tablas
- Bordes: linea simple, 1pt, gris claro (#D4D4D4)
- Filas alternadas: azul palido (#EBF2FA) / blanco
- Celdas de encabezado: fondo azul marino, texto blanco, bold
- Ancho total: 13680 DXA

---

## PROCESO DE ANALISIS DEL SCRIPT SQL

Al recibir un script SQL, seguir estos pasos:

1. **Identificar las fuentes**: tablas, CTEs, subconsultas. Clasificar por capa (rd_, cu_, cd_).
2. **Identificar los pasos del proceso**: cada CTE o subconsulta es un paso de preparacion; el SELECT final es el ensamble.
3. **Extraer los campos de salida**: listar todos los campos del SELECT final.
4. **Clasificar cada campo**: Directo o Transformado con subtipo correcto segun la operacion real.
5. **Extraer las reglas de negocio**: cada filtro, deduplicacion, normalizacion, calculo condicional.
6. **Mapear fuentes a campos finales**: para cada tabla insumo, que campos del producto final genera.
7. **Identificar tabla(s) Crystal de salida**: la tabla final que este proceso alimenta.
8. **Determinar periodicidad**: dia de la semana del corte (derivado de num_dia_sem u otro indicador) y horario esperado de disponibilidad.
9. **Construir la matriz de trazabilidad**: marcar en que pasos participa cada campo.
10. **Generar el documento** siguiendo la estructura de 8 secciones.

---

## EJEMPLO DE USO

```
Entrada: [script SQL pegado o adjuntado]
Instruccion: "Genera la especificacion funcional de este script usando el prompt v7."
```

El resultado sera un documento .docx con:
- Seccion 1: ficha con dia/horario de actualizacion + tablas Crystal de salida con descripcion
- Seccion 2: fuentes mapeadas a campos finales + tabla Crystal destino
- Seccion 3: flujo general
- Seccion 4: matriz sin columna Clase ni Regla
- Seccion 5: todas las transformaciones centralizadas (incluyendo intermedias)
- Seccion 6: reglas de negocio
- Seccion 7: pasos sin transformaciones (solo extraccion, filtros, cruces)
- Seccion 8: convenciones y navegacion
