(() => {
  "use strict";

  const form = document.getElementById("job-form");
  const urlInput = document.getElementById("url");
  const qualitySel = document.getElementById("quality");
  const burnInput = document.getElementById("burn_video");
  const submitBtn = document.getElementById("generate-btn");

  const statusCard = document.getElementById("status-card");
  const statusPill = document.getElementById("status-pill");
  const statusPct = document.getElementById("status-pct");
  const statusMsg = document.getElementById("status-msg");
  const progressBar = document.getElementById("progress-bar");
  const errorBox = document.getElementById("error-box");

  const downloads = document.getElementById("downloads");
  const dlSrt = document.getElementById("dl-srt");
  const dlTxt = document.getElementById("dl-txt");
  const dlOriginal = document.getElementById("dl-original");
  const dlOriginalLabel = document.getElementById("dl-original-label");
  const dlVideo = document.getElementById("dl-video");

  let pollTimer = null;

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function setPill(status) {
    statusPill.textContent = status;
    statusPill.classList.remove("queued", "processing", "done", "failed");
    statusPill.classList.add(status);
  }

  function resetStatusUI() {
    show(statusCard);
    setPill("queued");
    statusPct.textContent = "0%";
    progressBar.style.width = "0%";
    statusMsg.textContent = "Submitting your job…";
    hide(errorBox);
    errorBox.textContent = "";
    hide(downloads);
    [dlSrt, dlTxt, dlOriginal, dlVideo].forEach((b) => hide(b));
  }

  function applyJob(job) {
    setPill(job.status || "queued");
    const pct = Math.max(0, Math.min(100, Number(job.progress) || 0));
    statusPct.textContent = pct + "%";
    progressBar.style.width = pct + "%";
    statusMsg.textContent = job.message || "";

    if (job.status === "failed") {
      errorBox.textContent = job.error || "The job failed.";
      show(errorBox);
    } else {
      hide(errorBox);
    }

    const files = job.files || {};

    if (files.srt) { dlSrt.href = files.srt; show(dlSrt); show(downloads); } else { hide(dlSrt); }
    if (files.txt) { dlTxt.href = files.txt; show(dlTxt); show(downloads); } else { hide(dlTxt); }
    if (files.original) {
      dlOriginal.href = files.original;
      dlOriginalLabel.textContent = (job.quality === "audio" && !job.burn_video)
        ? "Download Original Audio"
        : "Download Original Video";
      show(dlOriginal); show(downloads);
    } else { hide(dlOriginal); }
    if (files.video) { dlVideo.href = files.video; show(dlVideo); show(downloads); } else { hide(dlVideo); }
  }

  async function pollOnce(jobId) {
    const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`Status request failed (${res.status}).`);
    }
    return res.json();
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
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
    if (!url) {
      urlInput.focus();
      return;
    }
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
        try {
          const j = await res.json();
          if (j && j.detail) detail = j.detail;
        } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const data = await res.json();
      if (!data.job_id) throw new Error("Server did not return a job_id.");
      startPolling(data.job_id);
    } catch (e) {
      console.error(e);
      setPill("failed");
      statusMsg.textContent = "Failed to start the job.";
      errorBox.textContent = String(e.message || e);
      show(errorBox);
      submitBtn.disabled = false;
      submitBtn.classList.remove("is-loading");
    }
  });
})();
