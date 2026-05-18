#!/usr/bin/env python3
"""Classify documents by type based on OCR content"""
import sqlite3
import json
import re
from pathlib import Path

import os
import time

def _find_data_dir():
    """Find the directory containing the database files."""
    if os.environ.get("EPSTEIN_DATA_DIR"):
        return os.environ["EPSTEIN_DATA_DIR"]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Standard v5.2 /data subdirectory
    data_dir = os.path.join(repo_root, "data")
    if os.path.exists(os.path.join(data_dir, "full_text_corpus.db")):
        return data_dir

    parent = os.path.dirname(os.getcwd())
    for name in os.listdir(parent):
        candidate = os.path.join(parent, name, "full_text_corpus.db")
        if os.path.exists(candidate):
            return os.path.join(parent, name)
    return os.getcwd()

_DATA_DIR = _find_data_dir()
CORPUS_DB = os.path.join(_DATA_DIR, "full_text_corpus.db")
OUTPUT_PATH = os.path.join(_DATA_DIR, "document_classifications.jsonl")
PRIORITY_PATH = os.path.join(_DATA_DIR, "priority_documents.jsonl")

# Document type patterns
PATTERNS = {
    'employee_roster': [r'employee', r'staff', r'payroll', r'roster', r'personnel'],
    'financial': [r'invoice', r'payment', r'account', r'balance', r'transfer', r'bank', r'\$\d+', r'amount'],
    'legal': [r'attorney', r'contract', r'agreement', r'notary', r'witness', r'court', r'deposition'],
    'correspondence': [r'dear\s', r'sincerely', r'regards', r'letter', r'memo', r'from:', r'to:'],
    'flight_log': [r'flight', r'passenger', r'pilot', r'aircraft', r'departure', r'arrival', r'tail\s*number'],
    'phone_records': [r'phone', r'call', r'voicemail', r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', r'dial'],
    'visitor_log': [r'visitor', r'guest', r'arrival', r'check.?in'],
    'property': [r'property', r'deed', r'real estate', r'mortgage', r'title'],
    'medical': [r'medical', r'prescription', r'doctor', r'patient', r'diagnosis', r'rx'],
    'thank_you_letter': [r'thank you', r'thanks', r'grateful', r'appreciate'],
    'contact_info': [r'emergency contact', r'address', r'phone number', r'email'],
    'corporate': [r'corporation', r'llc', r'inc\.', r'board', r'director', r'shareholder'],
    'schedule': [r'schedule', r'calendar', r'appointment', r'meeting', r'agenda'],
    'photo_metadata': [r'photo', r'image', r'picture', r'camera'],
}

# High priority indicators
HIGH_PRIORITY = [
    r'minor', r'underage', r'young', r'girl', r'teen',
    r'massage', r'recruit',
    r'prince', r'clinton', r'trump', r'president', r'senator', r'governor',
    r'settlement', r'nda', r'confidential',
    r'destroy', r'shred', r'delete', r'cover',
    r'victim', r'complaint', r'assault',
    r'passport', r'visa', r'immigration',
]

def classify_document(text):
    """Classify document based on content patterns"""
    text_lower = text.lower()
    
    classifications = []
    priority_score = 0
    priority_matches = []
    
    # Check document type patterns
    for doc_type, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                classifications.append(doc_type)
                break
    
    # Check priority indicators
    for pattern in HIGH_PRIORITY:
        matches = re.findall(pattern, text_lower)
        if matches:
            priority_score += len(matches) * 10
            priority_matches.extend(matches)
    
    return {
        'types': list(set(classifications)),
        'priority_score': priority_score,
        'priority_matches': list(set(priority_matches))
    }

def get_db_version(conn):
    """Determine the database version based on schema."""
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(pages)")
        columns = [col[1] for col in c.fetchall()]
        if "text_content" in columns:
            return "5.2"
    except sqlite3.OperationalError:
        pass # 'pages' table might not exist

    try:
        c.execute("PRAGMA table_info(ocr_results)")
        columns = [col[1] for col in c.fetchall()]
        if "text" in columns: # Assuming 'text' column for OCR results in v4.0
            return "4.0"
    except sqlite3.OperationalError:
        pass # 'ocr_results' table might not exist
    
    return "unknown"


def main():
    print("Classifying documents...")
    
    conn = sqlite3.connect(CORPUS_DB)
    c = conn.cursor()
    
    db_version = get_db_version(conn)
    print(f"Detected database version: {db_version}")

    if db_version == "5.2":
        query = "SELECT efta_number, text_content, '' FROM pages WHERE text_content IS NOT NULL AND text_content != ''"
        doc_id_col = 0 # efta_number
        text_col = 1 # text_content
        path_col = 2 # empty string
    elif db_version == "4.0":
        query = "SELECT bates, text, image_path FROM ocr_results WHERE text IS NOT NULL AND text != ''"
        doc_id_col = 0 # bates
        text_col = 1 # text
        path_col = 2 # image_path
    else:
        print("ERROR: Unsupported database version or schema not recognized. Please ensure full_text_corpus.db or ocr_database.db is present and valid.")
        conn.close()
        return

    # Get a count for the progress bar
    c.execute(f"SELECT COUNT(*) FROM ({query})") # Use subquery to count based on the actual query
    total_rows = c.fetchone()[0]
    print(f"Processing {total_rows:,} pages...")

    c.execute(query)
    
    priority_docs = []
    
    type_counts = {}
    processed_count = 0
    start_time = time.time()

    with open(OUTPUT_PATH, 'w') as f:
        for row in c:
            doc_id = row[doc_id_col]
            text = row[text_col]
            path = row[path_col]

            result = classify_document(text)
        
            doc = {
                'doc_id': doc_id, # Use generic 'doc_id' for version compatibility
                'path': path,
                'types': result['types'],
                'priority_score': result['priority_score'],
                'priority_matches': result['priority_matches']
            }
            
            # Write immediately to disk to save memory
            f.write(json.dumps(doc) + '\n')
            
            if result['priority_score'] > 0:
                priority_docs.append(doc)
            
            for t in result['types']:
                type_counts[t] = type_counts.get(t, 0) + 1
                
            processed_count += 1
            if processed_count % 1000 == 0:
                elapsed = time.time() - start_time
                rate = processed_count / elapsed
                eta = (total_rows - processed_count) / rate / 60
                print(f"  Processed {processed_count:,} / {total_rows:,} ({processed_count/total_rows*100:.1f}%) | ETA: {eta:.1f} min", end='\r')

    print(f"\n\nClassification complete in {(time.time() - start_time)/60:.1f} minutes.")
    # Write priority documents sorted by score
    priority_docs.sort(key=lambda x: -x['priority_score'])
    with open(PRIORITY_PATH, 'w') as f:
        for doc in priority_docs:
            f.write(json.dumps(doc) + '\n')
    
    print(f"\nDocument type distribution:")
    for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {dtype}: {count}")
    
    print(f"\nHigh priority documents: {len(priority_docs)}")
    print(f"Top 10 priority documents:")
    for doc in priority_docs[:10]:
        print(f"  {doc['doc_id']}: score={doc['priority_score']}, matches={doc['priority_matches']}")
    
    print(f"\nResults saved to:")
    print(f"  {OUTPUT_PATH}")
    print(f"  {PRIORITY_PATH}")
    
    conn.close()

if __name__ == "__main__":
    main()
