# Integracion y empaquetado

## Recomendacion principal

La forma mas segura de mover este proyecto a otra integracion es tratarlo como una **aplicacion portable instalada sobre una carpeta de proyecto**, no como una libreria aislada.

Esto significa:

1. Copiar o clonar la carpeta completa del proyecto.
2. Crear un entorno virtual en el destino.
3. Instalar desde la raiz del proyecto con `pip install -e .` o `pip install -e .[web]`.
4. Ejecutar `docgen-sql-doctor` antes de correr el pipeline o la API web.

Si el entorno no tiene salida a internet o usa una version vieja de `pip`, usa:

```bash
pip install -e . --no-build-isolation
```

Y si aun asi el `editable install` falla por tooling legacy, usa:

```bash
python setup.py develop --no-deps
```

## Por que no conviene copiar solo `src/`

El proyecto depende tambien de:

- `config/`
- `input/templates/`
- `input/sql/`
- `web/` para el frontend y Mermaid CLI local
- `output/` y `data/` para runtime y persistencia local

Si solo se copia `src/`, se rompen rutas relativas, plantillas `.docx`, configuraciones y artefactos auxiliares.

## Instalacion recomendada

### Pipeline / CLI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
docgen-sql-doctor
```

### API web

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[web]
docgen-sql-doctor
docgen-sql-serve-web --host 0.0.0.0 --port 8000
```

### Frontend React

```bash
cd web
npm install
npm run build
```

## Variable `DOCGEN_SQL_HOME`

Si el comando se ejecuta fuera de la raiz del proyecto, puedes fijar la carpeta base explicitamente:

```bash
export DOCGEN_SQL_HOME=/ruta/docgen-sql
docgen-sql-doctor
```

Con esto el runtime sigue encontrando `config/`, `input/`, `output/` y `web/`.

## Validacion antes de integrar

Ejecuta:

```bash
docgen-sql-doctor
```

Y, si quieres una salida consumible por otra herramienta:

```bash
docgen-sql-doctor --json
```

El comando valida:

- estructura base del proyecto
- plantillas y carpetas requeridas
- carpetas de runtime
- dependencias Python principales
- dependencias opcionales de la capa web

## Comandos disponibles

- `docgen-sql-run`
- `docgen-sql-sync-variables`
- `docgen-sql-sync-modules`
- `docgen-sql-export-datacontract`
- `docgen-sql-serve-web`
- `docgen-sql-doctor`

## Alcance actual

La instalacion con `pip install -e .` esta pensada para una carpeta de trabajo completa.  
Todavia no se recomienda distribuir este proyecto como wheel standalone sin antes mover plantillas y recursos no-Python a package data formal.
