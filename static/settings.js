(() => {
  "use strict";

  /* ----------------------------------------------------------------------
   * DOM lookup
   * ---------------------------------------------------------------------- */
  const $ = (id) => document.getElementById(id);

  const form        = $("llm-form");
  const baseUrlEl   = $("llm-base-url");
  const apiKeyEl    = $("llm-api-key");
  const testBtn     = $("llm-test-btn");
  const saveBtn     = $("llm-save-btn");
  const statusEl    = $("llm-status");
  const modelSel    = $("llm-model");
  const modelCount  = $("llm-model-count");
  const keyReveal   = $("llm-key-reveal");
  const iconEye     = $("icon-eye");
  const iconEyeOff  = $("icon-eye-off");

  const themeToggle = $("theme-toggle");
  const iconMoon    = $("icon-moon");
  const iconSun     = $("icon-sun");
  const themeLabel  = $("theme-label");

  const hasSavedKey = (form.dataset.hasKey === "true");
  const savedModel  = form.dataset.savedModel || "";

  /* ----------------------------------------------------------------------
   * Helpers
   * ---------------------------------------------------------------------- */
  function show(el) { if (el) el.classList.remove("hidden"); }
  function hide(el) { if (el) el.classList.add("hidden"); }

  function toast(text) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 250);
    }, 1800);
  }

  function setStatus(kind, text) {
    statusEl.classList.remove("ok", "fail", "info");
    if (!text) { hide(statusEl); statusEl.textContent = ""; return; }
    statusEl.classList.add(kind);
    statusEl.textContent = text;
    show(statusEl);
  }

  function setBusy(btn, busy) {
    if (!btn) return;
    btn.disabled = !!busy;
    btn.classList.toggle("is-loading", !!busy);
  }

  function isValidBaseUrl(url) {
    if (!url) return false;
    try {
      const u = new URL(url);
      return (u.protocol === "http:" || u.protocol === "https:");
    } catch (_) {
      return false;
    }
  }

  /* ----------------------------------------------------------------------
   * Theme — same toggle as the main app, kept self-contained for /settings
   * ---------------------------------------------------------------------- */
  function applyTheme(theme) {
    if (theme === "light") {
      document.body.classList.add("theme-light");
      hide(iconMoon); show(iconSun);
      themeLabel.textContent = "Light";
    } else {
      document.body.classList.remove("theme-light");
      show(iconMoon); hide(iconSun);
      themeLabel.textContent = "Dark";
    }
  }
  const storedTheme = (() => {
    try { return localStorage.getItem("sublyai_theme") || "dark"; } catch { return "dark"; }
  })();
  applyTheme(storedTheme);
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const next = document.body.classList.contains("theme-light") ? "dark" : "light";
      applyTheme(next);
      try { localStorage.setItem("sublyai_theme", next); } catch {}
    });
  }

  /* ----------------------------------------------------------------------
   * Reveal / hide API key
   * ---------------------------------------------------------------------- */
  if (keyReveal) {
    keyReveal.addEventListener("click", () => {
      if (apiKeyEl.type === "password") {
        apiKeyEl.type = "text";
        hide(iconEye); show(iconEyeOff);
        keyReveal.setAttribute("aria-label", "Hide API key");
      } else {
        apiKeyEl.type = "password";
        show(iconEye); hide(iconEyeOff);
        keyReveal.setAttribute("aria-label", "Reveal API key");
      }
    });
  }

  /* ----------------------------------------------------------------------
   * Wire form state
   * ---------------------------------------------------------------------- */
  function refreshSaveState() {
    // Enable Save when (a) a model is picked and (b) we have a base URL +
    // either a freshly-entered key or a saved key.
    const hasBase   = isValidBaseUrl(baseUrlEl.value.trim());
    const hasKey    = !!apiKeyEl.value.trim() || hasSavedKey;
    const hasModel  = !!(modelSel.value && !modelSel.disabled);
    saveBtn.disabled = !(hasBase && hasKey && hasModel);
  }

  baseUrlEl.addEventListener("input", () => {
    // Mutating base URL invalidates the previously-detected model list.
    if (baseUrlEl.value.trim() !== (form.dataset.savedBase || "")) {
      resetModelDropdown();
    }
    refreshSaveState();
  });
  apiKeyEl.addEventListener("input", refreshSaveState);
  modelSel.addEventListener("change", refreshSaveState);

  function resetModelDropdown() {
    modelSel.disabled = true;
    modelSel.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.disabled = true;
    opt.selected = true;
    opt.textContent = "Test connection first to load models…";
    modelSel.appendChild(opt);
    hide(modelCount);
    modelCount.textContent = "";
  }

  function populateModelDropdown(models, preferred) {
    modelSel.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.disabled = true;
    placeholder.textContent = "Select a default model…";
    modelSel.appendChild(placeholder);

    let matched = false;
    for (const id of models) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      if (preferred && id === preferred) {
        opt.selected = true;
        matched = true;
      }
      modelSel.appendChild(opt);
    }
    if (!matched) {
      placeholder.selected = true;
    }
    modelSel.disabled = false;
    modelCount.textContent = `${models.length} model${models.length === 1 ? "" : "s"}`;
    show(modelCount);
  }

  /* ----------------------------------------------------------------------
   * Test connection
   * ---------------------------------------------------------------------- */
  async function testConnection() {
    const baseUrl = baseUrlEl.value.trim();
    const apiKey  = apiKeyEl.value.trim();

    if (!isValidBaseUrl(baseUrl)) {
      setStatus("fail", "Base URL must be a valid http(s) URL.");
      baseUrlEl.focus();
      return;
    }
    if (!apiKey && !hasSavedKey) {
      setStatus("fail", "API key is required.");
      apiKeyEl.focus();
      return;
    }

    setBusy(testBtn, true);
    setStatus("info", "Connecting…");

    let resp;
    try {
      resp = await fetch("/api/llm/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
      });
    } catch (err) {
      setBusy(testBtn, false);
      setStatus("fail", `Network error: ${err.message || err}`);
      return;
    }

    let data;
    try {
      data = await resp.json();
    } catch {
      setBusy(testBtn, false);
      setStatus("fail", `Unexpected response (${resp.status}).`);
      return;
    }

    setBusy(testBtn, false);

    if (!data.ok) {
      setStatus("fail", data.error || "Connection failed.");
      resetModelDropdown();
      refreshSaveState();
      return;
    }

    const models = Array.isArray(data.models) ? data.models : [];
    if (models.length === 0) {
      setStatus("fail", "Connected but the provider returned no models.");
      resetModelDropdown();
      refreshSaveState();
      return;
    }

    populateModelDropdown(models, savedModel);
    setStatus("ok", `Connected. Detected ${models.length} model${models.length === 1 ? "" : "s"}.`);
    refreshSaveState();
  }

  testBtn.addEventListener("click", testConnection);

  /* ----------------------------------------------------------------------
   * Save
   * ---------------------------------------------------------------------- */
  async function saveSettings(ev) {
    ev.preventDefault();

    const baseUrl = baseUrlEl.value.trim();
    const apiKey  = apiKeyEl.value.trim();
    const model   = modelSel.value;

    if (!isValidBaseUrl(baseUrl)) {
      setStatus("fail", "Base URL must be a valid http(s) URL.");
      baseUrlEl.focus();
      return;
    }
    if (!model) {
      setStatus("fail", "Pick a model from the dropdown.");
      modelSel.focus();
      return;
    }
    if (!apiKey && !hasSavedKey) {
      setStatus("fail", "API key is required.");
      apiKeyEl.focus();
      return;
    }

    setBusy(saveBtn, true);
    setStatus("info", "Validating and saving…");

    let resp;
    try {
      resp = await fetch("/api/llm/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: baseUrl,
          api_key: apiKey,
          model: model,
        }),
      });
    } catch (err) {
      setBusy(saveBtn, false);
      setStatus("fail", `Network error: ${err.message || err}`);
      return;
    }

    let data;
    try {
      data = await resp.json();
    } catch {
      setBusy(saveBtn, false);
      setStatus("fail", `Unexpected response (${resp.status}).`);
      return;
    }

    setBusy(saveBtn, false);

    if (!resp.ok) {
      const msg = (data && (data.detail || data.error)) || `Save failed (${resp.status}).`;
      setStatus("fail", msg);
      return;
    }

    setStatus("ok", "Settings saved.");
    toast("Settings saved");

    // Refresh saved-state markers so subsequent tests don't ask for the key.
    if (data.config) {
      form.dataset.savedBase  = data.config.base_url || "";
      form.dataset.savedModel = data.config.model || "";
      if (data.config.has_api_key) {
        form.dataset.hasKey = "true";
        // Clear the input so the masked placeholder reappears on next focus.
        apiKeyEl.value = "";
        if (data.config.api_key_preview) {
          apiKeyEl.placeholder = `${data.config.api_key_preview} — leave blank to keep`;
        }
      }
    }
  }

  form.addEventListener("submit", saveSettings);

  /* ----------------------------------------------------------------------
   * Initial state
   * ---------------------------------------------------------------------- */
  if (hasSavedKey && baseUrlEl.value && savedModel) {
    // We have a previously-saved config — surface a soft hint and prime
    // the dropdown to "saved" so the user can immediately re-save with a
    // tweaked field without re-testing.
    setStatus("info", "Click ‘Test connection’ to refresh the model list.");
  }

  refreshSaveState();
})();
