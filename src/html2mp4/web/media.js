// The media library: images any module can use (Settings > Media library), the image picker above the script, and image
// attachments in the assistant. Edits (cut out, make it talk, crop...) make a new image; the original stays.
const M = {items: [], kinds: [], open: null, crop: null};
const KIND_LABEL = {mascot: "Mascot", logo: "Logo", icon: "Icon", photo: "Photo", background: "Background", other: "Other"};
const kb = n => n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
const badge = it => it.video ? "Clip" : it.animated ? ({talk: "Talks", character: "Alive"}[it.animated.mode] || "Moves") : it.transparent ? "Cut-out" : "";

async function loadMedia(){
  const r = await api("/api/media").catch(() => ({items: [], kinds: []}));
  M.items = r.items; M.kinds = r.kinds; renderMedia(); renderPicker();
  return r.items;
}
function renderMedia(){
  const g = $("#mdGrid"); if(!g) return;
  const shown = M.items.filter(it => !it.action_of);           // a clip cut out as a character's action lives with that character
  g.innerHTML = shown.length ? shown.slice().reverse().map(it => `<button type="button" class="md-card" data-id="${esc(it.id)}">
      <span class="md-th${it.transparent ? " chk" : ""}"><img src="${it.preview}" alt="" loading="lazy">${badge(it) ? `<i>${badge(it)}</i>` : ""}</span>
      <b>${esc(it.name)}</b><small>${KIND_LABEL[it.kind] || it.kind} · ${it.w}×${it.h} · ${kb(it.bytes)}</small></button>`).join("")
    : `<p class="md-empty">No images yet. Upload a mascot, a logo or an office photo to use them in your videos.</p>`;
}

/* ---------- uploading (Settings, and the assistant) ---------- */
async function uploadImages(files){
  const fd = new FormData(); [...files].forEach(f => fd.append("files", f));
  const r = await api("/api/media", {method: "POST", body: fd});
  if(r.errors && r.errors.length) toast(r.errors.join("; "));
  await loadMedia(); return r.items;
}
$("#mdFile").addEventListener("change", async e => {
  const files = e.target.files; if(!files.length) return;
  try{ const items = await uploadImages(files); toast(`Added ${items.length} image${items.length > 1 ? "s" : ""}. Claude is describing ${items.length > 1 ? "them" : "it"} in the background.`); setTimeout(loadMedia, 9000); }
  catch(err){ toast(err.message); }
  e.target.value = "";
});
const mdDrop = $("#mdDrop");
["dragover", "dragenter"].forEach(ev => mdDrop.addEventListener(ev, e => { e.preventDefault(); mdDrop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => mdDrop.addEventListener(ev, () => mdDrop.classList.remove("over")));
mdDrop.addEventListener("drop", async e => { e.preventDefault(); if(e.dataTransfer.files.length){ try{ await uploadImages(e.dataTransfer.files); toast("Added"); }catch(err){ toast(err.message); } } });

/* ---------- one image: details, edits, downloads ---------- */
$("#mdGrid").addEventListener("click", e => { const c = e.target.closest(".md-card"); if(c) openMedia(c.dataset.id); });
function openMedia(id){
  const it = M.items.find(x => x.id === id); if(!it) return;
  M.open = it; endCrop();
  const vid = $("#mdVid"); vid.hidden = !it.video; $("#mdImg").hidden = !!it.video;
  if (it.video) { vid.src = it.url + "?t=" + Date.now(); vid.play().catch(() => {}); } else { vid.removeAttribute("src"); vid.load(); $("#mdImg").src = it.preview + "?t=" + Date.now(); }
  $("#mdStage").classList.toggle("chk", !!it.transparent);
  $("#mdName").value = it.name; $("#mdDesc").value = it.description || ""; $("#mdSpeaker").value = it.speaker || "";
  $("#mdSpeakerL").hidden = !(it.animated && ["talk", "character"].includes(it.animated.mode));
  renderActor(it);
  $("#mdKind").innerHTML = M.kinds.map(k => `<option value="${k}" ${k === it.kind ? "selected" : ""}>${KIND_LABEL[k] || k}</option>`).join("");
  $("#mdMeta").textContent = [`${it.w}×${it.h}`, kb(it.bytes), it.format.toUpperCase(), it.transparent ? "transparent background" : "",
    it.video ? `${it.seconds} s clip` + (it.speech && it.speech.length ? `, speaks ${it.speech.map(([a, b]) => `${a}–${b} s`).join(", ")}` : ", no speech") : "",
    it.speaker ? `speaks as ${it.speaker}` : "",
    it.animated ? ({talk: "talks while the narrator speaks", character: "always moving; talks while the narrator speaks"}[it.animated.mode] || "loops") : "", it.note ? `made by ${it.note.replace(/_/g, " ")}` : ""].filter(Boolean).join(" · ");
  const fmts = it.format === "svg" ? [["svg"]] : it.video ? [["webm"], ["png"]] : it.animated ? [["gif"], ...(it.animated.rows > 1 ? [["gif", 1]] : []), ["webp"], ["png"]] : [["png"], ["jpg"], ["webp"], ["gif"]];
  $("#mdDl").innerHTML = fmts.map(([f, row]) => `<a class="link" href="/api/media/${encodeURIComponent(it.id)}/download?format=${f}${row ? "&row=1" : ""}">${f.toUpperCase()}${row ? " (talking)" : ""}${(it.animated || it.video) && f === "png" ? " (first frame)" : ""}</a>`).join("");
  document.querySelectorAll("#mdDlg .md-acts button").forEach(b => { const op = b.dataset.op || "crop";
    b.hidden = op === "character" ? !it.video : (it.video && op !== "remove_background");
    b.disabled = it.format === "svg" || (!!it.animated && !["resize", "flip", "trim", "pad", "rotate", "crop"].includes(op)) || (op === "animate" && !it.transparent)
      || (op === "character" && !(it.speech && it.speech.length)); });
  $("#mdDlg [data-op=character]").title = it.speech && it.speech.length ? "Makes a talking character from this clip: the quiet part becomes its idle loop, the speaking part its talking loop" : "This clip has no speech, so there's no talking part to use";
  $("#mdDlg [data-op=animate]").title = it.transparent ? "Claude finds the tail, ears and tongue; they move, the character breathes, and its mouth talks while the narrator speaks" : "Remove the background first: this works on a cut-out";
  $("#mdStatus").textContent = ""; $("#mdDlg").open || $("#mdDlg").showModal();
}
// a character: the voice it speaks with, and what it can do (clips of it, plus built-in motions)
const CV = {voices: null};
async function loadVoices(){ if(!CV.voices){ try{ CV.voices = await api("/api/voices/characters"); }catch(e){ CV.voices = {voices: []}; } } return CV.voices; }
async function renderActor(it){
  const isChar = it.animated && it.animated.mode === "character", isClip = !!it.video;
  $("#mdVoiceL").hidden = !isChar; $("#mdActions").hidden = !isChar; $("#mdClipTools").hidden = !isClip;
  if(isChar) $("#mdBundle").href = `/api/media/${encodeURIComponent(it.id)}/bundle`;
  if(isChar){
    const v = await loadVoices(); if(M.open !== it && M.open && M.open.id !== it.id) return;
    $("#mdVoice").innerHTML = `<option value="">Default (${esc((v.voices[0] || {}).name || "Puppy")})</option>` + v.voices.map(x => `<option value="${esc(x.id)}" ${String(it.voice || "").toLowerCase() === x.name.toLowerCase() || it.voice === x.id ? "selected" : ""}>${esc(x.name)}: ${esc(x.description)}</option>`).join("");
    const clips = (it.actor && it.actor.clips) || {};
    $("#mdActionList").innerHTML = Object.entries(clips).map(([k, c]) => `<span class="md-chip clip" title="A clip of ${esc(it.speaker || it.name)}, ${c.seconds} s"><b>${esc(k)}</b><i>${c.seconds}s</i><button type="button" data-rm="${esc(k)}" aria-label="Remove ${esc(k)}">×</button></span>`).join("")
      + ((it.actor && it.actor.motions) || []).filter(m => !clips[m]).map(m => `<span class="md-chip" title="A built-in motion of the picture"><b>${esc(m)}</b></span>`).join("");
    const vids = M.items.filter(x => x.video && !x.action_of);
    $("#mdActClip").innerHTML = `<option value="">Choose a clip…</option>` + vids.map(x => `<option value="${esc(x.id)}">${esc(x.name)} (${x.seconds}s)</option>`).join("");
    $("#mdActName").value = "";
  }
  if(isClip){
    const chars = M.items.filter(x => x.animated && x.animated.mode === "character");
    $("#mdClipActor").innerHTML = chars.length ? chars.map(x => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("") : `<option value="">No talking character yet</option>`;
    $("#mdClipAs").value = ""; $("#mdPartFrom").value = ""; $("#mdPartTo").value = "";
  }
}
$("#mdVoiceTry").addEventListener("click", () => {
  const id = $("#mdVoice").value || (CV.voices && CV.voices.voices[0] ? CV.voices.voices[0].id : "puppy");
  const a = new Audio(`/api/voice-sample/${encodeURIComponent(id)}`); $("#mdStatus").textContent = "Playing a sample…"; a.onended = () => $("#mdStatus").textContent = ""; a.play().catch(e => $("#mdStatus").textContent = "The sample couldn't be played: " + e.message);
});
$("#mdActionList").addEventListener("click", async e => {
  const b = e.target.closest("[data-rm]"); if(!b) return;
  try{ await api(`/api/media/${M.open.id}/actions/${encodeURIComponent(b.dataset.rm)}`, {method: "DELETE"}); await loadMedia(); openMedia(M.open.id); toast(`Removed “${b.dataset.rm}”`); }catch(err){ toast(err.message); }
});
$("#mdActAdd").addEventListener("click", async () => {
  try{ await post(`/api/media/${M.open.id}/actions`, {name: $("#mdActName").value, clip: $("#mdActClip").value}); const id = M.open.id; await loadMedia(); openMedia(id); toast("Added"); }
  catch(err){ $("#mdStatus").textContent = err.message; }
});
$("#mdClipLink").addEventListener("click", async () => {
  const actor = $("#mdClipActor").value, btn = $("#mdClipLink"); if(!actor){ $("#mdStatus").textContent = "Make a talking character first (open a clip of a character speaking and choose Make a talking character)."; return; }
  const from = parseFloat($("#mdPartFrom").value), to = parseFloat($("#mdPartTo").value);          // optional: only this part of the clip
  btn.disabled = true; $("#mdStatus").textContent = "Cutting the clip out to match the character… (a few seconds)";
  try{ await post(`/api/media/${actor}/actions`, {name: $("#mdClipAs").value, clip: M.open.id, start: isNaN(from) ? null : from, end: isNaN(to) ? null : to}); await loadMedia(); toast(`Added as “${$("#mdClipAs").value}”`); $("#mdStatus").textContent = ""; }
  catch(err){ $("#mdStatus").textContent = err.message; }
  finally{ btn.disabled = false; }
});
$("#mdPartGo").addEventListener("click", () => runEdit("clip", {start: parseFloat($("#mdPartFrom").value), end: parseFloat($("#mdPartTo").value)}));
$("#mdClose").addEventListener("click", () => $("#mdDlg").close());
$("#mdDlg").addEventListener("close", () => $("#mdVid").pause());
$("#mdSave").addEventListener("click", async () => {
  try{ await post(`/api/media/${M.open.id}`, {name: $("#mdName").value, kind: $("#mdKind").value, description: $("#mdDesc").value, speaker: $("#mdSpeaker").value,
        ...(M.open.animated && M.open.animated.mode === "character" ? {voice: $("#mdVoice").value} : {})}, "PATCH"); await loadMedia(); openMedia(M.open.id); toast("Saved"); }
  catch(err){ toast(err.message); }
});
$("#mdDescribe").addEventListener("click", async () => {
  $("#mdStatus").textContent = "Claude is looking at it…";
  try{ const it = await post(`/api/media/${M.open.id}/describe`, {}); $("#mdDesc").value = it.description; await loadMedia(); $("#mdStatus").textContent = it.suggested ? `Suggested name: “${it.suggested.name}” (${KIND_LABEL[it.suggested.kind]}).` : ""; }
  catch(err){ $("#mdStatus").textContent = err.message; }
});
$("#mdDelete").addEventListener("click", async () => {
  if(!confirm(`Delete “${M.open.name}” from the library? Slides already made keep their copy of it.`)) return;
  await api(`/api/media/${M.open.id}`, {method: "DELETE"}); $("#mdDlg").close(); loadMedia();
});
async function runEdit(op, params){
  const st = $("#mdStatus"); st.textContent = "Starting…";
  document.querySelectorAll("#mdDlg .md-acts button").forEach(b => b.disabled = true);
  try{
    const {id} = await post(`/api/media/${M.open.id}/edit`, {op, params});
    for(;;){
      await new Promise(r => setTimeout(r, 700));
      const j = await api(`/api/media/jobs/${id}`); st.textContent = j.label || "Working…";
      if(j.status === "done"){ await loadMedia(); openMedia(j.item.id); toast(`Made “${j.item.name}”`); return; }
      if(j.status === "failed") throw new Error(j.error);
    }
  }catch(err){ st.textContent = err.message; openMedia(M.open.id); st.textContent = err.message; }
}
document.querySelectorAll("#mdDlg .md-acts [data-op]").forEach(b => b.addEventListener("click", () => runEdit(b.dataset.op, b.dataset.p ? JSON.parse(b.dataset.p) : {})));

// crop: drag a box on the picture
function endCrop(){ M.crop = null; $("#mdCrop").hidden = true; $("#mdCropBar").hidden = true; $("#mdStage").classList.remove("cropping"); }
$("#mdCropGo").addEventListener("click", () => { M.crop = {box: null}; $("#mdCropBar").hidden = false; $("#mdStage").classList.add("cropping"); $("#mdCropApply").disabled = true; });
$("#mdCropCancel").addEventListener("click", endCrop);
$("#mdStage").addEventListener("pointerdown", e => {
  if(!M.crop) return; e.preventDefault();
  const r = $("#mdImg").getBoundingClientRect(), fx = x => Math.min(1, Math.max(0, (x - r.left) / r.width)), fy = y => Math.min(1, Math.max(0, (y - r.top) / r.height));
  const x0 = fx(e.clientX), y0 = fy(e.clientY), box = $("#mdCrop"), st = $("#mdStage").getBoundingClientRect();
  const move = ev => {
    const x1 = fx(ev.clientX), y1 = fy(ev.clientY); M.crop.box = [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
    Object.assign(box.style, {left: (r.left - st.left + M.crop.box[0] * r.width) + "px", top: (r.top - st.top + M.crop.box[1] * r.height) + "px",
      width: ((M.crop.box[2] - M.crop.box[0]) * r.width) + "px", height: ((M.crop.box[3] - M.crop.box[1]) * r.height) + "px"});
    box.hidden = false; $("#mdCropApply").disabled = (M.crop.box[2] - M.crop.box[0]) < 0.02 || (M.crop.box[3] - M.crop.box[1]) < 0.02;
  };
  const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
  addEventListener("pointermove", move); addEventListener("pointerup", up);
});
$("#mdCropApply").addEventListener("click", () => { const b = M.crop && M.crop.box; endCrop(); if(b) runEdit("crop", {box: b}); });

/* ---------- Insert image (above the script): adds "Image: NAME" to the slide the cursor is in ---------- */
function renderPicker(){
  const m = $("#wImgMenu"); if(!m) return;
  m.innerHTML = `<div class="menu-h">Media library</div>` + (M.items.filter(i => !i.action_of).length ? M.items.filter(i => !i.action_of).slice().reverse().map(it => `<button type="button" class="ip-row" data-name="${esc(it.name)}">
      <span class="ip-th${it.transparent ? " chk" : ""}"><img src="${it.preview}" alt="" loading="lazy"></span><span><b>${esc(it.name)}</b><small>${KIND_LABEL[it.kind] || it.kind}${badge(it) ? " · " + badge(it) : ""}</small></span></button>`).join("")
    : `<p class="ip-empty">No images yet. Add some in <a href="#settings">Settings > Media library</a>, or attach one in the assistant.</p>`);
}
$("#wImgPick").addEventListener("toggle", () => { if($("#wImgPick").open) loadMedia(); });
$("#wImgMenu").addEventListener("click", e => {
  const b = e.target.closest(".ip-row"); if(!b) return;
  $("#wImgPick").open = false;
  const lines = box.value.split("\n"); let at = box.value.slice(0, box.selectionStart).split("\n").length - 1;
  let head = -1; for(let i = at; i >= 0; i--) if(lines[i].startsWith("## ")){ head = i; break; }
  if(head < 0){ head = lines.findIndex(l => l.startsWith("## ")); if(head < 0){ toast("Add a slide first: a line starting with '## '"); return; } }
  lines.splice(head + 1, 0, `Image: ${b.dataset.name}`);
  box.value = lines.join("\n"); draft.set(box.value); parseNow(); box.focus();
  toast(`Added to “${lines[head].slice(3)}”. The slide shows it when it's designed (or updated).`);
});

/* ---------- attaching images in the assistant ---------- */
C.attach = [];
function renderAttach(){
  const a = $("#aiAtt"); a.hidden = !C.attach.length;
  a.innerHTML = C.attach.map((it, k) => `<span class="ai-chip-img"><img src="${it.preview}" alt=""><b>${esc(it.name)}</b><button type="button" data-k="${k}" aria-label="Remove">×</button></span>`).join("");
}
async function attachFiles(files){
  const imgs = [...files].filter(f => /^image\//.test(f.type) || /\.svg$/i.test(f.name)); if(!imgs.length) return;
  aiEl.state.textContent = "Adding the image to your library…";
  try{ const items = await uploadImages(imgs); C.attach.push(...items); renderAttach(); aiEl.input.focus(); if(!aiEl.input.value) aiEl.input.placeholder = "Say what to do with it…"; }
  catch(err){ toast(err.message); }
  render();
}
$("#aiFile").addEventListener("change", e => { attachFiles(e.target.files); e.target.value = ""; });
$("#aiAtt").addEventListener("click", e => { const b = e.target.closest("[data-k]"); if(b){ C.attach.splice(+b.dataset.k, 1); renderAttach(); } });
aiEl.input.addEventListener("paste", e => { const f = [...(e.clipboardData || {}).files || []]; if(f.length){ e.preventDefault(); attachFiles(f); } });
aiEl.panel.addEventListener("dragover", e => { if([...e.dataTransfer.types].includes("Files")){ e.preventDefault(); aiEl.panel.classList.add("drop"); } });
aiEl.panel.addEventListener("dragleave", e => { if(!aiEl.panel.contains(e.relatedTarget)) aiEl.panel.classList.remove("drop"); });
aiEl.panel.addEventListener("drop", e => { aiEl.panel.classList.remove("drop"); if(e.dataTransfer.files.length){ e.preventDefault(); attachFiles(e.dataTransfer.files); } });

/* the card the chat shows after the assistant edited images */
function mediaCard(i){
  return `<div class="ai-card media"><h5>${SPARK.replace("<svg", '<svg stroke="none" fill="currentColor"')}Media library</h5><div class="ai-media">${i.media.map(r => r.item
    ? `<a class="ai-mi" href="#settings" data-id="${esc(r.item.id)}" title="Open in Settings > Media library"><span class="${r.item.transparent ? "chk" : ""}"><img src="${r.item.preview}?t=${Date.now()}" alt=""></span><b>${esc(r.item.name)}</b><small>${badge(r.item) || KIND_LABEL[r.item.kind] || ""}</small></a>`
    : `<div class="ai-mi bad"><b>${esc(r.op.replace(/_/g, " "))}</b><small>${esc(r.error)}</small></div>`).join("")}</div></div>`;
}
document.addEventListener("click", e => {
  const a = e.target.closest(".ai-mi[data-id]"); if(!a) return;
  setTimeout(async () => { await loadMedia(); openMedia(a.dataset.id); }, 250);
});
pageHooks.settings = (prev => async () => { await prev(); loadMedia(); })(pageHooks.settings);
loadMedia();

// bring in a character file
$("#mdImportFile").addEventListener("change", async e => {
  const f = e.target.files[0]; e.target.value = ""; if(!f) return;
  const fd = new FormData(); fd.append("file", f);
  try{
    toast("Importing the character…");
    const r = await api("/api/media/import", {method: "POST", body: fd});
    await loadMedia(); toast(`Imported “${r.item.name}”` + (r.notes.length ? ". " + r.notes[0] : ""));
  }catch(err){ toast(err.message); }
});
