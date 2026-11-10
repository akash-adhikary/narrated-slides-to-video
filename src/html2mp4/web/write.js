// The Write page: a script becomes slides, you review and refine them, then hand them to the video page.
const W = {project: null, outline: null, parseTimer: null, jobTimer: null, current: null, keySet: false, quality: "balanced"};
const COST_HINT = {balanced: "Usually 2 to 4 minutes and about $0.60 in Claude usage.", thorough: "Usually 4 to 5 minutes and about $0.90 in Claude usage."};
const KINDS = {typo: "Typo", clarity: "Clearer wording", risk: "Careful wording", pronounce: "Pronunciation"};
const ago = t => { const m = Math.round((Date.now() / 1000 - t) / 60); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
const slideName = id => id === "s0" ? "Title slide" : id ? `Slide ${id.slice(1)}` : "Module";
const post = (url, body, method = "POST") => api(url, {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
const draft = {
  get(){ try{ return sessionStorage.getItem("h2m-draft") || ""; }catch{ return ""; } },
  set(v){ try{ sessionStorage.setItem("h2m-draft", v); }catch{} },
};

/* ---------- the script box ---------- */
const box = $("#wScript");
box.addEventListener("input", () => { clearTimeout(W.parseTimer); W.parseTimer = setTimeout(parseNow, 450); draft.set(box.value); updateButtons(); });
async function parseNow(){
  const text = box.value;
  if(!text.trim()){ W.outline = null; $("#wStats").textContent = ""; $("#wStatus").textContent = ""; $("#wStatus").className = "script-status"; updateButtons(); return; }
  try{
    const o = W.outline = await post("/api/write/parse", {script: text});
    $("#wStats").textContent = `${o.slides.length} slides · ${o.sentences} sentences · about ${Math.max(1, Math.round(o.seconds / 60))} min`;
    $("#wStatus").className = "script-status ok"; $("#wStatus").textContent = `“${o.title}”: ready to design.`;
  }catch(err){
    W.outline = null; $("#wStats").textContent = "";
    $("#wStatus").className = "script-status err"; $("#wStatus").textContent = err.message;
  }
  updateButtons();
}
function updateButtons(){
  const ok = !!W.outline, busy = W.busy;
  $("#wDesign").disabled = !ok || busy || (W.project && W.mode !== "basic" && box.value === W.saved) || (W.project && W.mode === "basic" && !W.keySet);
  $("#wReview").disabled = !ok || busy || !W.keySet;
  $("#wBasic").hidden = !!W.project;
  $("#wNew").hidden = !W.project;
  $("#wDesignText").textContent = !W.project ? "Design slides" : W.mode === "basic" ? "Design with Claude" : "Update slides";
  $("#wCostHint").innerHTML = !W.keySet ? `Designing needs an API key. <a href="#settings">Add one in Settings</a>.`
    : W.project ? "Only the slides you changed are redesigned." : COST_HINT[W.quality];
}
$("#wExample").addEventListener("click", async () => { box.value = (await api("/api/write/example")).script; draft.set(box.value); parseNow(); });
$("#wFile").addEventListener("change", e => {
  const f = e.target.files[0]; if(!f) return;
  const r = new FileReader(); r.onload = () => { box.value = r.result; draft.set(box.value); parseNow(); }; r.readAsText(f); e.target.value = "";
});
$("#wImport").addEventListener("change", async e => {
  const f = e.target.files[0]; e.target.value = ""; if(!f) return;
  const fd = new FormData(); fd.append("file", f);
  try{
    const r = await api("/api/projects/import", {method: "POST", body: fd});
    await openProject(r.project); loadModules(); $("#cardReview").scrollIntoView({behavior: "smooth"});
    toast(r.edited ? "Opened. This file was changed outside the Studio, so later redesigns start from the Studio's own version of the slides."
      : r.pronunciations_added ? `Opened, and added ${r.pronunciations_added} pronunciation${r.pronunciations_added > 1 ? "s" : ""} from the file.` : "Opened. You can keep refining it here.");
  }catch(err){ toast(err.message); }
});
$("#wHelp").addEventListener("click", () => { $("#wHelpBox").hidden = !$("#wHelpBox").hidden; });
$("#wNew").addEventListener("click", () => {
  W.project = null; W.saved = ""; box.value = ""; draft.set(""); W.outline = null;
  $("#cardReview").hidden = true; $("#wSuggest").innerHTML = ""; $("#wStats").textContent = ""; $("#wStatus").textContent = "";
  updateButtons(); scrollTo({top: 0, behavior: "smooth"});
});

/* ---------- suggestions ---------- */
$("#wReview").addEventListener("click", async () => {
  W.busy = true; updateButtons(); $("#wReview").lastChild.textContent = "Checking…";
  try{
    const r = await post("/api/write/review", {script: box.value});
    renderSuggestions(r.suggestions);
  }catch(err){ toast(err.message); }
  finally{ W.busy = false; $("#wReview").lastChild.textContent = "Check my script"; updateButtons(); }
});
function renderSuggestions(list){
  const el = $("#wSuggest");
  if(!list.length){ el.innerHTML = `<div class="sugg-none">No problems found. Your script reads well.</div>`; return; }
  el.innerHTML = `<h4 class="sugg-h">${list.length} suggestion${list.length > 1 ? "s" : ""} <small>Nothing changes unless you accept it.</small></h4>` + list.map((s, i) => `
    <div class="sugg" data-i="${i}"><div class="sugg-top"><span class="kind ${s.kind}">${KINDS[s.kind]}</span><span class="why">${esc(s.reason)}</span></div>
      ${s.kind === "pronounce" ? `<div class="diff">Say <b>${esc(s.replacement)}</b> for <b>${esc(s.quote)}</b></div>`
        : `<div class="diff"><del>${esc(s.quote)}</del><ins>${esc(s.replacement)}</ins></div>`}
      <div class="sugg-act"><button class="link" data-act="accept">${s.kind === "pronounce" ? "Add to pronunciation list" : "Accept"}</button><button class="link" data-act="skip">Dismiss</button></div></div>`).join("");
  el.onclick = async e => {
    const b = e.target.closest("[data-act]"); if(!b) return;
    const card = b.closest(".sugg"), s = list[+card.dataset.i];
    if(b.dataset.act === "accept"){
      if(s.kind === "pronounce"){
        const g = await api("/api/settings/glossary");
        await post("/api/settings/glossary", {pronunciations: {...g.pronunciations, [s.quote]: s.replacement}}, "PUT"); toast("Added to your pronunciation list");
      }else{
        if(!box.value.includes(s.quote)){ toast("That text has changed since; skipped"); }
        else{ box.value = box.value.replace(s.quote, s.replacement); draft.set(box.value); parseNow(); toast("Applied"); }
      }
    }
    card.remove();
  };
}

/* ---------- designing ---------- */
async function startJob(promise){
  W.busy = true; updateButtons();
  try{ const r = await promise; if(r.job){ trackJob(r.job, r.project); } else { W.busy = false; updateButtons(); toast("Nothing has changed"); } return r; }
  catch(err){ W.busy = false; updateButtons(); toast(err.message); }
}
$("#wDesign").addEventListener("click", () => {
  if(W.project && W.mode === "basic") startJob(post(`/api/projects/${W.project}/design`, {script: box.value}).then(r => ({...r, project: W.project})));
  else if(W.project) startJob(post(`/api/projects/${W.project}/script`, {script: box.value}, "PUT").then(r => ({...r, project: W.project})));
  else startJob(post("/api/write/generate", {script: box.value, mode: "design"}));
});
$("#wBasic").addEventListener("click", () => startJob(post("/api/write/generate", {script: box.value, mode: "basic"})));

const PHASES = ["plan", "write", "check", "fix", "review"];
function renderPhases(phase){
  const at = PHASES.indexOf(phase);
  document.querySelectorAll("#jobPhases li").forEach((li, i) => { li.classList.toggle("done", at > i || phase === "done"); li.classList.toggle("on", at === i); });
}
function renderThoughts(list){
  $("#jobThinking").hidden = !list.length;
  $("#jobThoughts").innerHTML = list.map(t => `<div class="thought">${list.length > 1 ? `<b>${esc(t.label)}</b> ` : ""}${esc(t.text.replace(/\s+/g, " ").replace(/^\S*\s/, "…"))}</div>`).join("");
}
function renderActivity(list){
  const box = $("#jobActivity"), atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  const mmss = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  box.innerHTML = list.map(e => `<li class="${e.kind}"><time>${mmss(e.t)}</time><span>${esc(e.text)}</span></li>`).join("");
  $("#jobActivityCount").textContent = list.length ? `· ${list.length}` : "";
  if(atEnd) box.scrollTop = box.scrollHeight;
}

function trackJob(job, project){
  $("#cardJob").hidden = false; W.busy = true; updateButtons();
  $("#cardJob").scrollIntoView({behavior: "smooth", block: "center"});
  clearInterval(W.jobTimer);
  const tick = async () => {
    const j = await api(`/api/write/jobs/${job.id}`).catch(() => null); if(!j) return;
    const p = Math.round(j.progress * 100);
    $("#jobPct").innerHTML = `${p}<small>%</small>`; $("#jobBar").style.width = Math.max(2, p) + "%";
    $("#jobLabel").textContent = j.status === "queued" ? "Waiting for the previous design to finish" : j.label;
    $("#jobEta").textContent = j.status === "queued" ? "" : j.eta ? (j.eta < 20 ? "Almost there…" : `About ${fmt(j.eta)} left`)
      : j.phase === "plan" ? "Claude plans every layout before writing. This usually takes 1 to 3 minutes." : "";
    renderPhases(j.phase); renderThoughts(j.thoughts); renderActivity(j.activity);
    if(j.status === "done" || j.status === "failed"){
      clearInterval(W.jobTimer); W.busy = false; $("#cardJob").hidden = true;
      if(j.status === "failed") toast(j.error || "The design failed");
      else toast(j.cost ? `Done. Claude usage about $${j.cost.toFixed(2)}` : "Done");
      await openProject(project || job.project); loadModules();
    }
  };
  tick(); W.jobTimer = setInterval(tick, 1000);
}

/* ---------- review ---------- */
function slideStarts(o){
  const rows = []; let pos = 0;
  if(o.intro.length){ rows.push({id: "s0", title: "Title", first: 0, last: o.intro.length - 1}); pos = o.intro.length; }
  for(const s of o.slides){ rows.push({id: s.id, title: s.title, first: pos, last: pos + s.say.length - 1}); pos += s.say.length; }
  return rows;
}
async function openProject(pid, version){
  const p = await api(`/api/projects/${pid}`);
  W.project = pid; W.current = p; W.saved = p.script; W.version = version || p.current;
  W.mode = (p.versions.find(v => v.n === p.current) || {}).mode || "design";
  if(box.value !== p.script){ box.value = p.script; draft.set(p.script); }
  await parseNow(); W.saved = p.script;
  if(!p.versions.length){ updateButtons(); return; }
  $("#cardReview").hidden = false;
  const o = W.outline || p.outline; W.rows = o ? slideStarts(o) : [];
  $("#rvMeta").textContent = p.title;
  $("#rvVersion").innerHTML = [...p.versions].reverse().map(v => `<option value="${v.n}" ${v.n === W.version ? "selected" : ""}>Version ${v.n}${v.n === p.current ? " (current)" : ""} · ${esc(v.note || "")} · ${ago(v.at)}</option>`).join("");
  $("#rvRestore").hidden = W.version === p.current;
  showFrame();
  const bySlide = {};
  for(const i of p.issues) (bySlide[i.slide] ||= []).push(i);
  $("#rvSlides").innerHTML = W.rows.map((r, i) => {
    const iss = bySlide[r.id] || [], errs = iss.filter(x => x.severity === "error").length;
    return `<li><button type="button" data-i="${i}"><b>${i + 1}</b><span>${esc(r.title)}</span>${errs ? `<em class="bad" title="${errs} to fix">${errs}</em>` : iss.length ? `<em class="note" title="${iss.length} to look at">${iss.length}</em>` : `<em class="ok">✓</em>`}</button></li>`; }).join("");
  const errs = p.issues.filter(i => i.severity === "error"), warns = p.issues.filter(i => i.severity !== "error");
  $("#rvIssues").innerHTML = !p.issues.length ? `<div class="chk ok">✓ The checker rendered every step of every slide. Nothing overlaps, everything fits, and the type is uniform.</div>`
    : `${errs.length ? `<div class="chk bad"><h4>${errs.length} problem${errs.length > 1 ? "s" : ""} to fix</h4><ul>${errs.map(i => `<li><b>${slideName(i.slide)}</b>${i.step ? ` · step ${i.step}` : ""}: ${esc(i.message)}</li>`).join("")}</ul><small>Describe what to change below, or edit the script.</small></div>` : `<div class="chk ok">✓ No layout problems found.</div>`}
       ${warns.length ? `<details class="chk note"><summary>${warns.length} note${warns.length > 1 ? "s" : ""} worth a look</summary><ul>${warns.map(i => `<li><b>${slideName(i.slide)}</b>: ${esc(i.message)}</li>`).join("")}</ul></details>` : ""}`;
  $("#fbScope").innerHTML = `<option value="">Whole module</option>` + (o ? o.slides.map(s => `<option value="${s.id}">Slide ${s.id.slice(1)} · ${esc(s.title)}</option>`).join("") : "");
  const total = p.versions.reduce((a, v) => a + (v.cost || 0), 0);
  $("#rvCost").textContent = total ? `Claude usage so far: about $${total.toFixed(2)}` : "";
  updateButtons();
}
function showFrame(){
  const f = $("#rvFrame");
  f.onload = () => { const r = W.rows && W.rows[0]; if(r) f.contentWindow.postMessage({html2mp4: "go", pos: r.last}, "*"); };
  f.src = `/api/projects/${W.project}/module.html?v=${W.version}&studio=${encodeURIComponent(W.project)}&t=${Date.now()}`;
  $("#rvOpen").href = `/api/projects/${W.project}/module.html?v=${W.version}&studio=${encodeURIComponent(W.project)}`;
  $("#rvDownload").href = `/api/projects/${W.project}/download?v=${W.version}`;
}
$("#rvSlides").addEventListener("click", e => {
  const b = e.target.closest("button"); if(!b) return;
  $("#rvFrame").contentWindow.postMessage({html2mp4: "go", pos: W.rows[+b.dataset.i].last}, "*");
});
addEventListener("message", e => {
  if(e.source === $("#rvFrame").contentWindow && e.data && e.data.html2mp4 === "fullscreen"){
    const f = $("#rvFrame"); if(document.fullscreenElement) document.exitFullscreen(); else if(f.requestFullscreen) f.requestFullscreen().catch(() => window.open($("#rvOpen").href, "_blank"));
    return;
  }
  if(e.source !== $("#rvFrame").contentWindow || !e.data || e.data.html2mp4 !== "step" || !W.rows) return;
  const i = W.rows.findIndex(r => e.data.pos >= r.first && e.data.pos <= r.last);
  document.querySelectorAll("#rvSlides button").forEach((b, k) => b.classList.toggle("on", k === i));
});
$("#rvVersion").addEventListener("change", e => { W.version = +e.target.value; $("#rvRestore").hidden = W.version === W.current.current; showFrame(); });
$("#rvRestore").addEventListener("click", async () => {
  try{ await post(`/api/projects/${W.project}/restore`, {version: W.version}); toast(`Restored version ${W.version}`); await openProject(W.project); loadModules(); }
  catch(err){ toast(err.message); }
});
$("#fbGo").addEventListener("click", () => {
  const text = $("#fbText").value.trim(); if(!text){ toast("Write what you'd like changed"); return; }
  const scope = $("#fbScope").value;
  startJob(post(`/api/projects/${W.project}/revise`, {feedback: text, scope: scope ? [scope] : []}).then(r => { $("#fbText").value = ""; return {...r, project: W.project}; }));
});
$("#rvUse").addEventListener("click", async () => {
  try{ const u = await post(`/api/projects/${W.project}/to-video`, {}); showUpload(u); location.hash = "#create"; toast("Slides ready. Choose a voice and music."); }
  catch(err){ toast(err.message); }
});

/* ---------- your modules ---------- */
async function loadModules(){
  const list = await api("/api/projects").catch(() => []);
  $("#modules").hidden = !list.length;
  $("#modList").innerHTML = list.map(m => `<article class="mod ${m.id === W.project ? "open" : ""}" data-id="${esc(m.id)}">
    <div class="mod-t">${esc(m.title)}</div><div class="mod-m">${m.designed ? `${m.versions} version${m.versions > 1 ? "s" : ""}` : "Not designed yet"} · ${ago(m.updated)}</div>
    <div class="mod-a"><button class="link" data-act="open">Open</button>${m.designed ? `<button class="link" data-act="video">Make video</button>` : ""}<button class="link rm" data-act="del">Delete</button></div></article>`).join("");
}
$("#modList").addEventListener("click", async e => {
  const b = e.target.closest("[data-act]"); if(!b) return;
  const id = b.closest(".mod").dataset.id;
  if(b.dataset.act === "open"){ await openProject(id); loadModules(); $("#cardScript").scrollIntoView({behavior: "smooth"}); }
  if(b.dataset.act === "video"){ try{ showUpload(await post(`/api/projects/${id}/to-video`, {})); location.hash = "#create"; }catch(err){ toast(err.message); } }
  if(b.dataset.act === "del" && confirm("Delete this module and all its versions? Videos you've made from it are not affected.")){
    await api(`/api/projects/${id}`, {method: "DELETE"}); if(W.project === id) $("#wNew").click(); loadModules();
  }
});

/* ---------- start ---------- */
pageHooks.write = async () => {
  const s = await api("/api/settings").catch(() => null); W.keySet = !!(s && s.api_key.set); W.quality = (s && s.design_quality) || "balanced"; updateButtons(); loadModules();
};
(async () => {
  const s = await api("/api/settings").catch(() => null); W.keySet = !!(s && s.api_key.set); W.quality = (s && s.design_quality) || "balanced";
  const active = await api("/api/write/active").catch(() => []);
  if(active.length){ trackJob(active[0], active[0].project); await openProject(active[0].project).catch(() => {}); }
  else{
    const d = draft.get(); if(d){ box.value = d; await parseNow(); }
    const list = await api("/api/projects").catch(() => []);
    if(!d && list.length && !location.hash.includes("create")) { /* leave the page empty; the list below offers the modules */ }
  }
  updateButtons(); loadModules();
})();
