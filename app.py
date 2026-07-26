import os
import sys
import sqlite3
import json
import webbrowser
from datetime import datetime
import pandas as pd
import numpy as np

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.ingest_data import DB_PATH, ingest_all
from backend.ml_engine import run_dbscan_clustering, evaluate_new_incident_patterns
from backend.ai_assistant import text_to_sql_query, generate_criminal_network_graph

# Ensure DB exists
if not os.path.exists(DB_PATH):
    print("Database not found. Triggering automated ingestion...")
    ingest_all()

app = FastAPI(title="KSP Intelligent Crime Analytics & Field Reporting Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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

    cursor.execute("""
        INSERT INTO crimes (
            case_id, crime_type, division, city, station_id, latitude, longitude,
            date_time, severity, status, suspect_id, suspect_name, amount_involved,
            resolution_notes, mo_signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        case_id, report.crime_type, report.division, report.city, report.station_id,
        report.latitude, report.longitude, dt_str, report.severity, report.status,
        "", "", report.amount_involved, report.description, report.mo_signature
    ))
    conn.commit()

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
