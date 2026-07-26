import os
import sys
import sqlite3
import json
import webbrowser
from datetime import datetime
import pandas as pd
import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.ingest_data import DB_PATH

# -------------------------------------------------------------------
# FIREBASE & IN-MEMORY SQLITE INITIALIZATION
# -------------------------------------------------------------------
use_firestore = False
db_fs = None

def _init_firebase_from_dict(creds_dict, source):
    global db_fs, use_firestore
    cred = credentials.Certificate(creds_dict)
    firebase_admin.initialize_app(cred)
    db_fs = firestore.client()
    use_firestore = True
    print(f"Firebase initialized via {source}.")

# Method 1: Single env var FIREBASE_CREDENTIALS (full JSON)
firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
if firebase_creds_json:
    try:
        _init_firebase_from_dict(json.loads(firebase_creds_json), "FIREBASE_CREDENTIALS env var")
    except Exception as e:
        print(f"Error parsing FIREBASE_CREDENTIALS: {e}")

# Method 2: Split env vars FIREBASE_CREDS_1 + FIREBASE_CREDS_2 + FIREBASE_CREDS_3
# Use this when the JSON exceeds Catalyst's 1000-char env var limit
if not use_firestore:
    part1 = os.environ.get("FIREBASE_CREDS_1", "")
    part2 = os.environ.get("FIREBASE_CREDS_2", "")
    part3 = os.environ.get("FIREBASE_CREDS_3", "")
    if part1 and part2:
        try:
            combined = part1 + part2 + part3
            _init_firebase_from_dict(json.loads(combined), "split env vars (FIREBASE_CREDS_1/2/3)")
        except Exception as e:
            print(f"Error parsing split Firebase credentials: {e}")

# Method 3: Local credentials file (for development)
if not use_firestore:
    local_creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase-credentials.json")
    if os.path.exists(local_creds_path):
        try:
            with open(local_creds_path, "r") as f:
                _init_firebase_from_dict(json.load(f), f"local file ({local_creds_path})")
        except Exception as e:
            print(f"Error loading local Firebase credentials: {e}")


# Shared in-memory connection URL for caching shared DB state across connections
MEM_DB_URI = "file:ksp_crimes_in_mem?mode=memory&cache=shared"
# Keep one persistent connection open to prevent in-memory DB destruction
_keep_alive_conn = sqlite3.connect(MEM_DB_URI, uri=True)

def get_db():
    conn = sqlite3.connect(MEM_DB_URI, uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def create_schema(conn):
    cursor = conn.cursor()
    
    # 1. State
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS State (
        StateID INTEGER PRIMARY KEY,
        StateName TEXT,
        NationalityID INTEGER,
        Active INTEGER
    );
    """)

    # 2. District
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS District (
        DistrictID INTEGER PRIMARY KEY,
        DistrictName TEXT,
        StateID INTEGER,
        Active INTEGER,
        FOREIGN KEY(StateID) REFERENCES State(StateID)
    );
    """)

    # 3. Court
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Court (
        CourtID INTEGER PRIMARY KEY,
        CourtName TEXT,
        DistrictID INTEGER,
        StateID INTEGER,
        Active INTEGER,
        FOREIGN KEY(DistrictID) REFERENCES District(DistrictID),
        FOREIGN KEY(StateID) REFERENCES State(StateID)
    );
    """)

    # 4. UnitType
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS UnitType (
        UnitTypeID INTEGER PRIMARY KEY,
        UnitTypeName TEXT,
        CityDistState TEXT,
        Hierarchy INTEGER,
        Active INTEGER
    );
    """)

    # 5. Unit
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Unit (
        UnitID INTEGER PRIMARY KEY,
        UnitName TEXT,
        TypeID INTEGER,
        ParentUnit INTEGER,
        NationalityID INTEGER,
        StateID INTEGER,
        DistrictID INTEGER,
        Active INTEGER,
        FOREIGN KEY(TypeID) REFERENCES UnitType(UnitTypeID),
        FOREIGN KEY(StateID) REFERENCES State(StateID),
        FOREIGN KEY(DistrictID) REFERENCES District(DistrictID)
    );
    """)

    # 6. Rank
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Rank (
        RankID INTEGER PRIMARY KEY,
        RankName TEXT,
        Hierarchy INTEGER,
        Active INTEGER
    );
    """)

    # 7. Designation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Designation (
        DesignationID INTEGER PRIMARY KEY,
        DesignationName TEXT,
        Active INTEGER,
        SortOrder INTEGER
    );
    """)

    # 8. Employee
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Employee (
        EmployeeID INTEGER PRIMARY KEY,
        DistrictID INTEGER,
        UnitID INTEGER,
        RankID INTEGER,
        DesignationID INTEGER,
        KGID TEXT,
        FirstName TEXT,
        EmployeeDOB TEXT,
        GenderID INTEGER,
        BloodGroupID INTEGER,
        PhysicallyChallenged INTEGER,
        AppointmentDate TEXT,
        FOREIGN KEY(DistrictID) REFERENCES District(DistrictID),
        FOREIGN KEY(UnitID) REFERENCES Unit(UnitID),
        FOREIGN KEY(RankID) REFERENCES Rank(RankID),
        FOREIGN KEY(DesignationID) REFERENCES Designation(DesignationID)
    );
    """)

    # 9. CaseCategory
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CaseCategory (
        CaseCategoryID INTEGER PRIMARY KEY,
        LookupValue TEXT
    );
    """)

    # 10. GravityOffence
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS GravityOffence (
        GravityOffenceID INTEGER PRIMARY KEY,
        LookupValue TEXT
    );
    """)

    # 11. CrimeHead
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CrimeHead (
        CrimeHeadID INTEGER PRIMARY KEY,
        CrimeGroupName TEXT,
        Active INTEGER
    );
    """)

    # 12. CrimeSubHead
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CrimeSubHead (
        CrimeSubHeadID INTEGER PRIMARY KEY,
        CrimeHeadID INTEGER,
        CrimeHeadName TEXT,
        SeqID INTEGER,
        FOREIGN KEY(CrimeHeadID) REFERENCES CrimeHead(CrimeHeadID)
    );
    """)

    # 13. CaseStatusMaster
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CaseStatusMaster (
        CaseStatusID INTEGER PRIMARY KEY,
        CaseStatusName TEXT
    );
    """)

    # 14. CaseMaster
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CaseMaster (
        CaseMasterID INTEGER PRIMARY KEY,
        CrimeNo TEXT,
        CaseNo TEXT,
        CrimeRegisteredDate TEXT,
        PolicePersonID INTEGER,
        PoliceStationID INTEGER,
        CaseCategoryID INTEGER,
        GravityOffenceID INTEGER,
        CrimeMajorHeadID INTEGER,
        CrimeMinorHeadID INTEGER,
        CaseStatusID INTEGER,
        CourtID INTEGER,
        IncidentFromDate TEXT,
        IncidentToDate TEXT,
        InfoReceivedPSDate TEXT,
        latitude REAL,
        longitude REAL,
        BriefFacts TEXT,
        FOREIGN KEY(PolicePersonID) REFERENCES Employee(EmployeeID),
        FOREIGN KEY(PoliceStationID) REFERENCES Unit(UnitID),
        FOREIGN KEY(CaseCategoryID) REFERENCES CaseCategory(CaseCategoryID),
        FOREIGN KEY(GravityOffenceID) REFERENCES GravityOffence(GravityOffenceID),
        FOREIGN KEY(CrimeMajorHeadID) REFERENCES CrimeHead(CrimeHeadID),
        FOREIGN KEY(CrimeMinorHeadID) REFERENCES CrimeSubHead(CrimeSubHeadID),
        FOREIGN KEY(CaseStatusID) REFERENCES CaseStatusMaster(CaseStatusID),
        FOREIGN KEY(CourtID) REFERENCES Court(CourtID)
    );
    """)

    # 15. CasteMaster
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CasteMaster (
        caste_master_id INTEGER PRIMARY KEY,
        caste_master_name TEXT
    );
    """)

    # 16. ReligionMaster
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ReligionMaster (
        ReligionID INTEGER PRIMARY KEY,
        ReligionName TEXT
    );
    """)

    # 17. OccupationMaster
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS OccupationMaster (
        OccupationID INTEGER PRIMARY KEY,
        OccupationName TEXT
    );
    """)

    # 18. ComplainantDetails
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ComplainantDetails (
        ComplainantID INTEGER PRIMARY KEY,
        CaseMasterID INTEGER,
        ComplainantName TEXT,
        AgeYear INTEGER,
        OccupationID INTEGER,
        ReligionID INTEGER,
        CasteID INTEGER,
        GenderID INTEGER,
        FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
        FOREIGN KEY(OccupationID) REFERENCES OccupationMaster(OccupationID),
        FOREIGN KEY(ReligionID) REFERENCES ReligionMaster(ReligionID),
        FOREIGN KEY(CasteID) REFERENCES CasteMaster(caste_master_id)
    );
    """)

    # 19. Act
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Act (
        ActCode TEXT PRIMARY KEY,
        ActDescription TEXT,
        ShortName TEXT,
        Active INTEGER
    );
    """)

    # 20. Section
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Section (
        ActCode TEXT,
        SectionCode TEXT,
        SectionDescription TEXT,
        Active INTEGER,
        PRIMARY KEY (ActCode, SectionCode),
        FOREIGN KEY(ActCode) REFERENCES Act(ActCode)
    );
    """)

    # 21. ActSectionAssociation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ActSectionAssociation (
        CaseMasterID INTEGER,
        ActID TEXT,
        SectionID TEXT,
        ActOrderID INTEGER,
        SectionOrderID INTEGER,
        PRIMARY KEY (CaseMasterID, ActID, SectionID),
        FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
        FOREIGN KEY(ActID, SectionID) REFERENCES Section(ActCode, SectionCode)
    );
    """)

    # 22. Victim
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Victim (
        VictimMasterID INTEGER PRIMARY KEY,
        CaseMasterID INTEGER,
        VictimName TEXT,
        AgeYear INTEGER,
        GenderID INTEGER,
        VictimPolice TEXT,
        FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID)
    );
    """)

    # 23. Accused
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Accused (
        AccusedMasterID INTEGER PRIMARY KEY,
        CaseMasterID INTEGER,
        AccusedName TEXT,
        AgeYear INTEGER,
        GenderID INTEGER,
        PersonID TEXT,
        FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID)
    );
    """)

    # 24. ArrestSurrender
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ArrestSurrender (
        ArrestSurrenderID INTEGER PRIMARY KEY,
        CaseMasterID INTEGER,
        ArrestSurrenderTypeID INTEGER,
        ArrestSurrenderDate TEXT,
        ArrestSurrenderStateId INTEGER,
        ArrestSurrenderDistrictId INTEGER,
        PoliceStationID INTEGER,
        IOID INTEGER,
        CourtID INTEGER,
        AccusedMasterID INTEGER,
        IsAccused INTEGER,
        IsComplainantAccused INTEGER,
        FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
        FOREIGN KEY(ArrestSurrenderStateId) REFERENCES State(StateID),
        FOREIGN KEY(ArrestSurrenderDistrictId) REFERENCES District(DistrictID),
        FOREIGN KEY(PoliceStationID) REFERENCES Unit(UnitID),
        FOREIGN KEY(IOID) REFERENCES Employee(EmployeeID),
        FOREIGN KEY(CourtID) REFERENCES Court(CourtID),
        FOREIGN KEY(AccusedMasterID) REFERENCES Accused(AccusedMasterID)
    );
    """)

    # 25. CrimeHeadActSection
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CrimeHeadActSection (
        CrimeHeadID INTEGER,
        ActCode TEXT,
        SectionCode TEXT,
        PRIMARY KEY (CrimeHeadID, ActCode, SectionCode),
        FOREIGN KEY(CrimeHeadID) REFERENCES CrimeHead(CrimeHeadID),
        FOREIGN KEY(ActCode, SectionCode) REFERENCES Section(ActCode, SectionCode)
    );
    """)

    # 26. ChargesheetDetails
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ChargesheetDetails (
        CSID INTEGER PRIMARY KEY,
        CaseMasterID INTEGER,
        csdate TEXT,
        cstype TEXT,
        PolicePersonID INTEGER,
        FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
        FOREIGN KEY(PolicePersonID) REFERENCES Employee(EmployeeID)
    );
    """)

    # Original Platform Tables
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS district_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        district TEXT NOT NULL,
        ipc_bns_crimes INTEGER NOT NULL,
        sll_crimes INTEGER NOT NULL,
        year INTEGER DEFAULT 2025
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crime_heads_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        head_of_crime TEXT NOT NULL,
        sub_category TEXT,
        count_2025 INTEGER NOT NULL
    );
    """)
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

def run_csv_ingestion_on_db(conn):
    import csv
    from scripts.ingest_data import parse_and_clean_crimes, DATASET_DIR
    cursor = conn.cursor()
    
    # Ingest crimes
    crimes = parse_and_clean_crimes()
    cursor.executemany("""
    INSERT INTO crimes (
        case_id, crime_type, division, city, station_id, latitude, longitude,
        date_time, severity, status, suspect_id, suspect_name, amount_involved,
        resolution_notes, mo_signature
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, crimes)
    print(f"Ingested {len(crimes)} crimes into in-memory database.")

    # Ingest District trends
    dist_file = os.path.join(DATASET_DIR, "ka-district-wise-2025.csv")
    if os.path.exists(dist_file):
        with open(dist_file, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            next(reader, None)
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
            print(f"Ingested {len(dist_records)} district trend records into in-memory database.")

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
            print(f"Ingested {len(head_records)} IPC crime head records into in-memory database.")
            
    conn.commit()

TABLE_PRIMARY_KEYS = {
    "crimes": "case_id",
    "district_trends": "id",
    "crime_heads_trends": "id",
    "ml_alerts": "alert_id",
    "CaseMaster": "CaseMasterID",
    "ComplainantDetails": "ComplainantID",
    "ActSectionAssociation": "CaseMasterID",
    "Victim": "VictimMasterID",
    "Accused": "AccusedMasterID",
    "ArrestSurrender": "ArrestSurrenderID",
    "Act": "ActCode",
    "Section": "SectionCode",
    "CrimeHeadActSection": "CrimeHeadID",
    "CrimeHead": "CrimeHeadID",
    "CrimeSubHead": "CrimeSubHeadID",
    "CasteMaster": "caste_master_id",
    "ReligionMaster": "ReligionID",
    "OccupationMaster": "OccupationID",
    "CaseStatusMaster": "CaseStatusID",
    "Court": "CourtID",
    "District": "DistrictID",
    "State": "StateID",
    "Unit": "UnitID",
    "UnitType": "UnitTypeID",
    "Rank": "RankID",
    "Designation": "DesignationID",
    "Employee": "EmployeeID",
    "CaseCategory": "CaseCategoryID",
    "GravityOffence": "GravityOffenceID",
    "ChargesheetDetails": "CSID"
}

TABLES_TO_SYNC = list(TABLE_PRIMARY_KEYS.keys())

def upload_sqlite_to_firestore(conn):
    if not use_firestore or db_fs is None:
        return
    print("Uploading SQLite database tables to Firestore to seed cloud storage...")
    
    for table_name in TABLES_TO_SYNC:
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
        except Exception:
            continue
            
        rows = cursor.execute(f"SELECT * FROM {table_name}").fetchall()
        if not rows:
            continue
            
        print(f"Seeding {len(rows)} records from table '{table_name}' to Firestore...")
        batch = db_fs.batch()
        count = 0
        pk_col = TABLE_PRIMARY_KEYS.get(table_name)
        
        for row in rows:
            doc_data = dict(row)
            if pk_col and doc_data.get(pk_col) is not None:
                doc_id = str(doc_data[pk_col])
            else:
                import uuid
                doc_id = str(uuid.uuid4())
                
            doc_ref = db_fs.collection(table_name).document(doc_id)
            batch.set(doc_ref, doc_data)
            count += 1
            if count % 400 == 0:
                batch.commit()
                batch = db_fs.batch()
        if count % 400 != 0:
            batch.commit()
    print("Firestore seeding completed.")

def sync_firestore_to_sqlite():
    conn = get_db()
    create_schema(conn)
    cursor = conn.cursor()
    
    if not use_firestore or db_fs is None:
        print("Firestore not initialized. Using local backup or fresh CSV parsing...")
        local_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ksp_crimes.db")
        if os.path.exists(local_db_path):
            print(f"Restoring data from local backup database: {local_db_path}")
            backup_conn = sqlite3.connect(local_db_path)
            backup_conn.backup(conn)
            backup_conn.close()
        else:
            print("No local backup file found. Ingesting from local CSVs...")
            run_csv_ingestion_on_db(conn)
        conn.close()
        return

    try:
        # Check if crimes collection has any data
        crimes_ref = db_fs.collection("crimes")
        test_docs = list(crimes_ref.limit(1).stream())
        
        if len(test_docs) == 0:
            print("Firestore is empty. Doing initial local CSV ingestion and seeding to cloud...")
            run_csv_ingestion_on_db(conn)
            upload_sqlite_to_firestore(conn)
        else:
            print("Syncing data from Firestore into in-memory SQLite...")
            for table_name in TABLES_TO_SYNC:
                ref = db_fs.collection(table_name)
                docs = list(ref.stream())
                if len(docs) == 0:
                    continue
                
                print(f"Syncing {len(docs)} records for table '{table_name}' from Firestore...")
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = [col[1] for col in cursor.fetchall()]
                
                placeholders = ", ".join(["?"] * len(columns))
                col_list = ", ".join(columns)
                sql = f"INSERT OR REPLACE INTO {table_name} ({col_list}) VALUES ({placeholders});"
                
                records = []
                for doc in docs:
                    data = doc.to_dict()
                    record = []
                    for col in columns:
                        val = data.get(col)
                        if isinstance(val, (dict, list)):
                            val = json.dumps(val)
                        record.append(val)
                    records.append(record)
                    
                if records:
                    cursor.executemany(sql, records)
            conn.commit()
            print("Successfully loaded all Firestore records into shared in-memory SQLite database.")
    except Exception as e:
        print(f"Error during Firestore to SQLite synchronization: {e}")
        print("Falling back to local SQLite database ingestion...")
        run_csv_ingestion_on_db(conn)
    finally:
        conn.close()

# Execute initial synchronization
sync_firestore_to_sqlite()

app = FastAPI(title="KSP Intelligent Crime Analytics & Field Reporting Platform")



# Data Models
class IncidentReport(BaseModel):
    crime_type: str
    division: str
    city: Optional[str] = "District HQ"
    station_id: str
    latitude: float
    longitude: float
    date_time: Optional[str] = None
    severity: str
    status: Optional[str] = "Open"
    description: Optional[str] = ""
    amount_involved: Optional[float] = 0.0
    mo_signature: Optional[str] = "Standard Incident"

class CaseResolution(BaseModel):
    status: str # Solved, Closed, Under Investigation
    resolution_notes: str
    suspect_id: Optional[str] = ""
    suspect_name: Optional[str] = ""
    amount_recovered: Optional[float] = 0.0

class AIChatQuery(BaseModel):
    question: str
    language: Optional[str] = "en" # "en" or "kn"

KNOWN_CRIME_TYPES = [
    # Specific Theft types first
    ("vehicle theft", "Vehicle Theft"), ("ವಾಹನ ಕಳವು", "Vehicle Theft"), ("ಬೈಕ್ ಕಳವು", "Vehicle Theft"), ("ಕಾರು ಕಳವು", "Vehicle Theft"), ("vahana kalavu", "Vehicle Theft"), ("ವಾಹನ", "Vehicle Theft"),
    ("mobile theft", "Mobile Theft"), ("ಮೊಬೈಲ್ ಕಳವು", "Mobile Theft"), ("ಫೋನ್ ಕಳವು", "Mobile Theft"), ("mobile kalavu", "Mobile Theft"), ("ಮೊಬೈಲ್", "Mobile Theft"),
    ("chain snatching", "Chain Snatching"), ("ಚೈನ್ ಕಳವು", "Chain Snatching"), ("ಚೈನ್ ಕಸಿಯುವಿಕೆ", "Chain Snatching"), ("ಚೈನ್", "Chain Snatching"), ("chain kalavu", "Chain Snatching"),
    
    # Domestic & Land & Drug
    ("domestic violence", "Domestic Violence"), ("ಗೃಹ ಹಿಂಸೆ", "Domestic Violence"), ("ಕುಟುಂಬ ದೌರ್ಜನ್ಯ", "Domestic Violence"), ("gruha himse", "Domestic Violence"),
    ("drug offense", "Drug Offense"), ("drug", "Drug Offense"), ("ಮಾದಕ", "Drug Offense"), ("ಮಾದಕ ದ್ರವ್ಯ", "Drug Offense"), ("ಗಾಂಜಾ", "Drug Offense"), ("madaka", "Drug Offense"),
    ("land dispute", "Land Dispute"), ("ಜಮೀನು ವಿವಾದ", "Land Dispute"), ("ಭೂ ವಿವಾದ", "Land Dispute"), ("ಜಮೀನು", "Land Dispute"), ("jaminu", "Land Dispute"),
    ("cybercrime", "Cybercrime"), ("cyber", "Cybercrime"), ("ಸೈಬರ್", "Cybercrime"), ("ಸೈಬರ್ ಅಪರಾಧ", "Cybercrime"),
    
    # Standard Theft & Major IPC crimes
    ("theft", "Theft"), ("ಕಳವು", "Theft"), ("ಕಳ್ಳತನ", "Theft"), ("ಕದ್ದ", "Theft"), ("kalavu", "Theft"), ("kallathana", "Theft"),
    ("robbery", "Robbery"), ("ದರೋಡೆ", "Robbery"), ("ಲೂಟಿ", "Robbery"), ("darode", "Robbery"), ("daroode", "Robbery"),
    ("burglary", "Burglary"), ("ಮನೆಗಳ್ಳತನ", "Burglary"), ("ಮನೆ ಕಳ್ಳತನ", "Burglary"), ("managallathana", "Burglary"),
    ("assault", "Assault"), ("ಹಲ್ಲೆ", "Assault"), ("ಹೊಡೆದಾಟ", "Assault"), ("halle", "Assault"),
    ("murder", "Murder"), ("ಕೊಲೆ", "Murder"), ("ಕೊಲೆಗಳು", "Murder"), ("kole", "Murder"),
    ("kidnapping", "Kidnapping"), ("ಅಪಹರಣ", "Kidnapping"), ("ಕಿಡ್ನ್ಯಾಪ್", "Kidnapping"), ("apaharana", "Kidnapping"),
    ("fraud", "Fraud"), ("ವಂಚನೆ", "Fraud"), ("ಮೋಸ", "Fraud"), ("vanchane", "Fraud"),
]

KNOWN_DIVISIONS = [
    ("mysuru", "Mysuru"), ("mysore", "Mysuru"), ("ಮೈಸೂರು", "Mysuru"), ("ಮೈಸೂರಿನಲ್ಲಿ", "Mysuru"), ("ಮೈಸೂರಿನ", "Mysuru"),
    ("bengaluru", "Bengaluru"), ("bangalore", "Bengaluru"), ("ಬೆಂಗಳೂರು", "Bengaluru"), ("ಬೆಂಗಳೂರಿನಲ್ಲಿ", "Bengaluru"), ("ಬೆಂಗಳೂರಿನ", "Bengaluru"),
    ("mangaluru", "Mangaluru"), ("mangalore", "Mangaluru"), ("ಮಂಗಳೂರು", "Mangaluru"), ("ಮಂಗಳೂರಿನಲ್ಲಿ", "Mangaluru"),
    ("hubballi", "Hubballi"), ("dharwad", "Hubballi"), ("ಹುಬ್ಬಳ್ಳಿ", "Hubballi"), ("ಧಾರವಾಡ", "Hubballi"), ("ಹುಬ್ಬಳ್ಳಿಯಲ್ಲಿ", "Hubballi"),
    ("belagavi", "Belagavi"), ("belgaum", "Belagavi"), ("ಬೆಳಗಾವಿ", "Belagavi"), ("ಬೆಳಗಾವಿಯಲ್ಲಿ", "Belagavi"),
    ("whitefield", "Whitefield"), ("ವೈಟ್‌ಫೀಲ್ಡ್", "Whitefield"),
    ("vijayanagar", "Vijayanagar"), ("ವಿಜಯನಗರ", "Vijayanagar"), ("ವಿಜಯನಗರದಲ್ಲಿ", "Vijayanagar"),
]

KNOWN_STATUSES = [
    ("solved", "Solved"), ("ಪರಿಹರಿಸಲಾದ", "Solved"), ("ಪರಿಹಾರ", "Solved"),
    ("closed", "Closed"), ("ಮುಕ್ತಾಯ", "Closed"),
    ("open", "Open"), ("ಖುಲ್ಲಾ", "Open"), ("ಮುಕ್ತ", "Open"),
    ("under investigation", "Under Investigation"), ("ತನಿಖೆ", "Under Investigation"), ("ತನಿಖೆಯಲ್ಲಿ", "Under Investigation")
]

KNOWN_SEVERITIES = [
    ("critical", "Critical"), ("ತೀವ್ರ", "Critical"), ("ಗಂಭೀರ", "Critical"),
    ("high", "High"), ("ಹೆಚ್ಚಿನ", "High"), ("ಉನ್ನತ", "High"),
    ("medium", "Medium"), ("ಸಾಧಾರಣ", "Medium"), ("ಮಧ್ಯಮ", "Medium"),
    ("low", "Low"), ("ಕಡಿಮೆ", "Low")
]

def build_crimes_filter(q=None, division=None, city=None, crime_type=None, severity=None, status=None, start_date=None, end_date=None):
    query = "SELECT * FROM crimes WHERE 1=1"
    params = []

    if q and q.strip():
        q_clean = q.strip()
        q_lower = q_clean.lower()
        
        # 1. Check if query targets a specific crime type (English or Kannada)
        matched_exact_type = None
        for keyword, target_type in KNOWN_CRIME_TYPES:
            if keyword in q_lower:
                matched_exact_type = target_type
                break

        # 2. Check if query targets a specific division (English or Kannada)
        matched_exact_div = None
        for keyword, target_div in KNOWN_DIVISIONS:
            if keyword in q_lower:
                matched_exact_div = target_div
                break

        # 3. Check status match
        matched_exact_status = None
        for keyword, target_status in KNOWN_STATUSES:
            if keyword in q_lower:
                matched_exact_status = target_status
                break

        # 4. Check severity match
        matched_exact_sev = None
        for keyword, target_sev in KNOWN_SEVERITIES:
            if keyword in q_lower:
                matched_exact_sev = target_sev
                break

        if matched_exact_type:
            query += " AND LOWER(crime_type) = LOWER(?)"
            params.append(matched_exact_type)

        if matched_exact_div:
            query += " AND (LOWER(division) LIKE LOWER(?) OR LOWER(city) LIKE LOWER(?) OR LOWER(station_id) LIKE LOWER(?))"
            params.extend([f"%{matched_exact_div}%", f"%{matched_exact_div}%", f"%{matched_exact_div}%"])

        if matched_exact_status:
            query += " AND LOWER(status) = LOWER(?)"
            params.append(matched_exact_status)

        if matched_exact_sev:
            query += " AND LOWER(severity) = LOWER(?)"
            params.append(matched_exact_sev)

        # If none of the specific Kannada/English keywords matched, fallback to full-text search
        if not matched_exact_type and not matched_exact_div and not matched_exact_status and not matched_exact_sev:
            search_term = f"%{q_clean}%"
            query += """ AND (
                case_id LIKE ? OR 
                crime_type LIKE ? OR 
                division LIKE ? OR 
                city LIKE ? OR
                station_id LIKE ? OR 
                suspect_name LIKE ? OR 
                suspect_id LIKE ? OR 
                mo_signature LIKE ? OR 
                resolution_notes LIKE ?
            )"""
            params.extend([search_term] * 9)

    if division and division != "All":
        query += " AND division LIKE ?"
        params.append(f"%{division.strip()}%")
    if city and city != "All":
        query += " AND (LOWER(city) LIKE LOWER(?) OR LOWER(division) LIKE LOWER(?))"
        params.extend([f"%{city.strip()}%", f"%{city.strip()}%"])
    if crime_type and crime_type != "All":
        # Strict exact match for crime_type filter dropdown to avoid mixing Theft with Vehicle/Mobile Theft
        query += " AND LOWER(crime_type) = LOWER(?)"
        params.append(crime_type.strip())
    if severity and severity != "All":
        query += " AND severity LIKE ?"
        params.append(f"%{severity.strip()}%")
    if status and status != "All":
        query += " AND status LIKE ?"
        params.append(f"%{status.strip()}%")
    if start_date:
        query += " AND date_time >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date_time <= ?"
        params.append(end_date + " 23:59:59")

    return query, params

@app.get("/api/crimes")
def get_crimes(
    q: Optional[str] = Query(None, description="Search query string"),
    division: Optional[str] = None,
    city: Optional[str] = None,
    crime_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 2500
):
    conn = get_db()
    cursor = conn.cursor()

    query, params = build_crimes_filter(q, division, city, crime_type, severity, status, start_date, end_date)
    query += " ORDER BY date_time DESC LIMIT ?"
    params.append(limit)

    rows = cursor.execute(query, params).fetchall()
    conn.close()

    crimes = [dict(r) for r in rows]
    return {"status": "success", "count": len(crimes), "data": crimes}

@app.get("/api/stats/dashboard")
def get_dashboard_stats():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Total KPI counters
    total_crimes = cursor.execute("SELECT COUNT(*) FROM crimes").fetchone()[0]
    total_solved = cursor.execute("SELECT COUNT(*) FROM crimes WHERE status IN ('Solved', 'Closed')").fetchone()[0]
    total_open = cursor.execute("SELECT COUNT(*) FROM crimes WHERE status = 'Open'").fetchone()[0]
    total_under_inv = cursor.execute("SELECT COUNT(*) FROM crimes WHERE status = 'Under Investigation'").fetchone()[0]
    total_loss = cursor.execute("SELECT SUM(amount_involved) FROM crimes").fetchone()[0] or 0.0

    # 2. Breakdown by Crime Type
    type_rows = cursor.execute("""
        SELECT crime_type, COUNT(*) as count, SUM(amount_involved) as total_loss
        FROM crimes GROUP BY crime_type ORDER BY count DESC
    """).fetchall()
    by_crime_type = [dict(r) for r in type_rows]

    # 3. Breakdown by Division
    div_rows = cursor.execute("""
        SELECT division, COUNT(*) as count, SUM(amount_involved) as total_loss
        FROM crimes GROUP BY division ORDER BY count DESC LIMIT 10
    """).fetchall()
    by_division = [dict(r) for r in div_rows]

    # 4. Monthly 3-year timeline (2023 - 2025)
    time_rows = cursor.execute("""
        SELECT strftime('%Y-%m', date_time) as month, COUNT(*) as count
        FROM crimes
        WHERE date_time IS NOT NULL
        GROUP BY month ORDER BY month ASC
    """).fetchall()
    timeline = [dict(r) for r in time_rows]

    # 5. District 3-year historical dataset table
    dist_historical = cursor.execute("SELECT * FROM district_trends ORDER BY ipc_bns_crimes DESC").fetchall()
    
    # 6. IPC Crime Heads breakdown
    ipc_heads = cursor.execute("SELECT * FROM crime_heads_trends ORDER BY count_2025 DESC LIMIT 15").fetchall()

    conn.close()

    return {
        "kpi": {
            "total_crimes": total_crimes,
            "solved": total_solved,
            "open": total_open,
            "under_investigation": total_under_inv,
            "resolution_rate": round((total_solved / total_crimes * 100), 1) if total_crimes else 0,
            "total_monetary_loss": round(total_loss, 2)
        },
        "by_crime_type": by_crime_type,
        "by_division": by_division,
        "timeline": timeline,
        "district_historical": [dict(r) for r in dist_historical],
        "ipc_heads": [dict(r) for r in ipc_heads]
    }

@app.get("/api/analytics/hotspots")
def get_ml_hotspots(
    eps_km: float = 2.0,
    min_samples: int = 4,
    q: Optional[str] = Query(None),
    division: Optional[str] = None,
    crime_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None
):
    conn = get_db()
    cursor = conn.cursor()
    
    base_query, params = build_crimes_filter(q, division, crime_type, severity, status)
    query = base_query.replace("SELECT *", "SELECT case_id, crime_type, division, latitude, longitude, severity, status") + " LIMIT 2500"
    
    rows = cursor.execute(query, params).fetchall()
    conn.close()

    crimes = [dict(r) for r in rows]
    ml_result = run_dbscan_clustering(crimes, eps_km=eps_km, min_samples=min_samples)
    return {"status": "success", "data": ml_result}

@app.post("/api/crimes/report")
def report_field_incident(report: IncidentReport):
    conn = get_db()
    cursor = conn.cursor()

    dt_str = report.date_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    year = dt_str.split("-")[0]
    case_cnt = cursor.execute("SELECT COUNT(*) FROM crimes").fetchone()[0] + 1001
    case_id = f"KSP-{year}-{case_cnt}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    crime_doc = {
        "case_id": case_id,
        "crime_type": report.crime_type,
        "division": report.division,
        "city": report.city,
        "station_id": report.station_id,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "date_time": dt_str,
        "severity": report.severity,
        "status": report.status,
        "suspect_id": "",
        "suspect_name": "",
        "amount_involved": report.amount_involved,
        "resolution_notes": report.description,
        "mo_signature": report.mo_signature,
        "created_at": created_at
    }

    cursor.execute("""
        INSERT INTO crimes (
            case_id, crime_type, division, city, station_id, latitude, longitude,
            date_time, severity, status, suspect_id, suspect_name, amount_involved,
            resolution_notes, mo_signature, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        case_id, report.crime_type, report.division, report.city, report.station_id,
        report.latitude, report.longitude, dt_str, report.severity, report.status,
        "", "", report.amount_involved, report.description, report.mo_signature, created_at
    ))
    conn.commit()

    # Persist to Firestore (write-through)
    if use_firestore and db_fs:
        try:
            db_fs.collection("crimes").document(case_id).set(crime_doc)
        except Exception as e:
            print(f"Firestore write failed for crime {case_id}: {e}")

    # Fetch recent historical crimes to run ML Pattern Detection
    hist_rows = cursor.execute("SELECT * FROM crimes ORDER BY date_time DESC LIMIT 2000").fetchall()
    historical_crimes = [dict(r) for r in hist_rows]

    new_crime_dict = {
        "case_id": case_id,
        "crime_type": report.crime_type,
        "division": report.division,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "date_time": dt_str,
        "mo_signature": report.mo_signature,
        "suspect_id": ""
    }

    alert = evaluate_new_incident_patterns(new_crime_dict, historical_crimes, radius_meters=1200)

    if alert:
        cursor.execute("""
            INSERT INTO ml_alerts (
                alert_id, case_id, alert_type, confidence_score, matched_cases_count,
                matched_case_ids, message, distance_meters, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            alert["alert_id"], alert["case_id"], alert["alert_type"], alert["confidence_score"],
            alert["matched_cases_count"], alert["matched_case_ids"], alert["message"],
            alert["distance_meters"], alert["created_at"]
        ))
        conn.commit()

        # Persist alert to Firestore
        if use_firestore and db_fs:
            try:
                db_fs.collection("ml_alerts").document(alert["alert_id"]).set(alert)
            except Exception as e:
                print(f"Firestore write failed for alert {alert['alert_id']}: {e}")

    conn.close()

    return {
        "status": "success",
        "message": f"Incident reported successfully with Case ID: {case_id}",
        "case_id": case_id,
        "alert": alert
    }

@app.put("/api/crimes/{case_id}/resolve")
def resolve_case(case_id: str, payload: CaseResolution):
    conn = get_db()
    cursor = conn.cursor()

    existing = cursor.execute("SELECT * FROM crimes WHERE case_id = ?", (case_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Case ID not found")

    cursor.execute("""
        UPDATE crimes
        SET status = ?, resolution_notes = ?, suspect_id = ?, suspect_name = ?
        WHERE case_id = ?;
    """, (payload.status, payload.resolution_notes, payload.suspect_id, payload.suspect_name, case_id))
    conn.commit()

    # Persist resolution update to Firestore (write-through)
    if use_firestore and db_fs:
        try:
            db_fs.collection("crimes").document(case_id).update({
                "status": payload.status,
                "resolution_notes": payload.resolution_notes,
                "suspect_id": payload.suspect_id,
                "suspect_name": payload.suspect_name
            })
        except Exception as e:
            print(f"Firestore update failed for case {case_id}: {e}")

    conn.close()

    return {"status": "success", "message": f"Case {case_id} updated to {payload.status}."}

@app.get("/api/alerts")
def get_alerts(limit: int = 20):
    conn = get_db()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM ml_alerts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"status": "success", "data": [dict(r) for r in rows]}

# NEW AI ASSISTANT ENDPOINTS
@app.post("/api/ai/chat")
def ai_chat_assistant(query: AIChatQuery):
    """NL-to-SQL + Multilingual (English / Kannada) Intelligence Endpoint powered by LLM."""
    result = text_to_sql_query(query.question)
    return result

@app.post("/api/ai/transcribe")
async def transcribe_audio(file: UploadFile = File(...), language: str = "kn-IN"):
    """Bhashini ASR (Speech-to-Text) endpoint. Accepts audio file and returns transcribed text."""
    from backend.ai_assistant import process_asr_audio
    audio_bytes = await file.read()
    transcribed_text = process_asr_audio(audio_bytes, language=language)
    return {"status": "success", "transcribed_text": transcribed_text, "language": language}

@app.get("/api/ai/network_graph")
def get_network_graph(limit: int = 100):
    """Criminal Suspect & Incident Network Graph visualization data."""
    graph = generate_criminal_network_graph(limit=limit)
    return {"status": "success", "data": graph}

# Serve Frontend static directory
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>KSP Crime Analytics Hub Backend Operational</h2>")

if __name__ == "__main__":
    import uvicorn
    print("===============================================================")
    print(" KSP Intelligent Crime Analytics & Field Reporting Platform ")
    print(" Server launching on http://127.0.0.1:8000 ")
    print("===============================================================")
    port = int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", 8000))
    is_catalyst = "X_ZOHO_CATALYST_LISTEN_PORT" in os.environ
    if not is_catalyst:
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=not is_catalyst)
