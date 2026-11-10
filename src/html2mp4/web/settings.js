// The Settings page: the Anthropic API key and the brand kit.
const PRESETS = {
  dark:  {background: "#0f1222", text: "#f4f5fa", accent: "#7c83ff", accent2: "#3dd6c6"},
  light: {background: "#ffffff", text: "#14161f", accent: "#4b4de0", accent2: "#0e9f97"},
};
const settings = {brand: null, saveTimer: null};

/* ---------- API key ---------- */
function showKey(k){
  const el = $("#keyStatus");
  el.className = "key-status" + (k.set ? " ok" : "");
  el.innerHTML = !k.set ? "No key yet. Paste one below to design slides from scripts."
    : k.source === "settings" ? `Saved key <code>${esc(k.masked)}</code>`
    : `Using <code>ANTHROPIC_API_KEY</code> from this computer's environment (<code>${esc(k.masked)}</code>). A key saved here takes priority.`;
  $("#keyRemove").hidden = !(k.set && k.source === "settings");
}
$("#keyForm").addEventListener("submit", async e => {
  e.preventDefault();
  const key = $("#keyInput").value.trim();
  if(!key){ toast("Paste a key first"); return; }
  $("#keySave").disabled = true; $("#keySave").textContent = "Verifying…";
  try{
    showKey(await api("/api/settings/api-key", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({key})}));
    $("#keyInput").value = ""; toast("Key saved and verified");
  }catch(err){ toast(err.message); }
  finally{ $("#keySave").disabled = false; $("#keySave").textContent = "Save and verify"; }
});
$("#keyTest").addEventListener("click", async () => {
  $("#keyTest").textContent = "Testing…";
  try{ await api("/api/settings/api-key/test", {method: "POST"}); toast("Connected to Anthropic"); }
  catch(err){ toast(err.message); }
  finally{ $("#keyTest").textContent = "Test connection"; }
});
$("#keyRemove").addEventListener("click", async () => {
  if(!confirm("Remove the saved API key from this computer?")) return;
  showKey(await api("/api/settings/api-key", {method: "DELETE"})); toast("Saved key removed");
});

/* ---------- brand kit ---------- */
function fillBrand(b){
  settings.brand = b;
  document.querySelectorAll("#brandForm [data-k]").forEach(el => el.value = b[el.dataset.k] ?? "");
  document.querySelectorAll("#bStyle button").forEach(x => x.setAttribute("aria-checked", x.dataset.v === b.style));
  for(const [box, rm, src] of [["#logoBoxDark", "#logoRemoveDark", b.logo_on_dark || b.logo], ["#logoBoxLight", "#logoRemoveLight", b.logo_on_light || b.logo]]){
    $(box).innerHTML = src ? `<img src="${esc(src)}" alt="Logo">` : "No logo";
    $(rm).hidden = !src;
  }
  showKitCurrent(b);
}
function previewBrand(){
  const f = $("#brandFrame");
  f.onload = () => f.contentWindow.postMessage({html2mp4: "go", pos: 3}, "*");   // a content slide, fully revealed
  f.src = `/api/settings/brand-preview?v=${Date.now()}`;
}
async function saveBrand(changes){
  try{ fillBrand(await api("/api/settings/brand", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(changes)})); previewBrand(); }
  catch(err){ toast(err.message); }
}
function queueSave(changes){
  Object.assign(settings.pending ??= {}, changes);
  clearTimeout(settings.saveTimer);
  settings.saveTimer = setTimeout(() => { const c = settings.pending; settings.pending = null; saveBrand(c); }, 350);
}
document.querySelectorAll("#brandForm [data-k]").forEach(el =>
  el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => queueSave({[el.dataset.k]: el.value})));
document.querySelectorAll("#bStyle button").forEach(b => b.addEventListener("click", () => saveBrand({style: b.dataset.v, ...PRESETS[b.dataset.v]})));
for(const input of [$("#logoInputDark"), $("#logoInputLight")]) input.addEventListener("change", async e => {
  const f = e.target.files[0]; if(!f) return;
  const fd = new FormData(); fd.append("file", f);
  try{ fillBrand(await api(`/api/settings/logo?slot=${input.dataset.slot}`, {method: "POST", body: fd})); previewBrand(); toast("Logo added"); }
  catch(err){ toast(err.message); }
  e.target.value = "";
});
for(const btn of [$("#logoRemoveDark"), $("#logoRemoveLight")]) btn.addEventListener("click", async () => {
  fillBrand(await api(`/api/settings/logo?slot=${btn.dataset.slot}`, {method: "DELETE"})); previewBrand();
});
$("#brandReset").addEventListener("click", async () => {
  if(!confirm("Reset colours, fonts, footer text and logo to the default look?")) return;
  fillBrand(await api("/api/settings/brand/reset", {method: "POST"})); previewBrand();
});

/* ---------- brand kit import ---------- */
const kit = {p: null, style: "dark", roles: null, role: "background", fonts: []};
const ROLE_NAMES = {background: "Background", text: "Text", accent: "Accent", accent2: "Second accent"};

function showKitCurrent(b){
  const el = $("#kitCurrent");
  if(!b.kit_name && !(b.palette || []).length){ el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<div class="mini-swatches">${(b.palette || []).slice(0, 6).map(c => `<i style="background:${esc(c.hex)}"></i>`).join("")}</div>
    <div class="grow"><b>${esc(b.kit_name || "Imported brand kit")}</b><small>${(b.palette || []).length} colours · ${esc(b.heading_font)} and ${esc(b.body_font)}
    · ${(b.rules || []).length} design rules${b.reference ? ` · style reference: ${esc(b.reference)}` : ""}</small></div>
    <button class="link" type="button" id="kitRemove">Remove</button>`;
  $("#kitRemove").onclick = async () => {
    if(!confirm("Remove the imported palette, design rules and style reference? Your colours, fonts and logos stay as they are.")) return;
    fillBrand(await api("/api/brandkit/remove", {method: "POST"})); toast("Brand kit removed");
  };
}

async function walk(entry, path = ""){
  if(entry.isFile) return [{file: await new Promise((ok, no) => entry.file(ok, no)), path: path + entry.name}];
  const reader = entry.createReader(), out = [];
  for(;;){
    const batch = await new Promise((ok, no) => reader.readEntries(ok, no));
    if(!batch.length) break;
    for(const e of batch) out.push(...await walk(e, `${path}${entry.name}/`));
  }
  return out;
}

async function analyzeKit(items){
  items = items.filter(({path}) => !path.split("/").some(p => p.startsWith(".")));
  if(!items.length) return;
  const drop = $("#kitDrop"), text = drop.querySelector("strong");
  drop.classList.add("busy");
  text.textContent = items.some(i => /\.pdf$/i.test(i.path)) ? "Reading your brand kit… Claude is reading the guidelines (about 30 seconds)" : "Reading your brand kit…";
  const fd = new FormData();
  items.forEach(({file, path}) => fd.append("files", file, path));
  try{ kit.p = await api("/api/brandkit/analyze", {method: "POST", body: fd}); openReview(); }
  catch(err){ toast(err.message); }
  finally{ drop.classList.remove("busy"); text.textContent = "Import a brand kit"; }
}

function openReview(){
  const p = kit.p;
  kit.style = "dark"; kit.role = "background"; kit.roles = {dark: {...p.dark}, light: {...p.light}};
  $("#kitName").textContent = p.kit_name || "Brand kit";
  const src = [];
  if(p.sources.pdf) src.push(p.sources.ai ? `<span class="ai">Guidelines read by Claude</span>` : "<span>Guidelines (basic scan)</span>");
  if(p.sources.logos) src.push(`<span>${p.sources.logos} logos</span>`);
  if(p.sources.fonts) src.push(`<span>${p.sources.fonts} font ${p.sources.fonts === 1 ? "family" : "families"}</span>`);
  if(p.sources.module) src.push("<span>1 module</span>");
  $("#kitSources").innerHTML = src.join("");
  $("#kitPalette").innerHTML = p.palette.map(c => `<button type="button" class="swatch" data-hex="${esc(c.hex)}" title="${esc(c.usage || c.group)}">
    <i style="background:${esc(c.hex)}"></i>${esc(c.name)} <small>${esc(c.hex)}</small></button>`).join("") || "<small class='hint'>No colours found.</small>";
  const fonts = [...new Set([...p.font_names, ...kit.fonts])];
  for(const [sel, val] of [["#kitHead", p.heading_font], ["#kitBody", p.body_font]])
    $(sel).innerHTML = fonts.map(f => `<option ${f === val ? "selected" : ""}>${esc(f)}</option>`).join("");
  const logoOpts = sel => `<option value="">No logo</option>` + p.logos.map(l =>
    `<option value="${l.id}" ${l.id === sel ? "selected" : ""}>${esc(l.name)} · ${l.tone === "light" ? "light" : "dark"} ${l.kind}</option>`).join("");
  $("#kitLogoDark").innerHTML = logoOpts(p.logo_on_dark); $("#kitLogoLight").innerHTML = logoOpts(p.logo_on_light);
  $("#kitRules").innerHTML = p.rules.map(r => `<li>${esc(r)}</li>`).join("");
  $("#kitRulesWrap").hidden = !p.rules.length; $("#kitRulesCount").textContent = p.rules.length || "";
  $("#kitRefWrap").hidden = !p.reference; if(p.reference) $("#kitRefName").textContent = p.reference.name;
  $("#kitNotes").textContent = p.notes.join(" ");
  renderRoles(); renderLogoThumbs();
  $("#kitReview").hidden = false;
  $("#kitReview").scrollIntoView({behavior: "smooth", block: "start"});
}
function renderRoles(){
  document.querySelectorAll("#kitStyle button").forEach(x => x.setAttribute("aria-checked", x.dataset.v === kit.style));
  const r = kit.roles[kit.style];
  $("#kitRoles").innerHTML = Object.entries(ROLE_NAMES).map(([k, label]) =>
    `<button type="button" class="role" data-role="${k}" aria-pressed="${k === kit.role}"><i style="background:${esc(r[k])}"></i><span>${label}<small>${esc(r[k])}</small></span></button>`).join("");
}
function renderLogoThumbs(){
  const by = Object.fromEntries(kit.p.logos.map(l => [l.id, l]));
  const d = by[$("#kitLogoDark").value], l = by[$("#kitLogoLight").value];
  $("#kitLogoThumbs").innerHTML = (d ? `<div class="on-dark"><img src="${esc(d.data_uri)}" alt=""></div>` : "") + (l ? `<div class="on-light"><img src="${esc(l.data_uri)}" alt=""></div>` : "");
}
$("#kitRoles").addEventListener("click", e => { const b = e.target.closest(".role"); if(b){ kit.role = b.dataset.role; renderRoles(); } });
$("#kitPalette").addEventListener("click", e => { const b = e.target.closest(".swatch"); if(b){ kit.roles[kit.style][kit.role] = b.dataset.hex; renderRoles(); } });
document.querySelectorAll("#kitStyle button").forEach(b => b.addEventListener("click", () => { kit.style = b.dataset.v; renderRoles(); }));
$("#kitLogoDark").addEventListener("change", renderLogoThumbs); $("#kitLogoLight").addEventListener("change", renderLogoThumbs);
$("#kitCancel").addEventListener("click", () => { $("#kitReview").hidden = true; kit.p = null; });
$("#kitApply").addEventListener("click", async () => {
  $("#kitApply").disabled = true;
  try{
    const b = await api("/api/brandkit/apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: kit.p.id, choices: {
      style: kit.style, ...kit.roles[kit.style], heading_font: $("#kitHead").value, body_font: $("#kitBody").value,
      logo_on_dark: $("#kitLogoDark").value, logo_on_light: $("#kitLogoLight").value, use_reference: $("#kitRef").checked}})});
    $("#kitReview").hidden = true; kit.p = null;
    await pageHooks.settings(); fillBrand(b); toast("Brand kit applied");
    $("#hBrand").scrollIntoView({behavior: "smooth"});
  }catch(err){ toast(err.message); }
  finally{ $("#kitApply").disabled = false; }
});
const kitDrop = $("#kitDrop");
["dragenter", "dragover"].forEach(ev => kitDrop.addEventListener(ev, e => { e.preventDefault(); kitDrop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => kitDrop.addEventListener(ev, () => kitDrop.classList.remove("over")));
kitDrop.addEventListener("drop", async e => {
  e.preventDefault();
  const entries = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  const items = entries.length ? (await Promise.all(entries.map(en => walk(en)))).flat() : [...e.dataTransfer.files].map(f => ({file: f, path: f.name}));
  analyzeKit(items);
});
$("#kitFolder").addEventListener("change", e => { analyzeKit([...e.target.files].map(f => ({file: f, path: f.webkitRelativePath || f.name}))); e.target.value = ""; });
$("#kitFiles").addEventListener("change", e => { analyzeKit([...e.target.files].map(f => ({file: f, path: f.name}))); e.target.value = ""; });

pageHooks.settings = async () => {
  try{
    const s = await api("/api/settings");
    showKey(s.api_key);
    kit.fonts = s.fonts;
    for(const sel of [$("#fHead"), $("#fBody")]) sel.innerHTML = s.fonts.map(f => `<option>${esc(f)}</option>`).join("");
    fillBrand(s.brand); previewBrand();
  }catch(err){ toast(err.message); }
};

/* ---------- glossary ---------- */
const gloss = {pron: {}, timer: null};
function renderPron(){
  $("#pronList").innerHTML = Object.entries(gloss.pron).map(([w, s]) => `<div><span><b>${esc(w)}</b> is said <b>${esc(s)}</b></span><button type="button" data-w="${esc(w)}" aria-label="Remove">Remove</button></div>`).join("");
}
async function saveGloss(){
  const g = await api("/api/settings/glossary", {method: "PUT", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({pronunciations: gloss.pron, banned: $("#glBanned").value.split("\n")})});
  gloss.pron = g.pronunciations; renderPron();
}
$("#pronAdd").addEventListener("click", async () => {
  const w = $("#pronWritten").value.trim(), s = $("#pronSaid").value.trim();
  if(!w || !s){ toast("Fill in both boxes"); return; }
  gloss.pron[w] = s; $("#pronWritten").value = $("#pronSaid").value = ""; await saveGloss(); toast("Saved");
});
$("#pronList").addEventListener("click", async e => { const b = e.target.closest("button"); if(b){ delete gloss.pron[b.dataset.w]; await saveGloss(); } });
$("#glBanned").addEventListener("input", () => { clearTimeout(gloss.timer); gloss.timer = setTimeout(saveGloss, 600); });
const loadSettings = pageHooks.settings;
pageHooks.settings = async () => {
  await loadSettings();
  const g = await api("/api/settings/glossary"); gloss.pron = g.pronunciations; renderPron(); $("#glBanned").value = (g.banned || []).join("\n");
};


/* ---------- design quality ---------- */
const DQ_NOTES = {balanced: "Recommended. About 2 to 3 minutes and $0.60 for a six-slide module. Clean, consistent slides that pass every check.",
                  thorough: "Claude takes more care over each layout and illustration. About 4 minutes and $0.90 for a six-slide module."};
function showQuality(v){
  document.querySelectorAll("#dqSeg button").forEach(b => b.setAttribute("aria-checked", b.dataset.v === v));
  $("#dqNote").textContent = DQ_NOTES[v];
}
document.querySelectorAll("#dqSeg button").forEach(b => b.addEventListener("click", async () => {
  showQuality(b.dataset.v);
  try{ await api("/api/settings/design-quality", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({value: b.dataset.v})}); }
  catch(err){ toast(err.message); }
}));
/* ---------- motion ---------- */
const MV_NOTES = {lively: "Recommended. Entrances, drawn icons and arrows, count-ups, soft glows and gently moving backgrounds, so it feels like a video and not a slide deck.",
                  calm: "Entrances and slide changes only. Nothing loops or glows."};
function showMotion(v){
  document.querySelectorAll("#mvSeg button").forEach(b => b.setAttribute("aria-checked", b.dataset.v === v));
  $("#mvNote").textContent = MV_NOTES[v];
}
document.querySelectorAll("#mvSeg button").forEach(b => b.addEventListener("click", async () => {
  showMotion(b.dataset.v);
  try{ await api("/api/settings/motion", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({value: b.dataset.v})}); toast("Applies to slides you design from now on"); }
  catch(err){ toast(err.message); }
}));
/* ---------- pacing ---------- */
const HD_NOTES = {standard: "About a second and a half after the last sentence of each slide, then the next slide appears.",
                  comfortable: "About 1.5 seconds longer on every slide, so the last graphic can be taken in before the slide changes.",
                  relaxed: "About 3 seconds longer on every slide. For dense slides, or viewers who like to read the screen."};
function showHold(v){
  document.querySelectorAll("#hdSeg button").forEach(b => b.setAttribute("aria-checked", b.dataset.v === v));
  $("#hdNote").textContent = HD_NOTES[v] + " Applies to the preview player and to new videos. A slide's own \u201cHold:\u201d line in the script wins.";
}
document.querySelectorAll("#hdSeg button").forEach(b => b.addEventListener("click", async () => {
  showHold(b.dataset.v);
  try{ await api("/api/settings/hold", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({value: b.dataset.v})}); toast("Saved. It applies from now on, no redesign needed."); }
  catch(err){ toast(err.message); }
}));
const loadWithGloss = pageHooks.settings;
pageHooks.settings = async () => { await loadWithGloss(); const s = await api("/api/settings"); showQuality(s.design_quality); showMotion(s.motion || "lively"); showHold(s.hold || "standard"); };
