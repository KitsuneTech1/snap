#!/usr/bin/env python3
"""snapedit.py - turn snap.ps1 screenshots into documentation images (Moo, 2026-09-27).

Commands
  info  IMG                      print width x height
  grid  IMG -o OUT [--step 100]  copy with a labeled pixel grid, for reading exact coordinates
  edit  IMG -o OUT --ops JSON    annotate, redact, crop, zoom, caption and frame in one pass
  gif   IMG IMG ... -o OUT.gif [--ms 1400] [--max-width 1200]
                                 step-by-step animation from several edited images
  ocr   IMG                      read the text (Windows OCR); keys and tokens come back masked
  find  IMG "phrase"             boxes of every place that phrase appears (x,y,w,h in IMG pixels)

Text ops aim by what the screen SAYS, so they survive layouts that move between renders.
They run OCR on the input image (cached in IMG.ocr.json) and fail loudly if the phrase is missing:
  {"box_text": "Start a trace", "label": "...", "nth": 0}      box around that text
  {"callout_text": "Trace", "n": 2}                            badge just left of that text
  {"redact_text": "Widger", "style": "solid"}                   black out every match
  {"redact_secrets": true}                                     black out anything key-shaped

Ops (a JSON list, or @file.json). Every coordinate is in the INPUT image's pixels, whatever
order the ops are listed in: redactions run first, then marks, then crop, scale, caption, frame.
  {"redact": [x,y,w,h], "style": "solid"|"blur"|"pixelate"}   solid for secrets (default)
  {"spotlight": [x,y,w,h], "dim": 0.55}                        darken everything else
  {"box": [x,y,w,h], "label": "text", "color": "#f59e0b"}      rounded outline, label above
  {"arrow": [x1,y1,x2,y2], "color": "#f59e0b"}                 head at x2,y2
  {"callout": [x,y], "n": 1}                                   numbered badge
  {"text": "words", "at": [x,y], "color": "#f59e0b"}           label pill, top-left at x,y
  {"crop": [x,y,w,h]}
  {"zoom": 2}                 enlarge a crop for a readable on-screen guide (1-4x)
  {"max_width": 1400}
  {"caption": "words", "pos": "bottom"|"top"}
  {"frame": true, "bg": "#0b1222", "pad": 36}                  rounded corners and soft shadow

Output is rebuilt from pixels only, so it carries no EXIF, text chunks or other metadata.
Fonts: Segoe UI Semibold for labels, Consolas for numbers. Stdlib plus Pillow.
"""
import argparse
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

GOLD = "#f59e0b"
INK = "#0f172a"
FONT_UI = r"C:\Windows\Fonts\seguisb.ttf"
FONT_UI_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_MONO = r"C:\Windows\Fonts\consolab.ttf"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def rgba(color, alpha=255):
    c = color.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha)


def unit(img):
    """Mark sizes scale with the image so a 1600 px snap and a 4k snap both look right."""
    return max(1.0, min(img.size) / 900.0)


def clean(img):
    """New image from raw pixels: drops every metadata chunk the source carried."""
    return Image.frombytes("RGBA", img.size, img.convert("RGBA").tobytes())


def load_clean(src):
    with Image.open(src) as original:
        return clean(original)


def op_redact(img, o):
    x, y, w, h = o["redact"]
    box = (x, y, x + w, y + h)
    style = o.get("style", "solid")
    region = img.crop(box)
    if style == "blur":
        region = region.filter(ImageFilter.GaussianBlur(max(8, h // 2)))
    elif style == "pixelate":
        s = max(6, h // 3)
        region = region.resize((max(1, w // s), max(1, h // s)), Image.NEAREST).resize((w, h), Image.NEAREST)
    else:
        region = Image.new("RGBA", (w, h), rgba("#111827"))
    img.paste(region, box)


def op_spotlight(img, o):
    x, y, w, h = o["spotlight"]
    shade = Image.new("RGBA", img.size, (0, 0, 0, int(255 * o.get("dim", 0.55))))
    hole = Image.new("L", img.size, 255)
    ImageDraw.Draw(hole).rounded_rectangle((x, y, x + w, y + h), radius=int(10 * unit(img)), fill=0)
    img.alpha_composite(Image.composite(shade, Image.new("RGBA", img.size, (0, 0, 0, 0)), hole))


def pill(draw, xy, text, fill, fg, f, pad):
    x, y = xy
    l, t, r, b = draw.textbbox((0, 0), text, font=f)
    w, h = r - l + 2 * pad, b - t + 2 * pad * 0.7
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h / 2, fill=fill, outline=(255, 255, 255, 230), width=2)
    draw.text((x + pad - l, y + pad * 0.7 - t), text, font=f, fill=fg)
    return w, h


def op_box(img, o):
    u = unit(img)
    x, y, w, h = o["box"]
    col = o.get("color", GOLD)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x - 2, y - 2, x + w + 2, y + h + 2), radius=int(10 * u), outline=(0, 0, 0, 150), width=int(7 * u))
    d.rounded_rectangle((x, y, x + w, y + h), radius=int(9 * u), outline=rgba(col), width=int(4 * u))
    if o.get("label"):
        f = font(FONT_UI, int(18 * u))
        ly = y - int(38 * u) if y > 44 * u else y + h + int(8 * u)
        pill(d, (x, ly), o["label"], rgba(col), INK, f, int(12 * u))


def op_arrow(img, o):
    import math
    u = unit(img)
    x1, y1, x2, y2 = o["arrow"]
    col = rgba(o.get("color", GOLD))
    d = ImageDraw.Draw(img)
    ang = math.atan2(y2 - y1, x2 - x1)
    head = 22 * u
    bx, by = x2 - head * 0.8 * math.cos(ang), y2 - head * 0.8 * math.sin(ang)
    pts = [(x2, y2),
           (x2 - head * math.cos(ang - 0.45), y2 - head * math.sin(ang - 0.45)),
           (x2 - head * math.cos(ang + 0.45), y2 - head * math.sin(ang + 0.45))]
    d.line((x1, y1, bx, by), fill=(0, 0, 0, 150), width=int(10 * u))
    d.polygon(pts, fill=(0, 0, 0, 150))
    d.line((x1, y1, bx, by), fill=col, width=int(6 * u))
    d.polygon(pts, fill=col)


def op_callout(img, o):
    u = unit(img)
    x, y = o["callout"]
    r = 17 * u
    d = ImageDraw.Draw(img)
    d.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), fill=(0, 0, 0, 140))
    d.ellipse((x - r, y - r, x + r, y + r), fill=rgba(o.get("color", GOLD)), outline=(255, 255, 255, 240), width=int(2 * u))
    f = font(FONT_MONO, int(20 * u))
    t = str(o.get("n", 1))
    l, tp, rr, b = d.textbbox((0, 0), t, font=f)
    d.text((x - (rr - l) / 2 - l, y - (b - tp) / 2 - tp), t, font=f, fill=INK)


def op_text(img, o):
    u = unit(img)
    d = ImageDraw.Draw(img)
    pill(d, tuple(o["at"]), o["text"], rgba(o.get("color", GOLD)), INK, font(FONT_UI, int(18 * u)), int(12 * u))


def op_caption(img, o):
    u = unit(img)
    f = font(FONT_UI, int(22 * u))
    words, lines, cur = o["caption"].split(), [], ""
    probe = ImageDraw.Draw(img)
    for w in words:
        t = (cur + " " + w).strip()
        if probe.textlength(t, font=f) > img.width - 48 * u and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    lh = int(32 * u)
    bar = int(22 * u) * 2 + lh * len(lines)
    out = Image.new("RGBA", (img.width, img.height + bar), rgba("#0b1222"))
    top = o.get("pos", "bottom") == "top"
    out.paste(img, (0, bar if top else 0))
    d = ImageDraw.Draw(out)
    y0 = int(22 * u) + (0 if top else img.height)
    for i, line in enumerate(lines):
        d.text((int(24 * u), y0 + i * lh), line, font=f, fill=rgba("#f8fafc"))
    return out


def op_frame(img, o):
    u = unit(img)
    pad = int(o.get("pad", 36) * u)
    rad = int(14 * u)
    bg = rgba(o.get("bg", "#0b1222"))
    W, H = img.width + 2 * pad, img.height + 2 * pad
    out = Image.new("RGBA", (W, H), bg)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + int(8 * u), pad + img.width, pad + img.height + int(8 * u)),
                                             radius=rad, fill=(0, 0, 0, 170))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(int(14 * u))))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=rad, fill=255)
    out.paste(img, (pad, pad), mask)
    ImageDraw.Draw(out).rounded_rectangle((pad, pad, pad + img.width - 1, pad + img.height - 1), radius=rad,
                                          outline=(255, 255, 255, 40), width=1)
    return out


OCR_PS1 = os.environ.get("SNAP_OCR_PS1", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr.ps1"))


def ocr_data(src):
    """Words and boxes for src, from its .ocr.json sidecar (made fresh when missing or stale)."""
    side = src + ".ocr.json"
    if not os.path.exists(side) or os.path.getmtime(side) < os.path.getmtime(src):
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", OCR_PS1, "-Path", os.path.abspath(src)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=0x08000000 if os.name == "nt" else 0)
        if r.returncode != 0 or not os.path.exists(side):
            raise SystemExit("ocr failed: " + (r.stderr or r.stdout)[-400:])
    with open(side, encoding="utf-8-sig") as handle:
        return json.load(handle)


def find_text(src, phrase):
    """Every run of consecutive words on one OCR line that contains phrase (case-insensitive)."""
    want = " ".join(phrase.lower().split())
    hits = []
    for line in ocr_data(src)["lines"]:
        words = line["words"]
        for i in range(len(words)):
            joined = ""
            for j in range(i, len(words)):
                joined = (joined + " " + words[j]["t"].lower()).strip()
                if want in joined:
                    ws = words[i:j + 1]
                    x = min(w["x"] for w in ws); y = min(w["y"] for w in ws)
                    hits.append([x, y, max(w["x"] + w["w"] for w in ws) - x, max(w["y"] + w["h"] for w in ws) - y])
                    break
                if len(joined) > len(want) + 40:
                    break
    uniq = []
    for h in hits:  # a phrase inside a longer run is found from several start words; keep the tightest
        if not any(h[0] >= u[0] and h[1] >= u[1] and h[0] + h[2] <= u[0] + u[2] and h[1] + h[3] <= u[1] + u[3] for u in uniq):
            uniq = [u for u in uniq if not (u[0] <= h[0] and u[1] <= h[1] and u[0] + u[2] >= h[0] + h[2] and u[1] + u[3] >= h[1] + h[3])] + [h]
    return sorted(uniq, key=lambda b: (b[1], b[0]))


def expand_text_ops(src, ops):
    """Turn text-aimed ops into plain coordinate ops."""
    out = []
    for o in ops:
        if "box_text" in o or "callout_text" in o or "redact_text" in o:
            key = next(k for k in ("box_text", "callout_text", "redact_text") if k in o)
            hits = find_text(src, o[key])
            if not hits:
                raise SystemExit("text not found on the image: %r (run: snapedit.py ocr IMG)" % o[key])
            pad = o.get("pad", 6)
            chosen = hits if key == "redact_text" else [hits[min(o.get("nth", 0), len(hits) - 1)]]
            for x, y, w, h in chosen:
                rest = {k: v for k, v in o.items() if k not in (key, "nth", "pad")}
                if key == "box_text":
                    out.append(dict(rest, box=[x - pad, y - pad, w + 2 * pad, h + 2 * pad]))
                elif key == "callout_text":  # left of the text, or right of it when too close to the edge
                    cx = x - 26 if x >= 30 else x + w + 26
                    out.append(dict(rest, callout=[cx, y + h // 2]))
                else:
                    out.append(dict(rest, redact=[x - 3, y - 3, w + 6, h + 6]))
        elif o.get("redact_secrets"):
            for line in ocr_data(src)["lines"]:
                for w in line["words"]:
                    if w.get("secret"):
                        out.append({"redact": [w["x"] - 4, w["y"] - 4, w["w"] + 8, w["h"] + 8], "style": "solid"})
        elif "redact_secrets" in o:
            continue
        else:
            out.append(o)
    return out


ORDER = ["redact", "spotlight", "box", "arrow", "callout", "text", "crop", "zoom", "max_width", "caption", "frame"]


def _validate_number(value, name, *, integer=False, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")


def _validate_coords(value, name, count):
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(f"{name} must contain {count} values")
    for i, item in enumerate(value):
        _validate_number(item, f"{name}[{i}]", integer=True)


def _validate_color(value, name):
    if not isinstance(value, str) or len(value.lstrip("#")) != 6:
        raise ValueError(f"{name} must be a six-digit hex color")
    try:
        int(value.lstrip("#"), 16)
    except ValueError:
        raise ValueError(f"{name} must be a six-digit hex color") from None


def validate_ops(ops):
    """Reject malformed operation data before drawing code can fail ambiguously."""
    if not isinstance(ops, list):
        raise ValueError("ops must be a JSON list")
    allowed = set(ORDER) | {"box_text", "callout_text", "redact_text", "redact_secrets"}
    for index, op in enumerate(ops):
        if not isinstance(op, dict):
            raise ValueError(f"operation {index} must be an object")
        keys = [key for key in allowed if key in op]
        if len(keys) != 1:
            raise ValueError(f"operation {index} must contain exactly one known operation")
        key = keys[0]
        allowed_fields = {
            "redact": {"redact", "style"}, "spotlight": {"spotlight", "dim"},
            "box": {"box", "label", "color"}, "arrow": {"arrow", "color"},
            "callout": {"callout", "n", "color"}, "text": {"text", "at", "color"},
            "crop": {"crop"}, "zoom": {"zoom"}, "max_width": {"max_width"},
            "caption": {"caption", "pos"}, "frame": {"frame", "bg", "pad"},
            "box_text": {"box_text", "label", "color", "nth", "pad"},
            "callout_text": {"callout_text", "n", "color", "nth", "pad"},
            "redact_text": {"redact_text", "style", "nth", "pad"},
            "redact_secrets": {"redact_secrets"},
        }
        unknown = set(op) - allowed_fields[key]
        if unknown:
            raise ValueError(f"operation {index} has unknown field(s): {', '.join(sorted(unknown))}")
        if key in {"redact", "spotlight", "box", "crop"}:
            _validate_coords(op[key], key, 4)
            if key in {"redact", "spotlight", "box", "crop"} and op[key][2] <= 0:
                raise ValueError(f"{key} width must be positive")
            if key in {"redact", "spotlight", "box", "crop"} and op[key][3] <= 0:
                raise ValueError(f"{key} height must be positive")
        elif key == "arrow":
            _validate_coords(op[key], key, 4)
        elif key in {"callout", "text"}:
            _validate_coords(op.get("callout" if key == "callout" else "at"), "callout" if key == "callout" else "at", 2)
            if key == "text" and not isinstance(op.get("text"), str):
                raise ValueError("text must be a string")
        elif key == "zoom":
            _validate_number(op[key], "zoom", minimum=1, maximum=4)
        elif key == "max_width":
            _validate_number(op[key], "max_width", integer=True, minimum=1)
        elif key == "caption":
            if not isinstance(op[key], str):
                raise ValueError("caption must be a string")
        elif key == "frame":
            if not isinstance(op[key], bool):
                raise ValueError("frame must be true or false")
            if "pad" in op:
                _validate_number(op["pad"], "pad", integer=True, minimum=0)
        elif key in {"box_text", "callout_text", "redact_text"}:
            if not isinstance(op[key], str) or not op[key].strip():
                raise ValueError(f"{key} must be a non-empty string")
            if "nth" in op:
                _validate_number(op["nth"], "nth", integer=True, minimum=0)
            if "pad" in op:
                _validate_number(op["pad"], "pad", integer=True, minimum=0)
        elif key == "redact_secrets" and not isinstance(op[key], bool):
            raise ValueError("redact_secrets must be true or false")

        if "style" in op and op["style"] not in {"solid", "blur", "pixelate"}:
            raise ValueError("style must be solid, blur, or pixelate")
        for color_name in ("color", "bg"):
            if color_name in op:
                _validate_color(op[color_name], color_name)
        if "label" in op and not isinstance(op["label"], str):
            raise ValueError("label must be a string")
        if "dim" in op:
            _validate_number(op["dim"], "dim", minimum=0, maximum=1)
        if "pos" in op and op["pos"] not in {"top", "bottom"}:
            raise ValueError("pos must be top or bottom")

    return ops


def edit(src, ops):
    validate_ops(ops)
    ops = expand_text_ops(src, ops)
    img = load_clean(src)
    kind = lambda o: next(k for k in ORDER if k in o)
    for o in sorted(ops, key=lambda o: ORDER.index(kind(o))):
        k = kind(o)
        if k == "redact":
            op_redact(img, o)
        elif k == "spotlight":
            op_spotlight(img, o)
        elif k == "box":
            op_box(img, o)
        elif k == "arrow":
            op_arrow(img, o)
        elif k == "callout":
            op_callout(img, o)
        elif k == "text":
            op_text(img, o)
        elif k == "crop":
            x, y, w, h = o["crop"]
            img = img.crop((x, y, x + w, y + h))
        elif k == "zoom":
            factor = o["zoom"]
            if not isinstance(factor, (int, float)) or not 1 <= factor <= 4:
                raise ValueError("zoom must be between 1 and 4")
            img = img.resize((round(img.width * factor), round(img.height * factor)), Image.LANCZOS)
        elif k == "max_width" and img.width > o["max_width"]:
            img = img.resize((o["max_width"], round(img.height * o["max_width"] / img.width)), Image.LANCZOS)
        elif k == "caption":
            img = op_caption(img, o)
        elif k == "frame" and o["frame"]:
            img = op_frame(img, o)
    return img


def save(img, out):
    if out.lower().endswith((".jpg", ".jpeg")):
        img.convert("RGB").save(out, quality=90, optimize=True)
    else:
        img.save(out, optimize=True)


def grid(src, out, step):
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise ValueError("step must be a positive integer")
    img = load_clean(src)
    d = ImageDraw.Draw(img)
    f = font(FONT_MONO, 13)
    for x in range(0, img.width, step):
        d.line((x, 0, x, img.height), fill=(255, 0, 170, 110), width=1)
        d.text((x + 3, 3), str(x), font=f, fill=(255, 0, 170, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    for y in range(0, img.height, step):
        d.line((0, y, img.width, y), fill=(255, 0, 170, 110), width=1)
        d.text((3, y + 3), str(y), font=f, fill=(255, 0, 170, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    save(img, out)


def gif(srcs, out, ms, max_width):
    if not srcs:
        raise ValueError("at least one image is required")
    if isinstance(ms, bool) or not isinstance(ms, int) or ms < 0:
        raise ValueError("ms must be a non-negative integer")
    if isinstance(max_width, bool) or not isinstance(max_width, int) or max_width <= 0:
        raise ValueError("max_width must be a positive integer")
    frames = [load_clean(s) for s in srcs]
    W = min(max_width, max(f.width for f in frames))
    frames = [f.resize((W, round(f.height * W / f.width)), Image.LANCZOS) if f.width != W else f for f in frames]
    H = max(f.height for f in frames)
    canvas = []
    for f in frames:
        c = Image.new("RGBA", (W, H), rgba("#0b1222"))
        c.paste(f, (0, (H - f.height) // 2))
        canvas.append(c.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG))
    canvas[0].save(out, save_all=True, append_images=canvas[1:], duration=ms, loop=0, optimize=True)


def main():
    ap = argparse.ArgumentParser(description="Edit snap.ps1 screenshots for documentation.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("info"); a.add_argument("img")
    a = sub.add_parser("grid"); a.add_argument("img"); a.add_argument("-o", required=True); a.add_argument("--step", type=int, default=100)
    a = sub.add_parser("edit"); a.add_argument("img"); a.add_argument("-o", required=True); a.add_argument("--ops", required=True)
    a = sub.add_parser("ocr"); a.add_argument("img")
    a = sub.add_parser("find"); a.add_argument("img"); a.add_argument("phrase")
    a = sub.add_parser("gif"); a.add_argument("imgs", nargs="+"); a.add_argument("-o", required=True)
    a.add_argument("--ms", type=int, default=1400); a.add_argument("--max-width", type=int, default=1200)
    a = ap.parse_args()
    if a.cmd == "info":
        with Image.open(a.img) as image:
            w, h = image.size
        print(json.dumps({"width": w, "height": h}))
    elif a.cmd == "grid":
        try:
            grid(a.img, a.o, a.step)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        print(a.o)
    elif a.cmd == "ocr":
        d = ocr_data(a.img)
        text = "\n".join(" ".join("[SECRET HIDDEN]" if w.get("secret") else w["t"] for w in l["words"]) for l in d["lines"])
        print(json.dumps({"ocr": a.img + ".ocr.json", "lines": len(d["lines"]), "secrets": d.get("secrets", 0),
                          "text": text[:3000]}))
    elif a.cmd == "find":
        hits = find_text(a.img, a.phrase)
        print(json.dumps({"phrase": a.phrase, "matches": hits}))
        return 0 if hits else 3
    elif a.cmd == "edit":
        try:
            raw = open(a.ops[1:], encoding="utf-8").read() if a.ops.startswith("@") else a.ops
            img = edit(a.img, json.loads(raw))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            ap.error(str(exc))
        save(img, a.o)
        print(json.dumps({"out": a.o, "width": img.width, "height": img.height}))
    else:
        try:
            gif(a.imgs, a.o, a.ms, a.max_width)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        print(a.o)


if __name__ == "__main__":
    sys.exit(main())
