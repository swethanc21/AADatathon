import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
import math
from datetime import datetime

EARTH_RADIUS_KM = 6371.0088

def haversine_distance_meters(lat1, lon1, lat2, lon2):
    """Calculate Haversine distance in meters between two lat/lng pairs."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c * 1000.0

def run_dbscan_clustering(crimes_list, eps_km=1.5, min_samples=3):
    """
    Run DBSCAN spatial clustering on crime coordinates.
    eps_km: radius in kilometers (default 1.5km)
    min_samples: minimum crimes to form a cluster core
    """
    if not crimes_list or len(crimes_list) < min_samples:
        return {"clusters": [], "noise_count": len(crimes_list)}

    df = pd.DataFrame(crimes_list)
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return {"clusters": [], "noise_count": len(crimes_list)}

    # Convert degrees to radians for Haversine metric in scikit-learn
    coords_rad = np.radians(df[['latitude', 'longitude']].values)
    
    # eps in radians = eps_km / Earth radius in km
    kms_per_radian = EARTH_RADIUS_KM
    eps_rad = eps_km / kms_per_radian

    db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric='haversine')
    df['cluster_id'] = db.fit_predict(coords_rad)

    clusters = []
    unique_labels = set(df['cluster_id'])
    
    for label in unique_labels:
        if label == -1:
            continue
        
        cluster_df = df[df['cluster_id'] == label]
        centroid_lat = float(cluster_df['latitude'].mean())
        centroid_lng = float(cluster_df['longitude'].mean())
        
        # Most frequent crime type & division in cluster
        top_type = str(cluster_df['crime_type'].mode().iloc[0]) if not cluster_df['crime_type'].empty else "Mixed"
        top_div = str(cluster_df['division'].mode().iloc[0]) if not cluster_df['division'].empty else "District"
        
        clusters.append({
            "cluster_id": int(label),
            "crime_count": int(len(cluster_df)),
            "centroid_lat": round(centroid_lat, 6),
            "centroid_lng": round(centroid_lng, 6),
            "primary_crime_type": top_type,
            "division": top_div,
            "case_ids": cluster_df['case_id'].tolist()[:10],
            "risk_level": "High" if len(cluster_df) > 8 else ("Medium" if len(cluster_df) > 4 else "Low")
        })

    noise_count = int((df['cluster_id'] == -1).sum())
    
    return {
        "clusters": sorted(clusters, key=lambda x: x['crime_count'], reverse=True),
        "noise_count": noise_count,
        "total_clustered_crimes": len(df[df['cluster_id'] != -1])
    }

def evaluate_new_incident_patterns(new_crime, historical_crimes, radius_meters=1000):
    """
    Check a newly reported crime against historical records for:
    1. Spatial proximity (within radius_meters)
    2. Crime Type & MO match
    3. Repeat suspect ID match
    Returns alert dict or None.
    """
    new_lat = float(new_crime.get("latitude", 0.0))
    new_lng = float(new_crime.get("longitude", 0.0))
    new_type = str(new_crime.get("crime_type", "")).strip().lower()
    new_mo = str(new_crime.get("mo_signature", "")).strip().lower()
    new_suspect = str(new_crime.get("suspect_id", "")).strip()

    matched_cases = []

    for item in historical_crimes:
        if item.get("case_id") == new_crime.get("case_id"):
            continue
            
        h_lat = float(item.get("latitude", 0.0))
        h_lng = float(item.get("longitude", 0.0))
        dist_m = haversine_distance_meters(new_lat, new_lng, h_lat, h_lng)

        h_type = str(item.get("crime_type", "")).strip().lower()
        h_mo = str(item.get("mo_signature", "")).strip().lower()
        h_suspect = str(item.get("suspect_id", "")).strip()

        is_spatial_match = dist_m <= radius_meters and (new_type == h_type or new_type in h_type or h_type in new_type)
        is_mo_match = h_mo and new_mo and (new_mo in h_mo or h_mo in new_mo)
        is_suspect_match = new_suspect and h_suspect and (new_suspect == h_suspect)

        if is_spatial_match or is_mo_match or is_suspect_match:
            matched_cases.append({
                "case_id": item.get("case_id"),
                "crime_type": item.get("crime_type"),
                "date_time": item.get("date_time"),
                "distance_meters": round(dist_m, 1),
                "suspect_id": item.get("suspect_id"),
                "mo_signature": item.get("mo_signature"),
                "match_reason": "Suspect ID Match" if is_suspect_match else ("MO Pattern Match" if is_mo_match else "Spatial Proximity")
            })

    if len(matched_cases) >= 1:
        nearest_dist = min([m["distance_meters"] for m in matched_cases]) if matched_cases else radius_meters
        matched_ids = [m["case_id"] for m in matched_cases[:5]]
        
        alert_type = "Spatial Cluster Alert"
        if any(m["match_reason"] == "Suspect ID Match" for m in matched_cases):
            alert_type = "Repeat Suspect Alert"
        elif any(m["match_reason"] == "MO Pattern Match" for m in matched_cases):
            alert_type = "Modus Operandi Recurrence Alert"

        confidence = round(min(0.98, 0.65 + (len(matched_cases) * 0.08) + (0.2 if nearest_dist < 400 else 0.05)), 2)
        
        msg = f"Pattern Detected: {len(matched_cases)} similar {new_crime.get('crime_type')} incident(s) found within {int(nearest_dist)}m in {new_crime.get('division', 'area')}."

        return {
            "alert_id": f"ALT-{np.random.randint(1000, 9999)}",
            "case_id": new_crime.get("case_id", "NEW"),
            "alert_type": alert_type,
            "confidence_score": confidence,
            "matched_cases_count": len(matched_cases),
            "matched_case_ids": ", ".join(matched_ids),
            "matched_cases_detail": matched_cases[:5],
            "message": msg,
            "distance_meters": nearest_dist,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    return None
