const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Layout grid overlay: button or the G key
(() => {
  const btn = document.querySelector(".grid-toggle");
  const root = document.documentElement;
  const set = on => {
    root.classList.toggle("show-grid", on);
    if (btn) btn.setAttribute("aria-pressed", on);
    try { localStorage.setItem("grid", on ? "1" : ""); } catch (e) {}
  };
  try { if (localStorage.getItem("grid")) set(true); } catch (e) {}
  btn?.addEventListener("click", () => set(!root.classList.contains("show-grid")));
  addEventListener("keydown", e => {
    const t = e.target;
    if (e.key.toLowerCase() !== "g" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
    set(!root.classList.contains("show-grid"));
  });
})();

// Hero: each letter swells in width and weight as the cursor nears it
(() => {
  const word = document.querySelector(".hero__word");
  if (!word) return;
  const letters = [...word.children];
  const readout = document.querySelector("[data-readout]");
  const n = letters.length;
  const SIGMA = 0.13;
  const first = letters[0], last = letters[n - 1];
  let cx = 0.5, tx = 0.5, lastMove = -1e9, visible = true, running = false;

  const apply = x => {
    let peak = { g: -1 };
    letters.forEach((el, i) => {
      const d = (i + 0.5) / n - x;
      const g = Math.exp(-(d * d) / (2 * SIGMA * SIGMA));
      const wdth = 50 + 100 * g, wght = 100 + 800 * g;
      el.style.fontVariationSettings = `"wdth" ${wdth.toFixed(1)}, "wght" ${wght.toFixed(0)}`;
      // Pull the outer letters out by their side bearings so the ink, not the
      // glyph box, meets the grid margins. Coefficients measured from Anybody's S and n.
      if (el === first) el.style.marginLeft = `${-(0.014 + 0.037 * g).toFixed(4)}em`;
      if (el === last) el.style.marginRight = `${-(0.011 + 0.1 * g).toFixed(4)}em`;
      if (g > peak.g) peak = { g, wdth, wght };
    });
    return peak;
  };

  // Size the word so its widest state spans the grid exactly; spacing absorbs the rest.
  const fit = () => {
    word.classList.add("is-measuring");
    word.style.fontSize = "100px";
    let widest = 0;
    for (let x = 0; x <= 1.0001; x += 0.05) {
      apply(x);
      widest = Math.max(widest, letters.reduce((w, el) => w + el.getBoundingClientRect().width, 0));
    }
    const avail = word.clientWidth;
    word.style.fontSize = `${Math.floor((100 * avail) / widest * 1000) / 1000}px`;
    word.classList.remove("is-measuring");
    apply(cx);
    word.classList.add("is-fit");
  };

  // The word always follows the visitor's own pointer. With reduced motion on
  // (e.g. Windows "Animation effects" off) only the self-running idle wave is skipped.
  const render = () => {
    const p = apply(cx);
    if (readout) readout.textContent = `wdth ${Math.round(p.wdth)} · wght ${Math.round(p.wght)}`;
  };
  const tick = t => {
    if (!visible) { running = false; return; } // stop once scrolled away
    const idle = t - lastMove > 2500;
    if (idle && !reduceMotion) tx = 0.5 + 0.42 * Math.sin(t / 1600);
    cx += (tx - cx) * 0.085;
    render();
    // With reduced motion, sleep once the letters have caught up with the pointer.
    if (reduceMotion && Math.abs(tx - cx) < 0.0005) { running = false; return; }
    requestAnimationFrame(tick);
  };
  const start = () => {
    if (running || !word.classList.contains("is-fit")) return;
    running = true;
    requestAnimationFrame(tick);
  };

  const hero = word.closest(".hero");
  hero.addEventListener("pointermove", e => {
    const r = word.getBoundingClientRect();
    tx = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    lastMove = performance.now();
    start();
  });

  document.fonts.load('400 100px "Anybody"').then(() => document.fonts.ready).then(() => {
    fit();
    render();
    new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible && !reduceMotion) start();
    }).observe(word);
  });

  // Refit only when the width changes (mobile URL bars fire height-only resizes).
  let raf, lastW = innerWidth;
  addEventListener("resize", () => {
    if (innerWidth === lastW) return;
    lastW = innerWidth;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(fit);
  });
})();

// Big titles: shrink until the longest word fits its column (long names like "Merriweather" on phones)
(() => {
  const els = document.querySelectorAll("[data-fit]");
  if (!els.length) return;
  const fit = () => els.forEach(el => {
    el.style.fontSize = "";
    let size = parseFloat(getComputedStyle(el).fontSize);
    for (let i = 0; i < 40 && el.scrollWidth > el.clientWidth + 1 && size > 14; i++) {
      size *= 0.94;
      el.style.fontSize = `${size}px`;
    }
  });
  document.fonts.ready.then(fit);
  let lastW = innerWidth;
  addEventListener("resize", () => { if (innerWidth !== lastW) { lastW = innerWidth; fit(); } });
})();

// Type tester: size and variable axes
(() => {
  const text = document.querySelector(".tester__text");
  if (!text) return;
  const size = document.querySelector("[data-size]");
  const axes = [...document.querySelectorAll("[data-axis]")];
  const out = tag => document.querySelector(`[data-out="${tag}"]`);
  const lines = document.querySelectorAll(".waterfall__line");
  const sample = text.textContent;
  if (matchMedia("(max-width: 720px)").matches) size.value = size.defaultValue = 40;

  // Opened from a font match: start from its settings and the visitor's own words.
  const params = new URLSearchParams(location.search);
  if (params.has("size")) size.value = params.get("size");
  axes.forEach(a => { if (params.has(a.dataset.axis)) a.value = params.get(a.dataset.axis); });
  if (params.get("text")) {
    text.textContent = params.get("text").slice(0, 200);
    lines.forEach(l => { l.textContent = text.textContent; });
  }

  // Axis settings apply to the tester, the waterfall and the glyphs alike.
  const render = () => {
    text.style.fontSize = `${size.value}px`;
    out("size").textContent = `${size.value} px`;
    const fvs = axes.map(a => `"${a.dataset.axis}" ${a.value}`).join(", ") || "normal";
    document.querySelector(".specimen").style.setProperty("--fvs", fvs);
    axes.forEach(a => { out(a.dataset.axis).textContent = a.value; });
  };
  // Edited text flows into the waterfall; an emptied tester falls back to the sample.
  const syncText = () => {
    const t = text.textContent.trim() || sample;
    lines.forEach(l => { l.textContent = t; });
  };
  [size, ...axes].forEach(i => i.addEventListener("input", render));
  text.addEventListener("input", syncText);
  text.addEventListener("blur", () => { if (!text.textContent.trim()) text.textContent = sample; });
  document.querySelector("[data-reset]").addEventListener("click", () => {
    [size, ...axes].forEach(i => { i.value = i.defaultValue; });
    text.textContent = sample;
    syncText();
    render();
  });
  render();
})();

// Font matcher: send the description, render the typeface set in the visitor's words
(() => {
  const form = document.querySelector("[data-matcher]");
  if (!form) return;
  const input = form.querySelector("#match-q");
  const go = form.querySelector(".matcher__go");
  const error = form.querySelector(".matcher__error");
  const result = document.querySelector("[data-result]");
  const r = name => result.querySelector(`[data-r="${name}"]`);
  const recentWrap = document.querySelector("[data-recent-wrap]");
  const recent = document.querySelector("[data-recent]");
  let busy = false;

  const showError = msg => {
    error.textContent = msg;
    error.hidden = !msg;
    input.setAttribute("aria-invalid", msg ? "true" : "false");
  };

  const render = m => {
    const sample = r("sample");
    sample.textContent = m.query;
    sample.style.fontFamily = `'${m.face.family}'`;
    sample.style.fontVariationSettings = Object.entries(m.settings).map(([k, v]) => `"${k}" ${v}`).join(", ") || "normal";
    sample.style.setProperty("--size", `${m.size}px`);
    r("face").textContent = m.face.name;
    r("face").href = m.face.url;
    r("settings").textContent = m.settings_label;
    r("ms").textContent = m.ms != null ? `${m.ms} ms` : "—";
    r("reason").textContent = m.reason;
    r("tester").href = m.tester_url;
    const alt = r("alt");
    alt.hidden = !m.runner_up;
    if (m.runner_up) { alt.textContent = `Also try ${m.runner_up.name}`; alt.href = m.runner_up.url; }
    result.hidden = false;
    result.classList.remove("is-new");
    void result.offsetWidth; // restart the entrance animation
    result.classList.add("is-new");

    // newest first, five at most
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.className = "recent__row";
    a.href = m.tester_url;
    const q = Object.assign(document.createElement("span"), { className: "recent__q", textContent: m.query });
    const f = Object.assign(document.createElement("span"), { className: "recent__face", textContent: m.face.name });
    f.style.fontFamily = `'${m.face.family}'`;
    const arrow = Object.assign(document.createElement("span"), { className: "recent__go mono", textContent: "→" });
    arrow.setAttribute("aria-hidden", "true");
    a.append(q, f, arrow);
    li.append(a);
    recent.prepend(li);
    while (recent.children.length > 5) recent.lastElementChild.remove();
    recentWrap.hidden = false;
  };

  form.addEventListener("submit", async e => {
    e.preventDefault();
    if (busy) return;
    const q = input.value.trim();
    if (q.length < 3) {
      showError(q ? "Add a few more words, like what it's for and how it should feel." : "Describe what you're setting first.");
      input.focus();
      return;
    }
    busy = true;
    go.setAttribute("aria-busy", "true");
    showError("");
    try {
      const res = await fetch(form.action, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: new FormData(form),
        credentials: "same-origin",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Couldn't match that. Try again.");
      render(data);
    } catch (err) {
      showError(err instanceof TypeError ? "Can't reach the server. Check your connection and try again." : err.message);
    } finally {
      busy = false;
      go.removeAttribute("aria-busy");
    }
  });

  form.querySelectorAll("[data-example]").forEach(b => b.addEventListener("click", () => {
    input.value = b.dataset.example;
    form.requestSubmit();
  }));
})();

// Assistant: chat widget on every page. Answers from the FAQ and error codes,
// offers a support ticket when it can't answer, and lets visitors rate replies.
(() => {
  const root = document.querySelector("[data-assistant]");
  if (!root) return;
  const panel = root.querySelector(".assistant__panel");
  const launch = root.querySelector(".assistant__launch");
  const log = root.querySelector("[data-log]");
  const form = root.querySelector("[data-form]");
  const input = root.querySelector("#assistant-input");
  const send = root.querySelector(".assistant__send");
  const suggest = root.querySelector("[data-suggest]");
  const { chatUrl, feedbackUrl, ticketUrl } = root.dataset;
  const store = {
    get(k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch (e) { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
  };
  const session = store.get("assistant-session") ||
    (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "") : String(Date.now()) + Math.random().toString(36).slice(2));
  store.set("assistant-session", session);
  let history = store.get("assistant-history") || [];  // replayed so the chat follows you between pages
  let busy = false;

  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    children.filter(Boolean).forEach(c => node.append(c));
    return node;
  };
  const scroll = () => { log.scrollTop = log.scrollHeight; };

  const open = (focus = true) => {
    panel.hidden = false;
    launch.setAttribute("aria-expanded", "true");
    store.set("assistant-open", true);
    scroll();
    if (focus) input.focus();
  };
  const close = () => {
    panel.hidden = true;
    launch.setAttribute("aria-expanded", "false");
    store.set("assistant-open", false);
    launch.focus();
  };
  root.querySelectorAll("[data-assistant-toggle]").forEach(b =>
    b.addEventListener("click", () => (panel.hidden ? open() : close())));
  panel.addEventListener("keydown", e => { if (e.key === "Escape") close(); });

  const remember = entry => {
    history.push(entry);
    history = history.slice(-30);
    store.set("assistant-history", history);
  };

  const userBubble = text => log.append(el("li", { className: "msg msg--user" }, el("p", { textContent: text })));

  const rateRow = id => {
    if (!id) return null;
    const row = el("div", { className: "msg__rate" }, el("span", { textContent: "Helpful?" }));
    [["Yes", true], ["No", false]].forEach(([label, helpful]) => {
      const b = el("button", { type: "button", textContent: label });
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", async () => {
        row.querySelectorAll("button").forEach(x => { x.disabled = true; x.setAttribute("aria-pressed", String(x === b)); });
        try {
          await fetch(feedbackUrl, { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id, helpful }) });
          row.append(el("span", { textContent: helpful ? "Thanks!" : "Thanks. Ask again in other words, or open a ticket." }));
        } catch (e) { /* rating is best-effort */ }
      });
      row.append(b);
    });
    return row;
  };

  const ticketForm = question => {
    const f = el("form", { className: "ticket", noValidate: true });
    const id = Math.random().toString(36).slice(2, 8);
    const email = el("input", { type: "email", id: `t-email-${id}`, value: root.dataset.email || "", autocomplete: "email", required: true });
    const name = el("input", { type: "text", id: `t-name-${id}`, autocomplete: "name", maxLength: 80 });
    const q = el("textarea", { id: `t-q-${id}`, value: question, maxLength: 2000, rows: 3 });
    const err = el("p", { className: "ticket__error", role: "alert", hidden: true });
    f.append(
      el("label", { htmlFor: email.id, textContent: "Your email" }), email,
      el("label", { htmlFor: name.id, textContent: "Name (optional)" }), name,
      el("label", { htmlFor: q.id, textContent: "Your question" }), q, err,
      el("button", { className: "button", type: "submit", textContent: "Open a support ticket" }),
    );
    f.addEventListener("submit", async e => {
      e.preventDefault();
      err.hidden = true;
      if (!email.value.trim() || !email.checkValidity()) {
        err.textContent = "Enter a valid email address so we can reply.";
        err.hidden = false;
        email.focus();
        return;
      }
      const button = f.querySelector("button");
      button.disabled = true;
      try {
        const res = await fetch(ticketUrl, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.value.trim(), name: name.value.trim(), question: q.value.trim(), session_id: session }) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Couldn't open the ticket. Try again.");
        f.replaceWith(el("p", { className: "ticket__done", textContent: data.text }));
        remember({ who: "bot", text: data.text });
        scroll();
      } catch (ex) {
        err.textContent = ex instanceof TypeError ? "Can't reach the server. Check your connection." : ex.message;
        err.hidden = false;
        button.disabled = false;
      }
    });
    return f;
  };

  const botBubble = (data, question) => {
    const li = el("li", { className: "msg msg--bot" + (data.error ? " msg--error" : "") }, el("p", { textContent: data.text }));
    if (data.items && data.items.length) {  // website review: what to change, where and why
      const ol = el("ol", { className: "msg__items" });
      data.items.forEach(it => ol.append(el("li", {},
        el("b", { textContent: `${it.where}: ${it.change}` }), el("span", { textContent: it.why }))));
      li.append(ol);
    }
    if (data.code) {
      const pre = el("pre", {}, el("code", { textContent: data.code }));
      const copy = el("button", { type: "button", className: "msg__copy", textContent: "Copy" });
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(data.code); copy.textContent = "Copied"; }
        catch (e) { copy.textContent = "Select and copy"; }
        setTimeout(() => { copy.textContent = "Copy"; }, 1500);
      });
      li.append(el("div", { className: "msg__code" }, pre, copy));
    }
    if (data.source) li.append(el("a", { className: "msg__source", href: data.source.url, textContent: data.kind === "faq" || data.kind === "error_code" ? `Source: ${data.source.title}` : data.source.title }));
    if (data.related && data.related.length) {
      const rel = el("div", { className: "msg__related" });
      data.related.forEach(r => rel.append(el("button", { className: "chip", type: "button", textContent: r, onclick: () => ask(r) })));
      li.append(rel);
    }
    if (data.offer_ticket) li.append(ticketForm(question));
    else if (data.id) li.append(rateRow(data.id));
    log.append(li);
  };

  const ask = async text => {
    text = (text || "").trim();
    if (!text || busy) return;
    if (panel.hidden) open(false);
    busy = true;
    send.disabled = true;
    suggest.hidden = true;
    input.value = "";
    userBubble(text);
    remember({ who: "user", text });
    const typing = el("li", { className: "msg msg--bot msg--typing", ariaLabel: "Assistant is typing" },
      el("span", { textContent: "•" }), el("span", { textContent: "•" }), el("span", { textContent: "•" }));
    log.append(typing);
    scroll();
    try {
      const res = await fetch(chatUrl, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session, page: location.pathname }) });
      const data = await res.json().catch(() => ({}));
      typing.remove();
      if (!res.ok) {
        botBubble({ error: true, text: data.error || `Something went wrong (error ${res.status}).` }, text);
      } else {
        botBubble(data, text);
        remember({ who: "bot", text: data.text, source: data.source });
      }
    } catch (e) {
      typing.remove();
      botBubble({ error: true, text: "Can't reach the server. Check your connection and try again." }, text);
    } finally {
      busy = false;
      send.disabled = false;
      scroll();
      if (!panel.hidden) input.focus();
    }
  };

  form.addEventListener("submit", e => { e.preventDefault(); ask(input.value); });
  // "Ask the assistant" buttons anywhere on the page (error pages, FAQ, suggestions)
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-ask]");
    if (!b) return;
    if (b.dataset.ask) ask(b.dataset.ask);
    else open();
  });

  // Restore the conversation from earlier pages in this tab
  if (history.length) {
    suggest.hidden = true;
    history.forEach(h => h.who === "user"
      ? userBubble(h.text)
      : log.append(el("li", { className: "msg msg--bot" }, el("p", { textContent: h.text }),
          h.source ? el("a", { className: "msg__source", href: h.source.url, textContent: `Source: ${h.source.title}` }) : null)));
  }
  if (store.get("assistant-open")) open(false);
})();

// Typeface page: when the font last changed in google/fonts (GitHub API, with server-side timeout and fallback)
(() => {
  const box = document.querySelector("[data-history]");
  if (!box) return;
  const value = box.querySelector("[data-history-value]");
  fetch(box.dataset.history, { headers: { Accept: "application/json" } })
    .then(r => r.json())
    .then(d => {
      value.textContent = "";
      if (d.status === "ok" && d.date) {
        const when = new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
        value.append(`${when} · `);
        value.append(Object.assign(document.createElement("a"), { href: d.url, textContent: d.message, target: "_blank", rel: "noopener" }));
        if (d.source === "stale") value.append(" (saved copy: GitHub is slow right now)");
      } else {
        value.textContent = d.text || "Unavailable right now.";
      }
    })
    .catch(() => { value.textContent = "Unavailable right now."; });
})();

// Submit form: after a failed send, put focus on the first field that needs fixing
document.querySelector('[aria-invalid="true"]')?.focus();

// Glyph inspector
(() => {
  const view = document.querySelector("[data-glyph-view]");
  if (!view) return;
  const name = document.querySelector("[data-glyph-name]");
  const code = document.querySelector("[data-glyph-code]");
  const buttons = document.querySelectorAll("[data-glyph]");
  const show = btn => {
    const g = btn.dataset.glyph;
    view.textContent = g;
    name.textContent = g;
    code.textContent = "U+" + g.codePointAt(0).toString(16).toUpperCase().padStart(4, "0");
    buttons.forEach(b => b.setAttribute("aria-pressed", b === btn));
  };
  buttons.forEach(b => {
    b.addEventListener("mouseenter", () => show(b));
    b.addEventListener("focus", () => show(b));
    b.addEventListener("click", () => show(b));
  });
  show(buttons[0]);
})();
