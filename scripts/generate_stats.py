#!/usr/bin/env python3
"""Generate assets/stats-dashboard.svg and assets/contribution-city.svg from live GitHub data.

Runs inside .github/workflows/profile-stats.yml (standard library only).

  GH_USER   GitHub username (the workflow passes the repo owner)
  GH_TOKEN  OPTIONAL personal access token (classic, read:user). With it the
            graph uses the GraphQL API and counts private contributions.
            Without it the script reads the same public data visitors see.

Language stats only ever use PUBLIC repositories. If GitHub cannot be reached,
the existing SVG files are left untouched.
"""
import datetime as dt
import json
import os
import random
import re
import sys
import urllib.request
from xml.sax.saxutils import escape as esc

USER = os.environ.get("GH_USER", "Chandan-Kr-dev")
TOKEN = os.environ.get("GH_TOKEN", "").strip()
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
UA = "Mozilla/5.0 (profile-stats)"

BG, SURF, PRI, SEC, TXT, MUTE, BORD = "#0D1117", "#161B22", "#00D9FF", "#8B5CF6", "#E6EDF3", "#8B949E", "#30363D"
LEVELS = [SURF, "#12495C", "#0B8AA8", PRI, SEC]


# ------------------------------------------------------------------ data
def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def calendar_scrape():
    html = http(f"https://github.com/users/{USER}/contributions")
    cells = re.findall(r'<td[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*id="(contribution-day-component-\d+-\d+)"', html)
    tips = dict(re.findall(r'for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)</tool-tip>', html))
    out = {}
    for date, cid in cells:
        m = re.match(r"\s*(\d+)\s+contribution", tips.get(cid, ""))
        out[date] = int(m.group(1)) if m else 0
    if not out:
        raise RuntimeError("could not read the contribution calendar")
    return out


GQL = """query($login:String!){ user(login:$login){
  contributionsCollection{ contributionCalendar{ weeks{ contributionDays{ date contributionCount } } } }
  repositories(ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC, first:100){
    totalCount nodes{ languages(first:6, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name } } } } } } }"""


def graphql():
    body = json.dumps({"query": GQL, "variables": {"login": USER}}).encode()
    p = json.loads(http("https://api.github.com/graphql", body,
                        {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"}))
    if p.get("errors") or not p.get("data", {}).get("user"):
        raise RuntimeError(f"GraphQL: {p.get('errors')}")
    u = p["data"]["user"]
    cal = {}
    for w in u["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            cal[d["date"]] = d["contributionCount"]
    langs = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    return cal, sorted(langs.items(), key=lambda kv: -kv[1]), u["repositories"]["totalCount"]


def languages_scrape():
    counts, repos = {}, 0
    for page in range(1, 6):
        html = http(f"https://github.com/{USER}?tab=repositories&type=source&page={page}")
        for block in html.split('itemprop="owns"')[1:]:
            repos += 1
            m = re.search(r'itemprop="programmingLanguage">([^<]+)<', block)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        if 'rel="next"' not in html:
            break
    return sorted(counts.items(), key=lambda kv: -kv[1]), repos


def build_weeks(cal):
    days = sorted(cal)
    d0 = dt.date.fromisoformat(days[0])
    start = d0 - dt.timedelta(days=(d0.weekday() + 1) % 7)  # weeks start on Sunday
    n = (dt.date.fromisoformat(days[-1]) - start).days // 7 + 1
    weeks = [[None] * 7 for _ in range(n)]
    dates = [[None] * 7 for _ in range(n)]
    for ds in days:
        d = dt.date.fromisoformat(ds)
        wi, di = (d - start).days // 7, (d.weekday() + 1) % 7
        weeks[wi][di], dates[wi][di] = cal[ds], ds
    return weeks, dates


def gather():
    if TOKEN:
        cal, langs, repos = graphql()
    else:
        cal = calendar_scrape()
        langs, repos = languages_scrape()
    weeks, dates = build_weeks(cal)
    flat = [c for w in weeks for c in w if c is not None]
    cur, longest, run = 0, 0, 0
    for c in flat:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    i = len(flat) - 1
    if i >= 0 and flat[i] == 0:
        i -= 1
    while i >= 0 and flat[i] > 0:
        cur += 1
        i -= 1
    return {"weeks": weeks, "dates": dates, "total": sum(flat), "active": sum(1 for c in flat if c > 0),
            "cur": cur, "longest": longest, "langs": langs, "repos": repos}


# ------------------------------------------------------------------ drawing helpers
STYLE = ("text{font-family:'Segoe UI','SF Pro Display',-apple-system,'Helvetica Neue',Inter,Arial,sans-serif}"
         ".b{font-weight:700}@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
DEFS = f"""<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="{PRI}"/><stop offset="1" stop-color="{SEC}"/></linearGradient>
<linearGradient id="sheen" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".045"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<radialGradient id="glowC" cx=".08" cy="0" r=".9"><stop offset="0" stop-color="{PRI}" stop-opacity=".14"/><stop offset="1" stop-color="{PRI}" stop-opacity="0"/></radialGradient>
<radialGradient id="glowV" cx=".95" cy="1" r=".9"><stop offset="0" stop-color="{SEC}" stop-opacity=".18"/><stop offset="1" stop-color="{SEC}" stop-opacity="0"/></radialGradient>"""


def wrap(w, h, title, desc, body, extra_defs="", extra_style=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">'
            f'<title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>'
            f'<defs>{DEFS}{extra_defs}</defs><style>{STYLE}{extra_style}</style>{body}</svg>')


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


def level(c, mx):
    if not c or mx <= 0:
        return 0
    r = c / mx
    return 4 if r > .75 else 3 if r > .5 else 2 if r > .25 else 1


# ------------------------------------------------------------------ dashboard
def render_dashboard(d):
    W, H = 900, 450
    weeks, dates = d["weeks"], d["dates"]
    mx = max((c for w in weeks for c in w if c is not None), default=0)
    fmt = lambda n: f"{n:,}"
    kpis = [("Contributions", fmt(d["total"]), "last 12 months"),
            ("Active days", fmt(d["active"]), "with at least one contribution"),
            ("Longest streak", fmt(d["longest"]), "days in a row"),
            ("Current streak", fmt(d["cur"]), "days in a row")]
    o = [f'<rect width="{W}" height="{H}" rx="16" fill="{BG}"/>',
         f'<rect width="{W}" height="{H}" rx="16" fill="url(#glowC)"/>',
         f'<rect width="{W}" height="{H}" rx="16" fill="url(#glowV)"/>']
    for i, (lab, val, sub) in enumerate(kpis):
        x = 24 + i * 217
        o += [f'<rect x="{x}" y="24" width="203" height="92" rx="14" fill="{SURF}" stroke="{BORD}"/>',
              f'<rect x="{x}" y="24" width="203" height="92" rx="14" fill="url(#sheen)"/>',
              f'<text x="{x+18}" y="50" font-size="12.5" fill="{MUTE}">{esc(lab)}</text>',
              f'<text x="{x+18}" y="88" font-size="34" class="b" fill="url(#g)" letter-spacing="-1">{esc(val)}</text>',
              f'<text x="{x+18}" y="106" font-size="11" fill="{MUTE}">{esc(sub)}</text>']
    py = 134
    o += [f'<rect x="24" y="{py}" width="852" height="180" rx="14" fill="{SURF}" stroke="{BORD}"/>',
          f'<rect x="24" y="{py}" width="852" height="180" rx="14" fill="url(#sheen)"/>']
    gx, gy, pitch, cell = 64, py + 40, 15, 12
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text x="{gx-10}" y="{gy + r*pitch + 10}" font-size="10" fill="{MUTE}" text-anchor="end">{name}</text>')
    last = None
    for wi, w in enumerate(weeks):
        first = next((x for x in dates[wi] if x), None)
        if first:
            m = dt.date.fromisoformat(first).strftime("%b")
            if m != last and wi < len(weeks) - 2:
                o.append(f'<text x="{gx + wi*pitch}" y="{py+28}" font-size="10" fill="{MUTE}">{m}</text>')
                last = m
        for di, c in enumerate(w):
            if c is None:
                continue
            o.append(f'<rect x="{gx + wi*pitch}" y="{gy + di*pitch}" width="{cell}" height="{cell}" rx="3" fill="{LEVELS[level(c, mx)]}"/>')
    ly = py + 160
    o.append(f'<text x="722" y="{ly+3}" font-size="10" fill="{MUTE}" text-anchor="end">Less</text>')
    for k in range(5):
        o.append(f'<rect x="{730+k*17}" y="{ly-8}" width="12" height="12" rx="3" fill="{LEVELS[k]}" stroke="{BORD}" stroke-width="{1 if k == 0 else 0}"/>')
    o.append(f'<text x="822" y="{ly+3}" font-size="10" fill="{MUTE}">More</text>')

    qy = 332
    o += [f'<rect x="24" y="{qy}" width="852" height="94" rx="14" fill="{SURF}" stroke="{BORD}"/>',
          f'<rect x="24" y="{qy}" width="852" height="94" rx="14" fill="url(#sheen)"/>',
          f'<text x="42" y="{qy+28}" font-size="14" class="b" fill="{TXT}">Top languages across {d["repos"]} public repositories</text>',
          f'<clipPath id="barclip"><rect x="42" y="{qy+40}" width="816" height="10" rx="5"/></clipPath>',
          f'<rect x="42" y="{qy+40}" width="816" height="10" rx="5" fill="{BG}"/>']
    langs = d["langs"][:5]
    total = sum(s for _, s in langs) or 1
    x, lx = 42.0, 42
    o.append('<g clip-path="url(#barclip)">')
    for i, (name, size) in enumerate(langs):
        w = 816 * size / total
        o.append(f'<rect x="{x:.1f}" y="{qy+40}" width="{w+0.5:.1f}" height="10" fill="{mix(PRI, SEC, i / max(len(langs)-1, 1))}"/>')
        x += w
    o.append('</g>')
    for i, (name, size) in enumerate(langs):
        col = mix(PRI, SEC, i / max(len(langs) - 1, 1))
        label = f"{name} {size*100/total:.0f}%"
        o.append(f'<circle cx="{lx+5}" cy="{qy+73}" r="5" fill="{col}"/>')
        o.append(f'<text x="{lx+16}" y="{qy+77}" font-size="12" fill="{MUTE}">{esc(label)}</text>')
        lx += 16 + 7 * len(label) + 24
    desc = (f"{d['total']} contributions in the last 12 months across {d['active']} active days. "
            f"Longest streak {d['longest']} days, current streak {d['cur']} days.")
    return wrap(W, H, f"GitHub stats for {USER}", desc, "".join(o))


# ------------------------------------------------------------------ contribution city
def render_city(d):
    W, H, G = 900, 350, 270
    weeks, dates = d["weeks"], d["dates"]
    n = len(weeks)
    totals = [sum(c for c in w if c) for w in weeks]
    actives = [sum(1 for c in w if c) for w in weeks]
    mx = max(totals) or 1
    pitch = 852 / n
    bw, dep, sk = pitch - 3.4, 4.0, 2.5
    rnd = random.Random(7)

    sky, stars = [], []
    sky.append(f'<rect width="{W}" height="{H}" rx="16" fill="url(#sky)"/>')
    sky.append(f'<ellipse cx="450" cy="{G}" rx="470" ry="120" fill="url(#horizon)"/>')
    for i in range(46):
        sx, sy, sr = rnd.uniform(14, 886), rnd.uniform(12, G - 90), rnd.choice([.7, .9, 1.1, 1.4])
        tw = ' class="tw" style="animation-delay:%.1fs"' % rnd.uniform(0, 5) if i % 5 == 0 else ""
        stars.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr}" fill="{TXT}" opacity="{rnd.uniform(.25,.7):.2f}"{tw}/>')
    moon = (f'<circle cx="820" cy="64" r="40" fill="{PRI}" opacity=".10"/><circle cx="820" cy="64" r="26" fill="{PRI}" opacity=".12"/>'
            f'<circle cx="820" cy="64" r="15" fill="{TXT}" opacity=".93"/>'
            f'<circle cx="815" cy="60" r="3" fill="#C9D1D9" opacity=".6"/><circle cx="825" cy="69" r="2" fill="#C9D1D9" opacity=".6"/>')

    city, tops = [], []
    for i in range(n):
        t, a = totals[i], actives[i]
        x = 24 + i * pitch
        h = 14 + 176 * (t / mx) ** 0.65 if t else 6
        yt = G - h
        accent = mix(PRI, SEC, (t / mx) ** 0.8) if t else "#2A3340"
        city.append(f'<polygon points="{x+bw:.1f},{yt:.1f} {x+bw+dep:.1f},{yt-sk:.1f} {x+bw+dep:.1f},{G-sk} {x+bw:.1f},{G}" fill="#0A0E15"/>')
        city.append(f'<rect x="{x:.1f}" y="{yt:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="url(#bfront)"/>')
        city.append(f'<polygon points="{x:.1f},{yt:.1f} {x+bw:.1f},{yt:.1f} {x+bw+dep:.1f},{yt-sk:.1f} {x+dep:.1f},{yt-sk:.1f}" fill="{accent}" opacity=".55"/>')
        city.append(f'<rect x="{x:.1f}" y="{yt:.1f}" width="{bw:.1f}" height="1.6" fill="{accent}"/>')
        if t:
            p = 0.2 + 0.7 * a / 7
            cols = max(1, int((bw - 2) // 5.4))
            ww = (bw - 2 - (cols - 1) * 2.2) / cols
            lit_c, lit_v, dim = [], [], []
            y = G - 7
            while y > yt + 5:
                for c in range(cols):
                    wx = x + 1 + c * (ww + 2.2)
                    seg = f"M{wx:.1f} {y-3.6:.1f}h{ww:.1f}v3.6h-{ww:.1f}z"
                    r = rnd.random()
                    if r < p:
                        (lit_v if rnd.random() < .28 else lit_c).append(seg)
                    else:
                        dim.append(seg)
                y -= 6.8
            if dim:
                city.append(f'<path d="{"".join(dim)}" fill="#202937" opacity=".8"/>')
            if lit_c:
                city.append(f'<path d="{"".join(lit_c)}" fill="{PRI}" opacity=".9"/>')
            if lit_v:
                city.append(f'<path d="{"".join(lit_v)}" fill="{SEC}" opacity=".95"/>')
        tops.append((t, x, yt, bw))
    for t, x, yt, w in sorted(tops, reverse=True)[:3]:
        if t:
            cx = x + w / 2
            city.append(f'<rect x="{cx-0.5:.1f}" y="{yt-12:.1f}" width="1" height="12" fill="{MUTE}"/>')
            city.append(f'<circle class="bl" cx="{cx:.1f}" cy="{yt-13:.1f}" r="1.8" fill="{PRI}"/>')

    first = next(x for w in dates for x in w if x)
    lastd = next(x for w in reversed(dates) for x in reversed(w) if x)
    f = lambda s: dt.date.fromisoformat(s).strftime("%b %Y")
    body = "".join(sky) + "".join(stars) + moon
    body += f'<g id="city">{"".join(city)}</g>'
    body += f'<g mask="url(#fm)"><use href="#city" transform="translate(0 {2*G}) scale(1 -1)" opacity=".22"/></g>'
    body += f'<rect x="0" y="{G}" width="{W}" height="1.5" fill="url(#gline)"/>'
    body += f'<text x="24" y="34" font-size="13" class="b" fill="{TXT}">{d["total"]:,} contributions, {f(first)} to {f(lastd)}</text>'
    body += f'<text x="24" y="53" font-size="11.5" fill="{MUTE}">One tower per week. Taller means more contributions; lit windows mean active days.</text>'
    defs = f"""<linearGradient id="sky" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{BG}"/><stop offset=".65" stop-color="#121029"/><stop offset="1" stop-color="#1B1240"/></linearGradient>
<radialGradient id="horizon" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{SEC}" stop-opacity=".30"/><stop offset="1" stop-color="{SEC}" stop-opacity="0"/></radialGradient>
<linearGradient id="bfront" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#1D2636"/><stop offset="1" stop-color="#0F1520"/></linearGradient>
<linearGradient id="gline" x1="0" x2="1"><stop offset="0" stop-color="{PRI}" stop-opacity="0"/><stop offset=".5" stop-color="{PRI}" stop-opacity=".7"/><stop offset="1" stop-color="{SEC}" stop-opacity="0"/></linearGradient>
<linearGradient id="fmg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>
<mask id="fm" maskUnits="userSpaceOnUse" x="0" y="{G}" width="{W}" height="{H-G}"><rect x="0" y="{G}" width="{W}" height="{H-G}" fill="url(#fmg)"/></mask>
<clipPath id="round"><rect width="{W}" height="{H}" rx="16"/></clipPath>"""
    anim = (".tw{animation:tw 4s ease-in-out infinite}.bl{animation:bl 2.2s steps(1) infinite}"
            "@keyframes tw{0%,100%{opacity:.25}50%{opacity:.9}}@keyframes bl{50%{opacity:0}}")
    body = f'<g clip-path="url(#round)">{body}</g>'
    desc = (f"Night skyline of {d['total']:,} contributions over the last 12 months. "
            f"Each tower is one week; taller towers are weeks with more contributions.")
    return wrap(W, H, f"Contribution city for {USER}", desc, body, defs, anim)


def main():
    try:
        d = gather()
    except Exception as e:  # keep whatever is already in the repo
        print(f"Could not refresh stats ({e}); leaving existing files.", file=sys.stderr)
        return
    os.makedirs(ASSETS, exist_ok=True)
    open(os.path.join(ASSETS, "stats-dashboard.svg"), "w", encoding="utf-8").write(render_dashboard(d))
    open(os.path.join(ASSETS, "contribution-city.svg"), "w", encoding="utf-8").write(render_city(d))
    print(f"ok: {d['total']} contributions, {d['active']} active days, streak {d['cur']}/{d['longest']}, "
          f"{d['repos']} repos, top: {d['langs'][:3]}")


if __name__ == "__main__":
    main()
