// The Create video page: upload, voice, music, preview, render, library.
const STEPS = ["Recording the voiceover","Timing the animations","Animating the slides","Mixing the sound","Finishing up"];
const SHORT = ["Voiceover","Timing","Animation","Sound mix","Finishing"];
const state = { upload:null, voice:"af_heart", speed:0.9, music:"gentle-pulse", volume:"balanced", quality:"1440p", job:null, options:null, preview:null };
const VOL = {subtle:"subtle", balanced:"balanced", present:"present"};
const settingsKey = () => [state.upload?.upload_id, state.voice, state.speed, state.music, state.volume].join("|");
const fileUrl = (id, kind, dl) => `/api/jobs/${id}/file/${kind}${dl ? "?download=1" : ""}`;

/* ---------- audio previews ---------- */
const audio = new Audio(); let playingBtn = null;
function stopAudio(){ audio.pause(); if(playingBtn){ playingBtn.classList.remove("playing","loading"); playingBtn = null; } }
audio.addEventListener("ended", stopAudio);
audio.addEventListener("playing", () => playingBtn && playingBtn.classList.replace("loading","playing"));
audio.addEventListener("error", () => { if(playingBtn){ toast("Couldn't load that preview."); stopAudio(); } });
function preview(btn, url){
  if(playingBtn === btn){ stopAudio(); return; }
  stopAudio(); playingBtn = btn; btn.classList.add("loading");
  audio.src = url; audio.play().catch(() => {});
}
const playSvg = `<svg class="i-play" viewBox="0 0 12 12"><path d="M3 1.5v9l7.5-4.5z"/></svg><svg class="i-stop" viewBox="0 0 12 12"><rect x="2.5" y="2.5" width="7" height="7" rx="1.2"/></svg>`;

/* ---------- options ---------- */
function tile(group, id, name, desc, previewUrl, extra=""){
  const el = document.createElement("div");
  el.className = "tile"; el.setAttribute("role","radio"); el.tabIndex = 0; el.dataset.id = id;
  el.innerHTML = `<div class="tile-text"><div class="tile-name">${esc(name)}${extra}</div><div class="tile-desc">${esc(desc)}</div></div>` +
    (previewUrl ? `<button class="play" aria-label="Preview ${esc(name)}">${playSvg}</button>` : "");
  el.addEventListener("click", e => { if(e.target.closest(".play")) return; select(group, id); });
  el.addEventListener("keydown", e => { if(e.key === " " || e.key === "Enter"){ e.preventDefault(); select(group, id); } });
  const p = el.querySelector(".play");
  if(p) p.addEventListener("click", () => preview(p, typeof previewUrl === "function" ? previewUrl() : previewUrl));
  return el;
}
function select(group, id){
  state[group] = id;
  document.querySelectorAll(`#${group === "voice" ? "voices" : "music"} .tile`).forEach(t => t.setAttribute("aria-checked", t.dataset.id === id));
  $("#volRow").classList.toggle("off", state.music === "none");
  summary();
}
function seg(sel, key, after){
  document.querySelectorAll(`${sel} button`).forEach(b => b.addEventListener("click", () => {
    state[key] = isNaN(+b.dataset.v) ? b.dataset.v : parseFloat(b.dataset.v);
    document.querySelectorAll(`${sel} button`).forEach(x => x.setAttribute("aria-checked", x === b));
    after && after(); summary();
  }));
}
seg("#vol", "volume");
seg("#qual", "quality", () => { $("#qualHint").textContent = state.quality === "1440p"
  ? "Sharpest text, still a small web-friendly file" : "Full HD, quicker to make and a little smaller"; });
async function loadOptions(){
  const o = state.options = await api("/api/options");
  $("#outDir").textContent = o.output.replace(/^\/Users\/[^/]+/, "~");
  $("#libWhere").textContent = "Saved in " + o.output.replace(/^\/Users\/[^/]+/, "~");
  o.voices.forEach((v, i) => $("#voices").append(tile("voice", v.id, v.name, v.desc, () => `/api/voice-sample/${v.id}?speed=${state.speed}`, i === 0 ? `<span class="badge">Recommended</span>` : "")));
  $("#music").append(tile("music", "none", "No music", "Voice only", null));
  o.music.forEach(m => $("#music").append(tile("music", m.id, m.name, m.desc, `/api/music-preview/${m.id}`, m.id === "gentle-pulse" ? `<span class="badge">Default</span>` : "")));
  select("voice", state.voice); select("music", state.music);
}
seg("#pace", "speed", stopAudio);
$("#ownInput").addEventListener("change", async e => {
  const f = e.target.files[0]; if(!f) return;
  const fd = new FormData(); fd.append("file", f);
  try{
    const r = await api("/api/music-upload", {method:"POST", body:fd});
    document.querySelector('#music .tile[data-id^="upload:"]')?.remove();
    $("#music").append(tile("music", r.music_id, "Your track", r.name, null));
    select("music", r.music_id); toast("Your track will play under the narration");
  }catch(err){ toast(err.message); }
  e.target.value = "";
});

/* ---------- upload ---------- */
const drop = $("#drop");
["dragenter","dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave","drop"].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove("over")));
drop.addEventListener("drop", e => { e.preventDefault(); if(e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
$("#fileInput").addEventListener("change", e => { if(e.target.files[0]) upload(e.target.files[0]); e.target.value = ""; });
$("#changeFile").addEventListener("click", () => $("#fileInput").click());

async function upload(f){
  $("#uploadErr").classList.remove("show");
  drop.classList.add("busy"); $("#dropText").textContent = "Reading your module";
  const fd = new FormData(); fd.append("file", f);
  try{
    const u = state.upload = await api("/api/inspect", {method:"POST", body:fd});
    drop.style.display = "none"; $("#file").classList.add("show");
    $("#fileTitle").textContent = u.title;
    const mins = Math.max(1, Math.round(u.words / 2.4 / state.speed / 60));
    $("#fileMeta").innerHTML = `<span>${esc(u.filename)}</span><i>·</i><span>${u.scenes.length} slides</span><i>·</i><span>${u.sentences} sentences</span><i>·</i><span>about ${mins} min of video</span>`;
    $("#scriptBody").innerHTML = u.scenes.map((s, i) => `<div class="scene"><h4>Slide ${i + 1}</h4>${s.chunks.map(c => `<p>${esc(c)}</p>`).join("")}</div>`).join("");
    $("#script").hidden = false;
    ["#cardVoice","#cardMusic","#cardCreate"].forEach(s => $(s).classList.remove("locked"));
    summary(); toast("Module loaded");
  }catch(err){
    $("#uploadErr").textContent = err.message; $("#uploadErr").classList.add("show");
  }finally{ drop.classList.remove("busy"); $("#dropText").textContent = "Drop your HTML file here"; }
}

function summary(){
  const u = state.upload; if(!u || !state.options) return;
  const v = state.options.voices.find(x => x.id === state.voice);
  const m = state.music === "none" ? "no music" : (state.options.music.find(x => x.id === state.music)?.name.toLowerCase() || "your track");
  const len = u.words / 2.4 / state.speed;
  const make = 40 + len * (state.quality === "1080p" ? 1.4 : 2.2);
  const vol = state.music === "none" ? "" : ` at ${state.volume} volume`;
  $("#createSum").innerHTML = `<b>${esc(v.name)}</b> voice, ${esc(m)}${vol}. About <b>${fmt(len)}</b> of video, ready in roughly ${Math.max(1, Math.round(make / 60))} min.`;
  $("#go").disabled = false;
  $("#pvGo").disabled = state.preview && state.preview.status === "running";
  $("#pvStale").classList.toggle("show", !!(state.preview && state.preview.done && state.preview.key !== settingsKey()));
}

/* ---------- preview ---------- */
const jobBody = () => ({upload_id: state.upload.upload_id, voice: state.voice, speed: state.speed, music: state.music,
                        music_volume: state.volume, quality: state.quality});
const waitText = x => x.waiting_for ? `Waiting for “${x.waiting_for}” to finish first` : "Starting…";
function describe(j){
  const o = state.options, v = o.voices.find(x => x.id === j.voice)?.name || j.voice;
  const pace = {0.85:"relaxed", 0.9:"natural", 1:"brisk"}[j.speed] || `${j.speed}×`;
  const m = j.music === "none" ? "no music" : `${(o.music.find(x => x.id === j.music)?.name || "your track").toLowerCase()} (${j.music_volume})`;
  return `<b>${o.preview_seconds}-second preview</b> · ${esc(v)}, ${pace} pace · ${esc(m)}`;
}
function previewIdle(text){ $("#pvGo").disabled = !state.upload; $("#pvGoText").textContent = text; }
function pollPreview(j, key){
  state.preview = {id: j.id, key, status: "running"};
  $("#pv").classList.add("show"); $("#pvWait").hidden = false; $("#pvPlayerWrap").hidden = true; $("#pvCancel").hidden = false;
  $("#pvMeta").innerHTML = describe(j); $("#pvStale").classList.remove("show");
  $("#pvGo").disabled = true; $("#pvGoText").textContent = "Preparing…";
  clearInterval(state.pvTimer);
  const tick = async () => {
    const x = await api(`/api/jobs/${j.id}`).catch(() => null); if(!x || state.preview?.id !== j.id) return;
    $("#pvLabel").textContent = x.status === "queued" ? waitText(x) : x.status === "cancelling" ? "Stopping…" : `${x.label}… ${Math.round(x.progress * 100)}%`;
    $("#pvBar").style.width = Math.max(3, Math.round(x.progress * 100)) + "%";
    if(!["done","failed","cancelled"].includes(x.status)) return;
    clearInterval(state.pvTimer); state.preview.status = x.status; state.preview.done = x.status === "done";
    if(x.status === "cancelled"){ $("#pv").classList.remove("show"); previewIdle("Preview 10 s"); return; }
    previewIdle("Preview again");
    if(x.status === "failed"){ $("#pv").classList.remove("show"); toast(x.error || "The preview couldn't be made"); return; }
    const pl = $("#pvPlayer");
    pl.innerHTML = `<track kind="captions" srclang="en" label="English" src="${fileUrl(x.id, "vtt")}">`;
    pl.src = fileUrl(x.id, "mp4");
    $("#pvWait").hidden = true; $("#pvPlayerWrap").hidden = false;
    pl.play().catch(() => {});
    summary();
  };
  tick(); state.pvTimer = setInterval(tick, 600);
}
$("#pvGo").addEventListener("click", async () => {
  stopAudio(); $("#pvPlayer").pause();
  $("#pvGo").disabled = true;
  try{
    const j = await api("/api/preview", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(jobBody())});
    pollPreview(j, settingsKey());
  }catch(err){ toast(err.message); previewIdle("Preview 10 s"); }
});
$("#pvCancel").addEventListener("click", async () => {
  if(!state.preview) return;
  $("#pvCancel").hidden = true; $("#pvLabel").textContent = "Stopping…";
  await fetch(`/api/jobs/${state.preview.id}/cancel`, {method:"POST"});
});

/* ---------- create & progress ---------- */
$("#steps").innerHTML = SHORT.map(s => `<div class="step"><i></i><span>${s}</span></div>`).join("");
$("#go").addEventListener("click", async () => {
  stopAudio(); $("#pvPlayer").pause(); $("#go").disabled = true;
  try{
    const j = await api("/api/jobs", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(jobBody())});
    track(j);
  }catch(err){ toast(err.message); $("#go").disabled = false; }
});
function view(which){
  $("#create").style.display = which === "create" ? "" : "none";
  $("#prog").classList.toggle("show", which === "prog");
  $("#result").classList.toggle("show", which === "result");
  ["#cardUpload","#cardVoice","#cardMusic"].forEach(s => $(s).classList.toggle("locked", which === "prog" || (s !== "#cardUpload" && !state.upload)));
}
function track(j){
  state.job = j.id; view("prog"); render(j);
  $("#cardCreate").scrollIntoView({behavior:"smooth", block:"center"});
  clearInterval(track._t);
  track._t = setInterval(async () => {
    try{
      const x = await api(`/api/jobs/${j.id}`); render(x);
      if(["done","failed","cancelled"].includes(x.status)){ clearInterval(track._t); loadLibrary(); }
    }catch{}
  }, 800);
}
function render(j){
  $("#progTitle").textContent = j.title;
  const p = Math.round((j.progress || 0) * 100);
  $("#pct").innerHTML = `${p}<small>%</small>`;
  $("#barFill").style.width = Math.max(2, p) + "%";
  $("#progLabel").textContent = j.status === "queued" ? waitText(j) : j.status === "cancelling" ? "Stopping…" : (j.label || "Working");
  $("#progCancel").disabled = j.status === "cancelling";
  const k = (j.label || "").startsWith("Paused") ? 2 : STEPS.indexOf(j.label);
  document.querySelectorAll(".step").forEach((s, i) => { s.classList.toggle("done", k > i || j.status === "done"); s.classList.toggle("active", i === k && j.status === "running"); });
  $("#eta").textContent = j.eta != null ? (j.eta < 20 ? "Almost there…" : `About ${fmt(j.eta)} left`) : "Estimating time…";
  if(j.status === "done") showResult(j);
  if(j.status === "cancelled"){ view("create"); summary(); toast("Video cancelled"); }
  if(j.status === "failed"){ view("create"); $("#go").disabled = false; toast("The video couldn't be created"); $("#uploadErr").textContent = j.error; $("#uploadErr").classList.add("show"); $("#cardUpload").scrollIntoView({behavior:"smooth"}); }
}
function showResult(j){
  view("result");
  const v = state.options.voices.find(x => x.id === j.voice);
  const m = j.music === "none" ? "No music" : (state.options.music.find(x => x.id === j.music)?.name || "Your track");
  $("#resTitle").textContent = j.title;
  $("#resMeta").textContent = `${clock(j.duration)} · ${v ? v.name : j.voice} voice · ${m} · Captions included`;
  const pl = $("#player");
  if(pl.dataset.job !== j.id){
    pl.dataset.job = j.id; pl.innerHTML = `<track kind="captions" srclang="en" label="English" src="${fileUrl(j.id,"vtt")}">`;
    pl.src = fileUrl(j.id, "mp4");
  }
  $("#resDownload").href = fileUrl(j.id, "mp4", 1); $("#resSrt").href = fileUrl(j.id, "srt", 1); $("#resVtt").href = fileUrl(j.id, "vtt", 1);
  $("#resReveal").onclick = () => fetch(`/api/jobs/${j.id}/reveal`, {method:"POST"});
}
$("#progCancel").addEventListener("click", async () => {
  if(!state.job || !confirm("Stop creating this video? You can start it again any time.")) return;
  await fetch(`/api/jobs/${state.job}/cancel`, {method:"POST"});
});
$("#resAgain").addEventListener("click", () => { $("#player").pause(); view("create"); summary(); scrollTo({top:0, behavior:"smooth"}); });

/* ---------- library ---------- */
async function loadLibrary(){
  const list = await api("/api/jobs");
  $("#libCount").textContent = list.filter(j => j.status === "done").length;
  const sig = list.map(j => j.id + j.status + (j.status === "running" ? Math.round(j.progress * 20) : "")).join();
  if(sig === loadLibrary.sig) return list;          // unchanged: don't reload the thumbnails
  loadLibrary.sig = sig;
  if(!list.length){ $("#lib").innerHTML = `<div class="lib-empty">Videos you create will appear here.</div>`; return list; }
  const when = t => new Date(t * 1000).toLocaleString(undefined, {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"});
  $("#lib").innerHTML = `<div class="items">${list.map(j => `
    <article class="item fade-in" data-id="${j.id}">
      <div class="thumb">${j.status === "done"
        ? `<video src="${fileUrl(j.id,"mp4")}#t=4" preload="metadata" muted playsinline></video><span class="dur">${clock(j.duration)}</span>`
        : `<div class="state ${j.status === "failed" ? "err" : ""}">${j.status === "failed" ? esc(j.error || "Failed")
            : j.status === "cancelled" ? "Cancelled" : j.status === "queued" ? "Waiting to start"
            : j.status === "cancelling" ? "Stopping…" : `Creating… ${Math.round(j.progress * 100)}%`}</div>`}</div>
      <div class="item-b">
        <div><div class="item-t">${esc(j.title)}</div><div class="item-m">${when(j.created)}</div></div>
        <div class="item-a">${j.status === "done" ? `
          <a class="link" href="${fileUrl(j.id,"mp4",1)}">Download</a>
          <a class="link" href="${fileUrl(j.id,"srt",1)}">.srt</a>
          <a class="link" href="${fileUrl(j.id,"vtt",1)}">.vtt</a>
          <button class="link" data-act="reveal">Show</button>` : ""}
          ${["done","failed","cancelled"].includes(j.status) ? `<button class="link rm" data-act="rm" title="Remove from this list (the file stays on disk)">Remove</button>`
            : j.status !== "cancelling" ? `<button class="link rm" data-act="cancel">Cancel</button>` : ""}
        </div>
      </div>
    </article>`).join("")}</div>`;
  return list;
}
$("#lib").addEventListener("click", async e => {
  const item = e.target.closest(".item"); if(!item) return;
  const id = item.dataset.id, act = e.target.closest("[data-act]")?.dataset.act;
  if(act === "reveal") return fetch(`/api/jobs/${id}/reveal`, {method:"POST"});
  if(act === "rm"){ await fetch(`/api/jobs/${id}`, {method:"DELETE"}); loadLibrary(); return; }
  if(act === "cancel"){ if(confirm("Stop creating this video?")){ await fetch(`/api/jobs/${id}/cancel`, {method:"POST"}); loadLibrary(); } return; }
  if(e.target.closest(".thumb") && item.querySelector("video")){
    const j = await api(`/api/jobs/${id}`); $("#cardCreate").classList.remove("locked"); showResult(j);
    $("#cardCreate").scrollIntoView({behavior:"smooth", block:"center"});
  }
});

/* ---------- start ---------- */
(async () => {
  await loadOptions();
  await loadLibrary();
  const active = await api("/api/active");       // jobs keep running on this computer even if the page was closed
  const video = active.find(j => j.kind !== "preview"), preview = active.filter(j => j.kind === "preview").pop();
  if(video || preview) $("#cardCreate").classList.remove("locked");
  if(preview) pollPreview(preview, null);
  if(video) track(video);
  setInterval(loadLibrary, 4000);                 // keeps the list current if work was started elsewhere
})().catch(err => toast(err.message));
