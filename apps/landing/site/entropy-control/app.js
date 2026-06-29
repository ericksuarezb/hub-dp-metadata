const API_BASE_URL = "http://docgen.localhost";

const state = {
  search: "",
  loading: false,
  saving: false,
  importing: false,
  items: [],
  selectedRunId: "",
  draft: buildDraft(null),
  result: null
};

const elements = {
  searchInput: document.querySelector("#searchInput"),
  refreshButton: document.querySelector("#refreshButton"),
  loadingBadge: document.querySelector("#loadingBadge"),
  runList: document.querySelector("#runList"),
  emptyState: document.querySelector("#emptyState"),
  detailEmpty: document.querySelector("#detailEmpty"),
  detailView: document.querySelector("#detailView"),
  detailTitle: document.querySelector("#detailTitle"),
  detailRunId: document.querySelector("#detailRunId"),
  detailMetrics: document.querySelector("#detailMetrics"),
  includeCheckbox: document.querySelector("#includeCheckbox"),
  reviewStatus: document.querySelector("#reviewStatus"),
  lastStatus: document.querySelector("#lastStatus"),
  complementaryActions: document.querySelector("#complementaryActions"),
  notes: document.querySelector("#notes"),
  detailTimeline: document.querySelector("#detailTimeline"),
  saveButton: document.querySelector("#saveButton"),
  previewButton: document.querySelector("#previewButton"),
  executeButton: document.querySelector("#executeButton"),
  resultPanel: document.querySelector("#resultPanel"),
  resultRegistryCount: document.querySelector("#resultRegistryCount"),
  resultJson: document.querySelector("#resultJson"),
  errorBox: document.querySelector("#errorBox"),
  infoBox: document.querySelector("#infoBox")
};

let searchTimerId = null;

elements.searchInput.addEventListener("input", (event) => {
  state.search = event.target.value;
  window.clearTimeout(searchTimerId);
  searchTimerId = window.setTimeout(() => {
    loadRuns({ searchText: state.search });
  }, 220);
});

elements.refreshButton.addEventListener("click", () => {
  loadRuns({ searchText: state.search, preferredRunId: state.selectedRunId, forceDraftSync: false });
});

elements.includeCheckbox.addEventListener("change", (event) => {
  state.draft.includeInEntropy = event.target.checked;
  syncActionButtons();
});

elements.reviewStatus.addEventListener("change", (event) => {
  state.draft.reviewStatus = event.target.value;
});

elements.complementaryActions.addEventListener("input", (event) => {
  state.draft.complementaryActionsText = event.target.value;
});

elements.notes.addEventListener("input", (event) => {
  state.draft.notes = event.target.value;
});

elements.saveButton.addEventListener("click", () => saveControl());
elements.previewButton.addEventListener("click", () => runImport(false));
elements.executeButton.addEventListener("click", () => runImport(true));

loadRuns({ forceDraftSync: true });

async function loadRuns({ searchText = "", preferredRunId = null, forceDraftSync = false } = {}) {
  setBusy("loading", true);
  clearMessages();

  try {
    const params = new URLSearchParams();
    if (searchText.trim()) {
      params.set("search", searchText.trim());
    }
    params.set("limit", "100");

    const response = await fetch(`${API_BASE_URL}/api/entropy/runs?${params.toString()}`);
    const data = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(data, "No fue posible consultar los run_id para Entropy."));
    }

    state.items = Array.isArray(data.items) ? data.items : [];
    const candidateId = preferredRunId || state.selectedRunId;
    const nextSelected = state.items.find((item) => item.run_id === candidateId) || state.items[0] || null;

    if (!nextSelected) {
      state.selectedRunId = "";
      state.draft = buildDraft(null);
      state.result = null;
      render();
      return;
    }

    state.selectedRunId = nextSelected.run_id;
    if (forceDraftSync || preferredRunId || !candidateId || nextSelected.run_id !== candidateId) {
      state.draft = buildDraft(nextSelected);
    }
    state.result = nextSelected.last_import_result || state.result;
    render();
  } catch (error) {
    state.items = [];
    state.selectedRunId = "";
    state.result = null;
    showError(error.message);
    render();
  } finally {
    setBusy("loading", false);
  }
}

async function saveControl() {
  if (!state.selectedRunId) {
    return;
  }

  setBusy("saving", true);
  clearMessages();

  try {
    const response = await fetch(`${API_BASE_URL}/api/entropy/runs/${encodeURIComponent(state.selectedRunId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        include_in_entropy: state.draft.includeInEntropy,
        review_status: state.draft.reviewStatus,
        notes: state.draft.notes,
        complementary_actions: parseSimpleLines(state.draft.complementaryActionsText)
      })
    });
    const data = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(data, "No fue posible guardar el control de la corrida."));
    }

    state.draft = buildDraft(data);
    showInfo("Control actualizado correctamente.");
    await loadRuns({ searchText: state.search, preferredRunId: state.selectedRunId, forceDraftSync: true });
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy("saving", false);
  }
}

async function runImport(execute) {
  if (!state.selectedRunId) {
    return;
  }

  setBusy("importing", true);
  clearMessages();
  state.result = null;
  renderResult();

  try {
    const response = await fetch(`${API_BASE_URL}/api/entropy/runs/${encodeURIComponent(state.selectedRunId)}/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        execute,
        use_registry: true,
        refresh_registry: true
      })
    });
    const data = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(data, "No fue posible ejecutar la integracion con Entropy."));
    }

    state.result = data;
    showInfo(execute ? "Importacion ejecutada correctamente." : "Preview de importacion generado.");
    await loadRuns({ searchText: state.search, preferredRunId: state.selectedRunId, forceDraftSync: true });
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy("importing", false);
    renderResult();
  }
}

function setBusy(key, value) {
  state[key] = value;
  renderBusyState();
}

function render() {
  renderRunList();
  renderDetail();
  renderResult();
  renderBusyState();
}

function renderBusyState() {
  const busy = state.loading || state.saving || state.importing;
  elements.loadingBadge.classList.toggle("hidden", !state.loading);
  elements.refreshButton.disabled = busy;
  elements.saveButton.disabled = busy;
  elements.previewButton.disabled = busy;
  elements.executeButton.disabled = busy || !state.draft.includeInEntropy;
  elements.saveButton.textContent = state.saving ? "Guardando..." : "Guardar control";
  elements.previewButton.textContent = state.importing ? "Procesando..." : "Previsualizar importacion";
  elements.executeButton.textContent = state.importing ? "Procesando..." : "Ejecutar importacion";
}

function renderRunList() {
  elements.runList.innerHTML = "";
  elements.emptyState.classList.toggle("hidden", state.loading || state.items.length > 0);

  state.items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `run-card ${item.run_id === state.selectedRunId ? "active" : ""}`;
    button.addEventListener("click", () => {
      state.selectedRunId = item.run_id;
      state.draft = buildDraft(item);
      state.result = item.last_import_result || null;
      clearMessages();
      render();
    });

    button.innerHTML = `
      <div class="run-card-top">
        <strong>${escapeHtml(item.target_table || item.final_table_name || item.run_id)}</strong>
        <span class="status-pill ${item.include_in_entropy ? "success" : "muted"}">
          ${item.include_in_entropy ? "Incluido" : "Excluido"}
        </span>
      </div>
      <div class="run-card-id">${escapeHtml(item.run_id)}</div>
      <div class="run-card-meta">
        <span>${escapeHtml(item.product_name || "Sin producto")}</span>
        <span>${escapeHtml(item.sql_file_name || "Sin SQL")}</span>
        <span>${escapeHtml(formatStatusLabel(item.last_import_status))}</span>
      </div>
    `;
    elements.runList.appendChild(button);
  });
}

function renderDetail() {
  const item = state.items.find((entry) => entry.run_id === state.selectedRunId) || null;
  const hasSelection = Boolean(item);
  elements.detailEmpty.classList.toggle("hidden", hasSelection);
  elements.detailView.classList.toggle("hidden", !hasSelection);

  if (!item) {
    return;
  }

  elements.detailTitle.textContent = item.target_table || item.final_table_name || "Corrida seleccionada";
  elements.detailRunId.textContent = item.run_id;
  elements.detailMetrics.innerHTML = `
    <span>${item.created_at ? formatDateTime(item.created_at) : "Sin fecha"}</span>
    <span>${Number(item.source_count || 0)} sources</span>
    <span>${Number(item.transformation_count || 0)} transformaciones</span>
  `;

  elements.includeCheckbox.checked = state.draft.includeInEntropy;
  elements.reviewStatus.value = state.draft.reviewStatus || "pending";
  elements.lastStatus.value = formatStatusLabel(item.last_import_status);
  elements.complementaryActions.value = state.draft.complementaryActionsText;
  elements.notes.value = state.draft.notes;
  elements.detailTimeline.innerHTML = `
    <span>Ultima operacion: ${item.last_operation_at ? formatDateTime(item.last_operation_at) : "Aun no ejecutada"}</span>
    <span>Ultima importacion real: ${item.last_imported_at ? formatDateTime(item.last_imported_at) : "No registrada"}</span>
  `;

  syncActionButtons();
}

function renderResult() {
  const hasResult = Boolean(state.result);
  elements.resultPanel.classList.toggle("hidden", !hasResult);
  if (!hasResult) {
    elements.resultJson.textContent = "";
    elements.resultRegistryCount.textContent = "";
    return;
  }

  elements.resultRegistryCount.textContent = `${Number(state.result.registry_rows_synced || 0)} sources sincronizadas`;
  elements.resultJson.textContent = JSON.stringify(state.result.result || state.result, null, 2);
}

function syncActionButtons() {
  elements.executeButton.disabled = state.loading || state.saving || state.importing || !state.draft.includeInEntropy;
}

function buildDraft(item) {
  return {
    includeInEntropy: Boolean(item?.include_in_entropy),
    reviewStatus: item?.review_status || "pending",
    notes: item?.notes || "",
    complementaryActionsText: Array.isArray(item?.complementary_actions)
      ? item.complementary_actions.join("\n")
      : ""
  };
}

function parseSimpleLines(text) {
  return String(text || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function readResponsePayload(response) {
  const rawText = await response.text();
  if (!rawText) {
    return {};
  }

  try {
    return JSON.parse(rawText);
  } catch {
    return {
      rawText,
      detail: rawText
    };
  }
}

function extractErrorMessage(payload, fallback) {
  if (typeof payload === "string" && payload.trim()) {
    return payload.trim();
  }
  if (payload && typeof payload === "object") {
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
    if (typeof payload.error === "string" && payload.error.trim()) {
      return payload.error.trim();
    }
    if (typeof payload.rawText === "string" && payload.rawText.trim()) {
      return payload.rawText.trim();
    }
  }
  return fallback;
}

function formatStatusLabel(value) {
  const normalized = String(value || "idle").trim().toLowerCase();
  if (normalized === "planned") {
    return "Preview listo";
  }
  if (normalized === "executed") {
    return "Importado";
  }
  if (normalized === "failed") {
    return "Fallido";
  }
  if (normalized === "idle") {
    return "Sin ejecutar";
  }
  return normalized;
}

function formatDateTime(value) {
  try {
    return new Intl.DateTimeFormat("es-MX", {
      dateStyle: "medium",
      timeStyle: "short"
    }).format(new Date(value));
  } catch {
    return value || "Sin fecha";
  }
}

function showError(message) {
  elements.errorBox.textContent = message;
  elements.errorBox.classList.remove("hidden");
}

function showInfo(message) {
  elements.infoBox.textContent = message;
  elements.infoBox.classList.remove("hidden");
}

function clearMessages() {
  elements.errorBox.textContent = "";
  elements.infoBox.textContent = "";
  elements.errorBox.classList.add("hidden");
  elements.infoBox.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}
