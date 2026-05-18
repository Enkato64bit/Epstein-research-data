#!/usr/bin/env python3
"""
View an EFTA document with syntax highlighting.
Supports EML (emails), TSV (spreadsheets), and general text.
"""
import sqlite3
import sys
import re
import os

def _find_data_dir():
    """Find the directory containing the database files."""
    if os.environ.get("EPSTEIN_DATA_DIR"):
        return os.environ["EPSTEIN_DATA_DIR"]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(repo_root, "data")
    if os.path.exists(os.path.join(data_dir, "full_text_corpus.db")):
        return data_dir
    if os.path.exists(os.path.join(repo_root, "full_text_corpus.db")):
        return repo_root
    return os.getcwd()

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/view_doc.py <EFTA_NUMBER>")
        print("Example: python3 tools/view_doc.py EFTA00014026")
        return

    efta = sys.argv[1].upper()
    data_dir = _find_data_dir()
    db_path = os.path.join(data_dir, "full_text_corpus.db")
    trans_path = os.path.join(data_dir, "transcripts.db")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT page_number, text_content FROM pages WHERE efta_number = ? ORDER BY page_number", (efta,))
    rows = c.fetchall()
    
    if not rows and os.path.exists(trans_path):
        # Check transcripts database if not in corpus
        tc = sqlite3.connect(trans_path)
        row = tc.execute("SELECT transcript FROM transcripts WHERE efta_number = ?", (efta,)).fetchone()
        if row: rows = [(1, row[0])]
        tc.close()

    if not rows:
        print(f"Document {efta} not found.")
        conn.close()
        return

    full_text = "\n".join([r[1] for r in rows if r[1]])
    conn.close()

    try:
        from rich.console import Console
        from rich.syntax import Syntax
        from rich.panel import Panel
        
        console = Console()
        
        # Detect format
        lexer = "text"
        if re.search(r"^(From|To|Subject|Date):", full_text, re.MULTILINE | re.IGNORECASE):
            lexer = "email"
        elif "\t" in full_text:
            lexer = "tsv"
            
        syntax = Syntax(full_text, lexer, theme="monokai", line_numbers=True, word_wrap=True)
        console.print(Panel(syntax, title=f"[bold yellow]Document: {efta}[/bold yellow]", expand=False))
        
    except ImportError:
        print("\033[93mTip: Install 'rich' for professional highlighting: pip install rich\033[0m")
        for page_num, text in rows:
            print(f"\n--- Page {page_num} ---")
            print(text)

if __name__ == "__main__":
    main()