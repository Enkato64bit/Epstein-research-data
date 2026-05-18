import os
import json
import sqlite3

def get_base_dir():
    """Centralized directory discovery for the project."""
    if os.environ.get("EPSTEIN_DATA_DIR"):
        return os.environ["EPSTEIN_DATA_DIR"]
    
    # Discover from current file location (tools/utils.py)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Check for /data subdirectory (v5.2 standard)
    data_dir = os.path.join(repo_root, "data")
    if os.path.exists(os.path.join(data_dir, "full_text_corpus.db")):
        return data_dir
        
    if os.path.exists(os.path.join(repo_root, "full_text_corpus.db")):
        return repo_root
        
    return os.getcwd()

def save_query_interactive(query_term, results):
    """
    Global interactive prompt to save search results to a persistent database.
    """
    if not results:
        return

    prompt = f"\nDo you want to export query results for '{query_term}' to the 'saved_queries_db'? Press Y for Yes, N for No: "
    choice = input(prompt).strip().upper()
    
    if choice == 'Y':
        note_prompt = "Do you want to attach a note to the query results? Press Y for Yes, N for No: "
        note_choice = input(note_prompt).strip().upper()
        
        note = ""
        if note_choice == 'Y':
            note = input("Enter note: ").strip()
            
        base_dir = get_base_dir()
        output_dir = os.path.join(base_dir, "query-output")
        os.makedirs(output_dir, exist_ok=True)
        db_path = os.path.join(output_dir, "saved_queries_db.db")
        
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_term TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    note TEXT,
                    raw_data TEXT
                )
            """)
            
            raw_data = json.dumps(results, default=lambda x: list(x) if isinstance(x, set) else str(x))
            cur.execute("INSERT INTO saved_queries (query_term, note, raw_data) VALUES (?, ?, ?)",
                        (query_term, note, raw_data))
            conn.commit()
            conn.close()
            print(f"Results successfully saved to {db_path}")
        except Exception as e:
            print(f"Error saving to global database: {e}")

def save_query_silent(query_term, results):
    """
    Automatically saves query results to a JSON file in the data directory.
    """
    base_dir = get_base_dir()
    filename = f"{query_term}_db_results.json".replace(" ", "_").replace("*", "star")
    file_path = os.path.join(base_dir, filename)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=lambda x: list(x) if isinstance(x, set) else str(x))
        print(f"\nResults automatically saved to: {file_path}")
    except Exception as e:
        print(f"Error during automatic save: {e}")