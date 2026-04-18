/* =========================================================
   AM Discovery — Status bar and metadata source widget
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------
async function refreshStatus() {
  try {
    const s = await API.get("/api/system/status");
    const dot = $("status-dot");
    const val = $("status-last-run");
    const roomErrors = s.room_errors || [];
    if (s.is_running) {
      dot.className = "status-dot spin";
      val.textContent = "Scanning…";
    } else if (roomErrors.length > 0) {
      dot.className = "status-dot warn";
      val.textContent = s.last_run ? timeAgo(s.last_run.ran_at) : "never";
    } else {
      dot.className = "status-dot ok";
      val.textContent = s.last_run ? timeAgo(s.last_run.ran_at) : "never";
    }
    let warn = $("status-room-errors");
    if (roomErrors.length > 0) {
      if (!warn) {
        warn = document.createElement("div");
        warn.id = "status-room-errors";
        warn.className = "status-room-errors";
        $("status-card").insertAdjacentElement("afterend", warn);
      }
      const sfList = roomErrors.map(sf => sf.toUpperCase()).join(", ");
      warn.textContent = `⚠ Room fetch failed: ${sfList}`;
    } else if (warn) {
      warn.remove();
    }
  } catch {}
}

async function triggerRefresh() {
  const btn = $("btn-refresh");
  btn.disabled = true;
  btn.classList.add("spinning");
  const dot = $("status-dot");
  dot.className = "status-dot spin";
  $("status-last-run").textContent = "Scanning…";
  try {
    await API.post("/api/system/refresh", {});
  } catch {}
  // Poll until done
  const poll = setInterval(async () => {
    try {
      const s = await API.get("/api/system/status");
      if (!s.is_running) {
        clearInterval(poll);
        btn.disabled = false;
        btn.classList.remove("spinning");
        await refreshStatus();
        // Reload current page
        route(location.hash || "#/");
      }
    } catch {}
  }, 2000);
}

// ---------------------------------------------------------------------------
// Metadata source widget
// ---------------------------------------------------------------------------
function updateArtistExtLink() {
  const extLink = document.querySelector(".artist-ext-link");
  if (!extLink) return;
  const base = extLink.dataset.baseUrl;
  const sf = state.metadataStorefront;
  extLink.href = sf
    ? base.replace(/music\.apple\.com\/[a-z]{2}\//, `music.apple.com/${sf}/`)
    : base;
}

// ---------------------------------------------------------------------------
function updateFetchArtistBtn() {
  const fetchBtn = document.querySelector(".btn-fetch-artist");
  if (!fetchBtn || fetchBtn.disabled) return;
  const sf = state.metadataStorefront;
  fetchBtn.textContent = sf ? `↓ Fetch from ${sf.toUpperCase()}` : "↓ Fetch All";
}

function updateSrcBadge() {
  const badge = $("sidebar-src-badge");
  if (!badge) return;
  const sf = state.metadataStorefront;
  const home = state.homeStorefront;
  const showHome = state.alwaysIncludeMY && sf && home && sf !== home;
  if (sf && showHome) {
    badge.innerHTML = `${sf.toUpperCase()}<span class="badge-home">+${home.toUpperCase()}</span>`;
  } else {
    badge.textContent = sf ? sf.toUpperCase() : "—";
  }
  badge.className = `sidebar-src-badge${sf ? ` ${sf}` : ""}`;
}

function renderMetaSourceWidget() {
  const chips = $("meta-source-chips");
  if (!chips) return;
  chips.innerHTML = "";
  updateSrcBadge();

  const storefronts = state.configuredStorefronts || [];

  // "Off" option
  const offBtn = el("button", `meta-src-btn${!state.metadataStorefront ? " active" : ""}`, "Off");
  offBtn.title = "Use cached metadata";
  offBtn.addEventListener("click", () => {
    state.metadataStorefront = "";
    localStorage.setItem("metadataStorefront", "");
    renderMetaSourceWidget();
    updateFetchArtistBtn();
    updateArtistExtLink();
  });
  chips.appendChild(offBtn);

  storefronts.forEach(sf => {
    const isActive = state.metadataStorefront === sf;
    const btn = el("button", `meta-src-btn ${sf}${isActive ? " active" : ""}`, sf.toUpperCase());
    applyMetaSrcBtnColor(btn, sf, isActive);
    btn.title = `Fetch metadata from ${sf.toUpperCase()} storefront`;
    btn.addEventListener("click", () => {
      state.metadataStorefront = sf;
      localStorage.setItem("metadataStorefront", sf);
      renderMetaSourceWidget();
      updateFetchArtistBtn();
      updateArtistExtLink();
    });
    chips.appendChild(btn);
  });

  // "+HOME" comparison toggle — only shown when a non-home storefront is selected
  const home = state.homeStorefront;
  if (home && state.metadataStorefront && state.metadataStorefront !== home) {
    const label = `+${home.toUpperCase()}`;
    const myToggle = el("button", `meta-src-btn my-toggle${state.alwaysIncludeMY ? " active" : ""}`, label);
    myToggle.title = state.alwaysIncludeMY
      ? `Also fetching ${home.toUpperCase()} for tracklist comparison (click to disable)`
      : `Also fetch ${home.toUpperCase()} storefront to compare tracklists`;
    myToggle.addEventListener("click", () => {
      state.alwaysIncludeMY = !state.alwaysIncludeMY;
      if (state.alwaysIncludeMY) {
        localStorage.setItem("alwaysIncludeMY", "true");
      } else {
        localStorage.removeItem("alwaysIncludeMY");
      }
      renderMetaSourceWidget();
    });
    chips.appendChild(myToggle);
  }
}

async function initMetaSourceWidget() {
  if (state.configuredStorefronts === null) {
    try {
      const cfg = await API.get("/api/system/config");
      state.configuredStorefronts = cfg.check_storefronts || [];
      state.homeStorefront = cfg.home_storefront || "my";
      state.cliSchedulerEnabled = !!(cfg.cli_scheduler_url);
    } catch {
      state.configuredStorefronts = [];
      state.homeStorefront = "my";
      state.cliSchedulerEnabled = false;
    }
  }
  if (localStorage.getItem("metadataStorefront") === null) {
    state.metadataStorefront = state.homeStorefront;
    localStorage.setItem("metadataStorefront", state.homeStorefront);
  }
  renderMetaSourceWidget();
}
