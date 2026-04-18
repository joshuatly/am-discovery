/* =========================================================
   AM Discovery — Settings page
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// Page: Settings
// ---------------------------------------------------------------------------
async function renderSettings(main) {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("⚙️ Settings", "Configure application options"));
  main.appendChild(wrap);

  let cfg;
  try {
    cfg = await API.get("/api/system/config");
  } catch {
    wrap.innerHTML += `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load config</div></div>`;
    return;
  }

  const form = el("div", "settings-form");
  form.style.maxWidth = "600px";
  form.style.display = "flex";
  form.style.flexDirection = "column";
  form.style.gap = "20px";

  // Check Storefronts
  const sfsGroup = el("div");
  sfsGroup.style.display = "flex";
  sfsGroup.style.flexDirection = "column";
  sfsGroup.style.gap = "8px";
  const sfsLabel = el("label", "", "Check Storefronts (comma separated)");
  sfsLabel.style.fontWeight = "600";
  sfsGroup.appendChild(sfsLabel);
  const sfsInput = el("input", "search-input");
  sfsInput.type = "text";
  sfsInput.value = (cfg.check_storefronts || ["jp", "my", "us", "hk", "tw", "sg"]).join(", ");
  sfsGroup.appendChild(sfsInput);
  form.appendChild(sfsGroup);

  // Home Storefront
  const homeGroup = el("div");
  homeGroup.style.display = "flex";
  homeGroup.style.flexDirection = "column";
  homeGroup.style.gap = "8px";
  const homeLabel = el("label", "", "Home Storefront");
  homeLabel.style.fontWeight = "600";
  const homeDesc = el("p", "", "The storefront your Apple Music account is in. Used as the baseline for tracklist comparisons.");
  homeDesc.style.fontSize = "12px";
  homeDesc.style.color = "var(--text-dim)";
  homeDesc.style.margin = "0";
  homeGroup.appendChild(homeLabel);
  homeGroup.appendChild(homeDesc);
  const homeInput = el("input", "search-input");
  homeInput.type = "text";
  homeInput.value = cfg.home_storefront || "my";
  homeInput.placeholder = "e.g. my";
  homeInput.style.maxWidth = "120px";
  homeGroup.appendChild(homeInput);
  form.appendChild(homeGroup);

  // Poll Interval
  const pollGroup = el("div");
  pollGroup.style.display = "flex";
  pollGroup.style.flexDirection = "column";
  pollGroup.style.gap = "8px";
  const pollLabel = el("label", "", "New Release Poll Interval (days)");
  pollLabel.style.fontWeight = "600";
  pollGroup.appendChild(pollLabel);
  const pollInput = el("input", "search-input");
  pollInput.type = "number";
  pollInput.min = "1";
  pollInput.value = cfg.newrelease_poll_interval_days || 1;
  pollInput.style.maxWidth = "120px";
  pollGroup.appendChild(pollInput);
  form.appendChild(pollGroup);

  // Watchlist Poll Interval
  const wlPollGroup = el("div");
  wlPollGroup.style.display = "flex";
  wlPollGroup.style.flexDirection = "column";
  wlPollGroup.style.gap = "8px";
  const wlPollLabel = el("label", "", "Watchlist Poll Interval (minutes)");
  wlPollLabel.style.fontWeight = "600";
  const wlPollDesc = el("p", "", "How often to check watched artists for new releases.");
  wlPollDesc.style.fontSize = "12px";
  wlPollDesc.style.color = "var(--text-dim)";
  wlPollDesc.style.margin = "0";
  wlPollGroup.appendChild(wlPollLabel);
  wlPollGroup.appendChild(wlPollDesc);
  const wlPollInput = el("input", "search-input");
  wlPollInput.type = "number";
  wlPollInput.min = "1";
  wlPollInput.value = cfg.watchlist_poll_interval_minutes || 10;
  wlPollInput.style.maxWidth = "120px";
  wlPollGroup.appendChild(wlPollInput);
  form.appendChild(wlPollGroup);

  // Watchlist Poll Batch Size
  const wlBatchGroup = el("div");
  wlBatchGroup.style.display = "flex";
  wlBatchGroup.style.flexDirection = "column";
  wlBatchGroup.style.gap = "8px";
  const wlBatchLabel = el("label", "", "Watchlist Poll Batch Size");
  wlBatchLabel.style.fontWeight = "600";
  const wlBatchDesc = el("p", "", "Number of watched artists to refresh per poll cycle.");
  wlBatchDesc.style.fontSize = "12px";
  wlBatchDesc.style.color = "var(--text-dim)";
  wlBatchDesc.style.margin = "0";
  wlBatchGroup.appendChild(wlBatchLabel);
  wlBatchGroup.appendChild(wlBatchDesc);
  const wlBatchInput = el("input", "search-input");
  wlBatchInput.type = "number";
  wlBatchInput.min = "1";
  wlBatchInput.value = cfg.watchlist_poll_batch_size || 5;
  wlBatchInput.style.maxWidth = "120px";
  wlBatchGroup.appendChild(wlBatchInput);
  form.appendChild(wlBatchGroup);

  // Watchlist Refresh Interval
  const wlRefreshGroup = el("div");
  wlRefreshGroup.style.display = "flex";
  wlRefreshGroup.style.flexDirection = "column";
  wlRefreshGroup.style.gap = "8px";
  const wlRefreshLabel = el("label", "", "Watchlist Artist Refresh Interval (days)");
  wlRefreshLabel.style.fontWeight = "600";
  const wlRefreshDesc = el("p", "", "Days before a watched artist's catalog is considered stale and re-fetched.");
  wlRefreshDesc.style.fontSize = "12px";
  wlRefreshDesc.style.color = "var(--text-dim)";
  wlRefreshDesc.style.margin = "0";
  wlRefreshGroup.appendChild(wlRefreshLabel);
  wlRefreshGroup.appendChild(wlRefreshDesc);
  const wlRefreshInput = el("input", "search-input");
  wlRefreshInput.type = "number";
  wlRefreshInput.min = "1";
  wlRefreshInput.value = cfg.watchlist_refresh_interval_days || 7;
  wlRefreshInput.style.maxWidth = "120px";
  wlRefreshGroup.appendChild(wlRefreshInput);
  form.appendChild(wlRefreshGroup);

  // CORS Proxy
  const proxyGroup = el("div");
  proxyGroup.style.display = "flex";
  proxyGroup.style.flexDirection = "column";
  proxyGroup.style.gap = "8px";
  const proxyLabel = el("label", "", "CORS Proxy");
  proxyLabel.style.fontWeight = "600";
  const proxyDesc = el("p", "", "Optional URL prefix to proxy outgoing Apple Music requests through. Leave blank to disable.");
  proxyDesc.style.fontSize = "12px";
  proxyDesc.style.color = "var(--text-dim)";
  proxyDesc.style.margin = "0";
  proxyGroup.appendChild(proxyLabel);
  proxyGroup.appendChild(proxyDesc);
  const proxyInput = el("input", "search-input");
  proxyInput.type = "text";
  proxyInput.value = cfg.cors_proxy || "";
  proxyInput.placeholder = "e.g. https://proxy.example.com/";
  proxyGroup.appendChild(proxyInput);
  form.appendChild(proxyGroup);

  // CLI Scheduler URL
  const cliUrlGroup = el("div");
  cliUrlGroup.style.display = "flex";
  cliUrlGroup.style.flexDirection = "column";
  cliUrlGroup.style.gap = "8px";
  const cliUrlLabel = el("label", "", "CLI Scheduler URL");
  cliUrlLabel.style.fontWeight = "600";
  const cliUrlDesc = el("p", "", "Base URL of your CLI Scheduler instance. Leave blank to disable.");
  cliUrlDesc.style.fontSize = "12px";
  cliUrlDesc.style.color = "var(--text-dim)";
  cliUrlDesc.style.margin = "0";
  cliUrlGroup.appendChild(cliUrlLabel);
  cliUrlGroup.appendChild(cliUrlDesc);
  const cliUrlInput = el("input", "search-input");
  cliUrlInput.type = "text";
  cliUrlInput.value = cfg.cli_scheduler_url || "";
  cliUrlInput.placeholder = "http://192.168.5.198:5000";
  cliUrlGroup.appendChild(cliUrlInput);
  form.appendChild(cliUrlGroup);

  // CLI Scheduler Preset
  const cliPresetGroup = el("div");
  cliPresetGroup.style.display = "flex";
  cliPresetGroup.style.flexDirection = "column";
  cliPresetGroup.style.gap = "8px";
  const cliPresetLabel = el("label", "", "CLI Scheduler Preset");
  cliPresetLabel.style.fontWeight = "600";
  const cliPresetDesc = el("p", "", "Preset name to use when submitting jobs to the CLI Scheduler.");
  cliPresetDesc.style.fontSize = "12px";
  cliPresetDesc.style.color = "var(--text-dim)";
  cliPresetDesc.style.margin = "0";
  cliPresetGroup.appendChild(cliPresetLabel);
  cliPresetGroup.appendChild(cliPresetDesc);
  const cliPresetInput = el("input", "search-input");
  cliPresetInput.type = "text";
  cliPresetInput.value = cfg.cli_scheduler_preset || "";
  cliPresetInput.placeholder = "e.g. amdl";
  cliPresetGroup.appendChild(cliPresetInput);
  form.appendChild(cliPresetGroup);

  const errorMsg = el("div", "");
  errorMsg.style.color = "red";
  errorMsg.style.display = "none";
  form.appendChild(errorMsg);

  const saveBtn = el("button", "btn-primary", "Save Config");
  saveBtn.style.alignSelf = "flex-start";
  saveBtn.addEventListener("click", async () => {
    errorMsg.style.display = "none";
    saveBtn.textContent = "Saving...";
    saveBtn.disabled = true;

    try {
      const parsedSfs = sfsInput.value.split(",").map(s => s.trim().toLowerCase()).filter(s => s);
      const parsedHome = homeInput.value.trim().toLowerCase();
      const parsedPoll = parseInt(pollInput.value, 10);
      const parsedWlPoll = parseInt(wlPollInput.value, 10);
      const parsedWlBatch = parseInt(wlBatchInput.value, 10);
      const parsedWlRefresh = parseInt(wlRefreshInput.value, 10);
      const parsedProxy = proxyInput.value.trim();
      const newCfg = {
        ...cfg,
        check_storefronts: parsedSfs,
        home_storefront: parsedHome || "my",
        newrelease_poll_interval_days: isNaN(parsedPoll) ? 1 : parsedPoll,
        watchlist_poll_interval_minutes: isNaN(parsedWlPoll) ? 10 : parsedWlPoll,
        watchlist_poll_batch_size: isNaN(parsedWlBatch) ? 5 : parsedWlBatch,
        watchlist_refresh_interval_days: isNaN(parsedWlRefresh) ? 7 : parsedWlRefresh,
        cors_proxy: parsedProxy,
        cli_scheduler_url: cliUrlInput.value.trim(),
        cli_scheduler_preset: cliPresetInput.value.trim(),
      };

      await API.put("/api/system/config", newCfg);

      // Update in-memory state so widget/modal reflect new values immediately
      state.configuredStorefronts = parsedSfs;
      state.homeStorefront = newCfg.home_storefront;
      state.cliSchedulerEnabled = !!(newCfg.cli_scheduler_url);
      renderMetaSourceWidget();

      saveBtn.textContent = "Saved!";
      setTimeout(() => {
        saveBtn.textContent = "Save Config";
        saveBtn.disabled = false;
      }, 2000);
    } catch (e) {
      errorMsg.textContent = "Error saving config. Ensure JSON is valid.";
      errorMsg.style.display = "block";
      saveBtn.textContent = "Save Config";
      saveBtn.disabled = false;
    }
  });
  form.appendChild(saveBtn);
  wrap.appendChild(form);

  // Watchlist import/export
  const wlSection = el("div", "");
  wlSection.style.cssText = "max-width:600px;margin-top:32px;display:flex;flex-direction:column;gap:12px;";
  const wlTitle = el("div", "", "Watchlist");
  wlTitle.style.cssText = "font-weight:600;font-size:15px;";
  const wlDesc = el("p", "", "Export your watchlist as a JSON backup, or import a previously exported file.");
  wlDesc.style.cssText = "font-size:12px;color:var(--text-dim);margin:0;";
  const wlButtons = el("div", "");
  wlButtons.style.cssText = "display:flex;gap:8px;";

  const exportBtn = el("button", "btn-secondary", "Export Watchlist");
  exportBtn.title = "Download watchlist as JSON";
  exportBtn.addEventListener("click", () => {
    window.location.href = "/api/watchlist/export";
  });

  const importBtn = el("button", "btn-secondary", "Import Watchlist");
  importBtn.title = "Import watchlist from JSON file";
  importBtn.addEventListener("click", () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.addEventListener("change", async () => {
      if (!input.files.length) return;
      const file = input.files[0];
      const formData = new FormData();
      formData.append("file", file);
      try {
        const resp = await fetch("/api/watchlist/import", { method: "POST", body: formData });
        const result = await resp.json();
        if (!result.ok) alert(result.error || "Import failed");
      } catch {
        alert("Import failed");
      }
    });
    input.click();
  });

  wlButtons.appendChild(exportBtn);
  wlButtons.appendChild(importBtn);
  wlSection.appendChild(wlTitle);
  wlSection.appendChild(wlDesc);
  wlSection.appendChild(wlButtons);
  wrap.appendChild(wlSection);
}
