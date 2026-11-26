"""Screen Time Diary - interactive terminal app.  Run:  python cli.py"""
from __future__ import annotations

import sys
from datetime import date

import screentime as st

# ---- ANSI helpers (disabled automatically if not a terminal) -----------
USE_COLOR = sys.stdout.isatty()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def red(t): return c(t, "31")
def green(t): return c(t, "32")
def yellow(t): return c(t, "33")
def cyan(t): return c(t, "36")
def bold(t): return c(t, "1")


BANNER = r"""
  ____                           _____ _                 ____  _
 / ___|  ___ _ __ ___  ___ _ __ |_   _(_)_ __ ___   ___|  _ \(_) __ _ _ __ _   _
 \___ \ / __| '__/ _ \/ _ \ '_ \  | | | | '_ ` _ \ / _ \ | | | |/ _` | '__| | | |
  ___) | (__| | |  __/  __/ | | | | | | | | | | | |  __/ |_| | | (_| | |  | |_| |
 |____/ \___|_|  \___|\___|_| |_| |_| |_|_| |_| |_|\___|____/|_|\__,_|_|   \__, |
                                                                           |___/
"""

STATUS_COLOR = {"OK": green, "WARN": yellow, "OVER": red}


# ---- Centralised input wrappers: loop until valid ----------------------
def ask(prompt: str, validator, default: str | None = None):
    hint = f" [{default}]" if default else ""
    while True:
        raw = input(f"{prompt}{hint}: ").strip()
        if not raw and default is not None:
            raw = default
        try:
            return validator(raw)
        except st.ValidationError as exc:
            print(red(f"  x {exc}"))


def ask_choice(prompt: str, options: list[str], allow_blank: bool = False) -> str:
    print(f"{prompt}:")
    for i, o in enumerate(options, 1):
        print(f"  {i}. {o}")
    while True:
        raw = input("  Choose number or name" + (" (Enter = any)" if allow_blank else "") + ": ").strip()
        if not raw and allow_blank:
            return ""
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        try:
            return st.clean_choice(raw, options, prompt)
        except st.ValidationError as exc:
            print(red(f"  x {exc}"))


def ask_optional_date(prompt: str) -> str:
    def v(raw):
        return "" if not raw else st.parse_date(raw)
    return ask(prompt + " (YYYY-MM-DD, Enter to skip)", v, default="")


# ---- Presentation -------------------------------------------------------
def table(entries, page_size: int = 10) -> None:
    if not entries:
        print(yellow("No entries found."))
        return
    head = f"{'ID':<9}{'Date':<12}{'App':<20}{'Category':<15}{'Device':<9}{'Time':>8}  Notes"
    total_pages = (len(entries) + page_size - 1) // page_size
    for p in range(total_pages):
        print(bold(head))
        print("-" * 90)
        for e in entries[p * page_size:(p + 1) * page_size]:
            flag = red(" !") if e.minutes >= st.ANOMALY_ENTRY_MIN else ""
            print(f"{e.id:<9}{e.date:<12}{e.app[:19]:<20}{e.category:<15}{e.device:<9}"
                  f"{st.fmt_minutes(e.minutes):>8}  {e.notes[:28]}{flag}")
        print(f"\nPage {p + 1}/{total_pages}  ({len(entries)} entries)")
        if p < total_pages - 1:
            if input("Enter = next page, q = stop: ").strip().lower() == "q":
                break


def bar(value, maximum, width=28):
    n = int(round(width * value / maximum)) if maximum else 0
    return "#" * n


def show_warnings(entries) -> None:
    warns = st.find_warnings(entries)
    if not warns:
        print(green("No threshold warnings."))
        return
    print(bold(red(f"{len(warns)} warning(s):")))
    for w in warns[-15:]:
        print(yellow("  ! " + w))
    if len(warns) > 15:
        print(f"  ... {len(warns) - 15} older warning(s) hidden. Export a report to see all.")


# ---- Actions -------------------------------------------------------------
def action_add(diary: st.Diary) -> None:
    print(bold("\nLog new screen time"))
    day = ask("Date (YYYY-MM-DD)", st.parse_date, default=date.today().isoformat())
    app = ask("App / activity name", st.clean_app)
    category = ask_choice("Category", st.CATEGORIES)
    device = ask_choice("Device", st.DEVICES)
    minutes = ask("Time spent (90, 1h30m, 1.5h, 1:30)", st.parse_duration)
    notes = ask("Notes (optional)", st.clean_notes, default="")
    e = diary.add(st.make_entry(day, app, category, device, minutes, notes))
    print(green(f"Saved [{e.id}] {e.app} - {st.fmt_minutes(e.minutes)} on {e.date}"))
    total = st.daily_totals(diary.entries)[e.date]
    status = st.day_status(total)
    print(f"Total for {e.date}: {STATUS_COLOR[status](st.fmt_minutes(total))} [{status}]")
    if e.minutes >= st.ANOMALY_ENTRY_MIN:
        print(yellow("  ! Anomalous entry: 8+ hours in a single session."))


def action_search(diary: st.Diary) -> None:
    print(bold("\nSearch / filter (leave blank to skip a filter)"))
    kw = input("Keyword (app or notes): ").strip()
    cat = ask_choice("Category", st.CATEGORIES, allow_blank=True)
    dev = ask_choice("Device", st.DEVICES, allow_blank=True)
    start = ask_optional_date("From")
    end = ask_optional_date("To")
    table(diary.search(kw, cat, dev, start, end))


def action_daily(diary: st.Diary) -> None:
    daily = st.daily_totals(diary.entries)
    if not daily:
        print(yellow("No data yet."))
        return
    mx = max(max(daily.values()), st.DAILY_LIMIT_MIN)
    print(bold(f"\n{'Date':<12}{'Total':>8}  {'Status':<6} Chart (limit {st.fmt_minutes(st.DAILY_LIMIT_MIN)})"))
    for d in list(daily)[-21:]:
        v = daily[d]
        s = st.day_status(v)
        print(f"{d:<12}{st.fmt_minutes(v):>8}  {STATUS_COLOR[s](f'{s:<6}')} {bar(v, mx)}")


def action_summary(diary: st.Diary) -> None:
    s = st.summarize(diary.entries)
    if not s["entries"]:
        print(yellow("No data yet."))
        return
    print(bold("\n=== Executive Summary ==="))
    print(f"Entries: {s['entries']}   Days logged: {s['days']}")
    print(f"Total: {st.fmt_minutes(s['total'])}   Avg/day: {st.fmt_minutes(s['avg_per_day'])}"
          f"   Avg/entry: {st.fmt_minutes(s['avg_per_entry'])}")
    d, v = s["busiest_day"]
    print(f"Busiest day: {d} ({st.fmt_minutes(v)})")
    print(f"Top app: {s['top_app'][0]} ({st.fmt_minutes(s['top_app'][1])})   "
          f"Top category: {s['top_category'][0]}")
    arrow = {"rising": red("rising"), "falling": green("falling")}.get(s["trend"], s["trend"])
    print(f"Trend (last 7d vs previous 7d): {arrow} ({s['trend_pct']:+.0f}%)")
    print(f"Days over limit: {red(str(s['days_over']))}   near limit: {yellow(str(s['days_warn']))}")
    for title, key in (("By category", "by_category"), ("By device", "by_device")):
        print(bold(f"\n{title}"))
        mx = max(s[key].values())
        for k, val in s[key].items():
            print(f"  {k:<15}{st.fmt_minutes(val):>8} {val / s['total'] * 100:5.1f}%  {bar(val, mx, 20)}")
    print(bold("\nTop 5 apps"))
    for k, val in list(s["by_app"].items())[:5]:
        print(f"  {k:<20}{st.fmt_minutes(val):>8}")
    print()
    show_warnings(diary.entries)


def action_charts(diary: st.Diary) -> None:
    try:
        for kind in ("trend", "distribution"):
            print(green("Saved " + st.save_chart(kind, diary.entries, f"chart_{kind}.png")))
    except st.ChartUnavailable as exc:
        print(red(str(exc)))


def action_export(diary: st.Diary) -> None:
    fmt = ""
    while fmt not in ("md", "txt", "csv"):
        fmt = input("Format (md / txt / csv): ").strip().lower()
    print(green("Report written to " + st.export_report(diary.entries, fmt)))


def action_import(diary: st.Diary) -> None:
    path = input("CSV file path: ").strip().strip('"')
    try:
        res = st.import_csv(diary, path, error_log="import_errors.log")
    except (FileNotFoundError, UnicodeDecodeError, OSError) as exc:
        print(red(f"Cannot read file: {exc}"))
        return
    print(green(f"Imported {res.added} of {res.total_rows} rows") +
          f" ({res.duplicates} duplicate(s) skipped, {len(res.errors)} error(s)).")
    for line in res.errors[:10]:
        print(red("  " + line))
    if res.errors:
        print("Full error log: import_errors.log")


def action_delete(diary: st.Diary) -> None:
    eid = input("Entry ID (or unique prefix): ").strip()
    gone = diary.delete(eid)
    print(green(f"Deleted {gone.app} on {gone.date}.") if gone
          else red("No single entry matches that ID."))


MENU = [
    ("1", "Log new entry", action_add),
    ("2", "View all entries", lambda d: table(d.sorted_entries())),
    ("3", "Search / filter", action_search),
    ("4", "Daily totals", action_daily),
    ("5", "Executive summary", action_summary),
    ("6", "Save charts (PNG)", action_charts),
    ("7", "Export report (md/txt/csv)", action_export),
    ("8", "Import CSV", action_import),
    ("9", "Delete entry", action_delete),
    ("w", "Show warnings", lambda d: show_warnings(d.entries)),
    ("0", "Exit", None),
]


def main(path: str = "diary.json") -> None:
    diary = st.Diary(path)
    print(cyan(BANNER))
    print(bold("Screen Time Diary") + f" - {len(diary.entries)} entries loaded from {diary.path}")
    if diary.load_warning:
        print(yellow("Note: " + diary.load_warning))
    actions = {k: fn for k, _, fn in MENU}
    while True:
        print(bold("\nMENU"))
        for k, label, _ in MENU:
            print(f"  {k}. {label}")
        choice = input("Select: ").strip().lower()
        if choice == "0":
            print("Goodbye! Your data is saved.")
            return
        if choice not in actions:
            print(red("Please choose a number from the menu."))
            continue
        try:
            actions[choice](diary)
        except KeyboardInterrupt:
            print(yellow("\nCancelled."))


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "diary.json")
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
