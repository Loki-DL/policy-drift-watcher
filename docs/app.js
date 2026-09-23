/* Policy Drift Watcher — web app.
 * Security: every piece of data is inserted with textContent (never innerHTML), links are
 * only allowed to https:// pages, and nothing is sent anywhere. "Seen" markers stay in this
 * browser only.
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SEEN_KEY = "pdw-seen-v1";
  const NEW_WINDOW_DAYS = 30;
  let status = { apps: {} };
  let changes = [];

  // ---------- tiny DOM helper (text only, no HTML parsing) ----------
  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const c of children) if (c) node.append(c);
    return node;
  }
  const safeUrl = (u) => (typeof u === "string" && u.startsWith("https://") ? u : null);

  // ---------- "seen" markers (per browser; fine if storage is unavailable) ----------
  function loadSeen() {
    try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]")); } catch { return new Set(); }
  }
  function markSeen(id) {
    const seen = loadSeen();
    if (seen.has(id)) return;
    seen.add(id);
    try { localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-500))); } catch { /* ignore */ }
  }

  // ---------- formatting ----------
  function ago(iso) {
    if (!iso) return "";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 3600) return "within the last hour";
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    const d = Math.floor(s / 86400);
    return d === 1 ? "yesterday" : `${d} days ago`;
  }
  const dateText = (iso) =>
    new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  const initials = (name) => name.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "?";

  // ---------- data ----------
  async function getJSON(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  async function load() {
    try {
      [status, { changes }] = await Promise.all([getJSON("data/status.json"), getJSON("data/changes.json")]);
    } catch {
      $("last-run").textContent = "Couldn't load data. Pull to refresh.";
      return;
    }
    $("last-run").textContent = status.last_run
      ? `Last checked ${ago(status.last_run)}`
      : "Waiting for the first daily check";
    route();
  }

  function appRows() {
    const seen = loadSeen();
    const byId = Object.fromEntries(changes.map((c) => [c.id, c]));
    const rows = Object.entries(status.apps || {}).map(([id, a]) => {
      const latest = a.latest_change_id ? byId[a.latest_change_id] : null;
      const recent = latest && Date.now() - new Date(latest.detected_at) < NEW_WINDOW_DAYS * 864e5;
      return { id, ...a, latest, isNew: Boolean(latest && recent && !seen.has(latest.id)) };
    });
    const rank = (r) => (r.isNew ? 0 : r.latest ? 1 : 2);
    return rows.sort((a, b) => rank(a) - rank(b)
      || (b.latest?.detected_at || "").localeCompare(a.latest?.detected_at || "")
      || a.name.localeCompare(b.name));
  }

  // ---------- views ----------
  function renderHome() {
    $("home").hidden = false;
    $("detail").hidden = true;
    const rows = appRows();
    const list = $("app-list");
    list.replaceChildren();
    const newCount = rows.filter((r) => r.isNew).length;
    $("summary").textContent = rows.length === 0
      ? "No apps yet. The first daily check will add them."
      : newCount
        ? `${newCount} app${newCount > 1 ? "s" : ""} changed ${newCount > 1 ? "their" : "its"} privacy policy.`
        : `Watching ${rows.length} apps. No new changes.`;

    for (const r of rows) {
      let line;
      if (r.latest) line = `${r.latest.headline} · ${ago(r.latest.detected_at)}`;
      else if (r.state === "watching") line = `Watching since ${dateText(r.watching_since || r.last_checked)}. No changes yet.`;
      else line = "Not checked yet";

      const name = el("div", { class: "app-name" }, el("span", { text: r.name }));
      if (r.isNew) name.append(el("span", { class: "badge new", text: "Changed" }));
      if (r.latest) name.append(el("span", { class: `risk ${r.latest.risk}`, text: r.latest.risk }));
      if (r.error) name.append(el("span", { class: "badge warn", text: r.error }));

      const btn = el("button", {
        class: `app${r.isNew ? " is-new" : ""}`,
        type: "button",
        onclick: () => { location.hash = `app=${encodeURIComponent(r.id)}`; },
      },
      el("div", { class: "avatar", text: initials(r.name), "aria-hidden": "true" }),
      el("div", { class: "app-main" }, name, el("div", { class: "app-line", text: line })),
      el("span", { class: "chev", text: "›", "aria-hidden": "true" }));
      list.append(el("li", {}, btn));
    }
  }

  function changeCard(c) {
    const card = el("article", { class: "change", id: `c-${c.id}` },
      el("span", { class: `risk ${c.risk}`, text: `${c.risk} risk` }),
      el("h2", { text: c.headline }),
      el("p", { class: "meta", text: `Detected ${dateText(c.detected_at)} · AI summary` }),
      el("p", { class: "reason", text: c.risk_reason }),
      el("h3", { text: "What changed" }), el("p", { text: c.what_changed }),
      el("h3", { text: "What it means for you" }), el("p", { text: c.what_it_means }),
      el("h3", { text: "What you can do" }), el("p", { text: c.what_you_can_do }),
    );
    const details = el("details", {},
      el("summary", { text: "See the exact wording" }),
      el("h3", { text: "Removed" }),
      el("div", { class: "excerpt before", text: c.before_excerpt || "(nothing removed)" }),
      el("h3", { text: "Added" }),
      el("div", { class: "excerpt after", text: c.after_excerpt || "(nothing added)" }));
    card.append(details);
    const src = safeUrl(c.source_url);
    if (src) card.append(el("a", { class: "source", href: src, target: "_blank", rel: "noopener noreferrer", text: "Open the full policy ↗" }));
    return card;
  }

  function renderApp(appId, focusChangeId) {
    const a = status.apps?.[appId];
    if (!a) return renderHome();
    $("home").hidden = true;
    $("detail").hidden = false;
    const body = $("detail-body");
    body.replaceChildren();
    const appChanges = changes.filter((c) => c.app_id === appId);

    body.append(el("h2", { class: "history-title", text: a.name }));
    if (a.error) body.append(el("p", { class: "muted", text: `${a.error}. It will try again tomorrow.` }));
    if (appChanges.length === 0) {
      body.append(el("div", { class: "empty" },
        el("p", { text: `No changes detected since ${dateText(a.watching_since || a.last_checked)}.` }),
        safeUrl(a.policy_url) ? el("a", { class: "source", href: a.policy_url, target: "_blank", rel: "noopener noreferrer", text: "Open the current policy ↗" }) : null));
    }
    appChanges.forEach((c, i) => {
      if (i === 1) body.append(el("h3", { class: "history-title", text: "Earlier changes" }));
      body.append(changeCard(c));
      markSeen(c.id);
    });
    const target = focusChangeId && document.getElementById(`c-${focusChangeId}`);
    (target || body).scrollIntoView({ block: "start" });
  }

  function route() {
    const params = new URLSearchParams(location.hash.slice(1));
    const changeId = params.get("change");
    if (changeId) {
      const c = changes.find((x) => x.id === changeId);
      if (c) return renderApp(c.app_id, c.id);
    }
    const appId = params.get("app");
    if (appId) return renderApp(appId);
    renderHome();
    window.scrollTo(0, 0);
  }

  // ---------- notifications ----------
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isStandalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  function b64ToBytes(b64) {
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (ch) => ch.charCodeAt(0));
  }

  async function renderNotify() {
    const box = $("notify-card");
    const hideKey = "pdw-notify-done";
    let done = false;
    try { done = localStorage.getItem(hideKey) === "1"; } catch { /* ignore */ }

    if (isIOS && !isStandalone) {
      box.replaceChildren(
        el("h2", { text: "Get alerts on your iPhone" }),
        el("ol", {},
          el("li", { text: "Tap the Share button in Safari." }),
          el("li", { text: "Choose “Add to Home Screen”." }),
          el("li", { text: "Open Drift Watch from your Home Screen and turn on alerts." })));
      box.hidden = false;
      return;
    }
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      box.replaceChildren(el("p", { text: "This browser can't show push alerts. You can still check this page any time." }));
      box.hidden = false;
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    if (existing && done) { box.hidden = true; return; }

    const showSubscription = (sub) => {
      const text = JSON.stringify([sub.toJSON()]);
      const area = el("textarea", { readonly: "", "aria-label": "Your alert key" });
      area.value = text;
      box.replaceChildren(
        el("h2", { text: "Alerts are on for this phone" }),
        el("p", { text: "Last step: copy this key and paste it into your GitHub repository as the secret PUSH_SUBSCRIPTIONS (see the setup guide). Keep it private." }),
        area,
        el("button", { class: "btn", type: "button", onclick: async () => {
          try { await navigator.clipboard.writeText(text); } catch { area.select(); document.execCommand("copy"); }
          box.querySelector(".btn").textContent = "Copied ✓";
        }, text: "Copy key" }),
        el("button", { class: "btn secondary", type: "button", onclick: () => {
          reg.showNotification("Drift Watch test", { body: "Alerts work on this device.", icon: "icons/icon-192.png", tag: "test" });
        }, text: "Test alert" }),
        el("p", {}),
        el("button", { class: "btn secondary", type: "button", onclick: () => {
          try { localStorage.setItem(hideKey, "1"); } catch { /* ignore */ }
          box.hidden = true;
        }, text: "I've saved it — hide this" }));
      box.hidden = false;
    };

    if (existing) return showSubscription(existing);

    box.replaceChildren(
      el("h2", { text: "Turn on change alerts" }),
      el("p", { text: "Get a notification when one of your apps changes its privacy policy." }),
      el("button", { class: "btn", type: "button", onclick: async () => {
        const key = window.PDW_CONFIG && window.PDW_CONFIG.vapidPublicKey;
        if (!key) { alert("Setup isn't finished: the public alert key is missing from config.js."); return; }
        const perm = await Notification.requestPermission();
        if (perm !== "granted") {
          box.replaceChildren(el("p", { text: "Alerts are blocked. You can allow them later in your phone's Settings → Notifications." }));
          return;
        }
        const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
        showSubscription(sub);
      }, text: "Turn on alerts" }));
    box.hidden = false;
  }

  // ---------- start ----------
  $("back").addEventListener("click", () => { location.hash = ""; });
  window.addEventListener("hashchange", route);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => {});
  }
  load();
  renderNotify().catch(() => {});
})();
