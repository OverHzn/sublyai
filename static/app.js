(() => {
  "use strict";

  const form = document.getElementById("job-form");
  const urlInput = document.getElementById("url");
  const urlCheck = document.getElementById("url-check");
  const qualitySel = document.getElementById("quality");
  const burnInput = document.getElementById("burn_video");
  const submitBtn = document.getElementById("generate-btn");

  const statusCard = document.getElementById("status-card");
  const statusIcon = document.getElementById("status-icon");
  const iconQueued = document.getElementById("icon-queued");
  const iconProcessing = document.getElementById("icon-processing");
  const iconDone = document.getElementById("icon-done");
  const iconFailed = document.getElementById("icon-failed");
  const statusTitleLead = document.getElementById("status-title-lead");
  const statusTitleRest = document.getElementById("status-title-rest");
  const statusPct = document.getElementById("status-pct");
  const statusMsg = document.getElementById("status-msg");
  const progressBar = document.getElementById("progress-bar");
  const errorBox = document.getElementById("error-box");

  const downloads = document.getElementById("downloads");
  const dlSrt = document.getElementById("dl-srt");
  const dlTxt = document.getElementById("dl-txt");
  const dlOriginal = document.getElementById("dl-original");
  const dlOriginalLabel = document.getElementById("dl-original-label");
  const dlOriginalSub = document.getElementById("dl-original-sub");
  const dlVideo = document.getElementById("dl-video");

  /* Dark/light theme toggle (persists to localStorage). */
  const themeToggle = document.getElementById("theme-toggle");
  const iconMoon = document.getElementById("icon-moon");
  const iconSun = document.getElementById("icon-sun");
  const themeLabel = document.getElementById("theme-label");

  const STATUS_TITLE = {
    queued:     { lead: "Queued.",     rest: "Waiting to start…",                 cls: "ok" },
    processing: { lead: "Working on it.", rest: "AI is generating your subtitles…", cls: "ok" },
    done:       { lead: "Done!",       rest: "Your files are ready.",             cls: "ok" },
    failed:     { lead: "Failed.",     rest: "Something went wrong.",             cls: "fail" },
  };

  function show(el) { if (el) el.classList.remove("hidden"); }
  function hide(el) { if (el) el.classList.add("hidden"); }

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

  const savedTheme = localStorage.getItem("sublyai-theme") || "dark";
  applyTheme(savedTheme);
  themeToggle.addEventListener("click", () => {
    const next = document.body.classList.contains("theme-light") ? "dark" : "light";
    localStorage.setItem("sublyai-theme", next);
    applyTheme(next);
  });

  /* URL input — show green check when input parses as a valid URL. */
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

  /* Status icon swap */
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
    hide(errorBox);
    errorBox.textContent = "";
    hide(downloads);
    [dlSrt, dlTxt, dlOriginal, dlVideo].forEach(hide);
  }

  function applyJob(job) {
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

    if (files.srt) { dlSrt.href = files.srt; show(dlSrt); show(downloads); } else { hide(dlSrt); }
    if (files.txt) { dlTxt.href = files.txt; show(dlTxt); show(downloads); } else { hide(dlTxt); }

    if (files.original) {
      dlOriginal.href = files.original;
      if (isAudioOnly) {
        dlOriginalLabel.textContent = "Download Audio";
        dlOriginalSub.textContent = "Original (.m4a / .mp3)";
      } else {
        dlOriginalLabel.textContent = "Download Original";
        dlOriginalSub.textContent = "Full quality (.mp4)";
      }
      show(dlOriginal); show(downloads);
    } else { hide(dlOriginal); }

    if (files.video) { dlVideo.href = files.video; show(dlVideo); show(downloads); } else { hide(dlVideo); }
  }

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

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const url = (urlInput.value || "").trim();
    if (!url) { urlInput.focus(); return; }
    submitBtn.disabled = true;
    submitBtn.classList.add("is-loading");
    resetStatusUI();
    statusCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

    const fd = new FormData();
    fd.append("url", url);
    fd.append("quality", qualitySel.value);
    if (burnInput.checked) fd.append("burn_video", "true");

    try {
      const res = await fetch("/api/jobs", { method: "POST", body: fd });
      if (!res.ok) {
        let detail = `Server returned ${res.status}.`;
        try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch (_) {}
        throw new Error(detail);
      }
      const data = await res.json();
      if (!data.job_id) throw new Error("Server did not return a job_id.");
      startPolling(data.job_id);
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
})();
