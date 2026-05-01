(() => {
  "use strict";

  /* ----------------------------------------------------------------------
   * DOM lookup
   * ---------------------------------------------------------------------- */
  const $ = (id) => document.getElementById(id);

  const form          = $("job-form");
  const urlInput      = $("url");
  const urlCheck      = $("url-check");
  const qualitySel    = $("quality");
  const burnInput     = $("burn_video");
  const submitBtn     = $("generate-btn");

  const tabUrl        = $("tab-url");
  const tabBatch      = $("tab-batch");
  const tabFile       = $("tab-file");
  const paneUrl       = $("pane-url");
  const paneBatch     = $("pane-batch");
  const paneFile      = $("pane-file");
  const batchUrls     = $("batch-urls");
  const batchProgress = $("batch-progress");
  const dropzone      = $("dropzone");
  const fileInput     = $("file-input");
  const fileChip      = $("file-chip");

  const langSel       = $("target_lang");
  const modelSel      = $("whisper_model");
  const styleFontName = $("style_font_name");
  const styleFontSize = $("style_font_size");
  const styleAlign    = $("style_alignment");
  const styleColor    = $("style_font_color");
  const styleOutColor = $("style_outline_color");
  const styleOutline  = $("style_outline");

  const statusCard    = $("status-card");
  const statusIcon    = $("status-icon");
  const iconQueued    = $("icon-queued");
  const iconProcessing= $("icon-processing");
  const iconDone      = $("icon-done");
  const iconFailed    = $("icon-failed");
  const statusTitleLead = $("status-title-lead");
  const statusTitleRest = $("status-title-rest");
  const statusPct     = $("status-pct");
  const statusMsg     = $("status-msg");
  const progressBar   = $("progress-bar");
  const errorBox      = $("error-box");

  const downloads     = $("downloads");
  const dlSrt         = $("dl-srt");
  const dlVtt         = $("dl-vtt");
  const dlAss         = $("dl-ass");
  const dlTxt         = $("dl-txt");
  const dlOriginal    = $("dl-original");
  const dlOriginalLabel = $("dl-original-label");
  const dlOriginalSub = $("dl-original-sub");
  const dlVideo       = $("dl-video");
  const resultActions = $("result-actions");
  const btnEdit       = $("btn-edit");
  const btnCopyTxt    = $("btn-copy-txt");

  const themeToggle   = $("theme-toggle");
  const iconMoon      = $("icon-moon");
  const iconSun       = $("icon-sun");
  const themeLabel    = $("theme-label");

  const historyToggle = $("history-toggle");
  const historyDrawer = $("history-drawer");
  const historyClose  = $("history-close");
  const historyList   = $("history-list");
  const historyEmpty  = $("history-empty");
  const historyClear  = $("history-clear");

  const editorModal   = $("editor-modal");
  const editorBody    = $("editor-body");
  const editorClose   = $("editor-close");
  const editorCancel  = $("editor-cancel");
  const editorSave    = $("editor-save");
  const editorRerender= $("editor-rerender");

  /* ----------------------------------------------------------------------
   * Helpers
   * ---------------------------------------------------------------------- */
  const STATUS_TITLE = {
    queued:     { lead: "Queued.",       rest: "Waiting to start…",                cls: "ok" },
    processing: { lead: "Working on it.",rest: "AI is generating your subtitles…", cls: "ok" },
    done:       { lead: "Done!",         rest: "Your files are ready.",            cls: "ok" },
    failed:     { lead: "Failed.",       rest: "Something went wrong.",            cls: "fail" },
  };

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

  /* ----------------------------------------------------------------------
   * Theme
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
  applyTheme(localStorage.getItem("sublyai-theme") || "dark");
  themeToggle.addEventListener("click", () => {
    const next = document.body.classList.contains("theme-light") ? "dark" : "light";
    localStorage.setItem("sublyai-theme", next);
    applyTheme(next);
  });

  /* ----------------------------------------------------------------------
   * Mode tabs (URL / Batch / Upload)
   * ---------------------------------------------------------------------- */
  let mode = "url"; // "url" | "batch" | "upload"
  function setMode(next) {
    mode = next;
    [tabUrl, tabBatch, tabFile].forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    [paneUrl, paneBatch, paneFile].forEach(hide);
    if (next === "url")    { tabUrl.classList.add("active");   tabUrl.setAttribute("aria-selected", "true");   show(paneUrl); }
    if (next === "batch")  { tabBatch.classList.add("active"); tabBatch.setAttribute("aria-selected", "true"); show(paneBatch); }
    if (next === "upload") { tabFile.classList.add("active");  tabFile.setAttribute("aria-selected", "true");  show(paneFile); }
  }
  tabUrl.addEventListener("click",   () => setMode("url"));
  tabBatch.addEventListener("click", () => setMode("batch"));
  tabFile.addEventListener("click",  () => setMode("upload"));

  /* ----------------------------------------------------------------------
   * URL validation icon
   * ---------------------------------------------------------------------- */
  function refreshUrlCheck() {
    const v = (urlInput.value || "").trim();
    let ok = false;
    if (v) {
      try {
        const u = new URL(v);
        ok = u.protocol === "http:" || u.protocol === "https:";
      } catch (_) { ok = false; }
    }
    urlCheck.classList.toggle("is-valid", ok);
  }
  urlInput.addEventListener("input", refreshUrlCheck);
  urlInput.addEventListener("change", refreshUrlCheck);
  refreshUrlCheck();

  /* ----------------------------------------------------------------------
   * File drag & drop
   * ---------------------------------------------------------------------- */
  function setSelectedFile(file) {
    if (!file) { hide(fileChip); fileChip.textContent = ""; fileInput.value = ""; return; }
    fileChip.textContent = `${file.name} · ${(file.size / (1024 * 1024)).toFixed(1)} MB`;
    show(fileChip);
  }

  fileInput.addEventListener("change", () => {
    const f = fileInput.files && fileInput.files[0];
    setSelectedFile(f || null);
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropzone.classList.remove("is-dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (!dt || !dt.files || dt.files.length === 0) return;
    const f = dt.files[0];
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(f);
    fileInput.files = dataTransfer.files;
    setSelectedFile(f);
  });

  /* ----------------------------------------------------------------------
   * Status card
   * ---------------------------------------------------------------------- */
  function setStatus(status) {
    const s = STATUS_TITLE[status] || STATUS_TITLE.queued;
    statusTitleLead.textContent = s.lead;
    statusTitleRest.textContent = s.rest;
    statusTitleRest.classList.remove("ok", "fail");
    statusTitleRest.classList.add(s.cls);

    statusIcon.classList.remove("queued", "processing", "done", "failed");
    statusIcon.classList.add(status);
    [iconQueued, iconProcessing, iconDone, iconFailed].forEach(hide);
    if (status === "queued") show(iconQueued);
    else if (status === "processing") show(iconProcessing);
    else if (status === "done") show(iconDone);
    else if (status === "failed") show(iconFailed);
  }

  function resetStatusUI() {
    show(statusCard);
    setStatus("queued");
    statusPct.textContent = "0%";
    progressBar.style.width = "0%";
    statusMsg.textContent = "Submitting your job…";
    hide(errorBox); errorBox.textContent = "";
    hide(downloads);
    [dlSrt, dlVtt, dlAss, dlTxt, dlOriginal, dlVideo].forEach(hide);
    hide(resultActions);
  }

  let currentJobId = null;
  let currentJob = null;

  function applyJob(job) {
    currentJob = job;
    setStatus(job.status || "queued");
    const pct = Math.max(0, Math.min(100, Number(job.progress) || 0));
    statusPct.textContent = pct + "%";
    progressBar.style.width = pct + "%";

    if (job.status === "done") {
      statusMsg.textContent = "All files have been processed successfully.";
    } else if (job.status === "failed") {
      statusMsg.textContent = job.message || "The job failed.";
    } else {
      statusMsg.textContent = job.message || "";
    }

    if (job.status === "failed") {
      errorBox.textContent = job.error || "The job failed.";
      show(errorBox);
    } else {
      hide(errorBox);
    }

    const files = job.files || {};
    const isAudioOnly = job.quality === "audio" && !job.burn_video;
    const hasUpload = job.source_kind === "upload";

    if (files.srt) { dlSrt.href = files.srt; show(dlSrt); show(downloads); } else { hide(dlSrt); }
    if (files.vtt) { dlVtt.href = files.vtt; show(dlVtt); show(downloads); } else { hide(dlVtt); }
    if (files.ass) { dlAss.href = files.ass; show(dlAss); show(downloads); } else { hide(dlAss); }
    if (files.txt) { dlTxt.href = files.txt; show(dlTxt); show(downloads); } else { hide(dlTxt); }

    if (files.original) {
      dlOriginal.href = files.original;
      if (hasUpload) {
        dlOriginalLabel.textContent = "Original";
        dlOriginalSub.textContent = job.source_name || "Uploaded file";
      } else if (isAudioOnly) {
        dlOriginalLabel.textContent = "Audio";
        dlOriginalSub.textContent = "Original (.m4a / .mp3)";
      } else {
        dlOriginalLabel.textContent = "Original";
        dlOriginalSub.textContent = "Full quality";
      }
      show(dlOriginal); show(downloads);
    } else { hide(dlOriginal); }

    if (files.video) { dlVideo.href = files.video; show(dlVideo); show(downloads); } else { hide(dlVideo); }

    if (job.status === "done" && (files.srt || files.txt)) {
      show(resultActions);
    } else {
      hide(resultActions);
    }

    historyUpsert(job);
  }

  /* ----------------------------------------------------------------------
   * Polling
   * ---------------------------------------------------------------------- */
  let pollTimer = null;
  async function pollOnce(jobId) {
    const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Status request failed (${res.status}).`);
    return res.json();
  }
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }
  function startPolling(jobId) {
    stopPolling();
    currentJobId = jobId;
    const tick = async () => {
      try {
        const job = await pollOnce(jobId);
        applyJob(job);
        if (job.status === "done" || job.status === "failed") {
          stopPolling();
          submitBtn.disabled = false;
          submitBtn.classList.remove("is-loading");
        }
      } catch (e) {
        console.error(e);
        statusMsg.textContent = "Lost connection to the server. Retrying…";
      }
    };
    tick();
    pollTimer = setInterval(tick, 2500);
  }

  /* ----------------------------------------------------------------------
   * Build common form payload
   * ---------------------------------------------------------------------- */
  function styleObject() {
    return {
      font_name:     styleFontName.value,
      font_size:     parseInt(styleFontSize.value, 10) || 22,
      alignment:     styleAlign.value,
      font_color:    styleColor.value,
      outline_color: styleOutColor.value,
      outline:       parseInt(styleOutline.value, 10) || 2,
    };
  }

  function buildBaseFormData() {
    const fd = new FormData();
    fd.append("quality", qualitySel.value);
    if (burnInput.checked) fd.append("burn_video", "true");
    fd.append("target_lang", langSel.value);
    fd.append("whisper_model", modelSel.value);
    fd.append("style", JSON.stringify(styleObject()));
    return fd;
  }

  async function submitJob(fd) {
    const res = await fetch("/api/jobs", { method: "POST", body: fd });
    if (!res.ok) {
      let detail = `Server returned ${res.status}.`;
      try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch (_) {}
      throw new Error(detail);
    }
    const data = await res.json();
    if (!data.job_id) throw new Error("Server did not return a job_id.");
    return data.job_id;
  }

  async function waitForJob(jobId) {
    while (true) {
      const job = await pollOnce(jobId);
      applyJob(job);
      if (job.status === "done" || job.status === "failed") return job;
      await new Promise((r) => setTimeout(r, 2500));
    }
  }

  /* ----------------------------------------------------------------------
   * Submit handler
   * ---------------------------------------------------------------------- */
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    submitBtn.disabled = true;
    submitBtn.classList.add("is-loading");
    resetStatusUI();
    statusCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    hide(batchProgress);

    try {
      if (mode === "upload") {
        const f = fileInput.files && fileInput.files[0];
        if (!f) throw new Error("Select a file first.");
        const fd = buildBaseFormData();
        fd.append("file", f);
        const jobId = await submitJob(fd);
        startPolling(jobId);
        return;
      }

      if (mode === "batch") {
        const lines = (batchUrls.value || "")
          .split(/\n+/)
          .map((s) => s.trim())
          .filter(Boolean);
        if (lines.length === 0) throw new Error("Add at least one URL.");
        show(batchProgress);
        for (let i = 0; i < lines.length; i++) {
          const u = lines[i];
          batchProgress.textContent = `Processing ${i + 1} / ${lines.length}: ${u}`;
          const fd = buildBaseFormData();
          fd.append("url", u);
          try {
            const jobId = await submitJob(fd);
            currentJobId = jobId;
            await waitForJob(jobId);
          } catch (err) {
            batchProgress.textContent = `Failed on URL ${i + 1}: ${err.message || err}`;
          }
        }
        batchProgress.textContent = `Batch complete — ${lines.length} URL(s) processed.`;
        submitBtn.disabled = false;
        submitBtn.classList.remove("is-loading");
        return;
      }

      // URL mode
      const url = (urlInput.value || "").trim();
      if (!url) { urlInput.focus(); throw new Error("Paste a URL first."); }
      const fd = buildBaseFormData();
      fd.append("url", url);
      const jobId = await submitJob(fd);
      startPolling(jobId);
    } catch (e) {
      console.error(e);
      setStatus("failed");
      statusMsg.textContent = "Failed to start the job.";
      errorBox.textContent = String(e.message || e);
      show(errorBox);
      submitBtn.disabled = false;
      submitBtn.classList.remove("is-loading");
    }
  });

  /* ----------------------------------------------------------------------
   * Copy transcript
   * ---------------------------------------------------------------------- */
  btnCopyTxt.addEventListener("click", async () => {
    if (!currentJob || !currentJob.files || !currentJob.files.txt) return;
    try {
      const res = await fetch(currentJob.files.txt, { cache: "no-store" });
      const text = await res.text();
      await navigator.clipboard.writeText(text);
      toast("Transcript copied to clipboard.");
    } catch (e) {
      console.error(e);
      toast("Copy failed.");
    }
  });

  /* ----------------------------------------------------------------------
   * Subtitle editor
   * ---------------------------------------------------------------------- */
  let editorSegments = [];

  function tsHHMMSS(t) {
    t = Math.max(0, Number(t) || 0);
    const h = Math.floor(t / 3600);
    const m = Math.floor((t % 3600) / 60);
    const s = Math.floor(t % 60);
    const cs = Math.floor((t - Math.floor(t)) * 100);
    return `${h ? h + ":" : ""}${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
  }

  function renderEditor() {
    editorBody.innerHTML = "";
    editorBody.removeAttribute("aria-busy");
    if (!editorSegments.length) {
      editorBody.textContent = "No segments to edit.";
      return;
    }
    const frag = document.createDocumentFragment();
    editorSegments.forEach((seg, i) => {
      const row = document.createElement("div");
      row.className = "editor-row";
      row.innerHTML = `
        <div class="ts">${tsHHMMSS(seg.start)} →<br/>${tsHHMMSS(seg.end)}</div>
        <textarea data-i="${i}" rows="2"></textarea>
      `;
      const ta = row.querySelector("textarea");
      ta.value = seg.text || "";
      ta.addEventListener("input", () => {
        editorSegments[i].text = ta.value;
      });
      frag.appendChild(row);
    });
    editorBody.appendChild(frag);
  }

  async function openEditor() {
    if (!currentJobId) return;
    show(editorModal);
    editorBody.setAttribute("aria-busy", "true");
    editorBody.textContent = "Loading…";
    try {
      const res = await fetch(`/api/jobs/${currentJobId}/segments`, { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to load segments.");
      const data = await res.json();
      editorSegments = (data.segments || []).map((s) => ({
        start: Number(s.start) || 0,
        end: Number(s.end) || 0,
        text: String(s.text || ""),
      }));
      editorRerender.checked = false;
      renderEditor();
    } catch (e) {
      editorBody.textContent = `Error: ${e.message || e}`;
    }
  }
  function closeEditor() { hide(editorModal); }

  btnEdit.addEventListener("click", openEditor);
  editorClose.addEventListener("click", closeEditor);
  editorCancel.addEventListener("click", closeEditor);
  editorModal.addEventListener("click", (e) => {
    if (e.target === editorModal) closeEditor();
  });

  editorSave.addEventListener("click", async () => {
    if (!currentJobId) return;
    editorSave.disabled = true;
    try {
      const res = await fetch(`/api/jobs/${currentJobId}/segments`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segments: editorSegments,
          rerender_video: !!editorRerender.checked,
        }),
      });
      if (!res.ok) {
        let detail = `Save failed (${res.status}).`;
        try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch (_) {}
        throw new Error(detail);
      }
      toast("Subtitles saved.");
      closeEditor();
      // Refresh the job status to update the download links + maybe video.
      const job = await pollOnce(currentJobId);
      applyJob(job);
    } catch (e) {
      toast(`Error: ${e.message || e}`);
    } finally {
      editorSave.disabled = false;
    }
  });

  /* ----------------------------------------------------------------------
   * History sidebar (localStorage)
   * ---------------------------------------------------------------------- */
  const HISTORY_KEY = "sublyai-history-v1";
  const HISTORY_MAX = 10;

  function historyLoad() {
    try {
      const raw = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(raw) ? raw : [];
    } catch (_) { return []; }
  }
  function historySave(items) {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_MAX)));
  }
  function historyUpsert(job) {
    if (!job || !job.job_id) return;
    const items = historyLoad();
    const ix = items.findIndex((it) => it.job_id === job.job_id);
    const entry = {
      job_id: job.job_id,
      url: job.url || "",
      source_kind: job.source_kind || "url",
      source_name: job.source_name || null,
      target_lang: job.target_lang || "id",
      status: job.status || "queued",
      created_at: ix >= 0 ? items[ix].created_at : Date.now(),
      updated_at: Date.now(),
    };
    if (ix >= 0) items.splice(ix, 1);
    items.unshift(entry);
    historySave(items);
    historyRender();
  }
  function historyRender() {
    const items = historyLoad();
    historyList.innerHTML = "";
    if (!items.length) {
      show(historyEmpty);
      return;
    }
    hide(historyEmpty);
    const frag = document.createDocumentFragment();
    for (const it of items) {
      const li = document.createElement("li");
      const title = it.source_kind === "upload"
        ? (it.source_name || "Uploaded file")
        : (it.url || "(no URL)");
      const date = new Date(it.updated_at || it.created_at);
      li.innerHTML = `
        <div class="h-title"></div>
        <div class="h-meta">
          <span class="h-status ${it.status}">${it.status}</span>
          <span>${date.toLocaleString()}</span>
          <span>${(it.target_lang || "id").toUpperCase()}</span>
        </div>
      `;
      li.querySelector(".h-title").textContent = title;
      li.addEventListener("click", () => {
        historyDrawer.classList.add("hidden");
        startPolling(it.job_id);
        statusCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
      frag.appendChild(li);
    }
    historyList.appendChild(frag);
  }
  historyToggle.addEventListener("click", () => {
    historyRender();
    historyDrawer.classList.toggle("hidden");
  });
  historyClose.addEventListener("click", () => historyDrawer.classList.add("hidden"));
  historyClear.addEventListener("click", () => {
    if (!confirm("Clear job history?")) return;
    historySave([]);
    historyRender();
  });
  historyRender();

  /* ----------------------------------------------------------------------
   * Service worker
   * ---------------------------------------------------------------------- */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/static/service-worker.js").catch(() => {});
    });
  }
})();
