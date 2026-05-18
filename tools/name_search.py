#!/usr/bin/env python3
"""Search for known names/entities across all OCR'd documents"""
import sqlite3
import json
import re
from pathlib import Path
import os

def _find_data_dir():
    """Find the directory containing the database files."""
    if os.environ.get("EPSTEIN_DATA_DIR"):
        return os.environ["EPSTEIN_DATA_DIR"]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Check for /data subdirectory first as per v5.2 setup
    data_dir = os.path.join(repo_root, "data")
    if os.path.exists(os.path.join(data_dir, "full_text_corpus.db")):
        return data_dir
        
    if os.path.exists(os.path.join(repo_root, "full_text_corpus.db")):
        return repo_root
    if os.path.exists(os.path.join(os.getcwd(), "full_text_corpus.db")):
        return os.getcwd()
    parent = os.path.dirname(os.getcwd())
    for name in os.listdir(parent) if os.path.exists(parent) else []:
        candidate = os.path.join(parent, name, "full_text_corpus.db")
        if os.path.exists(candidate):
            return os.path.join(parent, name)
    return os.getcwd()

_DATA_DIR = _find_data_dir()
DB_PATH = os.path.join(_DATA_DIR, "full_text_corpus.db")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINDINGS_PATH = os.path.join(REPO_ROOT, "evidence_findings.jsonl")
OUTPUT_PATH = os.path.join(_DATA_DIR, "name_crossref.jsonl")

def extract_names_from_findings():
    """Extract all names from our evidence findings"""
    names = set()
    
    try:
        with open(FINDINGS_PATH, 'r') as f:
            for line in f:
                try:
                    finding = json.loads(line)
                    data = finding.get('data', {})
                    if isinstance(data, dict):
                        for key, val in data.items():
                            if isinstance(val, str) and len(val) > 2:
                                if any(word in key.lower() for word in ['name', 'manager', 'accountant', 'attorney', 'pilot', 'escort']):
                                    names.add(val.strip())
                except:
                    continue
    except FileNotFoundError:
        print(f"Warning: {FINDINGS_PATH} not found. Using hardcoded names only.")

    important_names = [
        "Epstein", "Maxwell", "Ghislaine", "Jeffrey",
        "Bedminster", "John Bedminster", "Maurice Bedminster", "Hilian Bedminster",
        "Gaillard", "Sylvester Gaillard", "Leon Black", "Debra Black", "Melanie Spinella",
        "Darren Indyke", "Richard Kahn", "Mark Tollison", "Lesley Groff", "Leslie Groff",
        "Ann Rodriguez", "Carlos Rodriguez", "Monique Rodriguez", "Daphne Wallace", 
        "Cecile deJongh", "Jeanne Brennan", "Larry Visoski", "Jermaine Ruan",
        "Clinton", "Trump", "Prince Andrew", "Alan Dershowitz", "Jean-Luc Brunel", 
        "Les Wexner", "Basillia Morales", "Basila Morales", "Pierre Jules", "Myla Trestiza",
        "Southern Trust", "HBRK", "LSJE", "Zorro Ranch", "Little St. James", "Avenue Foch"
    ]
    names.update(important_names)
    return list(names)

def search_names():
    """Search for all names in OCR database"""
    names = extract_names_from_findings()
    print(f"Searching for {len(names)} names/entities...")
    print(f"Using database: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    results = []
    
    for name in names:
        if len(name) < 3:
            continue
        try:
            # Use FTS5 for optimized searching as requested
            c.execute("""SELECT efta_number, text_content FROM pages_fts 
                        WHERE text_content MATCH ?""", (f'"{name}"',))
            matches = c.fetchall()
            
            if matches:
                for efta, text_content in matches:
                    idx = text_content.lower().find(name.lower())
                    if idx == -1: idx = 0 # Fallback if FTS match doesn't align with simple find
                    
                    start = max(0, idx - 50)
                    end = min(len(text_content), idx + len(name) + 50)
                    context = text_content[start:end]
                    
                    results.append({
                        'name': name,
                        'efta': efta,
                        'context': context,
                        'full_match': True
                    })
                print(f"  '{name}': {len(matches)} matches")
        except Exception as e:
            print(f"  Error searching '{name}': {e}")
    
    with open(OUTPUT_PATH, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    
    print(f"\nWrote {len(results)} cross-references to {OUTPUT_PATH}")
    conn.close()

if __name__ == "__main__":
    search_names()