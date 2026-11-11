// The script assistant: a floating chat that builds the script with you and keeps tweaking it (and the slides) as you talk.
// It edits the script box on the Write page (with an undo); designing slides stays an explicit step.
const C = {open: false, busy: false, items: [], cost: 0, rec: null, listening: false, auto: (() => { try{ return localStorage.getItem("h2m-chat-auto") === "1"; }catch{ return false; } })()};
const aiEl = {panel: $("#aiPanel"), orb: $("#aiOrb"), log: $("#aiLog"), chips: $("#aiChips"), input: $("#aiInput"), send: $("#aiSend"), state: $("#aiState")};
// The conversation belongs to the module and is kept with it (on disk, not in the browser), so it is there on any device and after a reload.
const store = {
  async load(pid){
    try{
      const items = (await api(`/api/projects/${pid}/chat`)).items;
      if(items.length) return items;
      const old = JSON.parse(localStorage.getItem("h2m-chat:" + pid) || "[]");           // a conversation this browser kept before chats lived with the module
      if(old.length){ post(`/api/projects/${pid}/chat`, {items: old}, "PUT").catch(() => {}); return old; }
    }catch{}
    return [];
  },
  save(pid){
    pid = pid || chatFor; if(!pid) return;
    const items = C.items.filter(i => i.text || i.kind).slice(-60).map(({before, running, state, ...rest}) => rest);
    post(`/api/projects/${pid}/chat`, {items}, "PUT").catch(() => {});
  },
};
const STARTERS_NEW = ["Help me plan a module from scratch", "Write a 5 minute script on a topic", "I'll paste my notes"];
const STARTERS_HAVE = ["Make it shorter", "Make the opening more engaging", "Add a closing recap slide"];

/* a small, safe renderer: paragraphs, **bold**, `code` and "- " lists */
function md(text){
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = []; let list = null;
  for(const line of String(text).split("\n")){
    const li = line.match(/^\s*[-*•]\s+(.*)/);
    if(li){ (list ||= []).push(`<li>${inline(li[1])}</li>`); continue; }
    if(list){ out.push(`<ul>${list.join("")}</ul>`); list = null; }
    if(line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if(list) out.push(`<ul>${list.join("")}</ul>`);
  return out.join("");
}

/* ---------- open and close ---------- */
function setOpen(on){
  C.open = on; aiEl.panel.hidden = !on; aiEl.orb.setAttribute("aria-expanded", on);
  aiEl.orb.setAttribute("aria-label", on ? "Close the script assistant" : "Open the script assistant"); aiEl.orb.classList.remove("hello");
  if(on){ render(); setTimeout(() => aiEl.input.focus(), 60); }
}
aiEl.orb.addEventListener("click", () => setOpen(!C.open));
$("#aiClose").addEventListener("click", () => { setOpen(false); aiEl.orb.focus(); });
$("#aiWide").addEventListener("click", () => aiEl.panel.classList.toggle("wide"));
$("#wAsk").addEventListener("click", () => setOpen(true));
addEventListener("keydown", e => { if(e.key === "Escape" && C.open && aiEl.panel.contains(document.activeElement)){ setOpen(false); aiEl.orb.focus(); } });
$("#aiNew").addEventListener("click", () => {
  if(C.busy) return;
  C.items = []; C.cost = 0; store.save(); try{ localStorage.removeItem("h2m-chat:" + chatFor); }catch{} render(); aiEl.input.focus();
});
setTimeout(() => { if(!C.open && document.body.dataset.page === "write"){ aiEl.orb.classList.add("hello"); setTimeout(() => aiEl.orb.classList.remove("hello"), 7000); } }, 1200);
// Opening another module brings its own conversation (and leaving for the module list closes the assistant). Not while a reply is on its way.
let chatFor = null;
async function switchChat(){
  if(chatFor === W.project || C.busy || C.items.some(i => i.running)) return;
  const pid = chatFor = W.project; C.cost = 0; C.items = []; C.stage = "";
  if(!pid){ if(C.open) setOpen(false); return; }
  const items = await store.load(pid);
  if(chatFor !== pid || W.project !== pid){ chatFor = null; return; }                // moved on while it loaded: try again for the new one
  C.items = [...items, ...C.items]; render();                                          // anything said while it loaded stays
}
setInterval(switchChat, 300);                                                          // (and straight away when a module opens: see showModule)

/* ---------- drawing the conversation ---------- */
const slideTitle = id => id === "s0" ? "Title slide" : ((W.outline && W.outline.slides.find(x => x.id === id)) || {}).title || id;
const SPARK = `<svg viewBox="0 0 16 16"><path d="M8 1.5l1.4 3.9L13.5 7 9.4 8.4 8 12.5 6.6 8.4 2.5 7l4.1-1.6z"/></svg>`;
const designed = () => !!(W.project && W.current && W.current.versions && W.current.versions.length);
function card(i, idx){
  if(i.kind !== "update") return "";
  const scriptRows = (i.changes || []).map(c => `<li><span class="tag ${c.kind}">${c.kind}</span><span>${c.slide === "s0" ? "Title slide · " : ""}${esc(c.title)}</span></li>`).join("")
    || (i.summary || []).map(s => `<li><span>${esc(s)}</span></li>`).join("");
  const lookRows = (i.requests || []).map(r => `<li><span class="tag look">${r.slides.length ? r.slides.map(slideTitle).join(", ") : "all slides"}</span><span>${esc(r.request)}</span></li>`).join("");
  const title = scriptRows && lookRows ? "Script and look" : lookRows ? "Change to how it looks" : "Script updated";
  const busy = i.running, finished = i.done || i.failed;
  const status = i.undone ? "Undone. Your script is back as it was." : busy ? `<span class="spin"></span>${esc(i.state || "Starting…")}` : i.done ? `✓ ${esc(i.done)}` : i.failed ? esc(i.failed) : "";
  const go = designed() ? "Apply to slides" : "Design slides";
  const acts = i.undone || busy || i.done ? "" : `<div class="acts"><button type="button" class="go" data-act="apply">${i.failed ? "Try again" : go}</button>${i.before != null && !i.failed ? `<button type="button" data-act="undo">Undo</button>` : ""}</div>`;
  return `<div class="ai-card" data-i="${idx}"><h5>${SPARK.replace("<svg", '<svg stroke="none" fill="currentColor"')}${title}</h5><ul>${scriptRows}${lookRows}</ul>
    ${status ? `<div class="quiet${i.failed ? " bad" : ""}">${status}</div>` : ""}${acts}</div>`;
}
function render(){
  const log = aiEl.log, atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 80 || !log.children.length;
  if(!C.items.length){
    const have = /^##\s/m.test(box.value);                                  // a script with slides in it (a new module is only its title)
    log.innerHTML = `<div class="ai-hello"><div class="big">${have ? "Let's improve your script." : "What's the video about?"}</div>
      <p>${have ? "Ask for changes in plain words: tone, length, a new slide, a stronger opening, or how a slide should look." : "Tell me the topic and who it's for, and I'll write a first draft. Then we'll tweak it together."}</p></div>`;
    renderChips(have ? STARTERS_HAVE : STARTERS_NEW);
  }else{
    // only things that have not been on screen yet fade in, so a streaming reply doesn't flicker as it grows
    const fresh = i => { const n = !i.shown; return n ? " new" : ""; };
    const html = C.items.map((i, k) => {
      const h = i.kind === "media" ? (typeof mediaCard === "function" ? mediaCard(i).replace('class="ai-card media"', `class="ai-card media${fresh(i)}"`) : "")
        : i.kind ? card(i, k).replace('class="ai-card"', `class="ai-card${fresh(i)}"`)
        : i.role === "user" ? `<div class="ai-msg user${fresh(i)}">${(i.images || []).map(m => `<img class="ai-msg-img" src="${m.preview}" alt="${esc(m.name)}">`).join("")}${esc(i.text).replace(/\n/g, "<br>")}</div>`
        : i.error ? `<div class="ai-msg err${fresh(i)}">${esc(i.text)}</div>` : i.text ? `<div class="ai-msg bot${fresh(i)}">${md(i.text)}</div>` : "";
      if(h) i.shown = true;
      return h;
    }).join("");
    log.innerHTML = html
      + (C.busy && !(C.items.at(-1) && C.items.at(-1).streaming && C.items.at(-1).text) ? `<div class="ai-typing" aria-label="Thinking"><i></i><i></i><i></i></div>` : "");
    const lastBot = [...C.items].reverse().find(i => i.role === "assistant" && !i.kind && !i.error);
    renderChips(!C.busy && lastBot && lastBot === C.items.filter(i => !i.kind).at(-1) && lastBot.suggestions ? lastBot.suggestions : []);
  }
  $("#aiAutoRow").hidden = !designed() || !!W.viewing;
  aiEl.input.disabled = !!W.viewing; aiEl.input.placeholder = W.viewing ? "Go back to the current version to talk to me" : (C.attach && C.attach.length) ? "Say what to do with it…" : "Tell me what to write or change…";
  aiEl.panel.classList.toggle("busy", C.busy);
  aiEl.send.disabled = C.busy || !!W.viewing;
  $("#aiModule").textContent = W.current ? W.current.name : "";
  aiEl.state.textContent = C.busy ? (C.stage || "Thinking…") : C.cost ? `Ready · about $${C.cost.toFixed(2)} this chat` : "Ready when you are";
  if(atEnd) log.scrollTop = log.scrollHeight;
}
function renderChips(list){
  const key = list.join("|"); if(aiEl.chips.dataset.key === key) return;
  aiEl.chips.dataset.key = key; aiEl.chips.classList.add("new"); aiEl.chips.innerHTML = list.map(t => `<button type="button">${esc(t)}</button>`).join("");
}
$("#aiAuto").checked = C.auto;
$("#aiAuto").addEventListener("change", e => { C.auto = e.target.checked; try{ localStorage.setItem("h2m-chat-auto", C.auto ? "1" : "0"); }catch{} });
aiEl.chips.addEventListener("click", e => {
  const b = e.target.closest("button"); if(!b || C.busy) return;
  if(b.textContent === "I'll paste my notes"){ aiEl.input.value = "Here are my notes:\n\n"; aiEl.input.focus(); autosize(); return; }
  sendMessage(b.textContent);
});

/* ---------- talking to Claude ---------- */
function autosize(){
  if(!aiEl.input.value){ aiEl.input.style.height = ""; return; }          // empty: one row, whatever the panel is doing
  aiEl.input.style.height = "auto"; aiEl.input.style.height = Math.min(140, aiEl.input.scrollHeight) + "px";
}
aiEl.input.addEventListener("input", autosize);
aiEl.input.addEventListener("keydown", e => { if(e.key === "Enter" && !e.shiftKey && !e.isComposing){ e.preventDefault(); $("#aiForm").requestSubmit(); } });
$("#aiForm").addEventListener("submit", e => { e.preventDefault(); const t = aiEl.input.value.trim() || ((C.attach || []).length ? "Here is an image." : ""); if(t && !C.busy) sendMessage(t); });

const VIEWING = "You're viewing an earlier version. Go back to the current one to make changes.";
async function sendMessage(text){
  if(W.viewing){ toast(VIEWING); return; }
  if(C.listening) stopListening();
  const pid = W.project;                                       // this reply belongs to the module it was asked in, even if you move on
  aiEl.input.value = ""; autosize();
  const att = (C.attach || []).splice(0); if(typeof renderAttach === "function") renderAttach();
  const said = att.length ? `${text}\n\n(Attached: ${att.map(a => `“${a.name}”`).join(", ")})` : text;
  C.items.push({role: "user", text, images: att.map(a => ({id: a.id, name: a.name, preview: a.preview})), said}); C.busy = true; C.stage = "Thinking…";
  const bot = {role: "assistant", text: "", streaming: true}; C.items.push(bot); render();
  const history = C.items.filter(i => !i.kind && !i.error && i !== bot && i.text).map(i => ({role: i.role, content: i.said || i.text}));
  try{
    const {id} = await post("/api/write/chat", {messages: history, script: box.value, project_id: W.project, attachments: att.map(a => a.id)});
    let j;
    for(;;){
      await new Promise(r => setTimeout(r, 350));
      j = await api(`/api/write/chat/${id}`);
      if(j.stage && j.status === "running" && C.stage !== j.stage){ C.stage = j.stage; render(); }
      if(j.reply && j.reply !== bot.text){ bot.text = j.reply; C.stage = j.status === "running" ? (j.stage || "Writing…") : C.stage; render(); }
      else if(j.status === "running" && bot.text) C.stage = "Updating your script…";
      if(j.status !== "running") break;
    }
    if(j.status === "failed") throw new Error(j.error);
    const r = j.result; bot.text = r.reply; bot.streaming = false; bot.suggestions = r.suggestions; C.cost += r.cost || 0;
    let before = null;
    const here = W.project === pid;
    if(r.script && here){
      before = box.value; box.value = r.script; draft.set(r.script); parseNow();
      box.classList.remove("flash"); void box.offsetWidth; box.classList.add("flash");
    }
    if(r.media && r.media.length){ C.items.push({kind: "media", media: r.media}); if(typeof loadMedia === "function") loadMedia(); }
    if((r.script && here) || r.visual_requests.length){
      const c = {kind: "update", changes: r.changes, summary: r.summary, requests: r.visual_requests, before};
      C.items.push(c);
      if(C.auto && designed() && here) setTimeout(() => applyCard(c), 0);
    }
  }catch(err){
    C.items = C.items.filter(i => i !== bot); C.items.push({role: "assistant", error: true, text: err.message});
  }finally{
    C.busy = false; C.stage = ""; bot.streaming = false; store.save(pid); render(); if(C.open) aiEl.input.focus();
  }
}

/* ---------- the buttons on a card ---------- */
async function applyCard(i){
  if(i.running) return;
  if(W.viewing){ toast(VIEWING); return; }
  if(!designed()){                                            // nothing designed yet: the page's own Design button does it
    if($("#wDesign").disabled){ toast(W.busy ? "Claude is still designing. Try again when it finishes." : !W.keySet ? "Add your Anthropic API key in Settings first." : "The slides already match your script."); return; }
    $("#wDesign").click(); setOpen(false); return;
  }
  if(W.busy){ toast("Claude is still designing. Try again when it finishes."); return; }
  i.running = true; i.failed = ""; i.state = "Starting…"; render();
  try{
    const r = await post(`/api/projects/${W.project}/apply`, {script: box.value, requests: i.requests || []});
    if(!r.job){ i.running = false; i.done = "The slides already match."; store.save(); render(); return; }
    trackJob(r.job, W.project, true);                          // the page shows the same progress; this keeps the chat in step
    for(;;){
      await new Promise(res => setTimeout(res, 1200));
      const j = await api(`/api/write/jobs/${r.job.id}`);
      i.state = `${Math.round(j.progress * 100)}% · ${j.status === "queued" ? "Waiting for the previous design" : j.label}`; render();
      if(j.status === "done"){ i.running = false; i.done = r.changed && r.changed.length ? `Slides updated (${r.changed.length} redesigned).` : "Slides updated."; delete i.before; break; }
      if(j.status === "failed") throw new Error(j.error || "The design failed");
    }
  }catch(err){ i.running = false; i.failed = err.message; }
  store.save(); render();
}

aiEl.log.addEventListener("click", async e => {
  const b = e.target.closest("[data-act]"); if(!b) return;
  const i = C.items[+b.closest(".ai-card").dataset.i];
  if(W.viewing){ toast(VIEWING); return; }
  if(b.dataset.act === "undo"){ box.value = i.before; draft.set(i.before); parseNow(); i.undone = true; delete i.before; store.save(); render(); toast("Script restored"); }
  if(b.dataset.act === "apply") applyCard(i);
});

/* ---------- speaking instead of typing ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function stopListening(){ try{ C.rec && C.rec.stop(); }catch{} C.listening = false; $("#aiMic").classList.remove("on"); $("#aiMic").setAttribute("aria-label", "Speak your message"); }
if(SR){
  const mic = $("#aiMic"); mic.hidden = false;
  mic.addEventListener("click", () => {
    if(C.listening){ stopListening(); return; }
    const rec = C.rec = new SR(); rec.lang = navigator.language || "en-US"; rec.interimResults = true; rec.continuous = true;
    const base = aiEl.input.value ? aiEl.input.value.replace(/\s*$/, " ") : "";
    rec.onresult = ev => { aiEl.input.value = base + [...ev.results].map(r => r[0].transcript).join(" ").trim(); autosize(); };
    rec.onend = () => { C.listening = false; mic.classList.remove("on"); };
    rec.onerror = ev => { C.listening = false; mic.classList.remove("on"); if(ev.error === "not-allowed") toast("Allow the microphone in your browser to speak."); };
    try{ rec.start(); C.listening = true; mic.classList.add("on"); mic.setAttribute("aria-label", "Stop listening"); }catch{}
  });
}
