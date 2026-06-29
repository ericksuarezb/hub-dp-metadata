import { useEffect, useMemo, useRef, useState } from "react";
import mermaid from "mermaid";

const API_BASE_URL = "";
const DUCKDB_UI_URL = "http://localhost:4213/";
const DOCX_ICON_URL = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTbYQcLfUfqY6nAiwop5kkdkSvuKg0qzIc2TA&s";
const ENTROPY_ICON_URL = "https://www.entropy-data.com/media/entropy-data-icon.png";

const initialState = {
  mode: "structural",
  sqlText: "",
  sqlFileName: "consulta_web.sql",
  productName: "",
  frequency: "Diario",
  finalTableName: "",
  filePrefix: "DA_REQ_CD_IT_",
  documentTitle: "Documentacion Funcional Estructural",
  generateDatacontract: true,
  variablesText: "",
  quickReferenceText: "",
  targetConsumersText: "",
  domain: "",
  owner: "",
  updateDay: "",
  expectedSchedule: "",
  granularity: "",
  purpose: "",
  outputType: "Tabla",
  moduleId: "paso_web_01",
  moduleName: "Paso web",
  moduleIntention: "",
  moduleDependsOnText: "",
  moduleOutputTablesText: "",
  moduleTagsText: "",
  ddlText: "",
  dictionaryText: ""
};

function App() {
  const [form, setForm] = useState(initialState);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [duckdbUiLoading, setDuckdbUiLoading] = useState(false);
  const [variablesLoading, setVariablesLoading] = useState(false);
  const [contextSuggestionLoading, setContextSuggestionLoading] = useState(false);
  const [contextSuggestionMeta, setContextSuggestionMeta] = useState(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [sqlFiles, setSqlFiles] = useState([]);
  const [activeSqlFileId, setActiveSqlFileId] = useState(null);
  const [contractEditor, setContractEditor] = useState({
    content: "",
    fileName: "",
    sourceLabel: "",
    runId: "",
    updatedAt: ""
  });
  const [editorMenuOpen, setEditorMenuOpen] = useState(false);
  const [storageModalOpen, setStorageModalOpen] = useState(false);
  const [storageSearch, setStorageSearch] = useState("");
  const [storageLoading, setStorageLoading] = useState(false);
  const [storageItems, setStorageItems] = useState([]);
  const [storageSelectionLoading, setStorageSelectionLoading] = useState(false);
  const sqlFileInputRef = useRef(null);

  const setField = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const setSqlField = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
    if (!activeSqlFileId) {
      return;
    }
    setSqlFiles((current) =>
      current.map((file) =>
        file.id === activeSqlFileId
          ? {
              ...file,
              name: key === "sqlFileName" ? value : file.name,
              content: key === "sqlText" ? value : file.content
            }
          : file
      )
    );
  };

  const handleSqlFileUpload = async (file) => {
    if (!file) {
      return;
    }

    const content = await file.text();
    const id = `${file.name}-${Date.now()}`;
    const nextFile = { id, name: file.name, content, isStep: false };

    setSqlFiles((current) => [...current, nextFile]);
    setActiveSqlFileId(id);
    setContextSuggestionMeta(null);
    setForm((current) => ({
      ...current,
      sqlFileName: file.name,
      sqlText: content,
      documentTitle: buildDocumentTitle(file.name),
      mode: "structural"
    }));
  };

  const selectSqlFile = (fileId) => {
    const selected = sqlFiles.find((item) => item.id === fileId);
    if (!selected) {
      return;
    }
    setActiveSqlFileId(fileId);
    setContextSuggestionMeta(null);
    setForm((current) => ({
      ...current,
      sqlFileName: selected.name,
      sqlText: selected.content,
      documentTitle: buildDocumentTitle(selected.name),
      mode: selected.isStep ? "step" : "structural"
    }));
  };

  const toggleSqlStep = (fileId, checked) => {
    setSqlFiles((current) =>
      current.map((file) =>
        file.id === fileId
          ? {
              ...file,
              isStep: checked
            }
          : file
      )
    );

    const selected = sqlFiles.find((item) => item.id === fileId);
    if (selected && fileId === activeSqlFileId) {
      setForm((current) => ({
        ...current,
        mode: checked ? "step" : "structural"
      }));
    }
  };

  const buildPayload = () => ({
    mode: form.mode,
    sql_text: form.sqlText,
    sql_file_name: form.sqlFileName,
    sql_files: sqlFiles.map((file) => ({
      sql_file_name: file.name,
      sql_text: file.content,
      is_step: file.isStep
    })),
    product_name: form.productName,
    frequency: form.frequency,
    final_table_name: form.finalTableName,
    file_prefix: form.filePrefix,
    document_title: form.documentTitle,
    generate_datacontract: form.generateDatacontract,
    variables: parseVariables(form.variablesText),
    profile_db_path: "data/duckdb/docgen_profiles.duckdb",
    profile_engine: "duckdb",
    product_sheet: {
      domain: form.domain || null,
      owner: form.owner || null,
      frequency: form.frequency || null,
      update_day: form.updateDay || null,
      expected_schedule: form.expectedSchedule || null,
      granularity: form.granularity || null,
      purpose: form.purpose || null,
      output_type: form.outputType || null,
      target_consumers: parseSimpleLines(form.targetConsumersText)
    },
    output_tables: [],
    quick_reference: parseSimpleLines(form.quickReferenceText),
    module:
      form.mode === "step"
        ? {
            id: form.moduleId,
            name: form.moduleName,
            intention: form.moduleIntention,
            depends_on: parseSimpleLines(form.moduleDependsOnText),
            output_tables: parseSimpleLines(form.moduleOutputTablesText),
            tags: parseSimpleLines(form.moduleTagsText),
            is_main: true
          }
        : null,
    ddl_text: form.ddlText || null,
    dictionary_text: form.dictionaryText || null,
    structural_template: null,
    step_template: null
  });

  const steps = useMemo(
    () => buildSteps(form),
    [form]
  );

  const activeStep = steps[currentStep];
  const progress = Math.round(((currentStep + 1) / steps.length) * 100);
  const canGoNext = activeStep.complete || activeStep.optional;
  const principalSqlFile = sqlFiles.find((file) => !file.isStep) || null;
  const stepSqlFiles = sqlFiles.filter((file) => file.isStep);
  const artifactEntries = result
    ? Object.entries(result.artifact_links || {}).map(([key, link]) => ({
        key,
        link,
        path: result.generated_files[key],
      }))
    : [];
  const visibleArtifactEntries = artifactEntries.filter((item) => !isHiddenArtifact(item.key));
  const docxArtifacts = artifactEntries.filter((item) => item.path?.toLowerCase().endsWith(".docx"));
  const yamlArtifacts = visibleArtifactEntries.filter((item) => item.path?.toLowerCase().endsWith(".yaml"));
  const otherArtifacts = visibleArtifactEntries.filter(
    (item) => !item.path?.toLowerCase().endsWith(".docx") && !item.path?.toLowerCase().endsWith(".yaml")
  );
  const mermaidArtifact = artifactEntries.find((item) => item.key === "pipeline_diagram_mermaid") || null;
  const pipelinePngArtifact = artifactEntries.find((item) => item.key === "pipeline_diagram_png") || null;
  const firstYamlArtifact = yamlArtifacts[0] || null;
  const detectedVariableTokens = useMemo(
    () => collectVariableTokensFromFiles(sqlFiles, form.sqlText),
    [sqlFiles, form.sqlText]
  );
  const providedVariables = useMemo(
    () => parseVariablesToMap(form.variablesText),
    [form.variablesText]
  );
  const missingVariableTokens = useMemo(
    () => detectedVariableTokens.filter((item) => !String(providedVariables[item] || "").trim()),
    [detectedVariableTokens, providedVariables]
  );

  useEffect(() => {
    setEditorMenuOpen(false);
  }, [storageModalOpen]);

  useEffect(() => {
    if (!firstYamlArtifact?.link) {
      return;
    }
    let cancelled = false;

    async function syncEditorWithLatestResult() {
      try {
        const response = await fetch(firstYamlArtifact.link);
        const text = await response.text();
        if (!response.ok) {
          throw new Error("No fue posible abrir el contrato generado");
        }
        if (cancelled) {
          return;
        }
        setContractEditor({
          content: text,
          fileName: firstYamlArtifact.path?.split("/").pop() || "datacontract.odcs.yaml",
          sourceLabel: "Resultado actual",
          runId: result?.run_id || "",
          updatedAt: ""
        });
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      }
    }

    syncEditorWithLatestResult();
    return () => {
      cancelled = true;
    };
  }, [firstYamlArtifact?.link, firstYamlArtifact?.path, result?.run_id]);

  useEffect(() => {
    if (!storageModalOpen) {
      return;
    }
    const timerId = window.setTimeout(() => {
      loadLatestDatacontracts(storageSearch);
    }, 220);
    return () => window.clearTimeout(timerId);
  }, [storageModalOpen, storageSearch]);

  const submit = async (endpoint) => {
    if (endpoint.includes("/api/generate") && missingVariableTokens.length > 0) {
      setError(`Faltan variables requeridas antes de generar: ${missingVariableTokens.join(", ")}`);
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload())
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "No fue posible procesar la solicitud");
      }
      if (endpoint.includes("preview")) {
        setPreview(data);
      } else {
        setResult(data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const openDuckDbUi = async () => {
    setDuckdbUiLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/api/duckdb-ui/start`, {
        method: "POST"
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "No fue posible levantar DuckDB UI");
      }
      window.open(data.url || DUCKDB_UI_URL, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err.message);
    } finally {
      setDuckdbUiLoading(false);
    }
  };

  const detectVariables = async () => {
    setVariablesLoading(true);
    setError("");

    try {
      const detectedVariables = collectVariableTokensFromFiles(sqlFiles, form.sqlText);
      const mergedText = detectedVariables
        .map((item) => `${item}=${providedVariables[item] || ""}`)
        .join("\n");
      setField("variablesText", mergedText);
    } catch (err) {
      setError(err.message);
    } finally {
      setVariablesLoading(false);
    }
  };

  const inferBusinessContext = async () => {
    setContextSuggestionLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/api/sql/business-context`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sql_text: form.sqlText,
          sql_file_name: form.sqlFileName
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "No fue posible inferir el contexto funcional");
      }
      setField("purpose", data.purpose || "");
      setField("quickReferenceText", (data.non_goals || []).join("\n"));
      setContextSuggestionMeta({
        provider: data.provider || "heuristic",
        warning: data.warning || ""
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setContextSuggestionLoading(false);
    }
  };

  const goNext = () => {
    if (currentStep < steps.length - 1 && canGoNext) {
      setCurrentStep((value) => value + 1);
    }
  };

  const goBack = () => {
    if (currentStep > 0) {
      setCurrentStep((value) => value - 1);
    }
  };

  const saveContractEditor = () => {
    const yamlText = contractEditor.content || "";
    if (!yamlText.trim()) {
      setError("No hay contenido ODCS para guardar.");
      return;
    }
    const fileName = contractEditor.fileName || "datacontract.odcs.yaml";
    const blob = new Blob([yamlText], { type: "application/yaml;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(objectUrl);
  };

  const loadLatestDatacontracts = async (searchText = "") => {
    setStorageLoading(true);
    setError("");

    try {
      const params = new URLSearchParams();
      if (searchText.trim()) {
        params.set("search", searchText.trim());
      }
      params.set("limit", "100");
      const response = await fetch(`${API_BASE_URL}/api/datacontracts/latest?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "No fue posible consultar Supabase");
      }
      setStorageItems(Array.isArray(data.items) ? data.items : []);
    } catch (err) {
      setError(err.message);
      setStorageItems([]);
    } finally {
      setStorageLoading(false);
    }
  };

  const openStorageModal = () => {
    setEditorMenuOpen(false);
    setStorageModalOpen(true);
  };

  const loadDatacontractFromSupabase = async (item) => {
    if (!item?.run_id) {
      return;
    }
    setStorageSelectionLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/datacontracts/${encodeURIComponent(item.run_id)}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "No fue posible cargar el contrato desde Supabase");
      }
      setContractEditor({
        content: data.yaml_text || "",
        fileName: data.file_name || item.file_name || "datacontract.odcs.yaml",
        sourceLabel: data.table_name ? `Supabase · ${data.table_name}` : "Supabase",
        runId: data.run_id || item.run_id || "",
        updatedAt: data.updated_at || item.updated_at || ""
      });
      setStorageModalOpen(false);
      setEditorMenuOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setStorageSelectionLoading(false);
    }
  };

  return (
    <div className="page-shell">
      <aside className="hero-panel">
        <p className="eyebrow">docgen-sql studio</p>
        <div className="hero-actions">
          <button
            className="hero-link primary-link"
            type="button"
            onClick={openDuckDbUi}
            disabled={duckdbUiLoading}
          >
            {duckdbUiLoading ? "Levantando DuckDB UI..." : "Abrir DuckDB UI"}
          </button>
        </div>
        <h1>Un flujo guiado para cargar el SQL sin perder al usuario.</h1>
        <p className="lede">
          Ahora el formulario avanza paso a paso: primero definimos el producto,
          luego pegamos el SQL, después agregamos contexto y al final anexos opcionales.
        </p>
        <div className="hero-card">
          <strong>Salida esperada</strong>
          <ul>
            <li>Analisis estructurado del SQL</li>
            <li>Documento DOCX estructural o STEP</li>
            <li>Contrato ODCS YAML enriquecido</li>
            <li>Diagrama visual del pipeline</li>
          </ul>
        </div>
        <div className="hero-card compact">
          <strong>Ruta sugerida</strong>
          <ol className="route-list">
            {steps.map((step, index) => (
              <li key={step.id} className={index === currentStep ? "current" : step.complete ? "done" : ""}>
                <span>{index + 1}</span>
                <div>
                  <b>{step.title}</b>
                  <small>{step.short}</small>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </aside>

      <main className="workspace">
        <section className="wizard-shell panel">
          <div className="wizard-topbar">
            <div>
              <p className="section-kicker">Wizard guiado</p>
              <h2>{activeStep.title}</h2>
              <p className="step-copy">{activeStep.description}</p>
            </div>
            <div className="mode-chip-group">
              <span className="pill">Paso {currentStep + 1} de {steps.length}</span>
              <span className="pill subtle">Modo activo: {form.mode === "step" ? "Step" : "Structural"}</span>
            </div>
          </div>

          <div className="progress-rail" aria-hidden="true">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>

          <div className="wizard-body">
            <div className="wizard-nav">
              {steps.map((step, index) => (
                <button
                  key={step.id}
                  type="button"
                  className={[
                    "step-tab",
                    index === currentStep ? "active" : "",
                    step.complete ? "complete" : ""
                  ].join(" ").trim()}
                  onClick={() => setCurrentStep(index)}
                >
                  <span className="step-index">{index + 1}</span>
                  <span className="step-meta">
                    <strong>{step.title}</strong>
                    <small>{step.complete ? "Completo" : step.optional ? "Opcional" : "Pendiente"}</small>
                  </span>
                </button>
              ))}
            </div>

            <div className="wizard-panel">
              {activeStep.id === "producto" && (
                <StepSection kicker="Primero lo esencial" title="Define el producto y la salida final">
                  <div className="grid two">
                    <Field label="Nombre del producto">
                      <input
                        value={form.productName}
                        onChange={(e) => setField("productName", e.target.value)}
                        placeholder="Portafolio de cuentas activas"
                      />
                    </Field>
                    <Field label="Tabla final del pipeline">
                      <input
                        value={form.finalTableName}
                        onChange={(e) => setField("finalTableName", e.target.value)}
                        placeholder="esquema.tabla_final"
                      />
                    </Field>
                    <Field label="Frecuencia">
                      <input value={form.frequency} onChange={(e) => setField("frequency", e.target.value)} />
                    </Field>
                    <Field label="Prefijo de archivo">
                      <input value={form.filePrefix} onChange={(e) => setField("filePrefix", e.target.value)} />
                    </Field>
                  </div>
                </StepSection>
              )}

              {activeStep.id === "sql" && (
                <StepSection kicker="Segundo el SQL" title="Carga el archivo y el cuerpo del proceso">
                  <div className="sql-upload-bar">
                    <div>
                      <h4>Secuencia de archivos SQL</h4>
                      <p>Carga archivos uno por uno y selecciona cuál es el activo para editarlo o procesarlo.</p>
                    </div>
                    <div className="actions">
                      <input
                        ref={sqlFileInputRef}
                        type="file"
                        accept=".sql"
                        className="hidden-input"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          handleSqlFileUpload(file);
                          e.target.value = "";
                        }}
                      />
                      <button
                        type="button"
                        className="primary"
                        onClick={() => sqlFileInputRef.current?.click()}
                      >
                        {sqlFiles.length > 0 ? "Agregar otro SQL" : "Cargar archivo SQL"}
                      </button>
                    </div>
                  </div>
                  {sqlFiles.length > 0 && (
                    <>
                      <div className="sql-generation-summary">
                        <div className="summary-block">
                          <span>Principal estructural</span>
                          <b>{principalSqlFile ? principalSqlFile.name : "Aun no definido"}</b>
                        </div>
                        <div className="summary-block">
                          <span>STEP a generar</span>
                          <b>{stepSqlFiles.length > 0 ? stepSqlFiles.map((file) => file.name).join(", ") : "Ninguno"}</b>
                        </div>
                      </div>
                      <div className="sql-sequence-list">
                        {sqlFiles.map((file, index) => (
                          <div
                            key={file.id}
                            className={`sql-file-chip ${file.id === activeSqlFileId ? "active" : ""}`}
                          >
                            <label className="sql-mode-check">
                              <input
                                type="checkbox"
                                checked={file.isStep}
                                onChange={(e) => toggleSqlStep(file.id, e.target.checked)}
                              />
                              <span>Step</span>
                            </label>
                            <button
                              type="button"
                              className="sql-file-main"
                              onClick={() => selectSqlFile(file.id)}
                            >
                              <span>{index + 1}</span>
                              <div>
                                <strong>{file.name}</strong>
                                <small>
                                  {file.id === activeSqlFileId
                                    ? file.isStep
                                      ? "Archivo activo · STEP"
                                      : "Archivo activo · Principal"
                                    : file.isStep
                                      ? "Marcado como STEP"
                                      : "Marcado como principal"}
                                </small>
                              </div>
                            </button>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                  {form.sqlFileName && (
                    <div className="sql-active-summary">
                      <div>
                        <span>Archivo activo</span>
                        <b>{form.sqlFileName}</b>
                      </div>
                      <div>
                        <span>Titulo derivado</span>
                        <b>{form.documentTitle}</b>
                      </div>
                      <div>
                        <span>Modo derivado</span>
                        <b>{form.mode === "step" ? "Step" : "Structural"}</b>
                      </div>
                    </div>
                  )}
                  <div className="grid two">
                    <Field label="Proposito">
                      <div className="field-stack">
                        <button
                          type="button"
                          className="ghost inline-action"
                          onClick={inferBusinessContext}
                          disabled={contextSuggestionLoading || !form.sqlText.trim()}
                        >
                          {contextSuggestionLoading ? "Infiriendo con IA..." : "Inferir proposito y que no hace"}
                        </button>
                        <textarea
                          rows="4"
                          value={form.purpose}
                          onChange={(e) => setField("purpose", e.target.value)}
                          placeholder="Resumen funcional breve del SQL."
                        />
                      </div>
                    </Field>
                    <Field label="Que no hace (uno por linea)">
                      <div className="field-stack">
                        {contextSuggestionMeta && (
                          <p className="field-hint">
                            Fuente: {contextSuggestionMeta.provider === "openai" ? "LLM" : "inferencia local"}
                            {contextSuggestionMeta.warning ? ` · ${contextSuggestionMeta.warning}` : ""}
                          </p>
                        )}
                        <textarea
                          rows="5"
                          value={form.quickReferenceText}
                          onChange={(e) => setField("quickReferenceText", e.target.value)}
                          placeholder="No cubre reportes finales.&#10;No describe reglas fuera del SQL."
                        />
                      </div>
                    </Field>
                  </div>
                </StepSection>
              )}

              {activeStep.id === "contexto" && (
                <StepSection kicker="Tercero el negocio" title="Explica el contexto funcional del pipeline">
                  <div className="grid two">
                    <Field label="Dominio">
                      <input value={form.domain} onChange={(e) => setField("domain", e.target.value)} />
                    </Field>
                    <Field label="Responsable">
                      <input value={form.owner} onChange={(e) => setField("owner", e.target.value)} />
                    </Field>
                    <Field label="Tipo de salida">
                      <input value={form.outputType} onChange={(e) => setField("outputType", e.target.value)} />
                    </Field>
                    <Field label="Dia de actualizacion">
                      <input value={form.updateDay} onChange={(e) => setField("updateDay", e.target.value)} />
                    </Field>
                    <Field label="Horario esperado">
                      <input value={form.expectedSchedule} onChange={(e) => setField("expectedSchedule", e.target.value)} />
                    </Field>
                  </div>
                  <div className="grid two">
                    <Field label="Granularidad">
                      <textarea rows="4" value={form.granularity} onChange={(e) => setField("granularity", e.target.value)} />
                    </Field>
                    <Field label="Consumidores objetivo (uno por linea)">
                      <textarea rows="6" value={form.targetConsumersText} onChange={(e) => setField("targetConsumersText", e.target.value)} />
                    </Field>
                  </div>
                </StepSection>
              )}

              {activeStep.id === "apoyos" && (
                <StepSection kicker="Cuarto enriquecer" title="Agrega variables, tablas y anexos opcionales">
                  <div className="grid two">
                    <Field label="Variables (${var}=valor)">
                      <div className="field-stack">
                        <button
                          type="button"
                          className="ghost inline-action"
                          onClick={detectVariables}
                          disabled={variablesLoading || !form.sqlText.trim()}
                        >
                          {variablesLoading ? "Detectando variables..." : "Obtener variables desde el SQL"}
                        </button>
                        <textarea
                          rows="8"
                          value={form.variablesText}
                          onChange={(e) => setField("variablesText", e.target.value)}
                          placeholder="${esquema}=demo&#10;${fecha}=2026-04-30"
                        />
                        {missingVariableTokens.length > 0 && (
                          <div className="inline-help warn">
                            Faltan variables por capturar: {missingVariableTokens.join(", ")}
                          </div>
                        )}
                      </div>
                    </Field>
                    <Field label="Diccionario opcional en markdown">
                      <div className="field-stack">
                        <a
                          className="inline-link"
                          href="https://tabletomarkdown.com/"
                          target="_blank"
                          rel="noreferrer"
                        >
                          Abrir Table To Markdown
                        </a>
                        <textarea
                          rows="8"
                          value={form.dictionaryText}
                          onChange={(e) => setField("dictionaryText", e.target.value)}
                          placeholder="| Nombre | Descripcion |"
                        />
                      </div>
                    </Field>
                  </div>
                  <Field label="DDL opcional">
                    <textarea rows="6" value={form.ddlText} onChange={(e) => setField("ddlText", e.target.value)} />
                  </Field>
                </StepSection>
              )}

              {activeStep.id === "final" && (
                <StepSection kicker="Quinto revisar" title="Cierra con plantillas, STEP y generacion">
                  {form.mode === "step" && (
                    <div className="step-subpanel">
                      <h3>Metadata STEP</h3>
                      <div className="grid two">
                        <Field label="Id del modulo">
                          <input value={form.moduleId} onChange={(e) => setField("moduleId", e.target.value)} />
                        </Field>
                        <Field label="Nombre del modulo">
                          <input value={form.moduleName} onChange={(e) => setField("moduleName", e.target.value)} />
                        </Field>
                        <Field label="Dependencias (una por linea)">
                          <textarea rows="5" value={form.moduleDependsOnText} onChange={(e) => setField("moduleDependsOnText", e.target.value)} />
                        </Field>
                        <Field label="Tablas de salida del modulo (una por linea)">
                          <textarea rows="5" value={form.moduleOutputTablesText} onChange={(e) => setField("moduleOutputTablesText", e.target.value)} />
                        </Field>
                      </div>
                      <Field label="Intencion del modulo">
                        <textarea rows="3" value={form.moduleIntention} onChange={(e) => setField("moduleIntention", e.target.value)} />
                      </Field>
                      <Field label="Tags del modulo (uno por linea)">
                        <textarea rows="4" value={form.moduleTagsText} onChange={(e) => setField("moduleTagsText", e.target.value)} />
                      </Field>
                    </div>
                  )}

                  <div className="review-card">
                    <div>
                      <span>Modo</span>
                      <b>{form.mode === "step" ? "STEP" : "Structural"}</b>
                    </div>
                    <div>
                      <span>Variables</span>
                      <b>{parseVariables(form.variablesText).length}</b>
                    </div>
                    <div>
                      <span>Variables faltantes</span>
                      <b>{missingVariableTokens.length}</b>
                    </div>
                    <div>
                      <span>Archivos SQL</span>
                      <b>{sqlFiles.length}</b>
                    </div>
                    <div>
                      <span>Contrato ODCS</span>
                      <b>{form.generateDatacontract ? "Activo" : "No generar"}</b>
                    </div>
                  </div>

                  <section className="action-bar wizard-actions">
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={form.generateDatacontract}
                        onChange={(e) => setField("generateDatacontract", e.target.checked)}
                      />
                      Generar contrato ODCS
                    </label>
                    <div className="actions">
                      <button type="button" className="ghost" onClick={() => submit("/api/preview-input")}>
                        Vista previa
                      </button>
                      <button
                        type="button"
                        className="primary"
                        onClick={() => submit("/api/generate")}
                        disabled={loading || missingVariableTokens.length > 0}
                      >
                        {loading ? "Procesando..." : "Generar artefactos"}
                      </button>
                    </div>
                  </section>
                </StepSection>
              )}

              <div className="wizard-footer">
                <div className="step-status">
                  <span className={`status-dot ${activeStep.complete ? "complete" : activeStep.optional ? "optional" : "pending"}`} />
                  <span>{activeStep.complete ? "Paso completo" : activeStep.optional ? "Paso opcional" : "Completa este paso para avanzar"}</span>
                </div>
                <div className="actions">
                  <button type="button" className="ghost" onClick={goBack} disabled={currentStep === 0}>
                    Anterior
                  </button>
                  <button type="button" className="primary" onClick={goNext} disabled={currentStep === steps.length - 1 || !canGoNext}>
                    Siguiente
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {error && <section className="panel error-box">{error}</section>}

        {preview && (
          <section className="panel result-panel">
            <p className="section-kicker">Preview</p>
            <pre>{JSON.stringify(preview, null, 2)}</pre>
          </section>
        )}

        {result && (
          <section className="panel result-panel">
            <p className="section-kicker">Resultado</p>
            <div className="result-grid">
              <div>
                <h3>Estatus de auditoria</h3>
                <p className={result.audit_passed ? "ok" : "warn"}>
                  {result.audit_passed ? "Paso" : "Con observaciones"}
                </p>
                <p><strong>run_id:</strong> {result.run_id}</p>
              </div>
              <div>
                <h3>Estadisticas</h3>
                <pre>{JSON.stringify(result.stats, null, 2)}</pre>
              </div>
            </div>
            {docxArtifacts.length > 0 && (
              <>
                <h3>Documentos Word</h3>
                <div className="docx-artifact-grid">
                  {docxArtifacts.map((artifact) => (
                    <a
                      key={artifact.key}
                      className="docx-artifact-card"
                      href={artifact.link}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <div className="docx-thumb" aria-hidden="true">
                        <img src={DOCX_ICON_URL} alt="" />
                      </div>
                      <div className="docx-meta">
                        <strong>{formatArtifactLabel(artifact.key)}</strong>
                        <small>{artifact.path.split("/").pop()}</small>
                        <em>Abrir archivo</em>
                      </div>
                    </a>
                  ))}
                </div>
              </>
            )}
            {(yamlArtifacts.length > 0 || contractEditor.content) && (
              <>
                <h3>Contrato ODCS</h3>
                <div className="docx-artifact-grid">
                  {yamlArtifacts.map((artifact) => (
                    <a
                      key={artifact.key}
                      className="docx-artifact-card"
                      href={artifact.link}
                      target="_blank"
                      rel="noreferrer"
                      download
                    >
                      <div className="docx-thumb yaml-thumb" aria-hidden="true">
                        <img src={ENTROPY_ICON_URL} alt="" />
                      </div>
                      <div className="docx-meta">
                        <strong>Contrato ODCS</strong>
                        <small>{artifact.path.split("/").pop()}</small>
                        <em>Descargar archivo</em>
                      </div>
                    </a>
                  ))}
                </div>
                <div className="datacontract-editor-shell">
                  <div className="datacontract-editor-toolbar">
                    <div>
                      <strong>Editor Data Contract</strong>
                      <small>
                        {contractEditor.sourceLabel || "Resultado actual"}
                        {contractEditor.updatedAt ? ` · ${formatDateTime(contractEditor.updatedAt)}` : ""}
                      </small>
                    </div>
                    <div className="datacontract-toolbar-actions">
                      <button type="button" className="primary" onClick={saveContractEditor}>
                        Save
                      </button>
                      <div className="datacontract-menu-shell">
                        <button
                          type="button"
                          className="ghost datacontract-menu-button"
                          onClick={() => setEditorMenuOpen((value) => !value)}
                          aria-haspopup="menu"
                          aria-expanded={editorMenuOpen}
                        >
                          ☰
                        </button>
                        {editorMenuOpen && (
                          <div className="datacontract-menu" role="menu">
                            <button
                              type="button"
                              className="datacontract-menu-item"
                              onClick={openStorageModal}
                            >
                              Cargar desde Supabase
                            </button>
                            <button
                              type="button"
                              className="datacontract-menu-item"
                              onClick={() => {
                                setEditorMenuOpen(false);
                                if (firstYamlArtifact?.link) {
                                  window.open(firstYamlArtifact.link, "_blank", "noopener,noreferrer");
                                }
                              }}
                            >
                              Abrir resultado actual
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                  <textarea
                    className="datacontract-editor"
                    rows="18"
                    value={contractEditor.content}
                    onChange={(e) =>
                      setContractEditor((current) => ({
                        ...current,
                        content: e.target.value
                      }))
                    }
                    placeholder="Aqui aparecera el contenido del contrato ODCS."
                  />
                </div>
              </>
            )}
            {result.pipeline_graph?.mermaid && (
              <>
                <h3>Diagrama del pipeline</h3>
                <PipelineGraph
                  graph={result.pipeline_graph}
                  mermaidArtifact={mermaidArtifact}
                  pngArtifact={pipelinePngArtifact}
                  runId={result.run_id}
                />
              </>
            )}
            <h3>Artefactos</h3>
            <ul className="artifact-list">
              {otherArtifacts.map((artifact) => (
                <li key={artifact.key}>
                  <a href={artifact.link} target="_blank" rel="noreferrer">
                    {artifact.key}
                  </a>
                  <span>{artifact.path}</span>
                </li>
              ))}
            </ul>
            {result.workspace_inventory?.length > 0 && (
              <>
                <h3>Workspace generado</h3>
                <div className="workspace-inventory-card">
                  <table className="workspace-inventory-table">
                    <thead>
                      <tr>
                        <th>Ruta</th>
                        <th>Tipo</th>
                        <th>Categoria</th>
                        <th>Tamano</th>
                        <th>Accion</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.workspace_inventory.map((item) => (
                        <tr key={item.relative_path}>
                          <td>
                            {item.storage_path ? (
                              <a
                                href={`${API_BASE_URL}/api/storage/docgen-artifacts/${item.storage_path}`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {item.relative_path}
                              </a>
                            ) : (
                              item.relative_path
                            )}
                          </td>
                          <td>{detectFileType(item.relative_path)}</td>
                          <td>{item.file_category}</td>
                          <td>{formatBytes(item.size_bytes)}</td>
                          <td>
                            {item.storage_path ? (
                              <a
                                className="workspace-open-link"
                                href={`${API_BASE_URL}/api/storage/docgen-artifacts/${item.storage_path}`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Abrir
                              </a>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {result.audit_errors?.length > 0 && (
              <>
                <h3>Errores</h3>
                <pre>{JSON.stringify(result.audit_errors, null, 2)}</pre>
              </>
            )}
            {result.audit_warnings?.length > 0 && (
              <>
                <h3>Warnings</h3>
                <pre>{JSON.stringify(result.audit_warnings, null, 2)}</pre>
              </>
            )}
          </section>
        )}

      </main>

      {storageModalOpen && (
        <div
          className="modal-backdrop"
          onClick={() => {
            if (!storageSelectionLoading) {
              setStorageModalOpen(false);
            }
          }}
        >
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <p className="section-kicker">Supabase Storage</p>
                <h3>Ultima version ODCS por tabla</h3>
                <p className="modal-copy">
                  Se usa la metadata persistida en la base para mostrar solo la version mas reciente de cada tabla.
                </p>
              </div>
              <button
                type="button"
                className="ghost"
                onClick={() => setStorageModalOpen(false)}
                disabled={storageSelectionLoading}
              >
                Cerrar
              </button>
            </div>
            <label className="field">
              <span>Buscar por tabla, producto o archivo SQL</span>
              <input
                value={storageSearch}
                onChange={(e) => setStorageSearch(e.target.value)}
                placeholder="clientes, portafolio, cuentas..."
              />
            </label>
            <div className="storage-results-shell">
              {storageLoading ? (
                <p className="field-hint">Consultando versiones en Supabase...</p>
              ) : storageItems.length === 0 ? (
                <p className="field-hint">No se encontraron contratos ODCS para esa busqueda.</p>
              ) : (
                <div className="storage-result-list">
                  {storageItems.map((item) => (
                    <button
                      key={item.run_id}
                      type="button"
                      className="storage-result-card"
                      onClick={() => loadDatacontractFromSupabase(item)}
                      disabled={storageSelectionLoading}
                    >
                      <div className="storage-result-main">
                        <strong>{item.table_name}</strong>
                        <small>{item.file_name}</small>
                      </div>
                      <div className="storage-result-meta">
                        <span>{item.product_name || "Sin producto"}</span>
                        <span>{item.sql_file_name || "Sin SQL"}</span>
                        <span>{item.updated_at ? formatDateTime(item.updated_at) : "Fecha no disponible"}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StepSection({ kicker, title, children }) {
  return (
    <section>
      <div className="step-section-head">
        <p className="section-kicker">{kicker}</p>
        <h3>{title}</h3>
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function buildSteps(form) {
  const variableCount = parseVariables(form.variablesText).length;

  return [
    {
      id: "producto",
      title: "Producto",
      short: "Nombre, tabla final y frecuencia",
      description: "Primero define el nombre del producto, la tabla final y la frecuencia del pipeline.",
      complete: Boolean(form.productName.trim() && form.finalTableName.trim() && form.frequency.trim()),
      optional: false
    },
    {
      id: "sql",
      title: "SQL",
      short: "Nombre de archivo y cuerpo del SQL",
      description: "Luego pega el SQL completo y el nombre del archivo que lo representa.",
      complete: Boolean(form.sqlFileName.trim() && form.sqlText.trim()),
      optional: false
    },
    {
      id: "contexto",
      title: "Contexto",
      short: "Dominio, responsable y consumidores",
      description: "Agrega el contexto de negocio estable para que el documento no se quede solo en la parte tecnica.",
      complete: Boolean(form.domain.trim() || form.owner.trim() || form.targetConsumersText.trim()),
      optional: true
    },
    {
      id: "apoyos",
      title: "Apoyos",
      short: "Variables, tablas y anexos",
      description: "Enriquece el contrato con variables, tablas de salida, muestras y metadatos opcionales.",
      complete: variableCount > 0 || Boolean(form.dictionaryText.trim() || form.ddlText.trim()),
      optional: true
    },
    {
      id: "final",
      title: "Revision final",
      short: "Plantillas, STEP y generacion",
      description: "Revisa lo opcional, activa ODCS si aplica y genera los artefactos finales.",
      complete: true,
      optional: true
    }
  ];
}

function buildDocumentTitle(fileName) {
  const stem = fileName.replace(/\.sql$/i, "");
  return stem
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase()) || "Documentacion Funcional Estructural";
}

function parseSimpleLines(text) {
  return text
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseVariables(text) {
  return parseSimpleLines(text).map((line) => {
    const [name, ...rest] = line.split("=");
    return {
      name: (name || "").trim(),
      value: rest.join("=").trim()
    };
  });
}

function parseVariablesToMap(text) {
  return parseVariables(text).reduce((accumulator, item) => {
    if (item.name) {
      accumulator[item.name] = item.value;
    }
    return accumulator;
  }, {});
}

function collectVariableTokensFromFiles(sqlFiles, fallbackSqlText) {
  const tokens = new Set();
  const pattern = /\$\{[^}]+\}/g;
  const contents = sqlFiles.length
    ? sqlFiles.map((file) => file.content || "")
    : [fallbackSqlText || ""];

  contents.forEach((text) => {
    const matches = text.match(pattern) || [];
    matches.forEach((item) => tokens.add(item));
  });

  return Array.from(tokens).sort();
}

function formatArtifactLabel(value) {
  return value
    .replace(/^step_docx__/, "STEP ")
    .replace(/^document_docx$/, "Documento principal")
    .replace(/__/g, " ")
    .replace(/_/g, " ")
    .trim();
}

function isHiddenArtifact(key) {
  return (
    key === "analysis_json" ||
    key === "audit_xlsx" ||
    key === "audit_json" ||
    key === "pipeline_diagram_mermaid" ||
    key === "pipeline_diagram_png" ||
    key.startsWith("step_audit_xlsx__") ||
    key.startsWith("step_audit_json__")
  );
}

function PipelineGraph({ graph, mermaidArtifact, pngArtifact, runId }) {
  const containerRef = useRef(null);
  const [svgMarkup, setSvgMarkup] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function renderGraph() {
      if (!containerRef.current || !graph?.mermaid) {
        return;
      }
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "loose",
        theme: "base"
      });
      const renderId = `pipeline-mermaid-${Math.random().toString(36).slice(2)}`;
      const { svg } = await mermaid.render(renderId, graph.mermaid);
      if (!cancelled && containerRef.current) {
        containerRef.current.innerHTML = svg;
        setSvgMarkup(svg);
      }
    }

    renderGraph().catch(() => {
      if (containerRef.current) {
        containerRef.current.innerHTML = "<p>No fue posible renderizar Mermaid en el navegador.</p>";
      }
      setSvgMarkup("");
    });

    return () => {
      cancelled = true;
    };
  }, [graph]);

  const openFullscreen = () => {
    if (!svgMarkup) {
      return;
    }
    const nextWindow = window.open("", "_blank", "noopener,noreferrer");
    if (!nextWindow) {
      return;
    }
    nextWindow.document.write(`<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>Diagrama del pipeline${runId ? ` · ${runId}` : ""}</title>
    <style>
      body {
        margin: 0;
        background: #f4f7f8;
        font-family: Arial, sans-serif;
        color: #14212b;
      }
      .wrap {
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
        box-sizing: border-box;
      }
      .canvas {
        width: 100%;
        overflow: auto;
        background: #ffffff;
        border: 1px solid #d7e0e3;
        border-radius: 20px;
        padding: 24px;
        box-sizing: border-box;
      }
      .canvas svg {
        width: 100%;
        height: auto;
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="canvas">${svgMarkup}</div>
    </div>
  </body>
</html>`);
    nextWindow.document.close();
  };

  const triggerDownload = (href, filename) => {
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const downloadDiagramImage = () => {
    if (pngArtifact?.link) {
      triggerDownload(pngArtifact.link, pngArtifact.path?.split("/").pop() || "pipeline_diagram.png");
      return;
    }
    if (!svgMarkup) {
      return;
    }
    const svgBlob = new Blob([svgMarkup], { type: "image/svg+xml;charset=utf-8" });
    const objectUrl = URL.createObjectURL(svgBlob);
    triggerDownload(objectUrl, `pipeline_diagram_${runId || "run"}.svg`);
    URL.revokeObjectURL(objectUrl);
  };

  const downloadMermaidSource = () => {
    if (mermaidArtifact?.link) {
      triggerDownload(mermaidArtifact.link, mermaidArtifact.path?.split("/").pop() || "pipeline_diagram.mmd");
      return;
    }
    const textBlob = new Blob([graph.mermaid || ""], { type: "text/plain;charset=utf-8" });
    const objectUrl = URL.createObjectURL(textBlob);
    triggerDownload(objectUrl, `pipeline_diagram_${runId || "run"}.mmd`);
    URL.revokeObjectURL(objectUrl);
  };

  return (
    <div className="pipeline-graph-shell">
      <div className="pipeline-graph-actions">
        <button type="button" className="ghost" onClick={openFullscreen} disabled={!svgMarkup}>
          Abrir en pantalla completa
        </button>
        <button type="button" className="ghost" onClick={downloadDiagramImage} disabled={!svgMarkup && !pngArtifact?.link}>
          {pngArtifact?.link ? "Descargar imagen PNG" : "Descargar imagen SVG"}
        </button>
        <button type="button" className="ghost" onClick={downloadMermaidSource}>
          Descargar .mmd
        </button>
      </div>
      <div className="pipeline-mermaid-canvas" ref={containerRef} />
      <div className="pipeline-legend">
        <span className="legend-chip green">cd_</span>
        <span className="legend-chip blue">rd_</span>
        <span className="legend-chip gray">cu_ y procesos</span>
        <span className="legend-chip amber">otros esquemas</span>
      </div>
      <div className="pipeline-relations-summary">
        <strong>Relaciones persistidas</strong>
        <small>{(graph.relations || []).length} relaciones detectadas para esta corrida.</small>
      </div>
      <details className="mermaid-block">
        <summary>Ver definicion Mermaid</summary>
        <pre>{graph.mermaid}</pre>
      </details>
    </div>
  );
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.split(",")[1] || "");
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function formatBytes(value) {
  const numeric = Number(value || 0);
  if (numeric < 1024) {
    return `${numeric} B`;
  }
  if (numeric < 1024 * 1024) {
    return `${(numeric / 1024).toFixed(1)} KB`;
  }
  return `${(numeric / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("es-MX", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function detectFileType(relativePath) {
  const lower = String(relativePath || "").toLowerCase();
  if (lower.endsWith(".sql")) {
    return "SQL";
  }
  if (lower.endsWith(".docx")) {
    return "DOCX";
  }
  if (lower.endsWith(".yml") || lower.endsWith(".yaml")) {
    return "YAML";
  }
  if (lower.endsWith(".md")) {
    return "Markdown";
  }
  if (lower.endsWith(".json")) {
    return "JSON";
  }
  if (lower.endsWith(".txt")) {
    return "Texto";
  }
  return "Archivo";
}

export default App;
