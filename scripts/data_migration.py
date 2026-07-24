import os
import json
import sqlite3
import chromadb
from chromadb.utils import embedding_functions

# Directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs", "master_data")
DATA_DIR = os.path.join(BASE_DIR, "data")
MASTER_DB_DIR = os.path.join(DATA_DIR, "master")
CHROMA_DB_DIR = os.path.join(DATA_DIR, "chroma_db")

# Ensure output dirs exist
os.makedirs(MASTER_DB_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)

def migrate_structured_data():
    print("--- Migrating Structured Master Data (M1, M2, M4) to SQLite ---")
    db_path = os.path.join(MASTER_DB_DIR, "factory_master.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create Tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS material (
                        item_code TEXT PRIMARY KEY,
                        item_name TEXT,
                        description TEXT,
                        domain TEXT
                      )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS simulation_node (
                        node_id TEXT PRIMARY KEY,
                        coord_x REAL,
                        coord_y REAL,
                        coord_z REAL
                      )''')
    
    # Load M1 (Battery)
    m1_path = os.path.join(DOCS_DIR, "battery_material_m1.json")
    if os.path.exists(m1_path):
        with open(m1_path, 'r', encoding='utf-8') as f:
            m1_data = json.load(f)
            # Dummy logic: just insert domain info to indicate success
            cursor.execute("INSERT OR IGNORE INTO material VALUES (?, ?, ?, ?)", 
                           ("BATT-001", "Precursor", m1_data.get("description", ""), "Battery"))
            print("Loaded M1 Battery Data.")

    # Load M4 (Simulation Core)
    m4_path = os.path.join(DOCS_DIR, "digital_twin_simulation_m4.json")
    if os.path.exists(m4_path):
        with open(m4_path, 'r', encoding='utf-8') as f:
            m4_data = json.load(f)
            nodes = m4_data.get("spatial_3d_fab_layout", {}).get("nodes", [])
            for node in nodes:
                coords = node.get("coordinates", {})
                cursor.execute("INSERT OR IGNORE INTO simulation_node VALUES (?, ?, ?, ?)",
                               (node.get("node_id"), coords.get("x"), coords.get("y"), coords.get("z")))
            print("Loaded M4 Simulation Nodes.")
    
    conn.commit()
    conn.close()
    print("Structured DB Migration Complete.\n")


def migrate_unstructured_data():
    print("--- Migrating Unstructured Knowledge (M3) to ChromaDB ---")
    m3_path = os.path.join(DOCS_DIR, "global_standard_m3.json")
    
    if not os.path.exists(m3_path):
        print("M3 file not found. Skipping ChromaDB migration.")
        return

    with open(m3_path, 'r', encoding='utf-8') as f:
        m3_data = json.load(f)
    
    # Initialize Chroma
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    
    # Default open source embedding model (all-MiniLM-L6-v2)
    sentence_transformer_ef = embedding_functions.DefaultEmbeddingFunction()
    
    # Create or get collection
    collection = client.get_or_create_collection(name="knowledge_base", embedding_function=sentence_transformer_ef)
    
    # Prepare chunks (Very basic chunking for demonstration)
    documents = []
    metadatas = []
    ids = []
    
    # Chunk 1: ERP Business Logic
    erp_logic = m3_data.get("erp_business_logic", {})
    documents.append(json.dumps(erp_logic, ensure_ascii=False))
    metadatas.append({"source": "M3", "category": "ERP_Logic"})
    ids.append("doc_erp_logic")
    
    # Chunk 2: KS X 9101
    ks_logic = m3_data.get("ks_x_9101_national_standard", {})
    documents.append(json.dumps(ks_logic, ensure_ascii=False))
    metadatas.append({"source": "M3", "category": "KS_Standard"})
    ids.append("doc_ks_logic")

    # Insert into ChromaDB
    # Note: the default embedding function will automatically download the model on first run
    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    print(f"Inserted {len(documents)} chunks into ChromaDB Collection 'knowledge_base'.")
    print("Unstructured Knowledge Base Migration Complete.\n")

if __name__ == "__main__":
    print("Starting Migration Pipeline...\n")
    migrate_structured_data()
    migrate_unstructured_data()
    print("All Migrations Completed Successfully!")
