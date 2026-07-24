import os
import json
import urllib.request
import urllib.error

# Config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs", "master_data")
API_BASE = "http://localhost:8080/api/v1/master"

def post_json(endpoint, payload):
    req = urllib.request.Request(
        f"{API_BASE}/{endpoint}",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 409:
            print(f"Skipping {payload.get('type_id') or payload.get('master_code')} - Already exists.")
        else:
            print(f"Failed to post to {endpoint}. Code: {e.code}, Reason: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")

def run_migration():
    print("--- Starting API-based Master Data Migration ---")
    
    # 1. Create Types
    print("Creating Master Types...")
    post_json("types", {
        "type_id": "material",
        "name_ko": "품목 마스터",
        "description": "배터리, 동제련 등 핵심 생산 자재 규격",
        "attr_schema": {}
    })
    post_json("types", {
        "type_id": "simulation_node",
        "name_ko": "시뮬레이션 물리 노드",
        "description": "디지털 트윈을 위한 X,Y,Z 3D 공간 제약 데이터",
        "attr_schema": {}
    })
    
    # 2. Insert Records
    print("\nInserting Master Records (Golden Core)...")
    
    # Load M1
    m1_path = os.path.join(DOCS_DIR, "battery_material_m1.json")
    if os.path.exists(m1_path):
        with open(m1_path, 'r', encoding='utf-8') as f:
            m1_data = json.load(f)
            post_json("records", {
                "master_code": "BATT-001",
                "type_id": "material",
                "name": "NCM Battery Precursor (M1)",
                "attributes": m1_data,
                "domains": ["battery", "production"],
                "aliases": ["전구체", "배터리소재"],
                "is_core": True
            })
    
    # Load M4
    m4_path = os.path.join(DOCS_DIR, "digital_twin_simulation_m4.json")
    if os.path.exists(m4_path):
        with open(m4_path, 'r', encoding='utf-8') as f:
            m4_data = json.load(f)
            nodes = m4_data.get("spatial_3d_fab_layout", {}).get("nodes", [])
            for node in nodes:
                node_id = node.get("node_id", "UNKNOWN")
                post_json("records", {
                    "master_code": node_id.upper(),
                    "type_id": "simulation_node",
                    "name": f"3D Node: {node_id}",
                    "attributes": node,
                    "domains": ["simulation", "logistics"],
                    "aliases": [],
                    "is_core": True
                })
                
    print("\nMigration Completed Successfully.")

if __name__ == "__main__":
    run_migration()
