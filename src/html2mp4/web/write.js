// The Write page: a script becomes slides, you review and refine them, then hand them to the video page.
const W = {project: null, outline: null, parseTimer: null, jobTimer: null, current: null, keySet: false, quality: "balanced"};
const COST_HINT = {balanced: "Usually 2 to 4 minutes and about $0.60 in Claude usage.", thorough: "Usually 4 to 5 minutes and about $0.90 in Claude usage."};
const KINDS = {typo: "Typo", clarity: "Clearer wording", risk: "Careful wording", pronounce: "Pronunciation"};
const ago = t => { const m = Math.round((Date.now() / 1000 - t) / 60); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
const slideName = id => id === "s0" ? "Title slide" : id ? `Slide ${id.slice(1)}` : "Module";
const post = (url, body, method = "POST") => api(url, {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
// What you type is kept with the module as you go (a moment after you stop), so a closed tab or a crash loses nothing.
const draft = {
  timer: null, pending: null,
  set(text){ if(!W.project || W.viewing) return; this.pending = {pid: W.project, text}; $("#wSaved").textContent = "Saving…"; clearTimeout(this.timer); this.timer = setTimeout(() => this.flush(), 700); },
  async flush(){
    clearTimeout(this.timer); const p = this.pending; this.pending = null; if(!p) return;
    try{
      await post(`/api/projects/${p.pid}`, {script: p.text}, "PATCH"); if(!this.pending) $("#wSaved").textContent = "Saved";
      if(W.current && W.current.id === p.pid && W.designed && !W.viewing){ W.current.has_draft = p.text !== W.current.designed_script; renderVersionMenu(W.current); }   // the history lists the draft
    }
    catch{ $("#wSaved").textContent = "Couldn't save. Is the Studio still running?"; }
  },
};
const leaving = () => { const p = draft.pending; if(p) fetch(`/api/projects/${p.pid}`, {method: "PATCH", keepalive: true, headers: {"Content-Type": "application/json"}, body: JSON.stringify({script: p.text})}); };
addEventListener("pagehide", leaving);
document.addEventListener("visibilitychange", () => { if(document.visibilityState === "hidden") leaving(); });

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
    const fresh = /no slides/i.test(err.message);                          // a new module is just its title: not an error yet
    $("#wStatus").className = "script-status" + (fresh ? "" : " err");
    $("#wStatus").textContent = fresh ? "Nothing to design yet. Write your first slide, or ask the assistant to write the script." : err.message;
  }
  updateButtons();
}
function updateButtons(){
  const ok = !!W.outline && !W.viewing, busy = W.busy;
  $("#wDesign").disabled = !ok || busy || !W.project || (W.designed && W.mode !== "basic" && box.value === W.saved) || (W.designed && W.mode === "basic" && !W.keySet);
  $("#wReview").disabled = !ok || busy || !W.keySet;
  $("#wBasic").hidden = !!W.designed;
  $("#wDesignText").textContent = !W.designed ? "Design slides" : W.mode === "basic" ? "Design with Claude" : "Update slides";
  $("#wCostHint").innerHTML = !W.keySet ? `Designing needs an API key. <a href="#settings">Add one in Settings</a>.`
    : W.designed ? "Only the slides you changed are redesigned." : COST_HINT[W.quality];
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
    await openProject(r.project); loadModules(); (r.designed === false ? $("#cardScript") : $("#cardReview")).scrollIntoView({behavior: "smooth"});
    toast(r.versions > 1 ? `Opened with its ${r.versions} versions.` + (r.edited ? " The file was edited by hand." : "")
      : r.designed === false ? "Opened the script. Design the slides when you're ready."
      : r.edited ? "Opened. This file was changed outside the Studio, so later redesigns start from the Studio's own version of the slides."
      : r.pronunciations_added ? `Opened, and added ${r.pronunciations_added} pronunciation${r.pronunciations_added > 1 ? "s" : ""} from the file.` : "Opened. You can keep refining it here.");
  }catch(err){ toast(err.message); }
});
$("#wHelp").addEventListener("click", () => { $("#wHelpBox").hidden = !$("#wHelpBox").hidden; });
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
$("#wDesign").addEventListener("click", async () => {
  if(!W.project) return;
  await draft.flush();
  if(W.designed && W.mode !== "basic") startJob(post(`/api/projects/${W.project}/script`, {script: box.value}, "PUT").then(r => ({...r, project: W.project})));
  else startJob(post(`/api/projects/${W.project}/design`, {script: box.value, mode: "design"}).then(r => ({...r, project: W.project})));   // first design, or a quick layout upgraded
});
$("#wBasic").addEventListener("click", async () => {
  if(!W.project) return; await draft.flush();
  startJob(post(`/api/projects/${W.project}/design`, {script: box.value, mode: "basic"}).then(r => ({...r, project: W.project})));
});

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

function trackJob(job, project, quiet){
  $("#cardJob").hidden = false; W.busy = true; updateButtons();
  if(!quiet) $("#cardJob").scrollIntoView({behavior: "smooth", block: "center"});
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
      const pid = project || job.project;
      if(W.project === pid) await openProject(pid);                          // only if you're still in that module
      loadModules();
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
  await draft.flush();                                                          // what was being typed, before the module (or the version) changes
  const p = await api(`/api/projects/${pid}` + (version ? `?v=${version}` : ""));
  W.project = pid; W.current = p; W.designed = p.versions.length > 0; W.saved = p.designed_script; W.version = p.version; W.viewing = p.viewing ? p.version : null;
  W.mode = (p.versions.find(v => v.n === p.current) || {}).mode || "design";
  if(box.value !== p.script) box.value = p.script;
  box.readOnly = !!W.viewing; $("#wSaved").textContent = "";
  showModule(p);
  await parseNow();
  if(!p.versions.length){ $("#cardReview").hidden = true; updateButtons(); return; }
  $("#cardReview").hidden = false;
  const o = W.outline || p.outline; W.rows = o ? slideStarts(o) : [];
  $("#rvMeta").textContent = p.title;
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
  $("#rvFile").href = `/api/projects/${W.project}/export?v=${W.version}`;
  $("#rvFileAll").href = `/api/projects/${W.project}/export?v=${W.version}&history=true`;
  $("#rvShare").open = false;
}
$("#rvShare").addEventListener("click", e => { if(e.target.closest(".share-menu a, .share-menu button")) setTimeout(() => { $("#rvShare").open = false; }, 0); });
addEventListener("click", e => document.querySelectorAll("details.share[open]").forEach(d => { if(!d.contains(e.target)) d.open = false; }));
addEventListener("keydown", e => { if(e.key === "Escape") document.querySelectorAll("details.share[open]").forEach(d => { d.open = false; d.querySelector("summary").focus(); }); });
$("#verSel").addEventListener("toggle", () => { if($("#verSel").open) $("#rvShare").open = false; });             // one menu at a time
$("#rvShare").addEventListener("toggle", () => { if($("#rvShare").open) $("#verSel").open = false; });
$("#rvYaml").addEventListener("click", async () => {
  const url = `/api/projects/${W.project}/export?v=${W.version}&format=yaml`, dlg = $("#yamlView");
  $("#yvText").textContent = "Loading…"; $("#yvMeta").textContent = ""; $("#yvSave").href = url;
  dlg.showModal();
  try{
    const text = await (await fetch(url + "&inline=true")).text();
    $("#yvText").textContent = text; $("#yvMeta").textContent = `${text.split("\n").length.toLocaleString()} lines`;
  }catch(err){ $("#yvText").textContent = "Couldn't load it."; }
});
$("#yvCopy").addEventListener("click", async () => {
  try{ await navigator.clipboard.writeText($("#yvText").textContent); toast("Copied."); }catch(err){ toast("Couldn't copy. Select the text and copy it."); }
});
$("#yvClose").addEventListener("click", () => $("#yamlView").close());
$("#yamlView").addEventListener("click", e => { if(e.target === e.currentTarget) e.currentTarget.close(); });
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
$("#fbGo").addEventListener("click", () => {
  const text = $("#fbText").value.trim(); if(!text){ toast("Write what you'd like changed"); return; }
  const scope = $("#fbScope").value;
  startJob(post(`/api/projects/${W.project}/revise`, {feedback: text, scope: scope ? [scope] : []}).then(r => { $("#fbText").value = ""; return {...r, project: W.project}; }));
});
$("#rvUse").addEventListener("click", async () => {
  if(W.viewing){ toast("Restore this version, or go back to the current one, to make a video."); return; }
  try{ const u = await post(`/api/projects/${W.project}/to-video`, {}); showUpload(u); location.hash = "#create"; toast("Slides ready. Choose a voice and music."); }
  catch(err){ toast(err.message); }
});

/* ---------- a module has a name, and an address (#write/<id>) ---------- */
const SITE = document.title;
function showModule(p){
  document.body.dataset.module = p.id; if(typeof switchChat === "function") switchChat();
  $("#wHero").hidden = true; $("#wHead").hidden = false; $("#cardScript").hidden = false;
  setHead(p);
  if(document.body.dataset.page === "write" && location.hash !== `#write/${encodeURIComponent(p.id)}`) history.replaceState(null, "", `#write/${encodeURIComponent(p.id)}`);
  document.querySelector('.tabs a[data-page="write"]').setAttribute("href", `#write/${encodeURIComponent(p.id)}`);   // the Write tab goes back to this module
}
const when = t => new Date(t * 1000).toLocaleString([], {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"});
function setHead(p){
  $("#wNameText").textContent = p.name; document.title = `${p.name} · ${SITE}`;
  const n = p.versions.length;
  $("#wState").hidden = n > 0; $("#wState").textContent = "Not designed yet";
  $("#verSel").hidden = !n; $("#verSel").open = false;
  if(n){
    $("#verLabel").textContent = p.viewing ? `Viewing version ${p.version}` : `Version ${p.current} · current`;
    $("#verLabel").classList.toggle("on", !p.viewing);
    renderVersionMenu(p);
  }
  $("#shareFor").textContent = n ? `Sharing version ${p.version}${p.viewing ? "" : " (current)"}` : "";
  $("#rvFile small").textContent = `.h2m.json · version ${p.version}`;
  $("#verBar").hidden = !p.viewing;
  if(p.viewing){
    const v = p.versions.find(x => x.n === p.version) || {};
    $("#verBarText").innerHTML = `Viewing <b>version ${p.version}</b> · ${esc(when(v.at))}${v.note ? ` · ${esc(v.note)}` : ""}. The script and slides are exactly as they were. Go back to the current version to make changes.`;
  }
  document.body.toggleAttribute("data-viewing", !!p.viewing);
  updateButtons();
  if(typeof render === "function"){ if(p.viewing && C.open) setOpen(false); render(); }       // the assistant can't edit an old version, so it gets out of the way
}
function renderVersionMenu(p){
  const rows = [...p.versions].reverse().map(v => `<button type="button" class="vrow" role="menuitem" data-n="${v.n}" ${v.n === p.version ? 'aria-current="true"' : ""}>
    <span class="vt"><b>v${v.n}</b><span class="vn">${esc(v.note || "Version " + v.n)}</span>${v.n === p.current ? `<span class="vtag">current</span>` : ""}</span>
    <small>${esc(when(v.at))}${v.cost ? ` · about $${v.cost.toFixed(2)}` : ""}</small></button>`).join("");
  const draftRow = p.has_draft ? `<div class="vrow draft"><span class="vt"><b>Draft</b><span class="vn">Script changes not designed yet</span></span><small>${p.viewing ? "Waiting for you in the current version" : "Update slides to save them as a version"}</small></div>` : "";
  $("#verMenu").innerHTML = `<div class="menu-h">Version history</div>${draftRow}${rows}`;
}
$("#verMenu").addEventListener("click", e => {
  const b = e.target.closest(".vrow[data-n]"); if(!b) return;
  $("#verSel").open = false;
  if(W.busy){ toast("Claude is still designing. Try again when it finishes."); return; }
  const n = +b.dataset.n; if(n === W.version) return;
  openProject(W.project, n === W.current.current ? undefined : n).catch(err => toast(err.message));
});
$("#verBack").addEventListener("click", () => openProject(W.project));
$("#verRestore").addEventListener("click", async () => {
  try{
    const n = W.version; await post(`/api/projects/${W.project}/restore`, {version: n}); await openProject(W.project); loadModules();
    toast(`Version ${n} is current again, saved as version ${W.current.current}.`);
  }catch(err){ toast(err.message); }
});
function showHome(){
  clearTimeout(W.parseTimer); W.project = null; W.current = null; W.designed = false; W.outline = null; box.value = ""; W.saved = "";
  W.viewing = null; box.readOnly = false; document.body.removeAttribute("data-viewing"); $("#verBar").hidden = true;
  delete document.body.dataset.module; document.title = SITE; if(typeof switchChat === "function") switchChat();
  document.querySelector('.tabs a[data-page="write"]').setAttribute("href", "#write");
  $("#wHero").hidden = false; $("#wHead").hidden = true; $("#cardScript").hidden = true; $("#cardReview").hidden = true;
  $("#wSuggest").innerHTML = ""; $("#wStats").textContent = ""; $("#wStatus").textContent = "";
  updateButtons(); loadModules();
}
// rename in place: click the name, type, Enter
$("#wName").addEventListener("click", () => { $("#wName").hidden = true; $("#wNameForm").hidden = false; const i = $("#wNameInput"); i.value = W.current.name; i.focus(); i.select(); });
const endRename = () => { $("#wNameForm").hidden = true; $("#wName").hidden = false; };
$("#wNameInput").addEventListener("keydown", e => { if(e.key === "Escape"){ e.stopPropagation(); endRename(); $("#wName").focus(); } });
$("#wNameInput").addEventListener("blur", () => setTimeout(endRename, 120));
$("#wNameForm").addEventListener("submit", async e => {
  e.preventDefault(); const v = $("#wNameInput").value.trim();
  if(!v || v === W.current.name){ endRename(); return; }
  try{ const r = await post(`/api/projects/${W.project}`, {name: v}, "PATCH"); W.current.name = r.name; setHead(W.current); endRename(); loadModules(); toast("Renamed"); }
  catch(err){ toast(err.message); $("#wNameInput").focus(); }
});

// starting a module: a name first, over a blurred page; Esc or Cancel creates nothing
const nd = {dlg: $("#nameDlg"), input: $("#ndInput"), err: $("#ndErr")};
const NUM = /^\s*(\d+)\s*[·.:\-–—)]\s*/;
function nextNumber(list){ const n = list.map(m => (m.name.match(NUM) || [])[1]).filter(Boolean).map(Number); return String((n.length ? Math.max(...n) : 0) + 1).padStart(2, "0"); }
function openNameDialog(){
  nd.input.value = ""; nd.err.hidden = true; nd.dlg.showModal(); nd.input.focus();
  api("/api/projects").then(l => { W.list = l; }).catch(() => {});
}
$("#wStart").addEventListener("click", openNameDialog);
$("#wNew").addEventListener("click", openNameDialog);
$("#ndNum").addEventListener("click", () => { nd.input.value = `${nextNumber(W.list || [])} · ` + nd.input.value.replace(NUM, ""); nd.input.focus(); });
$("#ndCancel").addEventListener("click", () => nd.dlg.close());
nd.input.addEventListener("input", () => { nd.err.hidden = true; });
$("#nameForm").addEventListener("submit", async e => {
  e.preventDefault();
  if(!nd.input.value.trim()){ nd.err.textContent = "Give the module a name."; nd.err.hidden = false; nd.input.focus(); return; }
  $("#ndGo").disabled = true;
  try{
    const p = await post("/api/projects", {name: nd.input.value});
    nd.dlg.close(); W.focusScript = true; location.hash = `#write/${encodeURIComponent(p.id)}`; loadModules();
  }catch(err){ nd.err.textContent = err.message; nd.err.hidden = false; nd.input.focus(); }
  finally{ $("#ndGo").disabled = false; }
});

/* ---------- your modules ---------- */
async function loadModules(){
  const list = W.list = await api("/api/projects").catch(() => []);
  $("#modules").hidden = !list.length;
  $("#modList").innerHTML = list.map(m => `<article class="mod ${m.id === W.project ? "open" : ""}" data-id="${esc(m.id)}">
    <div class="mod-t">${esc(m.name)}</div><div class="mod-m">${m.title && m.title !== m.name ? `“${esc(m.title)}” · ` : ""}${m.designed ? `${m.versions} version${m.versions > 1 ? "s" : ""}` : "Not designed yet"} · ${ago(m.updated)}</div>
    <div class="mod-a"><button class="link" data-act="open">Open</button>${m.designed ? `<button class="link" data-act="video">Make video</button>` : ""}<button class="link rm" data-act="del">Delete</button></div></article>`).join("");
}
$("#modList").addEventListener("click", async e => {
  const b = e.target.closest("[data-act]"); if(!b) return;
  const id = b.closest(".mod").dataset.id;
  if(b.dataset.act === "open") location.hash = `#write/${encodeURIComponent(id)}`;
  if(b.dataset.act === "video"){ try{ showUpload(await post(`/api/projects/${id}/to-video`, {})); location.hash = "#create"; }catch(err){ toast(err.message); } }
  if(b.dataset.act === "del" && confirm("Delete this module and all its versions? Videos you've made from it are not affected.")){
    await api(`/api/projects/${id}`, {method: "DELETE"}); if(W.project === id){ draft.pending = null; location.hash = "#write"; } loadModules();
  }
});

/* ---------- start ---------- */
pageHooks.write = async arg => {
  const s = await api("/api/settings").catch(() => null); W.keySet = !!(s && s.api_key.set); W.quality = (s && s.design_quality) || "balanced";
  if(arg){
    if(arg !== W.project){
      try{ await openProject(arg); }
      catch{ toast("That module wasn't found."); location.hash = "#write"; return; }
    }
    updateButtons(); loadModules();
    if(W.focusScript){ W.focusScript = false; box.focus(); box.setSelectionRange(box.value.length, box.value.length); }      // a module you just named: start writing
  }else if(W.project){ await draft.flush(); showHome(); }
  else{ updateButtons(); loadModules(); }
};
(async () => {
  const s = await api("/api/settings").catch(() => null); W.keySet = !!(s && s.api_key.set); W.quality = (s && s.design_quality) || "balanced";
  const active = await api("/api/write/active").catch(() => []);
  if(active.length){                                                    // a design is still running: pick it up where it is
    trackJob(active[0], active[0].project);
    if(document.body.dataset.page === "write" && !location.hash.includes("/")) location.hash = `#write/${encodeURIComponent(active[0].project)}`;
  }
  updateButtons(); loadModules();
})();
