"""Katkı takviminden animasyonlu "nesne tespiti" SVG'si üretir.

Bir görüntü modeli katkı takvimini soldan sağa tarar; geçtiği yerde her ayın en
yoğun gününü (çevresindeki katkı kümesiyle) sınırlayıcı kutuyla işaretler.
Yalnız standart kütüphane kullanır.

Kullanım: GITHUB_TOKEN=... python scripts/gen_vision.py <kullanıcı> <çıktı.svg>
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

CELL, GAP = 12, 3
STEP = CELL + GAP
W, H = 880, 240
X0, Y0 = (W - 53 * STEP + GAP) // 2, 78
DUR = 18.0          # saniye, tam döngü
SCAN = 0.82         # döngünün taramaya ayrılan kısmı
N_TARGETS = 12

BG = "#0b0f14"
GRID = "#1a2330"
EMPTY = "#141b24"
LEVELS = ["#0f3d2e", "#16694a", "#1fa36b", "#3dff9a"]
HUD = "#7fe8ff"
BOX = ["#7fe8ff", "#ff7ad9", "#ffd166", "#3dff9a"]

QUERY = """query($login:String!){user(login:$login){contributionsCollection{
contributionCalendar{totalContributions weeks{contributionDays{contributionCount weekday date}}}}}}"""


def fetch(login: str, token: str):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        cal = json.load(r)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    cells = []
    for w, week in enumerate(cal["weeks"]):
        for d in week["contributionDays"]:
            cells.append((w, d["weekday"], d["contributionCount"], d["date"]))
    return cal["totalContributions"], cells


def level(c, mx):
    if c <= 0:
        return -1
    q = c / mx
    return 0 if q <= 0.25 else 1 if q <= 0.5 else 2 if q <= 0.75 else 3


def pick_targets(cells, weeks):
    out = []
    for b in range(N_TARGETS):
        lo, hi = b * weeks / N_TARGETS, (b + 1) * weeks / N_TARGETS
        best = max((c for c in cells if lo <= c[0] < hi and c[2] > 0), key=lambda c: c[2], default=None)
        if best:
            out.append(best)
    return out


def cluster_box(t, counts):
    """Hedef hücre + komşu dolu hücreler (±1) için kutu (piksel)."""
    w0 = w1 = t[0]
    d0 = d1 = t[1]
    for dw in (-1, 0, 1):
        for dd in (-1, 0, 1):
            if counts.get((t[0] + dw, t[1] + dd), 0) > 0:
                w0, w1 = min(w0, t[0] + dw), max(w1, t[0] + dw)
                d0, d1 = min(d0, t[1] + dd), max(d1, t[1] + dd)
    pad = 3
    x = X0 + w0 * STEP - pad
    y = Y0 + d0 * STEP - pad
    return x, y, (w1 - w0) * STEP + CELL + 2 * pad, (d1 - d0) * STEP + CELL + 2 * pad


def kt(*ts):
    return ";".join(f"{min(max(t, 0), 1):.4f}" for t in ts)


def build(total, cells):
    weeks = max(c[0] for c in cells) + 1
    mx = max([c[2] for c in cells] + [1])
    counts = {(w, d): c for w, d, c, _ in cells}
    targets = pick_targets(cells, weeks)

    xs, xe = X0 - 16, X0 + weeks * STEP + 4
    span = xe - xs

    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">')
    o.append(f"""<defs>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="{GRID}" stroke-width="0.6"/></pattern>
<linearGradient id="beam" x1="0" x2="1"><stop offset="0" stop-color="{HUD}" stop-opacity="0"/><stop offset="0.85" stop-color="{HUD}" stop-opacity="0.28"/><stop offset="1" stop-color="{HUD}" stop-opacity="0.9"/></linearGradient>
</defs>""")
    o.append(f'<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>')
    o.append(f'<rect width="{W}" height="{H}" rx="14" fill="url(#grid)" opacity="0.7"/>')
    for x, y, sx, sy in ((10, 10, 1, 1), (W - 10, 10, -1, 1), (10, H - 10, 1, -1), (W - 10, H - 10, -1, -1)):
        o.append(f'<path d="M{x},{y + sy * 18}V{y}H{x + sx * 18}" fill="none" stroke="{HUD}" stroke-width="1.5" opacity="0.8"/>')

    o.append(f'<text x="28" y="36" fill="{HUD}" font-size="12" letter-spacing="2">VISION-01 // CONTRIBUTION DETECTOR</text>')
    o.append(f'<text x="28" y="54" fill="#5b6b7d" font-size="10" letter-spacing="1">MODEL yolo-commits · INPUT 53×7 · CONF ≥ 0.50 · NMS 0.45</text>')
    o.append(f'<text x="{W - 28}" y="36" fill="#e6edf3" font-size="12" text-anchor="end" letter-spacing="1">{total} CONTRIBUTIONS · LAST 12 MONTHS</text>')

    # tespit zamanları: tarama çizgisi hedef kutusunun sağ kenarını geçince
    boxes = [cluster_box(t, counts) for t in targets]
    times = [SCAN * min(1, (b[0] + b[2] - xs) / span) for b in boxes]
    order = sorted(range(len(targets)), key=lambda i: times[i])
    n = len(targets)

    # sayaç
    for k in range(n + 1):
        t0 = 0 if k == 0 else times[order[k - 1]]
        t1 = times[order[k]] if k < n else 1
        if k == 0:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t1)}" values="1;0"/>'
        elif k == n:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t0)}" values="0;1"/>'
        else:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t0, t1)}" values="0;1;0"/>'
        if k < n:
            label, col = f"DETECTIONS {k:02d}/{n:02d}", "#ffd166"
        else:
            label, col = f"INFERENCE DONE · {n} OBJECTS", "#3dff9a"
        o.append(f'<text x="{W - 28}" y="54" fill="{col}" font-size="10" text-anchor="end" letter-spacing="1" opacity="{1 if k == 0 else 0}">{label}{anim}</text>')

    # hücreler
    for w, d, c, date in cells:
        x, y = X0 + w * STEP, Y0 + d * STEP
        lv = level(c, mx)
        fill = EMPTY if lv < 0 else LEVELS[lv]
        o.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{fill}"><title>{date}: {c}</title></rect>')

    # işlenmemiş bölgeyi karartan perde (tarama ilerledikçe çekilir)
    gy0, gy1 = Y0 - 6, Y0 + 7 * STEP + 3
    o.append(f'<rect x="{xs}" y="{gy0}" width="{span}" height="{gy1 - gy0}" fill="{BG}" opacity="0.55">'
             f'<animate attributeName="x" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, SCAN, 0.97, 1)}" values="{xs};{xe};{xe};{xs}"/>'
             f'<animate attributeName="width" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, SCAN, 0.97, 1)}" values="{span};0;0;{span}"/></rect>')

    # tespit kutuları
    placed = []
    for i, (t, (bx, by, bw, bh), ti) in enumerate(zip(targets, boxes, times)):
        col = BOX[i % len(BOX)]
        conf = 0.55 + 0.44 * t[2] / mx
        label = f"commit {conf:.2f}"
        lw = 7 + len(label) * 6.1
        ly = by - 13 if by - 13 > Y0 - 20 else by + bh + 1
        if any(bx < px + pw + 2 and px < bx + lw + 2 and abs(ly - py) < 16 for px, py, pw in placed):
            ly = by + bh + 1
        placed.append((bx, ly, lw))
        per = 2 * (bw + bh)
        vis = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, ti, 0.97)}" values="0;1;0"/>'
        o.append(f'<g opacity="0">{vis}'
                 f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="2" fill="{col}" fill-opacity="0.08" stroke="{col}" stroke-width="1.5" stroke-dasharray="{per}" stroke-dashoffset="{per}" filter="url(#glow)">'
                 f'<animate attributeName="stroke-dashoffset" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, ti, ti + 0.02, 1)}" values="{per};{per};0;0"/></rect>'
                 f'<rect x="{bx}" y="{ly}" width="{lw:.0f}" height="12" rx="2" fill="{col}"/>'
                 f'<text x="{bx + 4}" y="{ly + 9}" fill="{BG}" font-size="9" font-weight="700">{label}</text></g>')

    # tarama ışını
    o.append(f'<g><rect x="-60" y="{gy0}" width="60" height="{gy1 - gy0}" fill="url(#beam)"/>'
             f'<rect x="-1.5" y="{gy0 - 4}" width="1.5" height="{gy1 - gy0 + 8}" fill="{HUD}" filter="url(#glow)"/>'
             f'<animateTransform attributeName="transform" type="translate" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, SCAN, 1)}" values="{xs} 0;{xe} 0;{xe} 0"/>'
             f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, 0.01, SCAN, SCAN + 0.02, 1)}" values="0;1;1;0;0"/></g>')

    ly = H - 24
    o.append(f'<rect x="28" y="{ly - 9}" width="9" height="9" rx="2" fill="{LEVELS[2]}"/><text x="43" y="{ly}" fill="#8b98a8" font-size="10">commit day</text>')
    o.append(f'<rect x="128" y="{ly - 10}" width="14" height="11" rx="2" fill="none" stroke="{BOX[0]}" stroke-width="1.2"/><text x="148" y="{ly}" fill="#8b98a8" font-size="10">detection (busiest day of each month + its cluster)</text>')
    o.append(f'<text x="{W - 28}" y="{ly}" fill="#5b6b7d" font-size="10" text-anchor="end">regenerated daily from my GitHub calendar</text>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    login, out = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN") or os.environ["GH_TOKEN"]
    total, cells = fetch(login, token)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build(total, cells))
    print(f"ok: {total} contributions -> {out}")


if __name__ == "__main__":
    main()
