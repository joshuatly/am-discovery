/* =========================================================
   AM Discovery — Settings page: notification event UI
   (list rendering + add/edit modal, split out of page-settings.js
   to keep it under the 800-line module limit)
   ========================================================= */

"use strict";

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
