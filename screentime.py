"""Screen Time Diary - core logic.

Pure standard library (matplotlib is optional and imported lazily).
Used by both the terminal app (cli.py) and the FastHTML web app (web.py).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

# --------------------------------------------------------------------------
# Constants / domain rules
# --------------------------------------------------------------------------
CATEGORIES = ["Social", "Entertainment", "Productivity", "Education",
              "Games", "Communication", "Other"]
DEVICES = ["Phone", "Laptop", "Tablet", "Desktop", "TV"]

DAILY_LIMIT_MIN = 240        # recommended max screen time per day
WARN_RATIO = 0.8             # warn at 80% of the limit
MAX_ENTRY_MIN = 1440         # one entry cannot exceed 24h
ANOMALY_ENTRY_MIN = 480      # single entries >= 8h are flagged as anomalous
FIELDS = ["id", "date", "app", "category", "device", "minutes", "notes"]
REQUIRED_IMPORT_COLUMNS = ["date", "app", "category", "device", "minutes"]

APP_PATTERN = re.compile(r"^[\w .+\-&'#/]+$")


class ValidationError(ValueError):
    """Raised when user-supplied data fails validation."""


# --------------------------------------------------------------------------
# Validation helpers (shared by CLI, web and CSV import)
# --------------------------------------------------------------------------
def parse_duration(text) -> int:
    """Accepts '90', '90m', '1h30m', '1h 30m', '1.5h', '1:30'. Returns minutes."""
    s = str(text if text is not None else "").strip().lower()
    if not s:
        raise ValidationError("Duration is required (e.g. 90, 1h30m, 1.5h).")
    m = None
    if re.fullmatch(r"\d+", s):
        m = int(s)
    elif re.fullmatch(r"\d+(\.\d+)?\s*h(ours?|rs?)?", s):
        m = round(float(re.match(r"\d+(\.\d+)?", s).group()) * 60)
    elif re.fullmatch(r"\d+:[0-5]\d", s):
        h, mm = s.split(":")
        m = int(h) * 60 + int(mm)
    else:
        mt = re.fullmatch(
            r"(?:(\d+)\s*h(?:ours?|rs?)?)?\s*(?:(\d+)\s*m(?:in(?:ute)?s?)?)?", s)
        if mt and (mt.group(1) or mt.group(2)):
            m = int(mt.group(1) or 0) * 60 + int(mt.group(2) or 0)
    if m is None:
        raise ValidationError(f"'{text}' is not a valid duration. Try 90, 1h30m or 1.5h.")
    if m < 1:
        raise ValidationError("Duration must be at least 1 minute.")
    if m > MAX_ENTRY_MIN:
        raise ValidationError(f"Duration cannot exceed {MAX_ENTRY_MIN} minutes (24h).")
    return m


def parse_date(text) -> str:
    s = str(text if text is not None else "").strip()
    if not s:
        raise ValidationError("Date is required (YYYY-MM-DD).")
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"'{s}' is not a valid date. Use YYYY-MM-DD.") from None
    if d > date.today():
        raise ValidationError("Date cannot be in the future.")
    if d.year < 2000:
        raise ValidationError("Date is too far in the past (before 2000).")
    return d.isoformat()


def clean_app(text) -> str:
    s = re.sub(r"\s+", " ", str(text if text is not None else "")).strip()
    if not s:
        raise ValidationError("App / device name is required.")
    if len(s) > 40:
        raise ValidationError("App name must be 40 characters or fewer.")
    if not APP_PATTERN.match(s):
        raise ValidationError("App name contains unsupported characters.")
    return s


def clean_choice(text, options: list[str], label: str) -> str:
    s = str(text if text is not None else "").strip().lower()
    for opt in options:
        if opt.lower() == s:
            return opt
    raise ValidationError(f"{label} must be one of: {', '.join(options)}.")


def clean_notes(text) -> str:
    s = re.sub(r"\s+", " ", str(text if text is not None else "")).strip()
    if len(s) > 120:
        raise ValidationError("Notes must be 120 characters or fewer.")
    return s


def fmt_minutes(m: float) -> str:
    m = int(round(m))
    h, mm = divmod(m, 60)
    return f"{h}h {mm:02d}m" if h else f"{mm}m"


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class Entry:
    id: str
    date: str
    app: str
    category: str
    device: str
    minutes: int
    notes: str = ""

    def to_row(self) -> dict:
        return asdict(self)


def make_entry(day, app, category, device, minutes, notes="", entry_id=None) -> Entry:
    """Validate raw values and build an Entry (raises ValidationError)."""
    return Entry(
        id=entry_id or uuid.uuid4().hex[:8],
        date=parse_date(day),
        app=clean_app(app),
        category=clean_choice(category, CATEGORIES, "Category"),
        device=clean_choice(device, DEVICES, "Device"),
        minutes=parse_duration(minutes),
        notes=clean_notes(notes),
    )


# --------------------------------------------------------------------------
# Analytics
# --------------------------------------------------------------------------
def day_status(minutes: float) -> str:
    if minutes > DAILY_LIMIT_MIN:
        return "OVER"
    if minutes >= DAILY_LIMIT_MIN * WARN_RATIO:
        return "WARN"
    return "OK"


def daily_totals(entries) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for e in entries:
        totals[e.date] += e.minutes
    return dict(sorted(totals.items()))


def _group(entries, attr) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for e in entries:
        out[getattr(e, attr)] += e.minutes
    return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))


def compute_trend(daily: dict[str, int]) -> tuple[str, float]:
    """Compare average of the latest 7 days with the 7 days before."""
    if len(daily) < 4:
        return "not enough data", 0.0
    last = date.fromisoformat(max(daily))
    cur_lo, prev_lo = last - timedelta(days=6), last - timedelta(days=13)
    cur = [v for d, v in daily.items() if cur_lo <= date.fromisoformat(d) <= last]
    prev = [v for d, v in daily.items() if prev_lo <= date.fromisoformat(d) < cur_lo]
    if not cur or not prev:
        return "not enough data", 0.0
    pct = (mean(cur) - mean(prev)) / mean(prev) * 100
    label = "rising" if pct > 10 else "falling" if pct < -10 else "steady"
    return label, pct


def summarize(entries) -> dict:
    entries = list(entries)
    daily = daily_totals(entries)
    total = sum(daily.values())
    by_app, by_cat, by_dev = (_group(entries, a) for a in ("app", "category", "device"))
    busiest = max(daily.items(), key=lambda kv: kv[1]) if daily else None
    trend_label, trend_pct = compute_trend(daily)
    statuses = {d: day_status(v) for d, v in daily.items()}
    return {
        "entries": len(entries),
        "days": len(daily),
        "total": total,
        "avg_per_day": total / len(daily) if daily else 0,
        "avg_per_entry": total / len(entries) if entries else 0,
        "busiest_day": busiest,
        "top_app": next(iter(by_app.items()), None),
        "top_category": next(iter(by_cat.items()), None),
        "by_app": by_app, "by_category": by_cat, "by_device": by_dev,
        "daily": daily, "statuses": statuses,
        "days_over": sum(1 for s in statuses.values() if s == "OVER"),
        "days_warn": sum(1 for s in statuses.values() if s == "WARN"),
        "trend": trend_label, "trend_pct": trend_pct,
    }


def find_warnings(entries) -> list[str]:
    """Threshold warnings: days over the limit and anomalous single entries."""
    entries = list(entries)
    msgs = []
    for d, v in daily_totals(entries).items():
        if v > DAILY_LIMIT_MIN:
            msgs.append(f"{d}: {fmt_minutes(v)} exceeds the daily limit of "
                        f"{fmt_minutes(DAILY_LIMIT_MIN)} (+{fmt_minutes(v - DAILY_LIMIT_MIN)}).")
    for e in entries:
        if e.minutes >= ANOMALY_ENTRY_MIN:
            msgs.append(f"{e.date}: anomalous entry - {e.app} on {e.device} "
                        f"for {fmt_minutes(e.minutes)} [{e.id}].")
    return msgs


# --------------------------------------------------------------------------
# Persistence (JSON, atomic writes, corruption-tolerant)
# --------------------------------------------------------------------------
class Diary:
    def __init__(self, path: str | os.PathLike = "diary.json"):
        self.path = Path(path)
        self.entries: list[Entry] = []
        self.load_warning: str | None = None
        self.load()

    # -- load / save --------------------------------------------------
    def load(self) -> None:
        self.load_warning = None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.entries = []
            self.save()                       # create clean template
            return
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            self._quarantine("Data file was unreadable")
            return
        items = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            self._quarantine("Data file had an unexpected structure")
            return
        loaded, skipped = [], 0
        for it in items:
            try:
                loaded.append(make_entry(it["date"], it["app"], it["category"],
                                         it["device"], it["minutes"],
                                         it.get("notes", ""), it.get("id")))
            except (KeyError, TypeError, ValidationError):
                skipped += 1
        self.entries = loaded
        if skipped:
            self.load_warning = f"Skipped {skipped} invalid record(s) while loading."

    def _quarantine(self, reason: str) -> None:
        backup = self.path.with_suffix(f".corrupt-{datetime.now():%Y%m%d-%H%M%S}.json")
        try:
            self.path.replace(backup)
            self.load_warning = f"{reason}. Backed up to {backup.name}; started a fresh diary."
        except OSError:
            self.load_warning = f"{reason}. Started a fresh diary."
        self.entries = []
        self.save()

    def save(self) -> None:
        payload = {"version": 1, "entries": [e.to_row() for e in self.entries]}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # -- mutations ----------------------------------------------------
    def add(self, entry: Entry) -> Entry:
        self.entries.append(entry)
        self.save()
        return entry

    def add_many(self, entries: list[Entry]) -> None:
        self.entries.extend(entries)
        self.save()

    def delete(self, entry_id: str) -> Entry | None:
        """Delete by full id or unique prefix. Returns the removed entry."""
        entry_id = entry_id.strip().lower()
        if not entry_id:
            return None
        hits = [e for e in self.entries if e.id.lower().startswith(entry_id)]
        if len(hits) != 1:
            return None
        self.entries.remove(hits[0])
        self.save()
        return hits[0]

    # -- queries ------------------------------------------------------
    def sorted_entries(self) -> list[Entry]:
        return sorted(self.entries, key=lambda e: (e.date, e.id), reverse=True)

    def search(self, keyword: str = "", category: str = "", device: str = "",
               start: str = "", end: str = "") -> list[Entry]:
        kw = (keyword or "").strip().lower()
        out = []
        for e in self.sorted_entries():
            if kw and kw not in e.app.lower() and kw not in e.notes.lower():
                continue
            if category and e.category.lower() != category.lower():
                continue
            if device and e.device.lower() != device.lower():
                continue
            if start and e.date < start:
                continue
            if end and e.date > end:
                continue
            out.append(e)
        return out


# --------------------------------------------------------------------------
# Bulk CSV import with row-by-row error log
# --------------------------------------------------------------------------
@dataclass
class ImportResult:
    total_rows: int = 0
    added: int = 0
    duplicates: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def import_csv_text(diary: Diary, text: str) -> ImportResult:
    res = ImportResult()
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames:
        res.errors.append("File is empty or has no header row.")
        return res
    reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]
    missing = [c for c in REQUIRED_IMPORT_COLUMNS if c not in reader.fieldnames]
    if missing:
        res.errors.append(f"Missing required column(s): {', '.join(missing)}.")
        return res
    seen = {(e.date, e.app.lower(), e.device, e.minutes) for e in diary.entries}
    new: list[Entry] = []
    for n, row in enumerate(reader, start=2):      # row 1 is the header
        res.total_rows += 1
        try:
            e = make_entry(row.get("date"), row.get("app"), row.get("category"),
                           row.get("device"), row.get("minutes"), row.get("notes") or "")
        except ValidationError as exc:
            res.errors.append(f"Row {n}: {exc}")
            continue
        key = (e.date, e.app.lower(), e.device, e.minutes)
        if key in seen:
            res.duplicates += 1
            continue
        seen.add(key)
        new.append(e)
    if new:
        diary.add_many(new)
    res.added = len(new)
    return res


def import_csv(diary: Diary, path: str, error_log: str | None = None) -> ImportResult:
    text = Path(path).read_text(encoding="utf-8-sig")
    res = import_csv_text(diary, text)
    if error_log and res.errors:
        Path(error_log).write_text("\n".join(res.errors) + "\n", encoding="utf-8")
    return res


# --------------------------------------------------------------------------
# Reports / export
# --------------------------------------------------------------------------
def to_csv_text(entries) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader()
    for e in sorted(entries, key=lambda x: (x.date, x.id)):
        w.writerow(e.to_row())
    return buf.getvalue()


def build_text(entries) -> str:
    s = summarize(entries)
    L = ["SCREEN TIME DIARY - SUMMARY REPORT",
         f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "=" * 46,
         f"Entries            : {s['entries']}",
         f"Days logged        : {s['days']}",
         f"Total screen time  : {fmt_minutes(s['total'])}",
         f"Average per day    : {fmt_minutes(s['avg_per_day'])}",
         f"Daily limit        : {fmt_minutes(DAILY_LIMIT_MIN)}",
         f"Days over limit    : {s['days_over']}   (near limit: {s['days_warn']})"]
    if s["busiest_day"]:
        L.append(f"Busiest day        : {s['busiest_day'][0]} ({fmt_minutes(s['busiest_day'][1])})")
    if s["top_app"]:
        L.append(f"Top app            : {s['top_app'][0]} ({fmt_minutes(s['top_app'][1])})")
    L.append(f"Trend (7d vs prev) : {s['trend']} ({s['trend_pct']:+.0f}%)")
    for title, key in (("BY CATEGORY", "by_category"), ("BY DEVICE", "by_device")):
        L += ["", title, "-" * 46]
        for k, v in s[key].items():
            L.append(f"{k:<18}{fmt_minutes(v):>10}  {v / s['total'] * 100:5.1f}%")
    L += ["", "DAILY TOTALS", "-" * 46]
    for d, v in s["daily"].items():
        L.append(f"{d}  {fmt_minutes(v):>8}  {s['statuses'][d]}")
    warns = find_warnings(entries)
    if warns:
        L += ["", "WARNINGS", "-" * 46] + warns
    return "\n".join(L) + "\n"


def build_markdown(entries) -> str:
    s = summarize(entries)
    L = ["# Screen Time Diary - Summary Report", "",
         f"_Generated {datetime.now():%Y-%m-%d %H:%M}_", "",
         "## Key metrics", "",
         "| Metric | Value |", "|---|---|",
         f"| Entries | {s['entries']} |",
         f"| Days logged | {s['days']} |",
         f"| Total screen time | {fmt_minutes(s['total'])} |",
         f"| Average per day | {fmt_minutes(s['avg_per_day'])} |",
         f"| Days over {fmt_minutes(DAILY_LIMIT_MIN)} limit | {s['days_over']} |",
         f"| Trend (last 7d vs previous 7d) | {s['trend']} ({s['trend_pct']:+.0f}%) |"]
    if s["top_app"]:
        L.append(f"| Top app | {s['top_app'][0]} ({fmt_minutes(s['top_app'][1])}) |")
    for title, key in (("By category", "by_category"), ("By device", "by_device")):
        L += ["", f"## {title}", "", "| Name | Time | Share |", "|---|---|---|"]
        for k, v in s[key].items():
            L.append(f"| {k} | {fmt_minutes(v)} | {v / s['total'] * 100:.1f}% |")
    L += ["", "## Daily totals", "", "| Date | Time | Status |", "|---|---|---|"]
    for d, v in s["daily"].items():
        L.append(f"| {d} | {fmt_minutes(v)} | {s['statuses'][d]} |")
    warns = find_warnings(entries)
    if warns:
        L += ["", "## Warnings", ""] + [f"- {w}" for w in warns]
    return "\n".join(L) + "\n"


def export_report(entries, fmt: str, path: str | None = None) -> str:
    """fmt in {'md','txt','csv'}. Returns the path written."""
    builders = {"md": build_markdown, "txt": build_text, "csv": to_csv_text}
    if fmt not in builders:
        raise ValidationError("Format must be md, txt or csv.")
    path = path or f"screen_time_report_{datetime.now():%Y%m%d_%H%M%S}.{fmt}"
    Path(path).write_text(builders[fmt](list(entries)), encoding="utf-8", newline="")
    return path


# --------------------------------------------------------------------------
# Charts (matplotlib, optional)
# --------------------------------------------------------------------------
class ChartUnavailable(RuntimeError):
    """matplotlib is not installed."""


def render_chart(kind: str, entries) -> bytes:
    """kind: 'trend' or 'distribution'. Returns PNG bytes."""
    try:
        from matplotlib.figure import Figure
    except ImportError as exc:
        raise ChartUnavailable("matplotlib is not installed (pip install matplotlib).") from exc

    s = summarize(entries)
    buf = io.BytesIO()

    if kind == "trend":
        fig = Figure(figsize=(8, 3.6), dpi=110)
        ax = fig.subplots()
        if not s["daily"]:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center")
            ax.set_axis_off()
        else:
            days = list(s["daily"])
            vals = [s["daily"][d] / 60 for d in days]
            xs = [date.fromisoformat(d) for d in days]
            colors = {"OK": "#4c9a6a", "WARN": "#e0a030", "OVER": "#d1495b"}
            ax.bar(xs, vals, color=[colors[s["statuses"][d]] for d in days], width=0.7)
            if len(vals) >= 3:
                ma = [mean(vals[max(0, i - 2): i + 1]) for i in range(len(vals))]
                ax.plot(xs, ma, color="#264653", marker="o", ms=3, lw=1.5, label="3-day average")
            ax.axhline(DAILY_LIMIT_MIN / 60, color="#d1495b", ls="--", lw=1,
                       label=f"Limit ({DAILY_LIMIT_MIN // 60}h)")
            ax.set_ylabel("Hours")
            ax.set_title("Daily screen time")
            ax.legend(loc="upper left", fontsize=8)
            fig.autofmt_xdate()
        fig.tight_layout()
    else:
        fig = Figure(figsize=(9, 3.8), dpi=110)
        a1, a2 = fig.subplots(1, 2)
        if not s["entries"]:
            for a in (a1, a2):
                a.text(0.5, 0.5, "No data yet", ha="center", va="center")
                a.set_axis_off()
        else:
            cats = s["by_category"]
            tot = sum(cats.values())
            wedges, _ = a1.pie(list(cats.values()), startangle=90, counterclock=False)
            a1.legend(wedges, [f"{k} ({v / tot * 100:.0f}%)" for k, v in cats.items()],
                      loc="center left", bbox_to_anchor=(0.95, 0.5), fontsize=8, frameon=False)
            a1.set_title("Time by category")
            top = list(s["by_app"].items())[:8][::-1]
            a2.barh([k for k, _ in top], [v / 60 for _, v in top], color="#2a9d8f")
            a2.set_xlabel("Hours")
            a2.set_title("Top apps")
        fig.tight_layout()

    fig.savefig(buf, format="png")
    return buf.getvalue()


def save_chart(kind: str, entries, path: str) -> str:
    Path(path).write_bytes(render_chart(kind, entries))
    return path
