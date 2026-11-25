#!/usr/bin/env python3
"""Generate a GitHub profile stats dashboard SVG from live GitHub API data."""
import os, json, urllib.request, urllib.error, datetime, html, sys

USERNAME = os.getenv("GH_USERNAME", "Chandan-Kr-dev")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
OUT = os.getenv("OUTPUT_FILE", "assets/stats-dashboard.svg")
if not TOKEN:
    raise SystemExit("Missing GitHub token: set GH_TOKEN or GITHUB_TOKEN")

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": "profile-stats-generator"}

def request(url, data=None):
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=payload, headers={**HEADERS, **({"Content-Type":"application/json"} if payload else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API returned HTTP {e.code}: {body[:500]}")

# GraphQL provides a complete contribution calendar and contribution totals.
query = '''query($login:String!, $from:DateTime!, $to:DateTime!){ user(login:$login){ contributionsCollection(from: $from, to: $to){
 totalCommitContributions totalIssueContributions totalPullRequestContributions totalPullRequestReviewContributions
 contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
 } } }'''
today = datetime.date.today()
start = today - datetime.timedelta(days=364)
from_dt = datetime.datetime.combine(start, datetime.time.min).isoformat() + "Z"
to_dt = datetime.datetime.combine(today, datetime.time.max.replace(microsecond=0)).isoformat() + "Z"
data = request("https://api.github.com/graphql", {"query": query, "variables":{"login":USERNAME,"from":from_dt,"to":to_dt}})
if data.get("errors"):
    raise RuntimeError("GraphQL errors: " + json.dumps(data["errors"]))
user = data.get("data",{}).get("user")
if not user:
    raise RuntimeError(f"GitHub user not found or inaccessible: {USERNAME}")
collection = user["contributionsCollection"]
calendar = collection["contributionCalendar"]
# Flatten contributions by day; include zero-contribution dates.
counts = {}
for week in calendar.get("weeks", []):
    for day in week.get("contributionDays", []):
        counts[day["date"]] = int(day["contributionCount"])
for i in range(365):
    d = start + datetime.timedelta(days=i)
    counts.setdefault(d.isoformat(), 0)
# Streaks based on calendar days, excluding future dates. Current streak ends today
# when today has activity; otherwise it ends yesterday.
series = [(start + datetime.timedelta(days=i), counts[(start + datetime.timedelta(days=i)).isoformat()]) for i in range(365)]
longest = current = run = 0
for d, n in series:
    run = run + 1 if n > 0 else 0
    longest = max(longest, run)
end_index = len(series)-1 if series[-1][1] > 0 else len(series)-2
current = 0
for idx in range(end_index, -1, -1):
    if series[idx][1] > 0: current += 1
    else: break
commits = int(collection.get("totalCommitContributions", 0))
contributions = int(calendar.get("totalContributions", 0))
# Language distribution from owned repositories, aggregating bytes reported by GitHub.
repo_lang_totals = {}
page = 1
while True:
    repos = request(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&page={page}&type=owner")
    if not repos: break
    for repo in repos:
        if repo.get("fork") or repo.get("archived"):
            continue
        langs = request(repo["languages_url"])
        for lang, size in langs.items():
            repo_lang_totals[lang] = repo_lang_totals.get(lang, 0) + int(size)
    if len(repos) < 100: break
    page += 1
languages = sorted(repo_lang_totals.items(), key=lambda item:item[1], reverse=True)[:5]
lang_sum = sum(size for _,size in languages) or 1

# Design: compact 980x390 dashboard, palette matching Midnight Developer.
W,H = 980,390
bg="#0D1117"; surface="#161B22"; border="#30363D"; text="#E6EDF3"; muted="#8B949E"; cyan="#00D9FF"; teal="#0E7490"; purple="#8B5CF6"
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', '<defs><linearGradient id="accent" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#00D9FF"/><stop offset="1" stop-color="#8B5CF6"/></linearGradient></defs>', f'<rect width="{W}" height="{H}" rx="20" fill="{bg}"/>']
def txt(x,y,s,size=12,color=text,weight=400): svg.append(f'<text x="{x}" y="{y}" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(str(s))}</text>')
def panel(x,y,w,h): svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="15" fill="{surface}" stroke="{border}"/>')
# 4 stat tiles
metrics=[("Contributions",contributions,"last 12 months"),("Commits",commits,"last 12 months"),("Longest streak",longest,"days in a row"),("Current streak",current,"days in a row")]
for i,(label,value,foot) in enumerate(metrics):
    x=16+i*242; panel(x,14,230,86); txt(x+16,38,label,11,muted); txt(x+16,68,value,25,cyan,700); txt(x+16,88,foot,10,muted)
# Calendar panel
panel(16,112,948,175); txt(34,135,"Contribution activity · last 12 months",12,text,600)
# 53 week columns, 7 day rows; position dates from first Sunday to align weekdays.
first = start - datetime.timedelta(days=(start.weekday()+1)%7)
cell=11; gap=4; grid_x=34; grid_y=154
for i in range(53*7):
    d=first+datetime.timedelta(days=i)
    if d < start or d > today: continue
    n=counts.get(d.isoformat(),0)
    color="#161B22" if n==0 else ("#075985" if n<=2 else ("#0891B2" if n<=5 else (cyan if n<=9 else purple)))
    x=grid_x+(i//7)*(cell+gap); y=grid_y+(i%7)*(cell+gap)
    svg.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{color}"/>')
txt(34,276,"Less",9,muted); 
for j,c in enumerate(["#161B22","#075985","#0891B2",cyan,purple]): svg.append(f'<rect x="{820+j*20}" y="265" width="12" height="12" rx="3" fill="{c}"/>')
txt(930,276,"More",9,muted)
# Language card
panel(16,302,948,72); txt(34,326,"Top languages",12,text,600)
barx,bary,barw,barh=34,337,910,9
svg.append(f'<rect x="{barx}" y="{bary}" width="{barw}" height="{barh}" rx="4.5" fill="#0B0F14"/>')
lang_colors=[cyan,"#8B5CF6","#0891B2","#2563EB","#A78BFA"]
offset=0
for idx,(lang,size) in enumerate(languages):
    width=barw*size/lang_sum
    svg.append(f'<rect x="{barx+offset}" y="{bary}" width="{width:.2f}" height="{barh}" rx="3" fill="{lang_colors[idx%len(lang_colors)]}"/>')
    offset+=width
if languages:
    labels=[]
    for i,(lang,size) in enumerate(languages):
        pct=size/lang_sum*100
        labels.append(f'<circle cx="{36+i*180}" cy="359" r="4" fill="{lang_colors[i%len(lang_colors)]}"/><text x="{47+i*180}" y="363" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="10" fill="{text}">{html.escape(lang)} {pct:.1f}%</text>')
    svg.extend(labels)
else:
    txt(34,362,"No repository language data available yet.",10,muted)
svg.append('</svg>')
os.makedirs(os.path.dirname(OUT) or '.',exist_ok=True)
with open(OUT,'w',encoding='utf-8') as f: f.write('\n'.join(svg))
print(f"Generated {OUT}: contributions={contributions}, commits={commits}, longest_streak={longest}, current_streak={current}, languages={len(languages)}")
