"""Katkı takviminden animasyonlu İHA görev SVG'si üretir.

Bir sabit kanat İHA, yasak uçuş bölgelerinden (NFZ) kaçınan bir rota ile katkı
takviminin en yoğun günlerine kilitlenir. Yalnız standart kütüphane kullanır.

Kullanım: GITHUB_TOKEN=... python scripts/gen_mission.py <kullanıcı> <çıktı.svg>
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.request

CELL, GAP = 12, 3
STEP = CELL + GAP
W, H = 880, 240
X0, Y0 = (W - 53 * (12 + 3) + 3) // 2, 74
DUR = 22.0          # saniye, tam döngü
FLY = 0.86          # döngünün uçuşa ayrılan kısmı
N_TARGETS = 12

BG = "#0b0f14"
GRID = "#1a2330"
EMPTY = "#141b24"
LEVELS = ["#0f3d2e", "#16694a", "#1fa36b", "#3dff9a"]
HUD = "#7fe8ff"
LOCK = "#ff4d5e"
NFZ = "#ff4d5e"

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


def center(w, d):
    return X0 + w * STEP + CELL / 2, Y0 + d * STEP + CELL / 2


def level(c, mx):
    if c <= 0:
        return -1
    q = c / mx
    return 0 if q <= 0.25 else 1 if q <= 0.5 else 2 if q <= 0.75 else 3


def pick_targets(cells, weeks):
    bins = max(1, N_TARGETS)
    out = []
    for b in range(bins):
        lo, hi = b * weeks / bins, (b + 1) * weeks / bins
        best = max((c for c in cells if lo <= c[0] < hi and c[2] > 0), key=lambda c: c[2], default=None)
        if best:
            out.append(best)
    return out


def pick_nfz(cells, targets, weeks):
    counts = {(w, d): c for w, d, c, _ in cells}
    r = 26
    zones = []
    for _ in range(3):
        best = None
        for w in range(4, weeks - 4):
            for d in (2, 3, 4):
                cx, cy = center(w, d)
                if any(math.hypot(cx - zx, cy - zy) < 160 for zx, zy, _ in zones):
                    continue
                if any(math.hypot(cx - center(t[0], t[1])[0], cy - center(t[0], t[1])[1]) < r + 14 for t in targets):
                    continue
                s = sum(counts.get((w + i, d + j), 0) for i in range(-2, 3) for j in range(-2, 3))
                if best is None or s < best[0]:
                    best = (s, cx, cy)
        if best:
            zones.append((best[1], best[2], r))
    return sorted(zones)


def avoid(points, zones):
    """Bir NFZ'yi kesen her bacak için çemberin dışından geçen bir ara nokta ekler."""
    for zx, zy, r in zones:
        out = [points[0]]
        for a, b in zip(points, points[1:]):
            ax, ay = a
            bx, by = b
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1
            t = max(0, min(1, ((zx - ax) * dx + (zy - ay) * dy) / L2))
            px, py = ax + t * dx, ay + t * dy
            dist = math.hypot(px - zx, py - zy)
            if dist < r + 10 and 0 < t < 1:
                if dist < 1e-6:
                    nx, ny = -dy, dx
                    n = math.hypot(nx, ny) or 1
                    nx, ny = nx / n, ny / n
                else:
                    nx, ny = (px - zx) / dist, (py - zy) / dist
                out.append((zx + nx * (r + 18), zy + ny * (r + 18)))
            out.append(b)
        points = out
    return points


def catmull(points):
    """Catmull-Rom -> kübik Bezier segmentleri."""
    segs = []
    p = [points[0]] + points + [points[-1]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        segs.append((p1, c1, c2, p2))
    return segs


def seg_len(s, n=40):
    def at(t):
        a, b, c, d = s
        mt = 1 - t
        return (mt**3 * a[0] + 3 * mt * mt * t * b[0] + 3 * mt * t * t * c[0] + t**3 * d[0],
                mt**3 * a[1] + 3 * mt * mt * t * b[1] + 3 * mt * t * t * c[1] + t**3 * d[1])
    pts = [at(i / n) for i in range(n + 1)]
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(pts, pts[1:]))


def f(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


def kt(*ts):
    return ";".join(f"{min(max(t, 0), 1):.4f}" for t in ts)


def build(total, cells):
    weeks = max(c[0] for c in cells) + 1
    mx = max([c[2] for c in cells] + [1])
    targets = pick_targets(cells, weeks)
    zones = pick_nfz(cells, targets, weeks)

    gy = Y0 + 3 * STEP + CELL / 2
    start = (X0 - 40, gy)
    end = (X0 + weeks * STEP + 40, gy)
    tpts = [center(t[0], t[1]) for t in targets]
    pts = avoid([start] + tpts + [end], zones)
    segs = catmull(pts)
    lens = [seg_len(s) for s in segs]
    total_len = sum(lens)

    # her hedefin döngü içindeki zamanı (paced hareket => uzunlukla doğrusal)
    times = []
    acc = 0.0
    tset = {(round(x, 3), round(y, 3)) for x, y in tpts}
    for s, l in zip(segs, lens):
        acc += l
        key = (round(s[3][0], 3), round(s[3][1], 3))
        if key in tset:
            times.append(FLY * acc / total_len)
    path_d = f"M{f(segs[0][0][0])},{f(segs[0][0][1])} " + " ".join(
        f"C{f(b[0])},{f(b[1])} {f(c[0])},{f(c[1])} {f(d[0])},{f(d[1])}" for _, b, c, d in segs)

    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">')
    o.append(f"""<defs>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="{GRID}" stroke-width="0.6"/></pattern>
<radialGradient id="nfz"><stop offset="0" stop-color="{NFZ}" stop-opacity="0.22"/><stop offset="1" stop-color="{NFZ}" stop-opacity="0.04"/></radialGradient>
<linearGradient id="fov" x1="0" x2="1"><stop offset="0" stop-color="{HUD}" stop-opacity="0.35"/><stop offset="1" stop-color="{HUD}" stop-opacity="0"/></linearGradient>
</defs>""")
    o.append(f'<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>')
    o.append(f'<rect width="{W}" height="{H}" rx="14" fill="url(#grid)" opacity="0.7"/>')
    # köşe çerçeveleri
    for x, y, sx, sy in ((10, 10, 1, 1), (W - 10, 10, -1, 1), (10, H - 10, 1, -1), (W - 10, H - 10, -1, -1)):
        o.append(f'<path d="M{x},{y + sy * 18}V{y}H{x + sx * 18}" fill="none" stroke="{HUD}" stroke-width="1.5" opacity="0.8"/>')
    # HUD metinleri
    o.append(f'<text x="28" y="36" fill="{HUD}" font-size="12" letter-spacing="2">UAV-01 // CONTRIBUTION RECON</text>')
    o.append(f'<text x="28" y="54" fill="#5b6b7d" font-size="10" letter-spacing="1">MODE AUTO · PLANNER PRM · NFZ AVOIDANCE ON</text>')
    o.append(f'<text x="{W - 28}" y="36" fill="#e6edf3" font-size="12" text-anchor="end" letter-spacing="1">{total} CONTRIBUTIONS · LAST 12 MONTHS</text>')
    # kilit sayacı
    n = len(times)
    for i in range(n + 1):
        t0 = 0 if i == 0 else times[i - 1]
        t1 = times[i] if i < n else 1
        vals = "0;1;1;0;0" if i else "1;1;0;0;0"
        if i == 0:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t1)}" values="1;0"/>'
        elif i == n:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t0)}" values="0;1"/>'
        else:
            anim = f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t0, t1)}" values="0;1;0"/>'
        col = LOCK if i < n else "#3dff9a"
        label = f"TARGETS LOCKED {i:02d}/{n:02d}" if i < n else f"MISSION COMPLETE {n:02d}/{n:02d}"
        o.append(f'<text x="{W - 28}" y="54" fill="{col}" font-size="10" text-anchor="end" letter-spacing="1" opacity="{1 if i == 0 else 0}">{label}{anim}</text>')

    # katkı hücreleri
    for w, d, c, date in cells:
        x, y = X0 + w * STEP, Y0 + d * STEP
        lv = level(c, mx)
        fill = EMPTY if lv < 0 else LEVELS[lv]
        o.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{fill}"><title>{date}: {c}</title></rect>')

    # NFZ
    for i, (zx, zy, r) in enumerate(zones):
        o.append(f'<circle cx="{f(zx)}" cy="{f(zy)}" r="{r}" fill="url(#nfz)" stroke="{NFZ}" stroke-width="1.2" stroke-dasharray="4 3">'
                 f'<animate attributeName="stroke-dashoffset" from="0" to="14" dur="1.6s" repeatCount="indefinite"/></circle>')
        o.append(f'<text x="{f(zx)}" y="{f(zy - r - 6)}" fill="{NFZ}" font-size="9" text-anchor="middle" letter-spacing="1">NFZ-{i + 1}</text>')

    # planlanan rota + uçulan iz
    o.append(f'<path d="{path_d}" fill="none" stroke="{HUD}" stroke-width="1" stroke-dasharray="2 5" opacity="0.35"/>')
    L = f(total_len)
    o.append(f'<path d="{path_d}" fill="none" stroke="{HUD}" stroke-width="1.6" opacity="0.9" stroke-dasharray="{L}" stroke-dashoffset="{L}" filter="url(#glow)">'
             f'<animate attributeName="stroke-dashoffset" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, FLY, 1)}" values="{L};0;0"/>'
             f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, FLY, 0.97, 1)}" values="0.9;0.9;0;0"/></path>')

    # kilitlenme işaretleri
    for (x, y), t, tg in zip(tpts, times, targets):
        s = 9
        br = (f"M{f(x - s)},{f(y - s + 4)}V{f(y - s)}H{f(x - s + 4)} M{f(x + s - 4)},{f(y - s)}H{f(x + s)}V{f(y - s + 4)} "
              f"M{f(x + s)},{f(y + s - 4)}V{f(y + s)}H{f(x + s - 4)} M{f(x - s + 4)},{f(y + s)}H{f(x - s)}V{f(y + s - 4)}")
        o.append(f'<g opacity="0"><animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t, 0.97)}" values="0;1;0"/>'
                 f'<path d="{br}" fill="none" stroke="{LOCK}" stroke-width="1.4">'
                 f'<animate attributeName="stroke" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt(0, t + 0.02)}" values="{LOCK};#3dff9a"/></path>'
                 f'<circle cx="{f(x)}" cy="{f(y)}" r="2" fill="#e6edf3"/></g>')
        o.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="4" fill="none" stroke="{LOCK}" stroke-width="1.2" opacity="0">'
                 f'<animate attributeName="r" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, t, t + 0.03, 1)}" values="4;4;20;20"/>'
                 f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, t, t + 0.001, t + 0.03, 1)}" values="0;0;1;0;0"/></circle>')

    # İHA
    o.append(f'<g filter="url(#glow)">'
             f'<path d="M0,0 L46,-16 A50,50 0 0 1 46,16 Z" fill="url(#fov)"/>'
             f'<path d="M11,0 L4,-1.6 L-1,-12 L-4,-12 L-2,-1.6 L-9,-1.4 L-12,-5 L-13.5,-5 L-12.5,0 L-13.5,5 L-12,5 L-9,1.4 L-2,1.6 L-4,12 L-1,12 L4,1.6 Z" fill="#e6edf3"/>'
             f'<animateMotion dur="{DUR}s" repeatCount="indefinite" rotate="auto" calcMode="linear" keyPoints="0;1;1" keyTimes="{kt(0, FLY, 1)}" path="{path_d}"/>'
             f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" keyTimes="{kt(0, 0.02, FLY - 0.02, FLY, 1)}" values="0;1;1;0;0"/>'
             f'</g>')

    # gösterge
    ly = H - 24
    o.append(f'<rect x="28" y="{ly - 9}" width="9" height="9" rx="2" fill="{LEVELS[2]}"/><text x="43" y="{ly}" fill="#8b98a8" font-size="10">commit day</text>')
    o.append(f'<path d="M128,{ly - 9}h3m3,0h3v3m0,3v3h-3m-3,0h-3v-3m0,-3v-3" fill="none" stroke="{LOCK}" stroke-width="1.2"/><text x="146" y="{ly}" fill="#8b98a8" font-size="10">locked target (busiest day per month)</text>')
    o.append(f'<circle cx="392" cy="{ly - 4}" r="5" fill="none" stroke="{NFZ}" stroke-dasharray="2 2"/><text x="403" y="{ly}" fill="#8b98a8" font-size="10">no-fly zone</text>')
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
