import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_backend():
    print("Testing KSP Backend Endpoints...")
    
    # 1. Test /api/crimes with Kannada query
    queries = [
        "ಮೈಸೂರಿನಲ್ಲಿ ಕಳವು",
        "ವಾಹನ ಕಳವು",
        "ಬೆಂಗಳೂರು ದರೋಡೆ",
        "ಸೈಬರ್",
        "ಕೊಲೆ",
        "Vehicle Theft"
    ]

    for q in queries:
        try:
            r = requests.get(f"{BASE_URL}/api/crimes", params={"q": q, "limit": 10}, timeout=5)
            r.raise_for_status()
            data = r.json()
            print(f"[OK] Query '{q}': count={data.get('count', 0)}")
        except Exception as e:
            print(f"[FAIL] Query '{q}': {e}")

    # 2. Test /api/ai/chat with Kannada prompt
    ai_prompts = [
        "ಮೈಸೂರಿನಲ್ಲಿ ಕಳವು ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ",
        "ವಾಹನ ಕಳವು ಪ್ರಕರಣಗಳು",
        "Show theft cases in Mysuru"
    ]

    for prompt in ai_prompts:
        try:
            r = requests.post(f"{BASE_URL}/api/ai/chat", json={"question": prompt}, timeout=5)
            r.raise_for_status()
            data = r.json()
            print(f"[OK] AI Chat '{prompt}': count={data.get('result_count', 0)}, SQL={data.get('generated_sql')}")
        except Exception as e:
            print(f"[FAIL] AI Chat '{prompt}': {e}")

    # 3. Test /api/ai/network_graph
    try:
        r = requests.get(f"{BASE_URL}/api/ai/network_graph", timeout=5)
        r.raise_for_status()
        data = r.json()
        print(f"[OK] Network Graph: nodes={data.get('data', {}).get('nodes_count')}, insights={bool(data.get('data', {}).get('companion_insight_en'))}")
    except Exception as e:
        print(f"[FAIL] Network Graph: {e}")

if __name__ == "__main__":
    test_backend()
