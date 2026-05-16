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

  // Timezone
  const tzGroup = el("div");
  tzGroup.style.display = "flex";
  tzGroup.style.flexDirection = "column";
  tzGroup.style.gap = "8px";
  const tzLabel = el("label", "", "Timezone");
  tzLabel.style.fontWeight = "600";
  const tzDesc = el(
    "p",
    "",
    "IANA timezone name used to format timestamps in notifications and API responses. " +
      "Examples: UTC, Asia/Hong_Kong, America/New_York, Europe/London. Defaults to UTC.",
  );
  tzDesc.style.fontSize = "12px";
  tzDesc.style.color = "var(--text-dim)";
  tzDesc.style.margin = "0";
  tzGroup.appendChild(tzLabel);
  tzGroup.appendChild(tzDesc);
  const tzInput = el("input", "search-input");
  tzInput.type = "text";
  tzInput.value = cfg.timezone || "UTC";
  tzInput.placeholder = "UTC";
  tzInput.style.maxWidth = "240px";
  tzGroup.appendChild(tzInput);
  form.appendChild(tzGroup);

  const errorMsg = el("div", "");
  errorMsg.style.color = "red";
  errorMsg.style.display = "none";
  form.appendChild(errorMsg);

  // Notification Events
  const notifGroup = el("div");
  notifGroup.style.cssText = "display:flex;flex-direction:column;gap:12px;";
  const notifLabel = el("label", "", "Notification Events");
  notifLabel.style.fontWeight = "600";
  const notifDesc = el("p", "", "Send Apprise notifications when discovery cycles complete or watched artists release new music.");
  notifDesc.style.cssText = "font-size:12px;color:var(--text-dim);margin:0;";
  notifGroup.appendChild(notifLabel);
  notifGroup.appendChild(notifDesc);
  const notifList = el("div");
  notifList.style.cssText = "display:flex;flex-direction:column;gap:8px;";
  notifGroup.appendChild(notifList);

  let eventTypesMeta = null;
  async function refreshNotifList() {
    const [listResp, typesResp] = await Promise.all([
      API.get("/api/notifications"),
      eventTypesMeta ? Promise.resolve({ types: eventTypesMeta }) : API.get("/api/notifications/event-types"),
    ]);
    eventTypesMeta = typesResp.types || eventTypesMeta;
    renderNotificationEvents(notifList, listResp.events || [], eventTypesMeta, refreshNotifList);
  }

  const addBtn = el("button", "btn-secondary", "+ Add Notification Event");
  addBtn.style.alignSelf = "flex-start";
  addBtn.addEventListener("click", () => openNotificationEventModal(null, eventTypesMeta, refreshNotifList));
  notifGroup.appendChild(addBtn);
  form.appendChild(notifGroup);
  try {
    await refreshNotifList();
  } catch {
    notifList.textContent = "Could not load notification events.";
    notifList.style.color = "var(--text-dim)";
  }

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
        timezone: tzInput.value.trim() || "UTC",
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

// ---------------------------------------------------------------------------
// Notification events — list row rendering
// ---------------------------------------------------------------------------

const NOTIF_EVENT_LABELS = {
  onDiscoveryComplete: "Discovery complete",
  onDiscoveryFailed: "Discovery failed",
  onArtistNewRelease: "Watched artist: new release",
  onArtistNewSingle: "Watched artist: new single",
  onWatchlistBatchComplete: "Watchlist batch complete",
};

function _notifTruncateUrl(url, max = 40) {
  if (!url) return "(no URL)";
  return url.length > max ? url.slice(0, max - 1) + "…" : url;
}

function renderNotificationEvents(container, events, eventTypesMeta, onChange) {
  container.innerHTML = "";
  if (!events.length) {
    const empty = el("div", "empty-state", "");
    empty.innerHTML = `<div class="empty-title">No notification events configured</div>`;
    container.appendChild(empty);
    return;
  }
  for (const ev of events) {
    const row = el("div");
    row.style.cssText =
      "display:flex;align-items:center;gap:12px;padding:10px 12px;" +
      "background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);";

    const info = el("div");
    info.style.cssText = "flex:1;display:flex;flex-direction:column;gap:2px;min-width:0;";
    const typeLabel = el("div", "", NOTIF_EVENT_LABELS[ev.event_type] || ev.event_type);
    typeLabel.style.cssText = "font-weight:600;font-size:13px;";
    const urlLabel = el("div", "", _notifTruncateUrl(ev.apprise_url));
    urlLabel.style.cssText = "font-size:11px;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;";
    info.appendChild(typeLabel);
    info.appendChild(urlLabel);
    if (ev.disabled_reason === "max_failures") {
      const badge = el("div", "", "auto-disabled");
      badge.style.cssText = "font-size:10px;color:#f85149;font-weight:600;";
      info.appendChild(badge);
    }
    row.appendChild(info);

    const enabled = el("input");
    enabled.type = "checkbox";
    enabled.checked = !!ev.enabled;
    enabled.title = "Enabled";
    enabled.addEventListener("change", async () => {
      try {
        await API.put(`/api/notifications/${ev.id}`, {
          enabled: enabled.checked,
          // Clear the auto-disable reason if the user re-enables.
          disabled_reason: enabled.checked ? null : ev.disabled_reason,
          consecutive_failures: enabled.checked ? 0 : ev.consecutive_failures,
        });
      } finally {
        onChange();
      }
    });
    row.appendChild(enabled);

    const testBtn = el("button", "btn-secondary", "Test");
    testBtn.style.cssText = "padding:4px 10px;font-size:11px;";
    testBtn.addEventListener("click", async () => {
      const orig = testBtn.textContent;
      testBtn.disabled = true;
      testBtn.textContent = "Sending…";
      try {
        const resp = await API.post(`/api/notifications/${ev.id}/test`, {});
        testBtn.textContent = resp.ok ? "✓ Sent" : "✗ Error";
      } catch {
        testBtn.textContent = "✗ Error";
      }
      setTimeout(() => {
        testBtn.textContent = orig;
        testBtn.disabled = false;
      }, 2000);
    });
    row.appendChild(testBtn);

    const editBtn = el("button", "btn-secondary", "Edit");
    editBtn.style.cssText = "padding:4px 10px;font-size:11px;";
    editBtn.addEventListener("click", () => openNotificationEventModal(ev, eventTypesMeta, onChange));
    row.appendChild(editBtn);

    const delBtn = el("button", "btn-secondary", "Delete");
    delBtn.style.cssText = "padding:4px 10px;font-size:11px;";
    delBtn.addEventListener("click", async () => {
      if (!confirm("Delete this notification event?")) return;
      await API.del(`/api/notifications/${ev.id}`);
      onChange();
    });
    row.appendChild(delBtn);

    container.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// Notification events — edit modal
// ---------------------------------------------------------------------------

function openNotificationEventModal(existing, eventTypesMeta, onSaved) {
  const overlay = $("modal-overlay");
  const body = $("modal-body");
  overlay.style.display = "flex";
  body.innerHTML = "";

  const wrap = el("div");
  wrap.style.cssText = "padding:24px;display:flex;flex-direction:column;gap:16px;max-width:560px;";
  body.appendChild(wrap);

  const heading = el("div", "", existing ? "Edit notification event" : "Add notification event");
  heading.style.cssText = "font-weight:700;font-size:16px;";
  wrap.appendChild(heading);

  // Event type select
  const typeGroup = el("div");
  typeGroup.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  const typeLbl = el("label", "", "Event type");
  typeLbl.style.cssText = "font-weight:600;font-size:12px;";
  const typeSel = el("select", "search-input");
  for (const meta of eventTypesMeta) {
    const opt = el("option");
    opt.value = meta.event_type;
    opt.textContent = NOTIF_EVENT_LABELS[meta.event_type] || meta.event_type;
    typeSel.appendChild(opt);
  }
  typeSel.value = existing?.event_type || eventTypesMeta[0]?.event_type;
  typeGroup.appendChild(typeLbl);
  typeGroup.appendChild(typeSel);
  wrap.appendChild(typeGroup);

  // Apprise URL
  const urlGroup = el("div");
  urlGroup.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  const urlLbl = el("label", "", "Apprise URL");
  urlLbl.style.cssText = "font-weight:600;font-size:12px;";
  const urlInput = el("input", "search-input");
  urlInput.type = "text";
  urlInput.placeholder = "http://192.168.5.201:8100/notify/apprise";
  urlInput.value = existing?.apprise_url || "";
  urlGroup.appendChild(urlLbl);
  urlGroup.appendChild(urlInput);
  wrap.appendChild(urlGroup);

  // Title template
  const titleGroup = el("div");
  titleGroup.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  const titleLbl = el("label", "", "Title template");
  titleLbl.style.cssText = "font-weight:600;font-size:12px;";
  const titleInput = el("input", "search-input");
  titleInput.type = "text";
  titleGroup.appendChild(titleLbl);
  titleGroup.appendChild(titleInput);
  wrap.appendChild(titleGroup);

  // Body template
  const bodyGroup = el("div");
  bodyGroup.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  const bodyLbl = el("label", "", "Body template");
  bodyLbl.style.cssText = "font-weight:600;font-size:12px;";
  const bodyInput = el("textarea", "search-input");
  bodyInput.rows = 4;
  bodyInput.style.fontFamily = "inherit";
  bodyGroup.appendChild(bodyLbl);
  bodyGroup.appendChild(bodyInput);
  wrap.appendChild(bodyGroup);

  // Variables panel
  const varsGroup = el("div");
  varsGroup.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  const varsLbl = el("label", "", "Available variables (click to insert into body)");
  varsLbl.style.cssText = "font-weight:600;font-size:12px;";
  const varsChips = el("div");
  varsChips.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;";
  varsGroup.appendChild(varsLbl);
  varsGroup.appendChild(varsChips);
  wrap.appendChild(varsGroup);

  // Notification type
  const ntGroup = el("div");
  ntGroup.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  const ntLbl = el("label", "", "Notification type");
  ntLbl.style.cssText = "font-weight:600;font-size:12px;";
  const ntSel = el("select", "search-input");
  for (const t of ["info", "success", "warning", "failure"]) {
    const opt = el("option");
    opt.value = t;
    opt.textContent = t;
    ntSel.appendChild(opt);
  }
  ntSel.value = existing?.notification_type || "info";
  ntGroup.appendChild(ntLbl);
  ntGroup.appendChild(ntSel);
  wrap.appendChild(ntGroup);

  // Enabled
  const enabledRow = el("label");
  enabledRow.style.cssText = "display:flex;align-items:center;gap:8px;font-size:13px;";
  const enabledCb = el("input");
  enabledCb.type = "checkbox";
  enabledCb.checked = existing ? !!existing.enabled : true;
  enabledRow.appendChild(enabledCb);
  enabledRow.appendChild(document.createTextNode("Enabled"));
  wrap.appendChild(enabledRow);

  // Feedback + buttons
  const feedback = el("div");
  feedback.style.cssText = "font-size:12px;min-height:16px;";
  wrap.appendChild(feedback);

  const btnRow = el("div");
  btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;";
  const cancelBtn = el("button", "btn-secondary", "Cancel");
  const testBtn = el("button", "btn-secondary", "Test");
  const saveBtn = el("button", "btn-primary", existing ? "Save" : "Create");
  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(testBtn);
  btnRow.appendChild(saveBtn);
  wrap.appendChild(btnRow);

  // --- Behaviour: populate templates + vars for the selected type ---
  function syncForType() {
    const meta = eventTypesMeta.find(m => m.event_type === typeSel.value);
    if (!meta) return;
    // Only overwrite templates/notification_type when they're blank (so we don't clobber user edits).
    if (!titleInput.value) titleInput.value = meta.default_title || "";
    if (!bodyInput.value) bodyInput.value = meta.default_body || "";
    if (!existing && ntSel.value === "info") ntSel.value = meta.default_notification_type || "info";
    // Rebuild chips
    varsChips.innerHTML = "";
    for (const v of meta.variables || []) {
      const chip = el("code", "", `{${v}}`);
      chip.style.cssText =
        "padding:2px 8px;background:var(--bg-card);border:1px solid var(--border);" +
        "border-radius:999px;font-size:11px;cursor:pointer;";
      chip.addEventListener("click", () => {
        const token = `{${v}}`;
        // Insert into whichever field is focused — body textarea by default.
        const target = document.activeElement === titleInput ? titleInput : bodyInput;
        const start = target.selectionStart ?? target.value.length;
        const end = target.selectionEnd ?? target.value.length;
        target.value = target.value.slice(0, start) + token + target.value.slice(end);
        const pos = start + token.length;
        target.focus();
        target.setSelectionRange(pos, pos);
      });
      varsChips.appendChild(chip);
    }
  }

  // Prefill with existing values first, then sync (which only fills blanks).
  titleInput.value = existing?.title_template || "";
  bodyInput.value = existing?.body_template || "";
  syncForType();

  typeSel.addEventListener("change", () => {
    // On type change, if current templates match the previous type's defaults, overwrite them.
    // Simpler heuristic: if templates are blank OR match any known default, overwrite.
    const priorMatches = eventTypesMeta.some(
      m => titleInput.value === (m.default_title || "") && bodyInput.value === (m.default_body || ""),
    );
    if (priorMatches) {
      titleInput.value = "";
      bodyInput.value = "";
    }
    syncForType();
  });

  function collect() {
    return {
      event_type: typeSel.value,
      apprise_url: urlInput.value.trim(),
      title_template: titleInput.value,
      body_template: bodyInput.value,
      notification_type: ntSel.value,
      enabled: enabledCb.checked,
    };
  }

  cancelBtn.addEventListener("click", closeModal);

  testBtn.addEventListener("click", async () => {
    feedback.style.color = "var(--text-dim)";
    feedback.textContent = "Sending test…";
    try {
      const resp = await API.post("/api/notifications/test", collect());
      if (resp.ok) {
        feedback.style.color = "#34d399";
        feedback.textContent = `✓ Sent (${resp.message || "OK"})`;
      } else {
        feedback.style.color = "#f85149";
        feedback.textContent = `✗ ${resp.message || "Error"}`;
      }
    } catch (e) {
      feedback.style.color = "#f85149";
      feedback.textContent = `✗ ${e.message || "Error"}`;
    }
  });

  saveBtn.addEventListener("click", async () => {
    feedback.textContent = "";
    saveBtn.disabled = true;
    try {
      const payload = collect();
      if (existing) {
        await API.put(`/api/notifications/${existing.id}`, payload);
      } else {
        await API.post("/api/notifications", payload);
      }
      closeModal();
      onSaved();
    } catch (e) {
      feedback.style.color = "#f85149";
      feedback.textContent = `✗ ${e.message || "Save failed"}`;
      saveBtn.disabled = false;
    }
  });
}
