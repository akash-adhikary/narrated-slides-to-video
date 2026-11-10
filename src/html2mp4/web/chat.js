// The script assistant: a floating chat that builds the script with you and keeps tweaking it (and the slides) as you talk.
// It edits the script box on the Write page (with an undo); designing slides stays an explicit step.
const C = {open: false, busy: false, items: [], cost: 0, rec: null, listening: false};
const aiEl = {panel: $("#aiPanel"), orb: $("#aiOrb"), log: $("#aiLog"), chips: $("#aiChips"), input: $("#aiInput"), send: $("#aiSend"), state: $("#aiState")};
const chatKey = () => "h2m-chat:" + (W.project || "draft");
const store = {
  load(){ try{ return JSON.parse(localStorage.getItem(chatKey()) || "[]"); }catch{ return []; } },
  save(){ try{ localStorage.setItem(chatKey(), JSON.stringify(C.items.filter(i => i.text || i.kind).slice(-60).map(({before, ...rest}) => rest))); }catch{} },
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
  if(on){ if(!C.items.length) C.items = store.load(); render(); setTimeout(() => aiEl.input.focus(), 60); }
}
aiEl.orb.addEventListener("click", () => setOpen(!C.open));
$("#aiClose").addEventListener("click", () => { setOpen(false); aiEl.orb.focus(); });
$("#aiWide").addEventListener("click", () => aiEl.panel.classList.toggle("wide"));
$("#wAsk").addEventListener("click", () => setOpen(true));
addEventListener("keydown", e => { if(e.key === "Escape" && C.open && aiEl.panel.contains(document.activeElement)){ setOpen(false); aiEl.orb.focus(); } });
$("#aiNew").addEventListener("click", () => {
  if(C.busy) return;
  C.items = []; C.cost = 0; store.save(); try{ localStorage.removeItem(chatKey()); }catch{} render(); aiEl.input.focus();
});
setTimeout(() => { if(!C.open && document.body.dataset.page === "write"){ aiEl.orb.classList.add("hello"); setTimeout(() => aiEl.orb.classList.remove("hello"), 7000); } }, 1200);
// switching module on the Write page switches the conversation too
let chatFor = chatKey();
setInterval(() => { if(chatKey() !== chatFor && !C.busy){ const from = chatFor; chatFor = chatKey();
  if(from === "h2m-chat:draft" && W.project && C.items.length){ store.save(); }          // a draft conversation becomes the module's
  C.items = store.load(); if(C.open) render(); } }, 700);

/* ---------- drawing the conversation ---------- */
const slideTitle = id => id === "s0" ? "Title slide" : ((W.outline && W.outline.slides.find(x => x.id === id)) || {}).title || id;
const SPARK = `<svg viewBox="0 0 16 16"><path d="M8 1.5l1.4 3.9L13.5 7 9.4 8.4 8 12.5 6.6 8.4 2.5 7l4.1-1.6z"/></svg>`;
function card(i, idx){
  if(i.kind === "update"){
    const rows = (i.changes || []).map(c => `<li><span class="tag ${c.kind}">${c.kind}</span><span>${c.slide === "s0" ? "Title slide · " : ""}${esc(c.title)}</span></li>`).join("");
    const sum = (i.summary || []).map(s => `<li><span>${esc(s)}</span></li>`).join("");
    const next = W.project ? "Update slides" : "Design slides";
    return `<div class="ai-card" data-i="${idx}"><h5>${SPARK.replace("<svg", '<svg stroke="none" fill="currentColor"')}Script updated</h5><ul>${rows || sum}</ul>
      ${i.undone ? `<div class="quiet">Undone. Your script is back as it was.</div>` : `<div class="acts"><button type="button" class="go" data-act="design">${next}</button>${i.before != null ? `<button type="button" data-act="undo">Undo</button>` : ""}</div>`}</div>`;
  }
  if(i.kind === "visual"){
    return `<div class="ai-card" data-i="${idx}"><h5>${SPARK.replace("<svg", '<svg stroke="none" fill="currentColor"')}Change to how it looks</h5>
      <ul>${i.requests.map(r => `<li><span class="tag">${r.slides.length ? r.slides.map(slideTitle).join(", ") : "all slides"}</span><span>${esc(r.request)}</span></li>`).join("")}</ul>
      ${i.applied ? `<div class="quiet">Sent to the designer. Watch the progress on the page.</div>` : `<div class="acts"><button type="button" class="go" data-act="apply">Apply to slides</button></div>`}</div>`;
  }
  return "";
}
function render(){
  const log = aiEl.log, atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 80 || !log.children.length;
  if(!C.items.length){
    const have = !!box.value.trim();
    log.innerHTML = `<div class="ai-hello"><div class="big">${have ? "Let's improve your script." : "What's the video about?"}</div>
      <p>${have ? "Ask for changes in plain words: tone, length, a new slide, a stronger opening, or how a slide should look." : "Tell me the topic and who it's for, and I'll write a first draft. Then we'll tweak it together."}</p></div>`;
    renderChips(have ? STARTERS_HAVE : STARTERS_NEW);
  }else{
    // only things that have not been on screen yet fade in, so a streaming reply doesn't flicker as it grows
    const fresh = i => { const n = !i.shown; return n ? " new" : ""; };
    const html = C.items.map((i, k) => {
      const h = i.kind ? card(i, k).replace('class="ai-card"', `class="ai-card${fresh(i)}"`) : i.role === "user" ? `<div class="ai-msg user${fresh(i)}">${esc(i.text).replace(/\n/g, "<br>")}</div>`
        : i.error ? `<div class="ai-msg err${fresh(i)}">${esc(i.text)}</div>` : i.text ? `<div class="ai-msg bot${fresh(i)}">${md(i.text)}</div>` : "";
      if(h) i.shown = true;
      return h;
    }).join("");
    log.innerHTML = html
      + (C.busy && !(C.items.at(-1) && C.items.at(-1).streaming && C.items.at(-1).text) ? `<div class="ai-typing" aria-label="Thinking"><i></i><i></i><i></i></div>` : "");
    const lastBot = [...C.items].reverse().find(i => i.role === "assistant" && !i.kind && !i.error);
    renderChips(!C.busy && lastBot && lastBot === C.items.filter(i => !i.kind).at(-1) && lastBot.suggestions ? lastBot.suggestions : []);
  }
  aiEl.panel.classList.toggle("busy", C.busy);
  aiEl.send.disabled = C.busy;
  aiEl.state.textContent = C.busy ? (C.stage || "Thinking…") : C.cost ? `Ready · about $${C.cost.toFixed(2)} this chat` : "Ready when you are";
  if(atEnd) log.scrollTop = log.scrollHeight;
}
function renderChips(list){
  const key = list.join("|"); if(aiEl.chips.dataset.key === key) return;
  aiEl.chips.dataset.key = key; aiEl.chips.classList.add("new"); aiEl.chips.innerHTML = list.map(t => `<button type="button">${esc(t)}</button>`).join("");
}
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
$("#aiForm").addEventListener("submit", e => { e.preventDefault(); const t = aiEl.input.value.trim(); if(t && !C.busy) sendMessage(t); });

async function sendMessage(text){
  if(C.listening) stopListening();
  aiEl.input.value = ""; autosize();
  C.items.push({role: "user", text}); C.busy = true; C.stage = "Thinking…";
  const bot = {role: "assistant", text: "", streaming: true}; C.items.push(bot); render();
  const history = C.items.filter(i => !i.kind && !i.error && i !== bot && i.text).map(i => ({role: i.role, content: i.text}));
  try{
    const {id} = await post("/api/write/chat", {messages: history, script: box.value, project_id: W.project});
    let j;
    for(;;){
      await new Promise(r => setTimeout(r, 350));
      j = await api(`/api/write/chat/${id}`);
      if(j.reply && j.reply !== bot.text){ bot.text = j.reply; C.stage = j.status === "running" ? "Writing…" : C.stage; render(); }
      else if(j.status === "running" && bot.text) C.stage = "Updating your script…";
      if(j.status !== "running") break;
    }
    if(j.status === "failed") throw new Error(j.error);
    const r = j.result; bot.text = r.reply; bot.streaming = false; bot.suggestions = r.suggestions; C.cost += r.cost || 0;
    if(r.script){
      const before = box.value; box.value = r.script; draft.set(r.script); parseNow();
      box.classList.remove("flash"); void box.offsetWidth; box.classList.add("flash");
      C.items.push({kind: "update", changes: r.changes, summary: r.summary, before});
    }
    if(r.visual_requests.length) C.items.push({kind: "visual", requests: r.visual_requests});
  }catch(err){
    C.items = C.items.filter(i => i !== bot); C.items.push({role: "assistant", error: true, text: err.message});
  }finally{
    C.busy = false; C.stage = ""; bot.streaming = false; store.save(); render(); if(C.open) aiEl.input.focus();
  }
}

/* ---------- the buttons on a card ---------- */
aiEl.log.addEventListener("click", async e => {
  const b = e.target.closest("[data-act]"); if(!b) return;
  const i = C.items[+b.closest(".ai-card").dataset.i];
  if(b.dataset.act === "undo"){ box.value = i.before; draft.set(i.before); parseNow(); i.undone = true; delete i.before; store.save(); render(); toast("Script restored"); }
  if(b.dataset.act === "design"){
    if($("#wDesign").disabled){ toast(W.busy ? "Claude is still designing. Try again when it finishes." : !W.keySet ? "Add your Anthropic API key in Settings first." : "The slides already match your script."); return; }
    setOpen(false); $("#wDesign").click();
  }
  if(b.dataset.act === "apply"){
    if(!W.project || !W.current || !W.current.versions.length){ toast("Design the slides first, then apply visual changes."); return; }
    if(box.value !== W.saved){ toast("Update the slides first so they match your script, then apply this."); return; }
    setOpen(false); i.applied = true; store.save();
    for(const r of i.requests) await startJob(post(`/api/projects/${W.project}/revise`, {feedback: r.request, scope: r.slides}).then(x => ({...x, project: W.project})));
  }
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
