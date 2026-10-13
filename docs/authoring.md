# Authoring modules

A module is a single, self-contained HTML file that plays as a narrated slideshow in a browser. Narrated Slides Studio
records it as a video. This page describes the conventions a module must follow, and how to write narration that
sounds right.

The quickest way to start is to copy [`examples/example.html`](../examples/example.html). It is a complete two-slide
module. You can open it in a browser and click to step through it.

## Structure

```html
<div id="frame">
  <div id="stage">                                 <!-- fixed-size 16:9 canvas, e.g. 1280×720 -->
    <section class="slide" id="s0">…</section>     <!-- one per scene -->
    <section class="slide" id="s1">…</section>
  </div>
</div>
<script>
  var scenes = [ … ];                              <!-- the narration -->
</script>
```

### The stage

`#stage` is the canvas that becomes the video frame. Give it a fixed pixel size in a 16:9 ratio. 1280×720 is the
convention, and every example in this repository uses it. The renderer draws the stage at the output resolution
(2560×1440 or 1920×1080) by raising the device pixel ratio, so text and vector graphics stay sharp. Raster images
should be at least twice the size they're displayed at.

`#frame` wraps the stage. Many modules use it to centre and scale the stage in a browser window. The renderer
removes any scaling it applies.

### Slides

Each scene is a `<section class="slide">` with a unique `id`. The renderer adds the class `active` to the current
slide and removes it from the others, so your CSS should show `.slide.active` and hide the rest. The example uses a
0.6 s opacity transition, which also becomes the transition between slides in the video.

### Narration

The narration is a global `scenes` array in a `<script>` block. Each entry names a slide and lists its sentences, in
the order they're spoken:

```js
var scenes = [
  {id:'s0', chunks:[
    "Welcome. This short example shows how a narrated slide module becomes a video.",
    "Everything you see is plain HTML and CSS."]},
  {id:'s1', chunks:[
    "There are three simple rules to follow.",
    "First, each scene is a section with the class slide."]}
];
```

- Write each sentence as a double-quoted string. Escaped characters such as `\"` work.
- A chunk can contain more than one sentence. It's the unit that triggers animations, so split the narration wherever
  something on screen should change.
- Every `id` must match a `<section>` on the page.

### Cues: `data-c` and `data-d`

Elements that should appear during narration carry a `data-c` attribute: the zero-based index of the chunk, within
its slide, that reveals them. The renderer adds the class `on` to an element when its chunk starts. Elements on
earlier slides stay `on`.

```html
<h2 data-c="0">Three simple rules</h2>                     <!-- with the first sentence -->
<div class="card" data-c="1">Scenes</div>                  <!-- with the second -->
<div class="card" data-c="1" data-d="0.6">Sentences</div>  <!-- with the second, 0.6 s later -->
```

`data-d` adds a delay in seconds. It's exposed to CSS as the custom property `--d`, so a typical rule is:

```css
[data-c]      { opacity: 0; transform: translateY(10px);
                transition: opacity .8s ease var(--d, 0s), transform .8s ease var(--d, 0s); }
[data-c].on   { opacity: 1; transform: none; }
```

Animate with CSS transitions or CSS animations. The renderer controls both through the Web Animations API, so they
play at exactly the right moment in every frame. JavaScript-driven animation (`requestAnimationFrame`, timers,
canvas) isn't synchronised and should be avoided.

If an element's animation would still be running when the narration moves to the next slide, the renderer holds the
slide until it finishes. Long delays therefore lengthen the video rather than being cut off.

### Optional player controls

A module may include its own in-browser player: a control bar with the id `bar` and a start overlay with the id
`start`. Both are hidden in the video. Anything else on the stage appears exactly as it does in the browser.

## Writing narration that sounds right

The narrator reads the text literally, so a few habits make a big difference:

- **Spell abbreviations the way they're said.** Write "S Q L" or "sequel", "A I", "H R".
- **Write numbers in words when the reading matters.** "Two thousand twenty-six" rather than "2026" if the year
  should sound a particular way.
- **Use punctuation for pacing.** A comma gives a short pause and a full stop a longer one. The renderer also adds a
  short pause between chunks and before each new slide.
- **Keep sentences short.** One idea per chunk reads well on screen and makes captions easy to follow.
- **Check names.** Product and company names are usually pronounced well. If one isn't, try spacing it out
  ("Thought Spot") or spelling it phonetically.

Use the Studio's **Preview 10 s**, or `html2mp4 module.html --preview 10`, to listen before rendering the whole module.

## Validation

The tool checks a module before converting it and stops with a clear message if:

- there's no `scenes` narration list, or it's empty;
- a scene `id` doesn't match any element on the page;
- there's no `<div id="stage">`.

## Fonts and assets

- Web fonts (for example from Google Fonts) are loaded while rendering. The computer needs an internet connection,
  or the fonts should be embedded in the file.
- Images, logos and icons are best embedded as data URIs or inline SVG, so the file is self-contained. Relative paths
  work for command-line use, but not when the file is uploaded to the Studio on its own.
