import os
import re
import csv
import sqlite3
from datetime import datetime, timedelta
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ksp_crimes.db")
DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "datasets")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1: Master crimes table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crimes (
        case_id TEXT PRIMARY KEY,
        crime_type TEXT NOT NULL,
        division TEXT NOT NULL,
        city TEXT,
        station_id TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        date_time TEXT NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL,
        suspect_id TEXT,
        suspect_name TEXT,
        amount_involved REAL DEFAULT 0.0,
        resolution_notes TEXT,
        mo_signature TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Table 2: District-wise historical data (3-year trends)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS district_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        district TEXT NOT NULL,
        ipc_bns_crimes INTEGER NOT NULL,
        sll_crimes INTEGER NOT NULL,
        year INTEGER DEFAULT 2025
    );
    """)

    # Table 3: IPC Crime heads statistics
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crime_heads_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        head_of_crime TEXT NOT NULL,
        sub_category TEXT,
        count_2025 INTEGER NOT NULL
    );
    """)

    # Table 4: ML Alerts Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ml_alerts (
        alert_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        confidence_score REAL NOT NULL,
        matched_cases_count INTEGER NOT NULL,
        matched_case_ids TEXT NOT NULL,
        message TEXT NOT NULL,
        distance_meters REAL,
        created_at TEXT NOT NULL
    );
    """)

    conn.commit()
    return conn

def parse_and_clean_crimes():
    crimes_file = os.path.join(DATASET_DIR, "crimes.csv")
    if not os.path.exists(crimes_file):
        print(f"Error: {crimes_file} not found")
        return []

    lines = []
    with open(crimes_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    header_idx = -1
    for i, line in enumerate(lines):
        if "Area,city,police_station,crime_type,latitude,longitude,date,severity,status" in line:
            header_idx = i
            break

    if header_idx == -1:
        print("Header not found in crimes.csv!")
        return []

    csv_data = lines[header_idx:]
    reader = csv.DictReader(csv_data)

    records = []
    case_counter = 1000

    mo_signatures = [
        "Night time door lock picking",
        "Two-wheeler mobile snatching",
        "Fake online banking OTP fraud",
        "ATM card swapping near booth",
        "Highway truck cargo hijacking",
        "Residential burglaries during weekend",
        "Chain snatching by duo on motorbikes",
        "Land document forgery & impersonation",
        "Alleyway robbery under weapon threat",
        "Domestic dispute argument escalation"
    ]

    suspect_names = [
        "Ramesh @ Kali", "Suresh Kumar", "Venkatesh Naik", "Kiran Gowda",
        "Syed Ibrahim", "Manjunath S.", "Basavaraj @ Bullet", "Anand Rao",
        "Praveen Shetty", "Deepak Lal"
    ]

    for raw_row in reader:
        # Strip all whitespace from keys and values
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items() if k}
        try:
            area = row.get("Area", "").strip() or "Karnataka Division"
            city = row.get("city", "").strip() or "District HQ"
            ps = row.get("police_station", "").strip() or "Local PS"
            ctype = row.get("crime_type", "").strip() or "General Offense"
            lat = float(row.get("latitude", 0.0))
            lng = float(row.get("longitude", 0.0))
            raw_date = row.get("date", "").strip()
            sev = row.get("severity", "medium").strip().capitalize()
            stat_raw = row.get("status", "open").strip().lower()

            if lat == 0.0 or lng == 0.0:
                continue

            # Normalize status
            if "investigat" in stat_raw:
                stat = "Under Investigation"
            elif "solve" in stat_raw:
                stat = "Solved"
            elif "close" in stat_raw:
                stat = "Closed"
            else:
                stat = "Open"

            # Date parsing (e.g., 09-01-2023 or 2023-01-09)
            try:
                dt_obj = datetime.strptime(raw_date, "%d-%m-%Y")
            except Exception:
                try:
                    dt_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                except Exception:
                    dt_obj = datetime.now() - timedelta(days=random.randint(1, 730))

            iso_date = dt_obj.strftime("%Y-%m-%d %H:%M:%S")

            case_counter += 1
            case_id = f"KSP-{dt_obj.year}-{case_counter}"

            # Synthetic amount for theft/robbery/burglary
            amount = 0.0
            if ctype in ["Theft", "Vehicle Theft", "Robbery", "Burglary", "Drug Offense"]:
                amount = float(random.randint(5, 450) * 1000)

            suspect_id = ""
            suspect_name = ""
            resolution_notes = ""
            if stat in ["Solved", "Closed"]:
                suspect_id = f"SUSP-{random.randint(1000, 9999)}"
                suspect_name = random.choice(suspect_names)
                resolution_notes = f"Case resolved by {ps} team. Suspect confessed and evidence recovered."
            elif stat == "Under Investigation" and random.random() > 0.5:
                suspect_id = f"SUSP-{random.randint(1000, 9999)}"
                suspect_name = random.choice(suspect_names)

            mo = random.choice(mo_signatures)

            records.append((
                case_id, ctype, area, city, ps, lat, lng, iso_date,
                sev, stat, suspect_id, suspect_name, amount, resolution_notes, mo
            ))
        except Exception as e:
            continue

    print(f"Parsed {len(records)} clean crime records.")
    return records

def ingest_all():
    conn = init_db()
    cursor = conn.cursor()

    # Clear previous if re-running
    cursor.execute("DELETE FROM crimes;")
    cursor.execute("DELETE FROM district_trends;")
    cursor.execute("DELETE FROM crime_heads_trends;")

    crimes = parse_and_clean_crimes()
    cursor.executemany("""
    INSERT INTO crimes (
        case_id, crime_type, division, city, station_id, latitude, longitude,
        date_time, severity, status, suspect_id, suspect_name, amount_involved,
        resolution_notes, mo_signature
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, crimes)

    # Ingest District trends
    dist_file = os.path.join(DATASET_DIR, "ka-district-wise-2025.csv")
    if os.path.exists(dist_file):
        with open(dist_file, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            next(reader, None) # header
            dist_records = []
            for row in reader:
                if len(row) >= 4 and row[1].strip() and not row[1].strip().endswith("Range"):
                    dist_name = row[1].strip()
                    try:
                        ipc_val = int(row[2].replace(",", "").strip()) if row[2].strip() else 0
                        sll_val = int(row[3].replace(",", "").strip()) if row[3].strip() else 0
                        dist_records.append((dist_name, ipc_val, sll_val, 2025))
                    except Exception:
                        continue
            cursor.executemany("""
            INSERT INTO district_trends (district, ipc_bns_crimes, sll_crimes, year)
            VALUES (?, ?, ?, ?);
            """, dist_records)
            print(f"Ingested {len(dist_records)} district trend records.")

    # Ingest Crime Heads
    ipc_file = os.path.join(DATASET_DIR, "ka-ipc-crimes-2025.csv")
    if os.path.exists(ipc_file):
        with open(ipc_file, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            next(reader, None)
            head_records = []
            curr_head = ""
            for row in reader:
                if len(row) >= 3:
                    h_val = row[1].strip()
                    c_val = row[2].strip()
                    if h_val and not h_val.startswith("For ") and not h_val.startswith("Due to"):
                        curr_head = h_val
                    elif h_val:
                        sub = h_val
                        try:
                            cnt = int(c_val.replace(",", "")) if c_val else 0
                            head_records.append((curr_head, sub, cnt))
                        except Exception:
                            continue
            cursor.executemany("""
            INSERT INTO crime_heads_trends (head_of_crime, sub_category, count_2025)
            VALUES (?, ?, ?);
            """, head_records)
            print(f"Ingested {len(head_records)} IPC crime head records.")

    conn.commit()
    conn.close()
    print("Ingestion completed successfully!")

if __name__ == "__main__":
    ingest_all()
