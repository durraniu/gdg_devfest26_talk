"""Shared helper for the lonboard HTML exports: an info + controls panel.

The panel is a small anywidget drawn with plain HTML, so it does not depend on
how ipywidgets styles its buttons. Its values are linked to lonboard layer
properties with ipywidgets.jsdlink. jsdlink runs in the browser, so the links
keep working in the exported HTML file (no Python process needed).
"""

import anywidget
import matplotlib as mpl
import numpy as np
import traitlets

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{title}</title>
<style>body {{ margin: 0; background: #fff; }}</style>
</head>
<body>
{snippet}
</body>
</html>
"""

_ESM = r"""
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const pad = (n) => String(n).padStart(2, "0");

function render({ model, el }) {
  el.classList.add("tp");

  const info = document.createElement("div");
  info.className = "tp-info";
  info.innerHTML = model.get("info");
  el.appendChild(info);

  // Time player (only when the Python side passed a "player" spec).
  let raf = 0;
  const P = model.get("player");
  if (P && P.duration) {
    const bar = document.createElement("div");
    bar.className = "tp-row";

    const btn = document.createElement("button");
    btn.textContent = "\u25B6 Play";

    const scrub = document.createElement("input");
    scrub.type = "range";
    scrub.className = "tp-scrub";
    scrub.min = 0;
    scrub.max = P.duration;
    scrub.step = 1;
    scrub.value = 0;

    const clock = document.createElement("span");
    clock.className = "tp-clock";
    const count = document.createElement("span");
    count.className = "tp-count";

    const speedLabel = document.createElement("label");
    speedLabel.className = "tp-ctl";
    const speed = document.createElement("select");
    for (const m of [10, 30, 60, 120, 240]) {
      const o = document.createElement("option");
      o.value = String(m);
      o.textContent = m + " min/s";
      o.selected = m === 60;
      speed.appendChild(o);
    }
    speedLabel.append("Speed", speed);

    bar.append(btn, scrub, clock, count, speedLabel);
    el.appendChild(bar);

    let elapsed = 0;
    let playing = false;
    let last = 0;

    const show = () => {
      const d = new Date(P.t0_ms + elapsed * 1000);
      clock.textContent =
        DAYS[d.getUTCDay()] + " " + d.getUTCFullYear() + "-" +
        pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) + " " +
        pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
      const i = Math.min(P.counts.length - 1, Math.floor(elapsed / 60));
      count.textContent = P.counts[i].toLocaleString() + " trips in progress (sample)";
      scrub.value = elapsed;
    };

    const setElapsed = (e) => {
      elapsed = Math.max(0, Math.min(P.duration, e));
      show();
      model.set("time", P.base + elapsed);
      model.save_changes();
    };

    const tick = (now) => {
      if (!playing) return;
      const dt = (now - last) / 1000;
      last = now;
      let e = elapsed + dt * parseFloat(speed.value) * 60;
      if (e >= P.duration) e = 0;
      setElapsed(e);
      raf = requestAnimationFrame(tick);
    };

    btn.addEventListener("click", () => {
      playing = !playing;
      btn.textContent = playing ? "\u275A\u275A Pause" : "\u25B6 Play";
      cancelAnimationFrame(raf);
      if (playing) {
        last = performance.now();
        raf = requestAnimationFrame(tick);
      }
    });
    scrub.addEventListener("input", () => setElapsed(parseFloat(scrub.value)));
    setElapsed(0);
  }

  // Checkboxes and sliders, one per entry in "controls".
  const controls = model.get("controls") || [];
  if (controls.length) {
    const row = document.createElement("div");
    row.className = "tp-row";
    for (const c of controls) {
      const label = document.createElement("label");
      label.className = "tp-ctl";
      const text = document.createElement("span");
      text.textContent = c.label;
      const input = document.createElement("input");
      if (c.kind === "checkbox") {
        input.type = "checkbox";
        input.checked = Boolean(model.get(c.id));
        input.addEventListener("change", () => {
          model.set(c.id, input.checked);
          model.save_changes();
        });
        label.append(input, text);
      } else {
        input.type = "range";
        input.min = c.min;
        input.max = c.max;
        input.step = c.step;
        input.value = model.get(c.id);
        const out = document.createElement("output");
        out.textContent = input.value;
        input.addEventListener("input", () => {
          out.textContent = input.value;
          model.set(c.id, parseFloat(input.value));
          model.save_changes();
        });
        label.append(text, input, out);
      }
      row.appendChild(label);
    }
    el.appendChild(row);
  }

  return () => cancelAnimationFrame(raf);
}

export default { render };
"""

_CSS = """
.tp { font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
      color: #222; background: #fff; padding: 10px 14px;
      border-bottom: 1px solid #ddd; }
.tp h1 { font-size: 18px; margin: 0 0 4px; }
.tp p { margin: 3px 0; max-width: 1150px; }
.tp-legend { display: inline-block; width: 150px; height: 10px;
             vertical-align: middle; border-radius: 2px; margin: 0 6px; }
.tp-row { display: flex; flex-wrap: wrap; gap: 8px 18px;
          align-items: center; margin-top: 8px; }
.tp-ctl { display: flex; gap: 6px; align-items: center; }
.tp button { font: inherit; padding: 4px 14px; border: 1px solid #777;
             border-radius: 4px; background: #f2f2f2; color: #222;
             cursor: pointer; min-width: 92px; }
.tp button:hover { background: #e4e4e4; }
.tp-scrub { width: 260px; }
.tp-clock { font-weight: 600; font-variant-numeric: tabular-nums;
            min-width: 12.5em; }
.tp-count { font-variant-numeric: tabular-nums; min-width: 17em; }
"""


class Panel(anywidget.AnyWidget):
    """Info text, optional time player and optional checkbox/slider controls."""

    _esm = _ESM
    _css = _CSS

    info = traitlets.Unicode("").tag(sync=True)  # HTML shown at the top
    controls = traitlets.List().tag(sync=True)  # [{"id", "kind", "label", ...}]
    player = traitlets.Dict().tag(sync=True)  # {"base", "duration", "t0_ms", "counts"}

    # Values the controls write to. Link them to layer properties with jsdlink.
    time = traitlets.Float(0.0).tag(sync=True)
    show_arcs = traitlets.Bool(True).tag(sync=True)
    show_pickups = traitlets.Bool(True).tag(sync=True)
    brushing = traitlets.Bool(False).tag(sync=True)
    arc_opacity = traitlets.Float(0.1).tag(sync=True)
    brush_radius = traitlets.Float(1500.0).tag(sync=True)


def gradient_css(cmap, n=7):
    """CSS linear-gradient built from a matplotlib colormap, for legends."""
    stops = [mpl.colormaps[cmap](v)[:3] for v in np.linspace(0, 1, n)]
    rgb = ",".join(f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})" for r, g, b in stops)
    return f"linear-gradient(90deg,{rgb})"
