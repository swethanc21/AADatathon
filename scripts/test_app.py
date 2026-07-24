import os
import sys
import unittest
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from backend.ml_engine import run_dbscan_clustering, haversine_distance_meters
from backend.ai_assistant import text_to_sql_query, generate_criminal_network_graph

class TestKSPPlatform(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_haversine(self):
        # Bengaluru MG Road to Vidhana Soudha ~1.8km
        dist = haversine_distance_meters(12.9756, 77.6066, 12.9796, 77.5906)
        print(f"Calculated Haversine distance: {dist:.1f} meters")
        self.assertGreater(dist, 1000)
        self.assertLess(dist, 3000)

    def test_crimes_api(self):
        res = self.client.get("/api/crimes?limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(len(data["data"]), 1)
        print(f"Crimes API returned {len(data['data'])} records.")

    def test_dashboard_api(self):
        res = self.client.get("/api/stats/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("kpi", data)
        self.assertGreater(data["kpi"]["total_crimes"], 5000)
        print("Dashboard KPI stats verified successfully!")

    def test_field_report_and_ml_alert(self):
        payload = {
            "crime_type": "Domestic Violence",
            "division": "Bengaluru Rural",
            "city": "Devanahalli",
            "station_id": "Vijayapura PS",
            "latitude": 13.431000,
            "longitude": 77.538500,
            "severity": "High",
            "amount_involved": 50000.0,
            "mo_signature": "Domestic dispute argument escalation",
            "description": "Field test report for ML pattern detection verification"
        }
        res = self.client.post("/api/crimes/report", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("case_id", data)
        print(f"Incident reported successfully with Case ID: {data['case_id']}")

    def test_ai_text_to_sql(self):
        # 1. English query via LLM pipeline
        res_en = self.client.post("/api/ai/chat", json={"question": "Show all robbery cases in Mysuru"})
        self.assertEqual(res_en.status_code, 200)
        data_en = res_en.json()
        self.assertEqual(data_en["status"], "success")
        self.assertIn("generated_sql", data_en)
        self.assertIn("narrative_english", data_en)
        self.assertIn("audio_url", data_en)
        print(f"LLM Text-to-SQL Generated (English): {data_en['generated_sql']}")
        print(f"LLM Narrative: {data_en['narrative_english']}")
        print(f"TTS Audio URL: {data_en['audio_url']}")

        # 2. Kannada query via LLM pipeline
        res_kn = self.client.post("/api/ai/chat", json={"question": "ಮೈಸೂರಿನಲ್ಲಿ ಕಳವು ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ"})
        self.assertEqual(res_kn.status_code, 200)
        data_kn = res_kn.json()
        self.assertEqual(data_kn["status"], "success")
        self.assertTrue(data_kn["is_kannada_input"])
        print(f"Kannada LLM Narrative: {data_kn.get('narrative_kannada', 'N/A').encode('ascii', errors='replace').decode()}")

    def test_ai_transcribe_endpoint(self):
        """Test Bhashini ASR (mock) endpoint with a dummy audio upload."""
        dummy_audio = b'\x00' * 1024  # Simulated audio bytes
        res = self.client.post(
            "/api/ai/transcribe",
            files={"file": ("test_audio.wav", dummy_audio, "audio/wav")},
            data={"language": "kn-IN"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("transcribed_text", data)
        print(f"ASR Transcribed Text: {data['transcribed_text'].encode('ascii', errors='replace').decode()}")

    def test_criminal_network_graph(self):
        res = self.client.get("/api/ai/network_graph?limit=50")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertGreater(data["nodes_count"], 0)
        print(f"Criminal Network Graph built with {data['nodes_count']} nodes and {data['edges_count']} edges.")

if __name__ == "__main__":
    unittest.main()
