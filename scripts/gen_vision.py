"""Açık repolardan animasyonlu "repo sınıflandırıcı" SVG'si üretir.

Bir tarama ışını repo kartlarının üzerinden geçer; geçtiği her karta konu
etiketlerinden (topics) çıkarılan sınıfla bir sınırlayıcı kutu çizer.
Yalnız standart kütüphane kullanır.

Kullanım: GITHUB_TOKEN=... python scripts/gen_vision.py <kullanıcı> <çıktı.svg>
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from html import escape

W, H = 880, 236
COLS, ROWS = 3, 2
PADX, TOP, GAPX, GAPY = 28, 72, 12, 12
CW = (W - 2 * PADX - (COLS - 1) * GAPX) / COLS
CH = 50
DUR = 16.0
SCAN = 0.8

BG = "#0b0f14"
GRID = "#1a2330"
CARD = "#121a23"
HUD = "#7fe8ff"
CLASSES = [  # (ad, renk, tetikleyen konular)
    ("vision", "#7fe8ff", {"computer-vision", "yolo", "opencv", "object-detection", "anomaly-detection", "vlm", "ocr"}),
    ("llm", "#ff7ad9", {"llm", "rag", "agents", "claude-code", "nlp"}),
    ("ml", "#3dff9a", {"pytorch", "classification", "deep-learning", "medical-imaging", "edge-ai", "machine-learning"}),
    ("uav", "#ffd166", {"uav", "drone", "path-planning", "px4", "ros2"}),
]


def gh(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def classify(topics):
    for name, color, keys in CLASSES:
        if keys & set(topics):
            return name, color
    return None


def fetch(login, token):
    repos = gh(f"https://api.github.com/users/{login}/repos?per_page=100&type=owner", token)
    out = []
    for r in repos:
        if r["fork"] or r["archived"] or r["private"] or r["name"].lower() == login.lower():
            continue
        c = classify(r.get("topics") or [])
        if not c:
            continue
        out.append({
            "name": r["name"], "stars": r["stargazers_count"], "pushed": r["pushed_at"],
            "cls": c[0], "color": c[1],
            "tags": [t for t in r.get("topics") or [] if t not in {"python"}][:3],
        })
    out.sort(key=lambda x: (x["stars"], x["pushed"]), reverse=True)
    picked = []
    for name, *_ in CLASSES:  # her sınıftan en az bir repo
        best = next((r for r in out if r["cls"] == name), None)
        if best:
            picked.append(best)
    for r in out:
        if len(picked) >= COLS * ROWS:
            break
        if r not in picked:
            picked.append(r)
    picked = picked[: COLS * ROWS]
    picked.sort(key=lambda x: (x["stars"], x["pushed"]), reverse=True)
    return picked


def kt(*ts):
    return ";".join(f"{min(max(t, 0), 1):.4f}" for t in ts)


def clip(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def build(repos):
    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">')
    o.append(f"""<defs>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="{GRID}" stroke-width="0.6"/></pattern>
<linearGradient id="beam" x1="0" x2="1"><stop offset="0" stop-color="{HUD}" stop-opacity="0"/><stop offset="0.85" stop-color="{HUD}" stop-opacity="0.22"/><stop offset="1" stop-color="{HUD}" stop-opacity="0.9"/></linearGradient>
</defs>""")
    o.append(f'<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>')
    o.append(f'<rect width="{W}" height="{H}" rx="14" fill="url(#grid)" opacity="0.7"/>')
    for x, y, sx, sy in ((10, 10, 1, 1), (W - 10, 10, -1, 1), (10, H - 10, 1, -1), (W - 10, H - 10, -1, -1)):
        o.append(f'<path d="M{x},{y + sy * 18}V{y}H{x + sx * 18}" fill="none" stroke="{HUD}" stroke-width="1.5" opacity="0.8"/>')

    counts = {}
    for r in repos:
        counts[r["cls"]] = counts.get(r["cls"], 0) + 1
    n = len(repos)

    o.append(f'<text x="{PADX}" y="36" fill="{HUD}" font-size="12" letter-spacing="2">VISION-01 // REPO CLASSIFIER</text>')
    o.append(f'<text x="{PADX}" y="54" fill="#5b6b7d" font-size="10" letter-spacing="1">INPUT {n} PUBLIC PROJECTS · LABELS FROM REPO TOPICS</text>')

    xs, xe = PADX - 10, W - PADX + 10
    cards = []
    for i, r in enumerate(repos):
        col, row = i % COLS, i // COLS
        x = PADX + col * (CW + GAPX)
        y = TOP + row * (CH + GAPY)
        t = SCAN * (x + CW * (0.55 + 0.12 * row) - xs) / (xe - xs)
        cards.append((r, x, y, t))

    order = sorted(t for *_, t in cards)
    for k in range(n + 1):
        t0 = 0 if k == 0 else order[k - 1]
        t1 = order[k] if k < n else 1
        if k == 0:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t1)}" values="1;0"/>'
        elif k == n:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t0)}" values="0;1"/>'
        else:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t0, t1)}" values="0;1;0"/>'
        if k < n:
            label, col = f"CLASSIFIED {k:02d}/{n:02d}", "#ffd166"
        else:
            parts = " · ".join(f"{c.upper()} {counts[c]}" for c, *_ in CLASSES if c in counts)
            label, col = f"DONE · {parts}", "#3dff9a"
        o.append(f'<text x="{W - PADX}" y="36" fill="{col}" font-size="11" text-anchor="end" letter-spacing="1" opacity="{1 if k == 0 else 0}">{label}{anim}</text>')

    for r, x, y, t in cards:
        o.append(f'<rect x="{x:.1f}" y="{y}" width="{CW:.1f}" height="{CH}" rx="5" fill="{CARD}" stroke="#1f2a36"/>')
        o.append(f'<text x="{x + 9:.1f}" y="{y + 21}" fill="#e6edf3" font-size="13" font-weight="700">{escape(clip(r["name"], 26))}</text>')
        o.append(f'<text x="{x + 9:.1f}" y="{y + 38}" fill="#8b98a8" font-size="10">{escape(clip(" · ".join(r["tags"]), 38))}</text>')

    gy0, gy1 = TOP - 6, TOP + ROWS * (CH + GAPY)
    span = xe - xs
    o.append(f'<rect x="{xs}" y="{gy0}" width="{span}" height="{gy1 - gy0}" fill="{BG}" opacity="0.5">'
             f'<animate attributeName="x" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, SCAN, 0.97, 1)}" values="{xs};{xe};{xe};{xs}"/>'
             f'<animate attributeName="width" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, SCAN, 0.97, 1)}" values="{span};0;0;{span}"/></rect>')

    for r, x, y, t in cards:
        col = r["color"]
        bx, by, bw, bh = x - 3, y - 3, CW + 6, CH + 6
        per = 2 * (bw + bh)
        label = r["cls"]
        lw = 8 + len(label) * 6.2
        o.append(f'<g opacity="0"><animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t, 0.97)}" values="0;1;0"/>'
                 f'<rect x="{bx:.1f}" y="{by}" width="{bw:.1f}" height="{bh}" rx="6" fill="{col}" fill-opacity="0.06" stroke="{col}" stroke-width="1.5" stroke-dasharray="{per:.0f}" stroke-dashoffset="{per:.0f}" filter="url(#glow)">'
                 f'<animate attributeName="stroke-dashoffset" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, t, t + 0.025, 1)}" values="{per:.0f};{per:.0f};0;0"/></rect>'
                 f'<rect x="{bx + bw - lw - 6:.1f}" y="{by + 5}" width="{lw:.0f}" height="13" rx="3" fill="{col}"/>'
                 f'<text x="{bx + bw - lw - 2:.1f}" y="{by + 15}" fill="{BG}" font-size="9" font-weight="700">{label}</text></g>')

    o.append(f'<g><rect x="-60" y="{gy0}" width="60" height="{gy1 - gy0}" fill="url(#beam)"/>'
             f'<rect x="-1.5" y="{gy0 - 4}" width="1.5" height="{gy1 - gy0 + 8}" fill="{HUD}" filter="url(#glow)"/>'
             f'<animateTransform attributeName="transform" type="translate" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, SCAN, 1)}" values="{xs} 0;{xe} 0;{xe} 0"/>'
             f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, 0.01, SCAN, SCAN + 0.02, 1)}" values="0;1;1;0;0"/></g>')

    lx, ly = PADX, H - 18
    for name, color, _ in CLASSES:
        if name not in counts:
            continue
        o.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" rx="2" fill="none" stroke="{color}" stroke-width="1.5"/>'
                 f'<text x="{lx + 16}" y="{ly}" fill="#8b98a8" font-size="10">{name}</text>')
        lx += 30 + len(name) * 7
    o.append(f'<text x="{W - PADX}" y="{ly}" fill="#5b6b7d" font-size="10" text-anchor="end">regenerated daily from my public repos</text>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    login, out = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN") or os.environ["GH_TOKEN"]
    repos = fetch(login, token)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build(repos))
    print(f"ok: {len(repos)} repos -> {out}")


if __name__ == "__main__":
    main()
