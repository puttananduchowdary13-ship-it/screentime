"""Screen Time Diary - FastHTML web interface.

Run:  python web.py     then open http://localhost:5001
Uses the same diary.json and logic as the terminal app.
"""
import os
import time

from fasthtml.common import *

import screentime as st

diary = st.Diary(os.environ.get("DIARY_FILE", "diary.json"))

CSS = """
:root { --pico-font-size: 95%; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.75rem; margin-bottom:1rem; }
.card { border:1px solid var(--pico-muted-border-color); border-radius:10px; padding:.7rem 1rem; }
.card small { color:var(--pico-muted-color); display:block; }
.card b { font-size:1.35rem; }
.err { color:#d1495b; font-weight:600; }
.ok  { color:#2a9d8f; font-weight:600; }
.warnbox { border-left:4px solid #e0a030; background:rgba(224,160,48,.12); padding:.5rem 1rem; border-radius:6px; margin-bottom:1rem; }
.badge { padding:.05rem .5rem; border-radius:99px; font-size:.75rem; color:#fff; }
.b-OK{background:#4c9a6a} .b-WARN{background:#e0a030} .b-OVER{background:#d1495b}
.charts { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:1rem; }
.charts img { width:100%; border-radius:8px; border:1px solid var(--pico-muted-border-color); background:#fff; }
table { font-size:.9rem; } td button { padding:.1rem .5rem; margin:0; }
"""

app, rt = fast_app(hdrs=(Style(CSS),), pico=True)


# ------------------------------------------------------------------ views
def stat(label, value):
    return Div(Small(label), B(value), cls="card")


def entry_form(error=None, values=None):
    v = values or {}
    return Form(
        H3("Log screen time"),
        P(error, cls="err") if error else None,
        Grid(
            Label("Date", Input(type="date", name="day", required=True,
                                max=str(st.date.today()),
                                value=v.get("day", str(st.date.today())))),
            Label("App / activity", Input(name="app_name", required=True, maxlength="40",
                                          placeholder="e.g. YouTube", value=v.get("app_name", ""))),
            Label("Time spent", Input(name="minutes", required=True, placeholder="90, 1h30m, 1.5h",
                                      value=v.get("minutes", ""))),
        ),
        Grid(
            Label("Category", Select(*[Option(c, selected=(c == v.get("category"))) for c in st.CATEGORIES],
                                     name="category")),
            Label("Device", Select(*[Option(d, selected=(d == v.get("device"))) for d in st.DEVICES],
                                   name="device")),
            Label("Notes (optional)", Input(name="notes", maxlength="120", value=v.get("notes", ""))),
        ),
        Button("Log time", type="submit"),
        hx_post="/add", hx_target="#dash", hx_swap="outerHTML",
    )


def entries_table(entries, limit=50):
    rows = []
    for e in entries[:limit]:
        rows.append(Tr(
            Td(e.date), Td(e.app), Td(e.category), Td(e.device),
            Td(st.fmt_minutes(e.minutes) + (" ⚠" if e.minutes >= st.ANOMALY_ENTRY_MIN else "")),
            Td(e.notes),
            Td(Button("✕", cls="secondary outline", hx_delete=f"/entry/{e.id}",
                      hx_target="#dash", hx_swap="outerHTML",
                      hx_confirm=f"Delete {e.app} on {e.date}?")),
        ))
    body = Tbody(*rows) if rows else Tbody(Tr(Td("No entries found.", colspan="7")))
    more = P(f"Showing {limit} of {len(entries)} entries - refine your search to see more.") \
        if len(entries) > limit else None
    return Div(Table(Thead(Tr(*[Th(h) for h in ("Date", "App", "Category", "Device", "Time", "Notes", "")])),
                     body, cls="striped"), more, id="entries")


def filters():
    return Form(
        Grid(
            Input(name="q", type="search", placeholder="Search app or notes…"),
            Select(Option("All categories", value=""), *[Option(c) for c in st.CATEGORIES], name="category"),
            Select(Option("All devices", value=""), *[Option(d) for d in st.DEVICES], name="device"),
            Input(type="date", name="start", title="From"),
            Input(type="date", name="end", title="To"),
        ),
        id="filters", hx_get="/entries", hx_trigger="input delay:300ms, change",
        hx_target="#entries", hx_swap="outerHTML",
    )


def dashboard(flash=None, error=None, values=None):
    s = st.summarize(diary.entries)
    warns = st.find_warnings(diary.entries)
    v = int(time.time())
    trend_txt = f"{s['trend']} ({s['trend_pct']:+.0f}%)" if s["entries"] else "-"
    top = f"{s['top_app'][0]}" if s["top_app"] else "-"
    return Div(
        P(flash, cls="ok") if flash else None,
        Div(stat("Total time", st.fmt_minutes(s["total"])),
            stat("Avg / day", st.fmt_minutes(s["avg_per_day"])),
            stat("Days logged", str(s["days"])),
            stat("Days over limit", str(s["days_over"])),
            stat("Top app", top),
            stat("7-day trend", trend_txt), cls="stats"),
        Div(B(f"⚠ {len(warns)} warning(s)"),
            Ul(*[Li(w) for w in warns[-5:]]), cls="warnbox") if warns else None,
        Article(entry_form(error, values)),
        Div(Img(src=f"/chart/trend?v={v}", alt="Daily trend"),
            Img(src=f"/chart/distribution?v={v}", alt="Distribution"), cls="charts"),
        H3("Entries"),
        filters(),
        entries_table(diary.sorted_entries()),
        id="dash",
    )


def page():
    return (
        Title("Screen Time Diary"),
        Main(
            Hgroup(H1("📱 Screen Time Diary"),
                   P(f"Daily limit: {st.fmt_minutes(st.DAILY_LIMIT_MIN)} · data file: {diary.path}")),
            P(diary.load_warning, cls="err") if diary.load_warning else None,
            dashboard(),
            Details(
                Summary("Import & export"),
                Form(Input(type="file", name="file", accept=".csv", required=True),
                     Button("Import CSV", type="submit"),
                     hx_post="/import", hx_target="#dash", hx_swap="outerHTML",
                     hx_encoding="multipart/form-data"),
                P("Export: ", A("Markdown", href="/export/md"), " · ",
                  A("Text", href="/export/txt"), " · ", A("CSV", href="/export/csv")),
            ),
            cls="container",
        ),
    )


# ----------------------------------------------------------------- routes
@rt("/")
def get():
    return page()


@rt("/add")
def post(day: str = "", app_name: str = "", category: str = "", device: str = "",
         minutes: str = "", notes: str = ""):
    values = dict(day=day, app_name=app_name, category=category, device=device,
                  minutes=minutes, notes=notes)
    try:
        e = diary.add(st.make_entry(day, app_name, category, device, minutes, notes))
    except st.ValidationError as exc:
        return dashboard(error=str(exc), values=values)
    total = st.daily_totals(diary.entries)[e.date]
    msg = f"Saved {e.app} ({st.fmt_minutes(e.minutes)}). Total for {e.date}: " \
          f"{st.fmt_minutes(total)} [{st.day_status(total)}]"
    return dashboard(flash=msg)


@rt("/entries")
def get(q: str = "", category: str = "", device: str = "", start: str = "", end: str = ""):
    return entries_table(diary.search(q, category, device, start, end))


@rt("/entry/{eid}")
def delete(eid: str):
    gone = diary.delete(eid)
    return dashboard(flash=f"Deleted {gone.app} on {gone.date}." if gone else None)


@rt("/import")
async def post(file: UploadFile):
    try:
        text = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        return dashboard(error="That file is not valid UTF-8 text.")
    res = st.import_csv_text(diary, text)
    msg = f"Imported {res.added} of {res.total_rows} rows ({res.duplicates} duplicates skipped)."
    if res.errors:
        shown = " | ".join(res.errors[:5]) + (f" … +{len(res.errors) - 5} more" if len(res.errors) > 5 else "")
        return dashboard(flash=msg, error=f"{len(res.errors)} row error(s): {shown}")
    return dashboard(flash=msg)


@rt("/chart/{kind}")
def get(kind: str):
    if kind not in ("trend", "distribution"):
        return Response("Unknown chart", status_code=404)
    try:
        png = st.render_chart(kind, diary.entries)
    except st.ChartUnavailable as exc:
        return Response(str(exc), status_code=503)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@rt("/export/{fmt}")
def get(fmt: str):
    types = {"md": "text/markdown", "txt": "text/plain", "csv": "text/csv"}
    if fmt not in types:
        return Response("Unknown format", status_code=404)
    build = {"md": st.build_markdown, "txt": st.build_text, "csv": st.to_csv_text}[fmt]
    return Response(build(diary.entries), media_type=types[fmt] + "; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="screen_time_report.{fmt}"'})


serve()
