# Screen Time Diary

Log time spent on apps and devices, validate it, and get daily totals, summaries, warnings and charts.
Two interfaces share one core module and one data file (`diary.json`).

| File | Purpose |
|---|---|
| `screentime.py` | Core logic: validation, JSON persistence, search, summaries, CSV import, exports, matplotlib charts |
| `cli.py` | Menu-driven terminal app |
| `web.py` | FastHTML web interface |
| `seed_data.py` | Creates 48 sample entries (JSON + CSV) and a messy CSV for the import demo |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed_data.py              # optional: load sample data
```

## Run

```bash
python cli.py        # terminal app
python web.py        # web app at http://localhost:5001
```

`matplotlib` is optional: without it everything works except chart images.

## Demo script

1. Launch `python cli.py` and show the banner and menu.
2. **1 – Log new entry**: type `abc` or `9999` for time, then a bad date to show validation; finish with `1h30m`.
3. **5 – Executive summary** and **4 – Daily totals** (status OK / WARN / OVER, trend, top apps).
4. **w – warnings**: days over the 4h limit and the 10h / 8h anomalous entries.
5. Exit and relaunch to show persistence. Then **6** for charts and **7** for a Markdown report.
6. **8 – Import CSV** with `sample_import_with_errors.csv`: 2 rows import, 6 are logged to `import_errors.log`.
7. Run `python web.py` and repeat the add / search / delete / chart flow in the browser.

## Validation rules

- Date: `YYYY-MM-DD`, not in the future.
- Time: `90`, `90m`, `1h30m`, `1.5h`, `1:30`; 1 to 1440 minutes.
- App: 1–40 characters, letters, digits and basic punctuation.
- Category and device must come from fixed lists. Notes up to 120 characters.

## Configuration

Edit constants at the top of `screentime.py`: `DAILY_LIMIT_MIN` (default 240), `ANOMALY_ENTRY_MIN` (default 480), `CATEGORIES`, `DEVICES`.
Set `DIARY_FILE=other.json` to point the web app at a different data file.

## Robustness

- Missing data file: a clean one is created.
- Corrupted or malformed JSON: the file is renamed to `diary.corrupt-<timestamp>.json` and a fresh diary starts.
- Invalid individual records are skipped on load with a warning.
- Saves are atomic (write to temp file, then replace).
