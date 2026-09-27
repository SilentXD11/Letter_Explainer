/* Letter Explainer: front-end.
 * Plain JavaScript, no build step. Letters are saved in localStorage on this
 * device only (never on the server). All user/OCR text is inserted with
 * textContent, never innerHTML, to avoid XSS.
 */
"use strict";

// ---------------------------------------------------------------- constants
const LANGS = {
  English: "en-GB", Hindi: "hi-IN", Marathi: "mr-IN", Gujarati: "gu-IN", Punjabi: "pa-IN",
  Bengali: "bn-IN", Tamil: "ta-IN", Urdu: "ur-PK", Polish: "pl-PL", Romanian: "ro-RO",
  Arabic: "ar-SA", Spanish: "es-ES", Portuguese: "pt-PT", French: "fr-FR", Italian: "it-IT",
  Somali: "so-SO", Turkish: "tr-TR", Ukrainian: "uk-UA",
};
const TYPE_ICONS = {
  tax: "🧾", council_tax: "🏛️", benefits: "🤝", energy_bill: "⚡", health: "🏥", parking_fine: "🚗",
  housing: "🏠", bank_or_debt: "🏦", immigration_or_visa: "🛂", tv_licence: "📺", general: "✉️",
};
const TYPE_NAMES = {
  tax: "Tax", council_tax: "Council tax", benefits: "Benefits", energy_bill: "Energy bill", health: "Health",
  parking_fine: "Parking fine", housing: "Housing", bank_or_debt: "Bank or debt", immigration_or_visa: "Visa",
  tv_licence: "TV licence", general: "Letter",
};
const STORE_KEY = "le.letters.v1";
const PREFS_KEY = "le.prefs.v1";

// Example letters so first-time visitors can see the value instantly.
function exampleLetters() {
  const d = (n) => { const x = new Date(); x.setDate(x.getDate() + n); return x.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }); };
  return [
    { label: "🏛️ Council tax reminder", text:
`Riverside Borough Council
Council Tax Department, 10 High Street, London E1 7AA

Date: ${d(-6)}
Account number: CT-4829-1173

Dear Resident,

FINAL REMINDER: Council Tax arrears

Our records show that you have not paid the instalment of £142.50 that was due on ${d(-20)}. The total amount now outstanding for this year is £1,282.50.

You must pay the missed instalment of £142.50 by ${d(8)}. If you do not pay within 7 days of this notice, you will lose the right to pay by instalments and the full balance will become due. We may then apply to the magistrates court for a liability order, which could add costs of £90.00.

How to pay: online at www.riverside.gov.uk/pay, or by phone on 020 7946 0000. Please quote your account number. If you are having difficulty paying, please contact us as soon as possible to discuss a payment arrangement or a discount.

Yours sincerely,
Revenue and Benefits Team` },
    { label: "🏥 NHS appointment", text:
`Northfield NHS Hospital Trust
Outpatients Department

NHS number reference: NHS-554-221-9087
Date: ${d(-2)}

Dear Patient,

We are pleased to offer you an appointment at the Cardiology Clinic on ${d(12)} at 10:30am, Building B, Level 2.

Please arrive 15 minutes early and bring a list of any medicines you take. If you cannot attend, you must call us on 020 7946 0321 at least 48 hours before so we can offer the slot to another patient. Please respond by ${d(5)} to confirm you will attend.

Yours sincerely,
Appointments Team` },
    { label: "⚠️ Suspicious 'HMRC' letter", text:
`HM Revenue and Customs
Tax Refund Department

Reference: TR-99812-X

Dear Customer,

After the last annual calculation of your fiscal activity we have determined that you are eligible to receive a tax refund of £864.20.

To receive your refund you must pay a processing fee of £45.00 using an iTunes gift card or bitcoin within 24 hours. Please click the link in our email and confirm your bank details and your PIN. Act now or your refund will be cancelled and you may face legal action.

HMRC Refunds Team` },
  ];
}

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Tiny DOM builder: h("div", {class: "x", onclick}, "text", childNode, [...]) */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const store = {
  read(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  write(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: ignore */ } },
  letters() { return this.read(STORE_KEY, []); },
  saveLetters(list) { this.write(STORE_KEY, list); },
  get(id) { return this.letters().find((l) => l.id === id); },
  upsert(item) { const list = this.letters().filter((l) => l.id !== item.id); list.unshift(item); this.saveLetters(list.slice(0, 100)); },
  remove(id) { this.saveLetters(this.letters().filter((l) => l.id !== id)); },
};
const prefs = Object.assign({ theme: null, big: false, language: "English" }, store.read(PREFS_KEY, {}));
const savePrefs = () => store.write(PREFS_KEY, prefs);

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const todayISO = () => new Date().toISOString().slice(0, 10);
const isISODate = (s) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s);

function daysUntil(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  const now = new Date(); now.setHours(0, 0, 0, 0);
  return Math.round((target - now) / 86400000);
}
function prettyDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}
function relDays(n) {
  if (n === 0) return "today";
  if (n === 1) return "tomorrow";
  if (n === -1) return "yesterday";
  return n > 0 ? `in ${n} days` : `${-n} days ago`;
}
const urgencyClass = (n) => (n < 0 || n <= 3 ? "soon" : n <= 10 ? "mid" : "far");
const fmtSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.round(b / 1024) + " KB");

let toastTimer;
function toast(msg, action) {
  const t = $("#toast");
  t.replaceChildren(h("span", null, msg));
  if (action) t.append(h("button", { onclick: () => { action.fn(); t.classList.remove("show"); } }, action.label));
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), action ? 6000 : 2600);
}

function confetti() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const box = $("#confetti");
  const colors = ["#4338ca", "#db2777", "#1f8a53", "#f59e0b", "#06b6d4"];
  for (let i = 0; i < 70; i++) {
    box.append(h("i", { style: `left:${Math.random() * 100}vw;background:${colors[i % colors.length]};animation-delay:${Math.random() * 0.4}s;animation-duration:${1.4 + Math.random()}s` }));
  }
  setTimeout(() => box.replaceChildren(), 2600);
}

async function copyText(text, label = "Copied") {
  try { await navigator.clipboard.writeText(text); toast(`✓ ${label}`); }
  catch { toast("Couldn't copy. Select the text and copy it manually."); }
}

// --------------------------------------------------------- letter helpers
/** Everything we need about a saved letter's tasks & deadlines. */
function tasksOf(item) {
  const e = item.response.explanation;
  // Never turn a scam's demands ("pay with a gift card") into a to-do list.
  if (!e || e.scam_warning) return [];
  const tasks = e.actions.map((a, i) => ({ i, text: a.action, deadline: a.deadline, done: item.done.includes(i) }));
  // If the explanation has dated deadlines not attached to any action, surface them as tasks too.
  // Past dates ("was due on …") are history, not tasks.
  e.deadlines.forEach((d) => {
    if (d.date >= todayISO() && !tasks.some((t) => t.deadline === d.date)) {
      const i = 1000 + tasks.length;
      tasks.push({ i, text: d.description, deadline: d.date, done: item.done.includes(i) });
    }
  });
  return tasks;
}
function nextDeadline(item) {
  const open = tasksOf(item).filter((t) => !t.done && isISODate(t.deadline));
  const e = item.response.explanation;
  const dates = open.map((t) => ({ date: t.deadline, text: t.text }));
  if (e?.scam_warning) return null;
  if (!dates.length && e) e.deadlines.forEach((d) => dates.push({ date: d.date, text: d.description }));
  const upcoming = dates.filter((d) => d.date >= todayISO()).sort((a, b) => a.date.localeCompare(b.date));
  if (upcoming.length) return upcoming[0];
  const openPast = open.filter((t) => t.deadline < todayISO()).sort((a, b) => b.deadline.localeCompare(a.deadline));
  return openPast.length ? { date: openPast[0].deadline, text: openPast[0].text } : null;
}
function titleOf(item) {
  const e = item.response.explanation;
  if (!e) return "Letter (couldn't read)";
  return e.sender || TYPE_NAMES[e.letter_type] || "Letter";
}
function progressOf(item) {
  const tasks = tasksOf(item);
  return { done: tasks.filter((t) => t.done).length, total: tasks.length };
}

function makeICS(item) {
  const e = item.response.explanation;
  const stamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  const esc = (s) => String(s).replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/[,;]/g, (m) => "\\" + m);
  const seen = new Set();
  const events = [];
  tasksOf(item).filter((t) => isISODate(t.deadline)).forEach((t) => {
    if (seen.has(t.deadline + t.text)) return;
    seen.add(t.deadline + t.text);
    const day = t.deadline.replace(/-/g, "");
    const [y, m, d] = t.deadline.split("-").map(Number);
    const next = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10).replace(/-/g, "");
    events.push([
      "BEGIN:VEVENT", `UID:${item.id}-${events.length}@letter-explainer`, `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${next}`,
      `SUMMARY:${esc(`${titleOf(item)}: ${t.text}`.slice(0, 140))}`,
      `DESCRIPTION:${esc(`${e.summary}\n\nReference: ${e.reference_numbers.join(", ") || "n/a"}`)}`,
      "BEGIN:VALARM", "TRIGGER:-P2D", "ACTION:DISPLAY", `DESCRIPTION:${esc("Reminder: " + t.text.slice(0, 100))}`, "END:VALARM",
      "END:VEVENT",
    ].join("\r\n"));
  });
  if (!events.length) return null;
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Letter Explainer//EN", "CALSCALE:GREGORIAN", ...events, "END:VCALENDAR"].join("\r\n");
}
function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = h("a", { href: url, download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ------------------------------------------------------------ read aloud
const speech = {
  on: false,
  supported: "speechSynthesis" in window,
  speak(text, language, btn) {
    if (!this.supported) return toast("Read-aloud isn't supported in this browser.");
    if (this.on) return this.stop();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = LANGS[language] || "en-GB";
    u.rate = 0.95;
    const voice = speechSynthesis.getVoices().find((v) => v.lang === u.lang) || speechSynthesis.getVoices().find((v) => v.lang.startsWith(u.lang.slice(0, 2)));
    if (voice) u.voice = voice;
    u.onend = u.onerror = () => this.stop();
    this.btn = btn; this.on = true;
    btn?.setAttribute("aria-pressed", "true");
    if (btn) btn.lastChild.textContent = " Stop";
    speechSynthesis.cancel(); speechSynthesis.speak(u);
  },
  stop() {
    if (this.supported) speechSynthesis.cancel();
    this.on = false;
    if (this.btn) { this.btn.setAttribute("aria-pressed", "false"); this.btn.lastChild.textContent = " Listen"; }
  },
};

// ---------------------------------------------------------------- views
const views = ["home", "working", "result", "letters"];
function show(view) {
  speech.stop();
  views.forEach((v) => $(`#view-${v}`).classList.toggle("hidden", v !== view));
  $$(".nav-link").forEach((a) => a.classList.toggle("active", a.dataset.nav === (view === "result" ? "letters" : view === "working" ? "home" : view)));
  window.scrollTo(0, 0);
}

function route() {
  const hash = location.hash.slice(1);
  if (hash === "letters") { renderLetters(); show("letters"); }
  else if (hash.startsWith("letter/")) {
    const item = store.get(hash.slice(7));
    if (item) { renderResult(item); show("result"); } else { location.hash = "letters"; }
  } else { renderUpcoming(); show("home"); }
  updateCount();
}

function updateCount() {
  const n = store.letters().length;
  const c = $("#navCount");
  c.textContent = n; c.classList.toggle("hidden", !n);
}

// --------------------------------------------------------------- home
let chosenFile = null;
let mode = "photo";

function setMode(m) {
  mode = m;
  $$(".mode").forEach((b) => { const on = b.dataset.mode === m; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
  $("#mode-photo").classList.toggle("hidden", m !== "photo");
  $("#mode-text").classList.toggle("hidden", m !== "text");
  if (m === "text") $("#pasteText").focus();
  updateGo();
}
function updateGo() {
  $("#go").disabled = mode === "photo" ? !chosenFile : $("#pasteText").value.trim().length < 20;
}
function chooseFile(file) {
  if (!file) return;
  if (!/^image\/|application\/pdf/.test(file.type) && !/\.(pdf|jpe?g|png|webp|heic)$/i.test(file.name)) {
    return toast("Please choose a photo (JPG, PNG) or a PDF.");
  }
  if (file.size > 10 * 1048576) return toast("That file is over 10 MB. Try a smaller photo.");
  chosenFile = file;
  if (mode !== "photo") setMode("photo");
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  $("#dropEmpty").classList.add("hidden");
  $("#dropFull").classList.remove("hidden");
  $("#preview").classList.toggle("hidden", isPdf);
  $("#pdfBadge").classList.toggle("hidden", !isPdf);
  if (!isPdf) $("#preview").src = URL.createObjectURL(file);
  $("#fileName").textContent = file.name || "Pasted image";
  $("#fileSize").textContent = fmtSize(file.size);
  updateGo();
}
function clearFile() {
  chosenFile = null;
  $("#camera").value = $("#file").value = "";
  $("#dropEmpty").classList.remove("hidden");
  $("#dropFull").classList.add("hidden");
  updateGo();
}

function renderUpcoming() {
  const box = $("#upcoming");
  const items = store.letters()
    .map((it) => ({ it, nd: nextDeadline(it) }))
    .filter((x) => x.nd && progressOf(x.it).done < progressOf(x.it).total)
    .sort((a, b) => a.nd.date.localeCompare(b.nd.date))
    .slice(0, 6);
  if (!items.length) { box.classList.add("hidden"); return; }
  const soon = items.filter((x) => daysUntil(x.nd.date) <= 7).length;
  box.replaceChildren(
    h("div", { class: "upcoming-head" },
      h("h2", null, soon ? `⏰ ${soon} ${soon === 1 ? "thing" : "things"} due this week` : "📌 Coming up"),
      h("a", { href: "#letters", class: "small" }, "See all letters")),
    h("div", { class: "upcoming-row" }, items.map(({ it, nd }) => {
      const n = daysUntil(nd.date);
      return h("button", { class: `due-card ${urgencyClass(n)}`, onclick: () => (location.hash = `letter/${it.id}`) },
        h("div", { class: "when" }, n < 0 ? `Overdue ${-n}d` : n === 0 ? "Due today" : `${n} day${n === 1 ? "" : "s"} left`),
        h("div", { class: "muted small" }, `${TYPE_ICONS[it.response.explanation?.letter_type] || "✉️"} ${titleOf(it)}`),
        h("div", { class: "what" }, nd.text));
    })));
  box.classList.remove("hidden");
}

// ----------------------------------------------------------- processing
let stepTimer;
function startWorking(isFile) {
  const steps = isFile
    ? ["Uploading your letter", "Straightening and sharpening the photo", "Reading the text", "Explaining it in plain words"]
    : ["Reading your text", "Finding dates, amounts and references", "Explaining it in plain words"];
  const ol = $("#steps");
  ol.replaceChildren(...steps.map((s) => h("li", null, s)));
  let i = 0;
  const lis = $$("li", ol);
  const tick = () => {
    lis.forEach((li, j) => { li.classList.toggle("done", j < i); li.classList.toggle("active", j === i); });
    if (i < lis.length - 1) { i++; stepTimer = setTimeout(tick, isFile ? 1800 : 900); }
  };
  tick();
  show("working");
}
const stopWorking = () => clearTimeout(stepTimer);

async function submit(kind, payload, language) {
  startWorking(kind === "file");
  try {
    let res;
    if (kind === "file") {
      const form = new FormData();
      form.append("file", payload);
      form.append("language", language);
      res = await fetch("/api/explain", { method: "POST", body: form });
    } else {
      res = await fetch("/api/explain-text", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: payload, language }) });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = data.detail;
      throw new Error(Array.isArray(d) ? d[0]?.msg : d || `Something went wrong (${res.status})`);
    }
    return data;
  } finally {
    stopWorking();
  }
}

async function explainNew(kind, payload) {
  const language = $("#language").value;
  try {
    const data = await submit(kind, payload, language);
    const item = { id: uid(), createdAt: new Date().toISOString(), language, done: [], response: data };
    if (data.explanation) store.upsert(item);
    clearFile(); $("#pasteText").value = ""; setMode("photo");
    if (data.explanation) { location.hash = `letter/${item.id}`; toast("✓ Saved to My letters"); }
    else { renderResult(item); show("result"); } // unreadable: don't save, show retake advice
  } catch (err) {
    show("home");
    toast("⚠️ " + err.message);
  }
}

async function reExplain(item, text) {
  try {
    const data = await submit("text", text, item.language);
    // Keep the original extraction info (method, confidence) but with the corrected text.
    data.extraction = { ...item.response.extraction, text, method: item.response.extraction.method === "user_text" ? "user_text" : item.response.extraction.method + " + your corrections", needs_retake: false };
    const updated = { ...item, response: data, done: [] };
    store.upsert(updated);
    if (location.hash === `#letter/${updated.id}`) route(); else location.hash = `letter/${updated.id}`;
    toast("✓ Explained again with your corrections");
  } catch (err) {
    renderResult(item); show("result");
    toast("⚠️ " + err.message);
  }
}

function goHome(ev) {
  ev?.preventDefault();
  if (location.hash) location.hash = ""; else route();
}

// --------------------------------------------------------------- result
function renderResult(item) {
  const view = $("#view-result");
  const { extraction: x, explanation: e, provider } = item.response;
  const saved = !!store.get(item.id);

  const back = h("a", { class: "back", href: saved ? "#letters" : "#", onclick: saved ? null : goHome }, "← ", saved ? "My letters" : "Back");

  // Unreadable photo: only advice + editable text.
  if (!e) {
    view.replaceChildren(back,
      h("div", { class: "banner warn" }, h("span", { class: "ico" }, "📷"),
        h("div", null, h("strong", null, "We couldn't read this photo clearly"),
          h("ul", null, [...new Set([...(x.retake_tips || []), ...(x.warnings || [])])].map((t) => h("li", null, t))))),
      h("div", { class: "card" },
        h("h2", null, "Two ways to fix this"),
        h("div", { class: "row" }, h("button", { class: "btn primary", onclick: (ev) => { goHome(ev); $("#camera").click(); } }, "📷 Take a clearer photo")),
        h("p", { class: "section-label" }, "Or correct the text we read and try again"),
        textPanel(item)));
    return;
  }

  const nd = nextDeadline(item);
  const tasks = tasksOf(item);
  const n = nd ? daysUntil(nd.date) : null;

  const listenBtn = h("button", { class: "btn sm", "aria-pressed": "false", onclick: (ev) => speech.speak(speakable(e), item.language, ev.currentTarget) }, "🔊", " Listen");
  const ics = makeICS(item);

  const head = h("div", { class: `card res-head u-${e.urgency}` },
    h("div", { class: "res-top" },
      h("div", { class: "type-icon", "aria-hidden": "true" }, TYPE_ICONS[e.letter_type] || "✉️"),
      h("div", { class: "res-title" },
        h("h1", null, titleOf(item)),
        h("div", { class: "meta" }, `${TYPE_NAMES[e.letter_type] || "Letter"} · explained ${new Date(item.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`)),
      e.scam_warning
        ? h("span", { class: "pill high" }, "Possible scam")
        : h("span", { class: `pill ${e.urgency}`, title: e.urgency_reason }, `${e.urgency[0].toUpperCase() + e.urgency.slice(1)} urgency`)),
    h("p", { class: "summary" }, e.summary),
    nd && h("div", { class: `countdown ${n < 0 ? "past" : urgencyClass(n)}` },
      h("div", { class: "days" }, n < 0 ? -n : n, h("small", null, n < 0 ? "days late" : n === 1 ? "day left" : "days left")),
      h("div", null, h("strong", null, n < 0 ? `This date passed ${relDays(n)}` : `Deadline ${relDays(n)}, ${prettyDate(nd.date)}`),
        h("div", { class: "muted small" }, nd.text))),
    h("div", { class: "actions-bar" },
      listenBtn,
      ics && h("button", { class: "btn sm", onclick: () => { download(`${titleOf(item).replace(/[^\w]+/g, "-")}-deadlines.ics`, ics, "text/calendar"); toast("📅 Open the file to add reminders to your calendar"); } }, "📅 Add to calendar"),
      h("button", { class: "btn sm", onclick: () => window.print() }, "🖨️ Print"),
      h("a", { class: "btn sm", href: "#", onclick: goHome }, "✨ New letter")));

  const banners = [];
  if (e.scam_warning) banners.push(h("div", { class: "banner danger", role: "alert" }, h("span", { class: "ico" }, "🚨"), h("div", null, h("strong", null, "This could be a scam"), h("p", null, e.scam_warning))));
  const warnings = (x.warnings || []).filter(Boolean);
  if (warnings.length) banners.push(h("div", { class: "banner warn" }, h("span", { class: "ico" }, "ℹ️"), h("div", null, h("strong", null, "Please check the text"), h("ul", null, warnings.map((w) => h("li", null, w))))));

  // Tabs
  const prog = progressOf(item);
  const tabDefs = [
    ["summary", "Summary", null, () => summaryPanel(e)],
    ["todo", "To-do", tasks.length ? `${prog.done}/${prog.total}` : null, () => todoPanel(item)],
    ["details", "Details", null, () => detailsPanel(e)],
    ["reply", "Reply", null, () => replyPanel(item)],
    ["text", "Original text", null, () => textPanel(item)],
  ];
  const tabBar = h("div", { class: "tabs", role: "tablist" });
  const panels = h("div");
  const tabBtns = tabDefs.map(([id, label, badge, build], idx) => {
    const panel = h("div", { class: "panel", role: "tabpanel", id: `panel-${id}` }, build());
    panel.classList.toggle("hidden", idx !== 0);
    panels.append(panel);
    const b = h("button", { class: "tab" + (idx === 0 ? " active" : ""), role: "tab", "aria-selected": idx === 0, "aria-controls": `panel-${id}`, dataset: { tab: id } }, label, badge && h("span", { class: "badge" }, badge));
    b.addEventListener("click", () => selectTab(id));
    return b;
  });
  tabBar.append(...tabBtns);
  function selectTab(id) {
    tabBtns.forEach((b) => { const on = b.dataset.tab === id; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
    $$(".panel", panels).forEach((p) => p.classList.toggle("hidden", p.id !== `panel-${id}`));
  }

  const body = h("div", { class: "card" }, tabBar, panels,
    h("p", { class: "disclaimer" }, `${e.disclaimer} Explained by: ${provider}.`));

  view.replaceChildren(back, ...banners, head, body);
  if (e.scam_warning || (tasks.length > 0 && e.urgency !== "low")) selectTab("todo");
}

function speakable(e) {
  const parts = [e.summary];
  if (e.actions.length) parts.push("What you need to do.", ...e.actions.map((a) => a.action));
  if (e.scam_warning) parts.push("Warning.", e.scam_warning);
  return parts.join(" ");
}

function summaryPanel(e) {
  return h("div", null,
    e.urgency_reason && h("p", { class: "muted" }, e.urgency_reason),
    e.key_points.length > 0 && [h("p", { class: "section-label" }, "Key points"), h("ul", { class: "kp" }, e.key_points.map((k) => h("li", null, k)))],
    e.glossary.length > 0 && [h("p", { class: "section-label" }, "Tricky words: tap to see what they mean"),
      h("div", { class: "gloss" }, e.glossary.map((g) => h("button", {
        "aria-expanded": "false",
        onclick: (ev) => { const b = ev.currentTarget; b.setAttribute("aria-expanded", b.getAttribute("aria-expanded") !== "true"); },
      }, g.term, h("span", { class: "def" }, g.meaning))))]);
}

function todoPanel(item) {
  if (item.response.explanation.scam_warning) {
    return h("div", { class: "banner danger" }, h("span", { class: "ico" }, "🛑"), h("div", null,
      h("strong", null, "We've hidden the to-do list because this looks like a scam"),
      h("ul", null,
        h("li", null, "Don't pay anything, click links, or share bank details, PINs or passwords."),
        h("li", null, "Contact the organisation using a phone number from its official website, not one from the letter."),
        h("li", null, "You can report scams to Action Fraud (actionfraud.police.uk) or by calling 0300 123 2040."))));
  }
  const tasks = tasksOf(item);
  if (!tasks.length) return h("p", { class: "muted" }, "Nothing to do. This letter looks like information only. 🎉");
  const bar = h("div");
  const label = h("span", { class: "small muted" });
  const setProgress = () => {
    const done = item.done.length;
    const total = tasks.length;
    bar.style.width = `${(done / total) * 100}%`;
    label.textContent = done === total ? "All done! 🎉" : `${done} of ${total} done`;
    const badge = $('.tab[data-tab="todo"] .badge');
    if (badge) badge.textContent = `${done}/${total}`;
  };
  const list = h("ul", { class: "todo" }, tasks.map((t) => {
    const nd = isISODate(t.deadline) ? daysUntil(t.deadline) : null;
    const li = h("li", { class: t.done ? "done" : "" });
    const cb = h("input", { type: "checkbox", checked: t.done, "aria-label": "Mark as done" });
    cb.addEventListener("change", () => {
      item.done = cb.checked ? [...new Set([...item.done, t.i])] : item.done.filter((i) => i !== t.i);
      li.classList.toggle("done", cb.checked);
      store.upsert(item);
      setProgress();
      if (cb.checked && item.done.length === tasks.length) { confetti(); toast("🎉 All done! Nice work."); }
    });
    li.append(h("label", null, cb, h("span", { class: "txt" }, t.text,
      t.deadline && h("span", null, h("br"), h("span", { class: `due-tag ${nd != null ? urgencyClass(nd) : ""}` },
        nd != null ? `📅 ${prettyDate(t.deadline)} · ${relDays(nd)}` : `⏱ ${t.deadline}`)))));
    return li;
  }));
  const wrap = h("div", null, h("div", { class: "progress" }, h("div", { class: "bar" }, bar), label), list);
  requestAnimationFrame(setProgress);
  return wrap;
}

function detailsPanel(e) {
  const today = todayISO();
  const any = e.amounts.length || e.reference_numbers.length || e.deadlines.length;
  return h("div", null,
    !any && h("p", { class: "muted" }, "No amounts, reference numbers or dates were found."),
    e.amounts.length > 0 && [h("p", { class: "section-label" }, "💷 Money mentioned"), h("div", { class: "money" }, e.amounts.map((a) => h("div", null, a)))],
    e.reference_numbers.length > 0 && [h("p", { class: "section-label" }, "🔢 Reference numbers: quote these when you call or write"),
      h("div", { class: "refs" }, e.reference_numbers.map((r) => h("div", { class: "ref" }, h("span", null, r), h("button", { class: "btn sm", onclick: () => copyText(r, "Reference copied") }, "Copy"))))],
    e.deadlines.length > 0 && [h("p", { class: "section-label" }, "📅 Dates"),
      h("ul", { class: "timeline" }, [...e.deadlines].sort((a, b) => a.date.localeCompare(b.date)).map((d) =>
        h("li", { class: d.date < today ? "past" : "" }, h("div", { class: "d" }, `${prettyDate(d.date)} · ${relDays(daysUntil(d.date))}`), h("div", null, d.description))))]);
}

function replyPanel(item) {
  const e = item.response.explanation;
  const ta = h("textarea", { "aria-label": "Draft reply" });
  ta.value = item.reply ?? e.draft_reply;
  ta.addEventListener("input", () => { item.reply = ta.value; store.upsert(item); });
  const subject = `Re: ${e.reference_numbers[0] ? "Reference " + e.reference_numbers[0] : "your letter"}`;
  return h("div", { class: "reply" },
    h("p", { class: "muted" }, "Fill in anything in [square brackets]. Your changes are saved automatically."),
    ta,
    h("div", { class: "row" },
      h("button", { class: "btn primary sm", onclick: () => copyText(ta.value, "Reply copied") }, "📋 Copy reply"),
      h("a", { class: "btn sm", href: "#", onclick: (ev) => { ev.preventDefault(); location.href = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(ta.value)}`; } }, "✉️ Open in email"),
      h("button", { class: "btn sm", onclick: () => { ta.value = e.draft_reply; item.reply = null; store.upsert(item); } }, "↺ Reset")));
}

function textPanel(item) {
  const x = item.response.extraction;
  const ta = h("textarea", { "aria-label": "Text read from your letter" });
  ta.value = x.text;
  const conf = x.confidence;
  return h("div", null,
    h("div", { class: "meter" },
      h("span", null, `Read using: ${x.method.replace(/_/g, " ")}`),
      conf != null && [h("div", { class: "bar" }, h("div", { style: `width:${conf}%;background:${conf >= 80 ? "var(--low)" : conf >= 60 ? "var(--med)" : "var(--high)"}` })), h("span", null, `${Math.round(conf)}% sure`)]),
    h("p", { class: "muted small" }, "Did we misread something? Fix it here and explain again."),
    ta,
    h("div", { class: "row" }, h("button", { class: "btn primary sm", onclick: () => {
      if (ta.value.trim().length < 20) return toast("Please enter a bit more text.");
      reExplain(item, ta.value);
    } }, "🔄 Explain again")));
}

// ---------------------------------------------------------- my letters
let filter = "all";
function renderLetters() {
  const q = $("#search").value.trim().toLowerCase();
  const all = store.letters();
  const list = all.filter((it) => {
    const e = it.response.explanation;
    const p = progressOf(it);
    if (filter === "todo" && !(p.total && p.done < p.total)) return false;
    if (filter === "done" && !(p.total === 0 || p.done === p.total)) return false;
    if (filter === "high" && e?.urgency !== "high") return false;
    if (q && !`${titleOf(it)} ${e?.summary} ${e?.reference_numbers.join(" ")} ${it.response.extraction.text}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const openTasks = all.reduce((s, it) => { const p = progressOf(it); return s + (p.total - p.done); }, 0);
  $("#lettersStats").textContent = all.length
    ? `${all.length} letter${all.length === 1 ? "" : "s"} · ${openTasks ? `${openTasks} thing${openTasks === 1 ? "" : "s"} still to do` : "everything done ✓"}`
    : "";
  $("#lettersEmpty").classList.toggle("hidden", all.length > 0);
  $("#lettersList").replaceChildren(...(list.length || !all.length ? list : [h("p", { class: "muted" }, "No letters match.")]).map((it) => {
    if (!(it.response)) return it;
    const e = it.response.explanation;
    const p = progressOf(it);
    const nd = nextDeadline(it);
    const n = nd ? daysUntil(nd.date) : null;
    const card = h("div", { class: "letter-card", role: "link", tabindex: "0", onclick: () => (location.hash = `letter/${it.id}`),
      onkeydown: (ev) => { if (ev.key === "Enter") location.hash = `letter/${it.id}`; } },
      h("div", { class: "type-icon", "aria-hidden": "true" }, TYPE_ICONS[e?.letter_type] || "✉️"),
      h("div", { class: "body" },
        h("h3", null, titleOf(it), e && (e.scam_warning ? h("span", { class: "pill high" }, "scam?") : h("span", { class: `pill ${e.urgency}` }, e.urgency))),
        h("div", { class: "snip" }, e?.summary || ""),
        h("div", { class: "sub" },
          h("span", null, new Date(it.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })),
          p.total > 0 && h("span", null, h("span", { class: "mini-bar" }, h("div", { style: `width:${(p.done / p.total) * 100}%` })), ` ${p.done}/${p.total} done`),
          nd && p.done < p.total && h("span", { class: `due-tag ${urgencyClass(n)}` }, n < 0 ? `${-n}d overdue` : `due ${relDays(n)}`))),
      h("button", { class: "del", title: "Delete", "aria-label": `Delete ${titleOf(it)}`, onclick: (ev) => {
        ev.stopPropagation();
        store.remove(it.id); renderLetters(); updateCount();
        toast("Letter deleted", { label: "Undo", fn: () => { store.upsert(it); renderLetters(); updateCount(); } });
      } }, "🗑"));
    return card;
  }));
}

// ----------------------------------------------------------- theme & a11y
function applyPrefs() {
  const root = document.documentElement;
  if (prefs.theme) root.dataset.theme = prefs.theme; else delete root.dataset.theme;
  root.classList.toggle("big", prefs.big);
  $("#bigText").setAttribute("aria-pressed", prefs.big);
}
function currentTheme() {
  return prefs.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

// ------------------------------------------------------------------ init
function init() {
  // language select
  const sel = $("#language");
  sel.append(...Object.keys(LANGS).map((l) => h("option", { value: l, selected: l === prefs.language }, l)));
  sel.addEventListener("change", () => { prefs.language = sel.value; savePrefs(); });

  // theme / text size
  applyPrefs();
  if (!prefs.theme) document.documentElement.dataset.theme = currentTheme();
  $("#themeBtn").addEventListener("click", () => { prefs.theme = currentTheme() === "dark" ? "light" : "dark"; savePrefs(); applyPrefs(); });
  $("#bigText").addEventListener("click", () => { prefs.big = !prefs.big; savePrefs(); applyPrefs(); });

  // mode switch
  $$(".mode").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  $("#pasteText").addEventListener("input", updateGo);

  // file choice: camera, picker, drag & drop, paste
  ["#camera", "#file"].forEach((s) => $(s).addEventListener("change", (ev) => {
    chooseFile(ev.target.files[0]);
    if (location.hash) location.hash = "";
  }));
  $("#clearFile").addEventListener("click", (ev) => { ev.stopPropagation(); clearFile(); });
  const drop = $("#drop");
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (ev) => { setMode("photo"); chooseFile(ev.dataTransfer.files[0]); });
  drop.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); $("#file").click(); } });
  document.addEventListener("paste", (ev) => {
    const f = [...(ev.clipboardData?.files || [])].find((x) => x.type.startsWith("image/"));
    if (f && !$("#view-home").classList.contains("hidden")) { setMode("photo"); chooseFile(f); toast("📋 Image pasted"); }
  });

  // go
  $("#go").addEventListener("click", () => {
    if (mode === "photo" && chosenFile) explainNew("file", chosenFile);
    else if (mode === "text") explainNew("text", $("#pasteText").value);
  });

  // examples
  $("#exampleChips").append(...exampleLetters().map((ex) => h("button", { class: "chip", onclick: () => {
    setMode("text"); $("#pasteText").value = ex.text; updateGo();
    explainNew("text", ex.text);
  } }, ex.label)));

  // my letters controls
  $("#search").addEventListener("input", renderLetters);
  $$("[data-filter]").forEach((b) => b.addEventListener("click", () => {
    filter = b.dataset.filter;
    $$("[data-filter]").forEach((x) => x.classList.toggle("active", x === b));
    renderLetters();
  }));

  window.addEventListener("hashchange", route);
  route();

  // installable app (PWA)
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}
document.addEventListener("DOMContentLoaded", init);
