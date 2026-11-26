"""Generate sample data: diary.json, sample_entries.csv and sample_import_with_errors.csv.

Run:  python seed_data.py
Dates are relative to today so the charts and 7-day trend always look realistic.
"""
import json
import random
from datetime import date, timedelta

import screentime as st

random.seed(7)

APPS = [  # (app, category, device, typical minutes)
    ("Instagram", "Social", "Phone", 45), ("YouTube", "Entertainment", "Phone", 60),
    ("YouTube", "Entertainment", "TV", 90), ("WhatsApp", "Communication", "Phone", 30),
    ("VS Code", "Productivity", "Laptop", 120), ("Google Docs", "Productivity", "Laptop", 60),
    ("Coursera", "Education", "Laptop", 75), ("Duolingo", "Education", "Phone", 15),
    ("Netflix", "Entertainment", "TV", 100), ("Valorant", "Games", "Desktop", 80),
    ("Reddit", "Social", "Tablet", 35), ("Zoom", "Communication", "Laptop", 50),
]

today = date.today()
entries = []
for i in range(44):
    day = today - timedelta(days=random.randint(0, 20))
    app, cat, dev, typ = random.choice(APPS)
    mins = max(5, int(random.gauss(typ, typ * 0.35)))
    entries.append(st.make_entry(day.isoformat(), app, cat, dev, min(mins, 300),
                                 random.choice(["", "", "commute", "before bed", "study break"])))

# Boundary and edge cases
entries += [
    st.make_entry(today.isoformat(), "Calculator", "Other", "Phone", 1, "minimum value"),
    st.make_entry((today - timedelta(days=1)).isoformat(), "Binge Watching", "Entertainment",
                  "TV", 600, "anomalous: 10h session"),
    st.make_entry((today - timedelta(days=2)).isoformat(), "Kindle", "Education", "Tablet", 1440 // 12),
    st.make_entry((today - timedelta(days=3)).isoformat(), "Remote Desktop", "Productivity",
                  "Desktop", 480, "boundary: exactly at the 8h anomaly threshold"),
]

diary = st.Diary("diary.json")
diary.entries = []
diary.add_many(entries)

with open("sample_entries.csv", "w", encoding="utf-8", newline="") as f:
    f.write(st.to_csv_text(entries))
with open("sample_entries.json", "w", encoding="utf-8") as f:
    json.dump({"version": 1, "entries": [e.to_row() for e in entries]}, f, indent=2)

# A messy legacy file for demonstrating row-by-row error logging
yesterday, tomorrow = (today - timedelta(days=1)).isoformat(), (today + timedelta(days=1)).isoformat()
with open("sample_import_with_errors.csv", "w", encoding="utf-8", newline="") as f:
    f.write(
        "date,app,category,device,minutes,notes\n"
        f"{yesterday},Notion,Productivity,Laptop,45,good row\n"
        f"{yesterday},Spotify,Entertainment,Phone,1h30m,good row (duration format)\n"
        f"{tomorrow},Twitter,Social,Phone,20,future date\n"
        "2026-13-45,Slack,Communication,Laptop,30,impossible date\n"
        f"{yesterday},,Social,Phone,20,blank app\n"
        f"{yesterday},Chess,Games,Toaster,20,unknown device\n"
        f"{yesterday},Telegram,Communication,Phone,abc,non-numeric minutes\n"
        f"{yesterday},Podcast,Entertainment,Phone,5000,over 24h\n"
    )

print(f"Wrote {len(entries)} entries to diary.json, sample_entries.csv and sample_entries.json")
print("Also wrote sample_import_with_errors.csv (2 valid rows, 6 invalid) for the import demo.")
