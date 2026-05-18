#!/usr/bin/env python3
"""
General FTS5 search utility for the Epstein Project.
Usage: python3 tools/search_fts.py "your keyword"
"""
import sqlite3
import sys
import os
import argparse
import re
import time
from utils import get_base_dir, save_query_interactive, save_query_silent

def main():
    parser = argparse.ArgumentParser(description="Search the corpus using FTS5")
    parser.add_argument("query", help="Keyword or FTS5 query string")
    parser.add_argument("--limit", type=int, default=20, help="Limit results (default 20, use 0 for all)")
    parser.add_argument("--full", action="store_true", help="Output complete OCR text for matching documents")
    parser.add_argument("--auto-page", action="store_true", help="Automatically show next page of results without prompting")
    parser.add_argument("--page-delay", type=float, default=0.5, help="Delay (seconds) between pages in auto-page mode")
    parser.add_argument("--sort-date", action="store_true", help="Sort results by date (requires concordance_complete.db)")
    parser.add_argument("--auto-save", action="store_true", help="Automatically save results to file (Filename = <query>_db_results)")
    args = parser.parse_args()

    base_dir = get_base_dir()
    db_path = os.path.join(base_dir, "full_text_corpus.db")
    conc_path = os.path.join(base_dir, "concordance_complete.db")

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Attach concordance if sorting by date is requested
    if args.sort_date:
        if os.path.exists(conc_path):
            cur.execute(f"ATTACH DATABASE '{conc_path}' AS conc")
        else:
            print(f"Warning: Concordance DB not found at {conc_path}. Sorting by rank instead.")
            args.sort_date = False
    
    # Escape special FTS5 characters in the query if they are meant to be literal.
    # The dot '.' is a special character in FTS5 query syntax.
    # If the query is a quoted phrase containing a dot, replace the dot with a space
    # to avoid syntax errors, effectively searching for the word part.
    processed_query = args.query.replace('.', ' ') if args.query.startswith('"') and args.query.endswith('"') else args.query
    if args.full:
        sql_base = """
            SELECT DISTINCT efta_number
            FROM pages_fts 
            WHERE text_content MATCH ? 
        """
    else:
        select_cols = "p.efta_number, p.page_number, snippet(pages_fts, 2, '>>>', '<<<', '...', 30)"
        from_clause = "pages_fts JOIN pages p ON p.rowid = pages_fts.rowid"
        
        if args.sort_date:
            select_cols = "p.efta_number, p.page_number, snippet(pages_fts, 2, '>>>', '<<<', '...', 30), c.date_sent"
            from_clause = "pages_fts JOIN pages p ON p.rowid = pages_fts.rowid JOIN conc.documents c ON p.efta_number = c.efta_number"

        sql_base = f"""
            SELECT {select_cols}
            FROM {from_clause}
            WHERE pages_fts MATCH ? 
        """

    sql = sql_base + (" ORDER BY c.date_sent DESC" if args.sort_date else " ORDER BY rank")
    params = [processed_query]
    
    if args.limit > 0:
        sql += " LIMIT ?"
        params.append(args.limit)

    try:
        # Using the cursor as an iterator streams results from the database
        # instead of loading them all into memory, managing resources for large hit sets.
        cur.execute(sql, params)
        
        count = 0
        found_any = False
        results_list = []

        # Prepare highlighting regex for full mode
        terms = []
        if args.full:
            # Remove FTS5 operators but keep asterisk for highlighting logic
            clean_query = re.sub(r'[()"]', ' ', args.query)
            terms = [t for t in clean_query.split() if t.lower() not in ('and', 'or', 'not', 'near', 'near/')]

        for row in cur:
            if count == 0:
                print(f"\n--- Search results for: \033[1;33m{args.query}\033[0m ---\n")
            
            found_any = True
            
            if args.full:
                efta = row[0]
                # Fetch all pages for this document using a separate cursor
                page_cur = conn.cursor()
                page_cur.execute("SELECT page_number, text_content FROM pages WHERE efta_number = ? ORDER BY page_number", (efta,))
                
                doc_text_parts = []
                for p_num, p_text in page_cur:
                    if not p_text: continue
                    p_header = f"\n\033[1;32m--- Page {p_num} ---\033[0m\n"
                    
                    # Highlight matches in the page text
                    highlighted_p = p_text
                    for t in terms:
                        if len(t) < 3: continue
                        if t.endswith('*'):
                            # Match the prefix plus any word characters
                            pattern = re.compile(rf"({re.escape(t[:-1])}\w*)", re.IGNORECASE)
                        else:
                            pattern = re.compile(rf"({re.escape(t)})", re.IGNORECASE)
                        highlighted_p = pattern.sub(r"\033[1;31m\1\033[0m", highlighted_p)
                    
                    doc_text_parts.append(p_header + highlighted_p)

                full_output = "\n".join(doc_text_parts)
                
                try:
                    from rich.console import Console
                    from rich.panel import Panel
                    from rich.text import Text
                    
                    console = Console()
                    rich_text = Text.from_ansi(full_output)
                    console.print(Panel(rich_text, title=f"[bold blue]Document: {efta}[/bold blue]", border_style="blue", expand=False))
                except ImportError:
                    print(f"\n\033[1;34m=== Document: {efta} ===\033[0m")
                    print(full_output)
                    print(f"\n\033[1;34m{'='*40}\033[0m\n")
                
                page_cur.close()
                results_list.append({"efta": efta, "type": "full_document"})
            else:
                efta, page, snip = row
                # Highlight markers in Red Bold (\033[1;31m) and document ID in Blue (\033[1;34m)
                highlighted = snip.replace('>>>', '\033[1;31m').replace('<<<', '\033[0m')
                clean_snip = highlighted.replace('\n', ' ').strip()
                print(f"\033[1;34m{efta}\033[0m (p{page}): {clean_snip}")
                print("-" * 40)
                results_list.append({"efta": efta, "page": page, "snippet": snip})
            
            count += 1
            
            # Implement basic pagination every 50 results if showing all and in an interactive terminal
            if args.limit == 0 and count % 50 == 0 and sys.stdout.isatty():
                try:
                    if args.auto_page:
                        print(f"\n[Auto-paging] Shown {count} results... pausing {args.page_delay}s for throttle")
                        time.sleep(args.page_delay)
                    else:
                        user_choice = input(f"\nShown {count} results. Press Enter for more, or 'q' to quit: ")
                        if user_choice.lower().startswith('q'):
                            break
                except (EOFError, KeyboardInterrupt):
                    break

        if found_any:
            print(f"\n--- Search complete. {count} hits shown ---\n")

            if args.auto_save:
                save_query_silent(args.query, results_list)
            else:
                save_query_interactive(args.query, results_list)
        else:
            print(f"No matches found for: {args.query}")

    except sqlite3.OperationalError as e:
        print(f"Search error: {e}")
        print("Tip: If searching for multiple words, wrap them in double quotes like '\"word1 word2\"'")
    finally:
        conn.close()

if __name__ == "__main__":
    main()