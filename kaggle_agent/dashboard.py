"""Local progress page: .kaggle-agent/views/dashboard.html (reloads every 30 s).

Rebuilt after every run, registration and submission, and by `ka dash`. It only
reads the database, so opening it can never change anything.
"""
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import statistics

from kaggle_agent.storage.export_state import atomic_write

CSS = """
:root{--bg:#fafaf8;--card:#fff;--text:#1f1f1e;--muted:#6b6a66;--line:#e6e4dd;--soft:#f1efe8;--good:#0f6e56;--bad:#a32d2d;--accent:#185fa5}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--card:#232322;--text:#ecebe6;--muted:#a3a29c;--line:#3a3a38;--soft:#2c2c2a;--good:#5dcaa5;--bad:#f09595;--accent:#85b7eb}}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:24px}
h1{font-size:20px;font-weight:600;margin:0}.sub{color:var(--muted);font-size:13px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px}
.pill{padding:4px 10px;border-radius:8px;font-size:12px;background:var(--soft)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:16px}
.card{background:var(--soft);border-radius:8px;padding:10px 12px}.card b{display:block;font-size:22px;font-weight:600}
.card span{font-size:12px;color:var(--muted)}.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:14px}
table{width:100%;border-collapse:collapse}td{padding:6px 4px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}.r{text-align:right;white-space:nowrap}.good{color:var(--good)}.bad{color:var(--bad)}.muted{color:var(--muted)}
.label{font-size:13px;color:var(--muted);margin-bottom:6px}
@media (max-width:700px){.grid{grid-template-columns:1fr}}
"""


def e(text):
    return html.escape(str(text if text is not None else ""))


def chart(points, champion_line, maximize):
    if not points:
        return '<p class="muted">No full runs yet.</p>'
    w, h, pad = 900, 170, 40
    values = [v for _, v in points]
    lo, hi = min(values), max(values)
    if hi == lo:
        lo, hi = lo - 1e-6, hi + 1e-6
    x = lambda i: pad + i * (w - pad - 10) / max(1, len(points) - 1)
    y = lambda v: 10 + (h - 30) * ((hi - v) / (hi - lo) if maximize else (v - lo) / (hi - lo))
    steps = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(champion_line))
    dots = "".join(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="var(--accent)"><title>{e(label)}: {v:.6g}</title></circle>'
                   for i, (label, v) in enumerate(points))
    best, worst = (hi, lo) if maximize else (lo, hi)
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="CV score per full run">'
            f'<line x1="{pad}" y1="{h-20}" x2="{w}" y2="{h-20}" stroke="var(--line)"/>'
            f'<text x="0" y="16" font-size="11" fill="var(--muted)">{best:.5g}</text>'
            f'<text x="0" y="{h-22}" font-size="11" fill="var(--muted)">{worst:.5g}</text>'
            f'<polyline fill="none" stroke="var(--good)" stroke-width="2" points="{steps}"/>{dots}</svg>')


def build(store, competition, directory, profile):
    from kaggle_agent import submit as submissions
    comp = store.rows("SELECT * FROM competitions WHERE id=?", (competition,))[0]
    maximize = profile.get("direction") == "maximize"
    sign = 1 if maximize else -1
    full = store.rows("SELECT id,state,metadata,result,created,campaign FROM experiments WHERE competition=? AND fidelity='full' ORDER BY created", (competition,))
    points, line, best = [], [], None
    for row in full:
        if row["state"] != "COMPLETED" or not row["result"]:
            continue
        value = statistics.mean(json.loads(row["result"])["fold_scores"])
        points.append((json.loads(row["metadata"]).get("hypothesis", row["id"][:8]), value))
        best = value if best is None or sign * value > sign * best else best
        line.append(best)
    today = datetime.now(timezone.utc).date().isoformat()
    sessions = store.rows("SELECT state FROM agent_sessions WHERE competition=? AND substr(created,1,10)=?", (competition, today))
    limits_hit = sum(s["state"] == "waiting_limit" for s in sessions)
    quota = submissions.quota(store, competition, directory)
    sub_settings = submissions.settings(directory)
    subs = submissions.history(store, competition, 8)
    scored = [s for s in subs if s["public_score"] is not None]
    target = profile.get("target_score")
    recent = store.rows("SELECT id,state,fidelity,metadata,result,failure_reason FROM experiments WHERE competition=? AND fidelity='full' ORDER BY created DESC LIMIT 10", (competition,))
    rows = []
    for r in recent:
        meta = json.loads(r["metadata"])
        result = json.loads(r["result"]) if r["result"] else {}
        name = meta.get("hypothesis", "")[:90]
        if r["state"] != "COMPLETED":
            rows.append(f'<tr><td>{e(name)}</td><td class="r bad">{e(r["state"].lower())}: {e((r["failure_reason"] or "")[:60])}</td></tr>')
            continue
        value = statistics.mean(result["fold_scores"])
        tag = "champion" if r["id"] in (comp["champion"], comp["ensemble_champion"]) else (
            "new best then" if result.get("standalone_improved") or result.get("ensemble_improved") else "no gain")
        cls = "good" if tag != "no gain" else "muted"
        rows.append(f'<tr><td>{e(name)}</td><td class="r {cls}">{value:.6g} · {tag}</td></tr>')
    branches = store.rows("SELECT name,status,details FROM research_branches WHERE competition=? ORDER BY updated DESC", (competition,))
    branch_rows = "".join(
        f'<tr><td>{e(b["name"])}</td><td class="r muted">{"parked" if b["status"] != "active" else str(json.loads(b["details"]).get("wins", 0)) + " wins / " + str(json.loads(b["details"])["trials"])}</td></tr>'
        for b in branches) or '<tr><td class="muted">none yet</td></tr>'
    sub_rows = "".join(
        f'<tr><td>{e(s["created"][:16].replace("T", " "))} {"auto" if s["auto"] else "manual"}</td>'
        f'<td class="r {"bad" if s["status"] == "failed" else ""}">cv {s["cv"]:.6g} · {"public " + format(s["public_score"], ".6g") if s["public_score"] is not None else s["status"]}</td></tr>'
        for s in subs) or '<tr><td class="muted">none yet</td></tr>'
    lessons = store.rows("SELECT count(*) AS n FROM discoveries WHERE competition=?", (competition,))[0]["n"]
    deadline = profile.get("deadline")
    days = None
    if deadline:
        try:
            days = (datetime.fromisoformat(deadline) - datetime.now(timezone.utc)).days
        except ValueError:
            days = None
    state = comp["state"]
    state_cls = "good" if state in {"RUNNING", "COMPLETED", "PENDING", "EVALUATING", "TESTING"} else "bad"
    title = sub_settings["slug"] or Path(directory).name
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} · progress</title><style>{CSS}</style></head><body><main>
<div class="top"><div><h1>{e(title)}</h1><div class="sub">{e(profile['task'])} · {e(profile['metric'])} ({'higher' if maximize else 'lower'} is better) · {e(profile.get('validation',''))}{f' · deadline in {days} days' if days is not None else ''}</div></div>
<span class="pill {state_cls}">{e(state.lower())}</span></div>
<div class="cards">
<div class="card"><span>Best CV</span><b>{f'{best:.6g}' if best is not None else '–'}</b><span>{len(points)} full runs</span></div>
<div class="card"><span>Public LB (last)</span><b>{f"{scored[0]['public_score']:.6g}" if scored else '–'}</b><span>{f'top public {target}' if target is not None else 'for reference only'}</span></div>
<div class="card"><span>Submissions today</span><b>{quota['used_today']} / {quota['limit']}</b><span>auto-submit {'on' if sub_settings['auto'] else 'off'}</span></div>
<div class="card"><span>Agent sessions today</span><b>{len(sessions)}</b><span>{f'{limits_hit} usage-limit stops' if limits_hit else 'no limit stops'}</span></div>
</div>
<div class="box"><div class="label">CV score per full run · line = best so far</div>{chart(points, line, maximize)}</div>
<div class="grid"><div class="box"><div class="label">Recent runs</div><table>{''.join(rows) or '<tr><td class="muted">none yet</td></tr>'}</table></div>
<div><div class="box"><div class="label">Research branches · lessons saved: {lessons}</div><table>{branch_rows}</table></div>
<div class="box"><div class="label">Submissions</div><table>{sub_rows}</table></div></div></div>
<p class="sub">Updated {e(datetime.now().strftime('%Y-%m-%d %H:%M'))} · refreshes every 30 s · decisions use CV only</p>
</main></body></html>"""
    path = Path(directory) / ".kaggle-agent" / "views" / "dashboard.html"
    atomic_write(path, page)
    return path
