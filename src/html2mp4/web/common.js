// Shared helpers and page routing.
const $ = s => document.querySelector(s);
const fmt = s => { s = Math.max(0, Math.round(s)); const m = Math.floor(s/60); return m ? `${m} min ${String(s%60).padStart(2,"0")} s` : `${s} s`; };
const clock = s => { s = Math.round(s); return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`; };
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function toast(msg){ const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2600); }
async function api(url, opts){ const r = await fetch(url, opts); const b = await r.json().catch(() => ({})); if(!r.ok) throw new Error(b.detail || "Something went wrong."); return b; }
addEventListener("scroll", () => $("#top").classList.toggle("scrolled", scrollY > 8), {passive:true});

/* ---------- pages: #create, #settings (and #library, which lives on the Create page) ---------- */
const PAGES = ["write", "create", "settings"];
const pageHooks = {};                       // page name -> function run when the page is shown
function route(){
  const h = location.hash.slice(1) || "write";
  const page = PAGES.includes(h) ? h : "create";
  document.body.dataset.page = page;
  document.querySelectorAll(".page").forEach(p => p.hidden = p.id !== `page-${page}`);
  document.querySelectorAll(".tabs a").forEach(a => a.dataset.page === page ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  if(h === "library") setTimeout(() => $("#library").scrollIntoView({behavior:"smooth"}), 50);
  else scrollTo({top:0});
  pageHooks[page]?.();
}
addEventListener("hashchange", route);
addEventListener("DOMContentLoaded", route);
