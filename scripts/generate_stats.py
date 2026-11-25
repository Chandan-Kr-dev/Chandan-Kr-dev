#!/usr/bin/env python3
"""Generate assets/stats-dashboard.svg from your live GitHub data.

Runs inside the GitHub Action in .github/workflows/profile-stats.yml.
Uses only the Python standard library.

  GH_USER   GitHub username (the workflow passes the repo owner)
  GH_TOKEN  token for the GraphQL API. A personal access token with the
            read:user scope (saved as the PROFILE_TOKEN secret) lets the
            graph include private contributions. Language stats only ever
            use PUBLIC repositories.

  python scripts/generate_stats.py --placeholder   # writes the empty state
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape as esc

USER = os.environ.get("GH_USER", "Chandan-Kr-dev")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "stats-dashboard.svg")

BG, SURF, PRI, SEC, TXT, MUTE, BORD = "#0D1117", "#161B22", "#00D9FF", "#8B5CF6", "#E6EDF3", "#8B949E", "#30363D"
LEVELS = [SURF, "#12495C", "#0B8AA8", PRI, SEC]  # empty, low -> high

QUERY = """
query($login:String!){
  user(login:$login){
    contributionsCollection{
      totalCommitContributions
      contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
    }
    repositories(ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC, first:100){
      totalCount
      nodes{ languages(first:6, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name } } } }
    }
  }
}"""


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload or not payload.get("data", {}).get("user"):
        raise RuntimeError(f"GraphQL error: {payload.get('errors')}")
    u = payload["data"]["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    weeks = [[d["contributionCount"] for d in w["contributionDays"]] for w in cal["weeks"]]
    dates = [[d["date"] for d in w["contributionDays"]] for w in cal["weeks"]]
    langs = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    return {
        "weeks": weeks,
        "dates": dates,
        "total": cal["totalContributions"],
        "commits": u["contributionsCollection"]["totalCommitContributions"],
        "repos": u["repositories"]["totalCount"],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1]),
    }


def streaks(weeks):
    days = [c for w in weeks for c in w]
    longest = run = 0
    for c in days:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    cur = 0
    i = len(days) - 1
    if i >= 0 and days[i] == 0:  # today may not have activity yet
        i -= 1
    while i >= 0 and days[i] > 0:
        cur += 1
        i -= 1
    return cur, longest


def level(c, mx):
    if c <= 0 or mx <= 0:
        return 0
    r = c / mx
    return 4 if r > .75 else 3 if r > .5 else 2 if r > .25 else 1


def mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


def render(data):
    W, H = 900, 450
    ph = data is None
    weeks = data["weeks"] if not ph else [[0] * 7 for _ in range(53)]
    dates = data["dates"] if not ph else None
    mx = max((c for w in weeks for c in w), default=0)
    cur, longest = streaks(weeks) if not ph else (0, 0)
    fmt = (lambda n: f"{n:,}") if not ph else (lambda n: "–")
    kpis = [
        ("Contributions", fmt(data["total"]) if not ph else "–", "last 12 months"),
        ("Commits", fmt(data["commits"]) if not ph else "–", "last 12 months"),
        ("Longest streak", fmt(longest) if not ph else "–", "days in a row"),
        ("Current streak", fmt(cur) if not ph else "–", "days in a row"),
    ]
    o = [f'<rect width="{W}" height="{H}" rx="16" fill="{BG}"/>',
         f'<rect width="{W}" height="{H}" rx="16" fill="url(#glowC)"/>',
         f'<rect width="{W}" height="{H}" rx="16" fill="url(#glowV)"/>']

    # KPI tiles
    for i, (lab, val, sub) in enumerate(kpis):
        x = 24 + i * 217
        o.append(f'<rect x="{x}" y="24" width="203" height="92" rx="14" fill="{SURF}" stroke="{BORD}"/>')
        o.append(f'<rect x="{x}" y="24" width="203" height="92" rx="14" fill="url(#sheen)"/>')
        o.append(f'<text x="{x+18}" y="50" font-size="12.5" fill="{MUTE}">{esc(lab)}</text>')
        o.append(f'<text x="{x+18}" y="88" font-size="34" class="b" fill="url(#g)" letter-spacing="-1">{esc(val)}</text>')
        o.append(f'<text x="{x+18}" y="106" font-size="11" fill="{MUTE}">{esc(sub)}</text>')

    # heatmap panel
    py = 134
    o.append(f'<rect x="24" y="{py}" width="852" height="180" rx="14" fill="{SURF}" stroke="{BORD}"/>')
    o.append(f'<rect x="24" y="{py}" width="852" height="180" rx="14" fill="url(#sheen)"/>')
    gx, gy, pitch, cell = 64, py + 40, 15, 12
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text x="{gx-10}" y="{gy + r*pitch + 10}" font-size="10" fill="{MUTE}" text-anchor="end">{name}</text>')
    last_month = None
    for wi, w in enumerate(weeks):
        if dates:
            m = dt.date.fromisoformat(dates[wi][0]).strftime("%b")
            if m != last_month and wi < len(weeks) - 2:
                o.append(f'<text x="{gx + wi*pitch}" y="{py+28}" font-size="10" fill="{MUTE}">{m}</text>')
                last_month = m
        for di, c in enumerate(w):
            o.append(f'<rect x="{gx + wi*pitch}" y="{gy + di*pitch}" width="{cell}" height="{cell}" rx="3" fill="{LEVELS[level(c, mx)]}"/>')
    ly = py + 160
    o.append(f'<text x="{876-18-5*17-30-34}" y="{ly+3}" font-size="10" fill="{MUTE}" text-anchor="end">Less</text>')
    for k in range(5):
        o.append(f'<rect x="{876-18-5*17-28+k*17+34-34}" y="{ly-8}" width="12" height="12" rx="3" fill="{LEVELS[k]}"/>')
    o.append(f'<text x="{876-18-12}" y="{ly+3}" font-size="10" fill="{MUTE}">More</text>')
    if ph:
        o.append(f'<text x="{gx}" y="{ly+3}" font-size="11" fill="{MUTE}">Fills in after the first workflow run.</text>')

    # languages panel
    qy = 332
    o.append(f'<rect x="24" y="{qy}" width="852" height="94" rx="14" fill="{SURF}" stroke="{BORD}"/>')
    o.append(f'<rect x="24" y="{qy}" width="852" height="94" rx="14" fill="url(#sheen)"/>')
    title = "Top languages" + (f" across {data['repos']} public repositories" if not ph else "")
    o.append(f'<text x="42" y="{qy+28}" font-size="14" class="b" fill="{TXT}">{esc(title)}</text>')
    langs = (data["langs"][:5] if not ph else [])
    total = sum(s for _, s in langs) or 1
    o.append(f'<clipPath id="barclip"><rect x="42" y="{qy+40}" width="816" height="10" rx="5"/></clipPath>')
    o.append(f'<rect x="42" y="{qy+40}" width="816" height="10" rx="5" fill="{BG}"/>')
    if langs:
        x = 42.0
        legend_x = 42
        o.append('<g clip-path="url(#barclip)">')
        for i, (name, size) in enumerate(langs):
            w = 816 * size / total
            col = mix(PRI, SEC, i / max(len(langs) - 1, 1))
            o.append(f'<rect x="{x:.1f}" y="{qy+40}" width="{w+0.5:.1f}" height="10" fill="{col}"/>')
            x += w
        o.append('</g>')
        for i, (name, size) in enumerate(langs):
            col = mix(PRI, SEC, i / max(len(langs) - 1, 1))
            o.append(f'<circle cx="{legend_x+5}" cy="{qy+73}" r="5" fill="{col}"/>')
            label = f"{name} {size*100/total:.0f}%"
            o.append(f'<text x="{legend_x+16}" y="{qy+77}" font-size="12" fill="{MUTE}">{esc(label)}</text>')
            legend_x += 16 + 8 * len(label) + 22
    else:
        o.append(f'<text x="42" y="{qy+77}" font-size="12" fill="{MUTE}">Language breakdown appears after the first workflow run.</text>')

    style = ("text{font-family:'Segoe UI','SF Pro Display',-apple-system,'Helvetica Neue',Inter,Arial,sans-serif}"
             ".b{font-weight:700}")
    defs = f"""<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="{PRI}"/><stop offset="1" stop-color="{SEC}"/></linearGradient>
<linearGradient id="sheen" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".045"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<radialGradient id="glowC" cx=".08" cy="0" r=".9"><stop offset="0" stop-color="{PRI}" stop-opacity=".14"/><stop offset="1" stop-color="{PRI}" stop-opacity="0"/></radialGradient>
<radialGradient id="glowV" cx=".95" cy="1" r=".9"><stop offset="0" stop-color="{SEC}" stop-opacity=".18"/><stop offset="1" stop-color="{SEC}" stop-opacity="0"/></radialGradient>"""
    desc = ("GitHub activity dashboard. Totals and the contribution graph refresh automatically." if ph else
            f"{data['total']} contributions and {data['commits']} commits in the last 12 months. Longest streak {longest} days, current streak {cur} days.")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">'
            f'<title id="t">GitHub stats for {esc(USER)}</title><desc id="d">{esc(desc)}</desc>'
            f'<defs>{defs}</defs><style>{style}</style>{"".join(o)}</svg>')


def main():
    if "--placeholder" in sys.argv or not TOKEN:
        data = None
        if not TOKEN and "--placeholder" not in sys.argv:
            print("GH_TOKEN not set; writing the placeholder.", file=sys.stderr)
    else:
        data = fetch()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(data))
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
