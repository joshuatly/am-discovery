/* =========================================================
   AM Discovery — Settings page
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// Settings page helpers — section grouping + a plain text/number field
// ---------------------------------------------------------------------------
function settingsSectionHeading(title, desc) {
  const wrap = el("div");
  wrap.style.cssText = "display:flex;flex-direction:column;gap:4px;";
  const label = el("div", "", title);
  label.style.cssText = "font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-dim);";
  wrap.appendChild(label);
  if (desc) {
    const descEl = el("p", "", desc);
    descEl.style.cssText = "font-size:12px;color:var(--text-secondary);margin:0;";
    wrap.appendChild(descEl);
  }
  return wrap;
}

function settingsSectionDivider() {
  const hr = el("div");
  hr.style.cssText = "border-top:1px solid var(--border);";
  return hr;
}

// A labeled text/number input with an optional description, matching the
// existing field markup exactly (label 600 weight, 12px dim desc).
function settingsField({ label, desc, value, placeholder, maxWidth, type = "text", min = "1" }) {
  const group = el("div");
  group.style.cssText = "display:flex;flex-direction:column;gap:8px;";
  const labelEl = el("label", "", label);
  labelEl.style.fontWeight = "600";
  group.appendChild(labelEl);
  if (desc) {
    const descEl = el("p", "", desc);
    descEl.style.cssText = "font-size:12px;color:var(--text-dim);margin:0;";
    group.appendChild(descEl);
  }
  const input = el("input", "search-input");
  input.type = type;
  if (type === "number") input.min = min;
  input.value = value;
  if (placeholder) input.placeholder = placeholder;
  if (maxWidth) input.style.maxWidth = maxWidth;
  group.appendChild(input);
  return { group, input };
}

// A single "Enable X" checkbox + description, used to gate a section's extra
// fields. Returns the checkbox so callers can wire up show/hide + read it on save.
function settingsEnableCheckbox({ id, label, desc, checked }) {
  const group = el("div");
  group.style.cssText = "display:flex;flex-direction:column;gap:8px;";
  const row = el("div");
  row.style.cssText = "display:flex;align-items:center;gap:8px;";
  const cb = el("input");
  cb.type = "checkbox";
  cb.id = id;
  cb.checked = checked;
  const cbLabel = el("label", "", label);
  cbLabel.style.fontWeight = "600";
  cbLabel.htmlFor = id;
  row.appendChild(cb);
  row.appendChild(cbLabel);
  group.appendChild(row);
  if (desc) {
    const descEl = el("p", "", desc);
    descEl.style.cssText = "font-size:12px;color:var(--text-dim);margin:0;";
    group.appendChild(descEl);
  }
  return { group, cb };
}

// Shows/hides `target` based on `checkbox`'s checked state, both immediately
// and on every change — used for the MusicBrainz/CLI Scheduler sub-fields,
// which are only meaningful once their feature is enabled.
function bindSettingsToggle(checkbox, target) {
  const sync = () => {
    // Restore "flex" explicitly rather than clearing to "" — an empty value
    // unsets the inline display and falls back to the default block layout,
    // which silently drops the container's `gap` (block children don't
    // respect it), collapsing the spacing between the revealed fields.
    target.style.display = checkbox.checked ? "flex" : "none";
  };
  checkbox.addEventListener("change", sync);
  sync();
}

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

  // ---------------------------------------------------------------------
  // Section: Storefronts & Discovery
  // ---------------------------------------------------------------------
  form.appendChild(settingsSectionHeading("Storefronts & Discovery"));

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

  // Discovery Room Matching — per-storefront + fallback title(s) used to
  // find each storefront's "New Releases" room. Fixable here without a
  // code change or restart when Apple renames a room (see room_errors in
  // the status footer).
  const discGroup = el("div");
  discGroup.style.cssText = "display:flex;flex-direction:column;gap:8px;";
  const discLabel = el("label", "", "Discovery Room Matching");
  discLabel.style.fontWeight = "600";
  const discDesc = el(
    "p",
    "",
    "Localized title Apple Music uses for each storefront's New Releases room. " +
      "This matches the new-albums room specifically — not the new-singles/EPs room, which some storefronts list separately. " +
      "If discovery fails for a storefront, fix its keyword here — takes effect on the next poll, no restart needed.",
  );
  discDesc.style.cssText = "font-size:12px;color:var(--text-dim);margin:0;";
  discGroup.appendChild(discLabel);
  discGroup.appendChild(discDesc);

  const discNames = { ...(cfg.discovery_names || {}) };
  const discCodes = Array.from(new Set([...(cfg.check_storefronts || []), ...Object.keys(discNames)])).sort();
  const discRows = [];
  const discRowsWrap = el("div");
  discRowsWrap.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  for (const code of discCodes) {
    const row = el("div");
    row.style.cssText = "display:flex;align-items:center;gap:8px;";
    const chipLink = el("a");
    chipLink.href = `https://music.apple.com/${code}/new`;
    chipLink.target = "_blank";
    chipLink.rel = "noopener noreferrer";
    chipLink.title = `Open ${code.toUpperCase()} New Releases on Apple Music`;
    chipLink.style.textDecoration = "none";
    chipLink.innerHTML = sfChipHtml(code);
    row.appendChild(chipLink);
    const rowInput = el("input", "search-input");
    rowInput.type = "text";
    rowInput.value = discNames[code] || "";
    rowInput.placeholder = "e.g. New Releases — the albums room, not singles/EPs (blank = use fallback titles below)";
    rowInput.style.flex = "1";
    row.appendChild(rowInput);
    discRowsWrap.appendChild(row);
    discRows.push({ code, input: rowInput });
  }
  discGroup.appendChild(discRowsWrap);

  const fallbackLabel = el("label", "", "Fallback Match Titles (comma separated)");
  fallbackLabel.style.cssText = "font-weight:600;font-size:12px;margin-top:4px;";
  const fallbackDesc = el(
    "p",
    "",
    "Substrings matched against a room's title when a storefront above has no keyword set.",
  );
  fallbackDesc.style.cssText = "font-size:12px;color:var(--text-dim);margin:0;";
  const fallbackInput = el("input", "search-input");
  fallbackInput.type = "text";
  fallbackInput.value = (cfg.discovery_fallback_titles || []).join(", ");
  discGroup.appendChild(fallbackLabel);
  discGroup.appendChild(fallbackDesc);
  discGroup.appendChild(fallbackInput);
  form.appendChild(discGroup);

  // Home Storefront
  const { group: homeGroup, input: homeInput } = settingsField({
    label: "Home Storefront",
    desc: "The storefront your Apple Music account is in. Used as the baseline for tracklist comparisons.",
    value: cfg.home_storefront || "my",
    placeholder: "e.g. my",
    maxWidth: "120px",
  });
  form.appendChild(homeGroup);

  // CORS Proxy
  const { group: proxyGroup, input: proxyInput } = settingsField({
    label: "CORS Proxy",
    desc: "Optional URL prefix to proxy outgoing Apple Music requests through. Leave blank to disable.",
    value: cfg.cors_proxy || "",
    placeholder: "e.g. https://proxy.example.com/",
  });
  form.appendChild(proxyGroup);

  // Timezone
  const { group: tzGroup, input: tzInput } = settingsField({
    label: "Timezone",
    desc:
      "IANA timezone name used to format timestamps in notifications and API responses. " +
      "Examples: UTC, Asia/Hong_Kong, America/New_York, Europe/London. Defaults to UTC.",
    value: cfg.timezone || "UTC",
    placeholder: "UTC",
    maxWidth: "240px",
  });
  form.appendChild(tzGroup);

  // ---------------------------------------------------------------------
  // Section: Polling Intervals & Batch Sizes
  // ---------------------------------------------------------------------
  form.appendChild(settingsSectionDivider());
  form.appendChild(settingsSectionHeading("Polling Intervals & Batch Sizes"));

  const { group: pollGroup, input: pollInput } = settingsField({
    label: "New Release Poll Interval (days)",
    value: cfg.newrelease_poll_interval_days || 1,
    type: "number",
    maxWidth: "120px",
  });
  form.appendChild(pollGroup);

  const { group: wlPollGroup, input: wlPollInput } = settingsField({
    label: "Watchlist Poll Interval (minutes)",
    desc: "How often to check watched artists for new releases.",
    value: cfg.watchlist_poll_interval_minutes || 10,
    type: "number",
    maxWidth: "120px",
  });
  form.appendChild(wlPollGroup);

  const { group: wlBatchGroup, input: wlBatchInput } = settingsField({
    label: "Watchlist Poll Batch Size",
    desc: "Number of watched artists to refresh per poll cycle.",
    value: cfg.watchlist_poll_batch_size || 5,
    type: "number",
    maxWidth: "120px",
  });
  form.appendChild(wlBatchGroup);

  const { group: wlRefreshGroup, input: wlRefreshInput } = settingsField({
    label: "Watchlist Artist Refresh Interval (days)",
    desc: "Days before a watched artist's catalog is considered stale and re-fetched.",
    value: cfg.watchlist_refresh_interval_days || 7,
    type: "number",
    maxWidth: "120px",
  });
  form.appendChild(wlRefreshGroup);

  // ---------------------------------------------------------------------
  // Section: MusicBrainz Seeding — the enable checkbox is always shown;
  // its own interval/batch fields only matter (and only render visibly)
  // once the feature is on.
  // ---------------------------------------------------------------------
  form.appendChild(settingsSectionDivider());
  form.appendChild(settingsSectionHeading("MusicBrainz Seeding"));

  const { group: mbGroup, cb: mbCb } = settingsEnableCheckbox({
    id: "cfg-mb-scan-enabled",
    label: "Enable MusicBrainz Seeding Admin",
    desc:
      "Suggests MusicBrainz artist IDs and flags releases missing from MusicBrainz. " +
      "When disabled, the background scanner stops running and the Admin page is hidden.",
    checked: cfg.mb_scan_enabled !== false,
  });
  form.appendChild(mbGroup);

  const mbExtra = el("div");
  mbExtra.style.cssText = "display:flex;flex-direction:column;gap:20px;";
  form.appendChild(mbExtra);

  const { group: mbIntervalGroup, input: mbIntervalInput } = settingsField({
    label: "MusicBrainz Scan Interval (minutes)",
    desc: "How often the seeding scanner runs a cycle.",
    value: cfg.mb_scan_interval_minutes || 60,
    type: "number",
    maxWidth: "120px",
  });
  mbExtra.appendChild(mbIntervalGroup);

  const { group: mbBatchGroup, input: mbBatchInput } = settingsField({
    label: "MusicBrainz Artist Batch Size",
    desc: "Artists processed per seeding-scan phase per cycle. Keep small — MusicBrainz allows ~1 request/sec.",
    value: cfg.mb_scan_artist_batch || 3,
    type: "number",
    maxWidth: "120px",
  });
  mbExtra.appendChild(mbBatchGroup);

  const { group: mbRecheckGroup, input: mbRecheckInput } = settingsField({
    label: "MusicBrainz Artist Recheck Interval (days)",
    desc: "Minimum days before re-scanning an already-checked artist for an MBID or new releases.",
    value: cfg.mb_artist_recheck_days || 7,
    type: "number",
    maxWidth: "120px",
  });
  mbExtra.appendChild(mbRecheckGroup);

  bindSettingsToggle(mbCb, mbExtra);

  // ---------------------------------------------------------------------
  // Section: CLI Scheduler — same enable/reveal pattern as MusicBrainz.
  // "Enabled" is derived from cli_scheduler_url being non-empty (there's no
  // separate boolean in config); unchecking clears the URL on save.
  // ---------------------------------------------------------------------
  form.appendChild(settingsSectionDivider());
  form.appendChild(settingsSectionHeading("CLI Scheduler"));

  const { group: cliEnabledGroup, cb: cliEnabledCb } = settingsEnableCheckbox({
    id: "cfg-cli-scheduler-enabled",
    label: "Enable CLI Scheduler",
    desc: "Send albums to an external CLI Scheduler instance for automated downloading.",
    checked: !!cfg.cli_scheduler_url,
  });
  form.appendChild(cliEnabledGroup);

  const cliExtra = el("div");
  cliExtra.style.cssText = "display:flex;flex-direction:column;gap:20px;";
  form.appendChild(cliExtra);

  const { group: cliUrlGroup, input: cliUrlInput } = settingsField({
    label: "CLI Scheduler URL",
    desc: "Base URL of your CLI Scheduler instance.",
    value: cfg.cli_scheduler_url || "",
    placeholder: "http://192.168.5.198:5000",
  });
  cliExtra.appendChild(cliUrlGroup);

  const { group: cliPresetGroup, input: cliPresetInput } = settingsField({
    label: "CLI Scheduler Preset",
    desc: "Preset name to use when submitting jobs to the CLI Scheduler.",
    value: cfg.cli_scheduler_preset || "",
    placeholder: "e.g. amdl",
  });
  cliExtra.appendChild(cliPresetGroup);

  bindSettingsToggle(cliEnabledCb, cliExtra);

  const errorMsg = el("div", "");
  errorMsg.style.color = "red";
  errorMsg.style.display = "none";
  form.appendChild(errorMsg);

  // ---------------------------------------------------------------------
  // Section: Notifications
  // ---------------------------------------------------------------------
  form.appendChild(settingsSectionDivider());
  form.appendChild(settingsSectionHeading("Notifications"));

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
      const parsedMbInterval = parseInt(mbIntervalInput.value, 10);
      const parsedMbBatch = parseInt(mbBatchInput.value, 10);
      const parsedMbRecheck = parseInt(mbRecheckInput.value, 10);
      const parsedDiscNames = { ...(cfg.discovery_names || {}) };
      for (const { code, input } of discRows) {
        const v = input.value.trim();
        if (v) parsedDiscNames[code] = v;
        else delete parsedDiscNames[code];
      }
      const parsedFallback = fallbackInput.value
        .split(",")
        .map(s => s.trim())
        .filter(s => s);
      const newCfg = {
        ...cfg,
        check_storefronts: parsedSfs,
        discovery_names: parsedDiscNames,
        discovery_fallback_titles: parsedFallback,
        home_storefront: parsedHome || "my",
        newrelease_poll_interval_days: isNaN(parsedPoll) ? 1 : parsedPoll,
        watchlist_poll_interval_minutes: isNaN(parsedWlPoll) ? 10 : parsedWlPoll,
        watchlist_poll_batch_size: isNaN(parsedWlBatch) ? 5 : parsedWlBatch,
        watchlist_refresh_interval_days: isNaN(parsedWlRefresh) ? 7 : parsedWlRefresh,
        cors_proxy: parsedProxy,
        mb_scan_enabled: mbCb.checked,
        mb_scan_interval_minutes: isNaN(parsedMbInterval) ? 60 : parsedMbInterval,
        mb_scan_artist_batch: isNaN(parsedMbBatch) ? 3 : parsedMbBatch,
        mb_artist_recheck_days: isNaN(parsedMbRecheck) ? 7 : parsedMbRecheck,
        cli_scheduler_url: cliEnabledCb.checked ? cliUrlInput.value.trim() : "",
        cli_scheduler_preset: cliPresetInput.value.trim(),
        timezone: tzInput.value.trim() || "UTC",
      };

      await API.put("/api/system/config", newCfg);

      // Update in-memory state so widget/modal reflect new values immediately
      state.configuredStorefronts = parsedSfs;
      state.homeStorefront = newCfg.home_storefront;
      state.cliSchedulerEnabled = !!(newCfg.cli_scheduler_url);
      state.mbScanEnabled = newCfg.mb_scan_enabled;
      const navAdmin = $("nav-admin");
      if (navAdmin) navAdmin.style.display = state.mbScanEnabled ? "" : "none";
      if (!state.mbScanEnabled && location.hash.startsWith("#/admin")) location.hash = "#/";
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

  // ---------------------------------------------------------------------
  // Section: Backup / Restore
  // ---------------------------------------------------------------------
  const wlSection = el("div", "");
  wlSection.style.cssText = "max-width:600px;margin-top:32px;display:flex;flex-direction:column;gap:12px;";
  wlSection.appendChild(settingsSectionHeading("Backup / Restore"));
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
  wlSection.appendChild(wlDesc);
  wlSection.appendChild(wlButtons);
  wrap.appendChild(wlSection);
}
