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
  $("#logoBox").innerHTML = b.logo ? `<img src="${esc(b.logo)}" alt="Logo">` : "No logo";
  $("#logoRemove").hidden = !b.logo;
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
$("#logoInput").addEventListener("change", async e => {
  const f = e.target.files[0]; if(!f) return;
  const fd = new FormData(); fd.append("file", f);
  try{ fillBrand(await api("/api/settings/logo", {method: "POST", body: fd})); previewBrand(); toast("Logo added"); }
  catch(err){ toast(err.message); }
  e.target.value = "";
});
$("#logoRemove").addEventListener("click", async () => { fillBrand(await api("/api/settings/logo", {method: "DELETE"})); previewBrand(); });
$("#brandReset").addEventListener("click", async () => {
  if(!confirm("Reset colours, fonts, footer text and logo to the default look?")) return;
  fillBrand(await api("/api/settings/brand/reset", {method: "POST"})); previewBrand();
});

pageHooks.settings = async () => {
  try{
    const s = await api("/api/settings");
    showKey(s.api_key);
    if(!$("#fHead").options.length)
      for(const sel of [$("#fHead"), $("#fBody")]) sel.innerHTML = s.fonts.map(f => `<option>${esc(f)}</option>`).join("");
    fillBrand(s.brand); previewBrand();
  }catch(err){ toast(err.message); }
};
