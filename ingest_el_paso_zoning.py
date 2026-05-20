import os
import re
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
# 16091 is the specific Municode Product/Client ID for El Paso, TX
MUNICODE_CLIENT_ID = "16091" 
BASE_API_URL = "https://library.municode.com/api/codeinfonext"
OUTPUT_DIR = "./el_paso_title_20_raw"
CSV_OUTPUT_PATH = "el_paso_zoning_text_master.csv"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_toc_node_id(client_id):
    """
    Fetches the root Table of Contents for El Paso to find the specific 
    internal Node ID designated for Title 20 - ZONING.
    """
    url = f"{BASE_API_URL}?clientId={client_id}"
    print(f"[*] Fetching root Table of Contents from Municode API...")
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        toc_data = response.json()
        
        # Traverse the TOC tree to find Title 20
        # Title 20 is usually under a primary 'children' or 'items' array
        for item in toc_data.get('items', []):
            title_text = item.get('title', '')
            if "TITLE 20" in title_text.upper() or "ZONING" in title_text.upper():
                print(f"[+] Found Target: {title_text} (Node ID: {item.get('id')})")
                return item.get('id')
                
        # Fallback to general search if the root layout varies
        print("[-] Could not automatically locate Title 20 Node ID in root list.")
        return None
    except Exception as e:
        print(f"[X] Error retrieving Table of Contents: {e}")
        return None

def fetch_section_content(client_id, node_id):
    """
    Hits the chunk endpoint to pull actual statutory text block content for a specific node.
    """
    url = f"{BASE_API_URL}/content?clientId={client_id}&nodeId={node_id}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[X] Error fetching text content for node {node_id}: {e}")
    return None

def clean_html_text(raw_html):
    """
    Parses Municode's embedded layout HTML into clean, readable plaintext.
    Removes standard web noise but preserves paragraph structure.
    """
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # Strip unnecessary scripts, styles, or specific Municode structural links
    for element in soup(["script", "style", "a"]):
        element.decompose()
        
    # Get raw text with standardized newline breaks
    text = soup.get_text(separator="\n")
    
    # Clean up excessive whitespace clusters
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def extract_recursive(client_id, current_node, master_data_list):
    """
    Recursively walks through every chapter, section, and sub-section item
    under Title 20 to ingest all corresponding text.
    """
    node_id = current_node.get('id')
    title = current_node.get('title', 'Unknown Title')
    heading = current_node.get('heading', '')
    
    print(f"[*] Processing: {heading} {title}".strip())
    
    # Check if this node has direct text content associated with it
    if current_node.get('hasContent', False) or 'content' in current_node:
        content_payload = fetch_section_content(client_id, node_id)
        if content_payload and 'content' in content_payload:
            raw_html = content_payload['content']
            clean_text = clean_html_text(raw_html)
            
            # Append record to our master dataset
            record = {
                "node_id": node_id,
                "heading": heading,
                "title": title,
                "raw_html": raw_html,
                "clean_text": clean_text
            }
            master_data_list.append(record)
            
            # Also save an isolated text file copy for local diffing/grep analysis
            safe_filename = "".join([c if c.isalnum() else "_" for c in f"{heading}_{title}"])[:100] + ".txt"
            with open(os.path.join(OUTPUT_DIR, safe_filename), "w", encoding="utf-8") as f:
                f.write(f"HEADING: {heading}\nTITLE: {title}\nNODE ID: {node_id}\n\n{clean_text}")
                
            # Throttle requests slightly to respect Municode servers
            time.sleep(0.5)

    # If the node has child nodes nested beneath it, crawl down them
    children = current_node.get('items', []) or current_node.get('children', [])
    for child in children:
        extract_recursive(client_id, child, master_data_list)

def main():
    master_records = []
    
    # Step 1: Discover Title 20 Node dynamically
    title_20_node_id = get_toc_node_id(MUNICODE_CLIENT_ID)
    
    # Fallback default: If dynamic fetch fails, historical API profiles indicate
    # El Paso Title 20 frequently cascades from root navigation objects.
    if not title_20_node_id:
        print("[!] Using manual baseline crawling attempt on root node tree...")
        # We fetch the primary dynamic navigation metadata structure
        url = f"{BASE_API_URL}/navigation?clientId={MUNICODE_CLIENT_ID}"
        response = requests.get(url)
        root_tree = response.json()
        title_20_node = next((item for item in root_tree.get('items', []) if "TITLE 20" in item.get('title', '').upper()), None)
        if title_20_node:
            title_20_node_id = title_20_node.get('id')
            
    if not title_20_node_id:
        print("[X] Execution Halted: Unable to resolve Title 20 Node ID from Municode API.")
        return

    # Step 2: Grab the complete specific nested branch structure for Title 20
    print(f"[*] Ingesting complete branch structure for Node ID: {title_20_node_id}")
    branch_url = f"{BASE_API_URL}?clientId={MUNICODE_CLIENT_ID}&nodeId={title_20_node_id}"
    branch_response = requests.get(branch_url)
    branch_data = branch_response.json()

    # Step 3: Crawl and extract text recursively
    extract_recursive(MUNICODE_CLIENT_ID, branch_data, master_records)
    
    # Step 4: Compile results into a structured Master CSV
    if master_records:
        df = pd.DataFrame(master_records)
        df.to_csv(CSV_OUTPUT_PATH, index=False, encoding='utf-8')
        print(f"\n[+++] INGESTION COMPLETE [+++]")
        print(f"-> Individual text files saved to directory: '{OUTPUT_DIR}'")
        print(f"-> Comprehensive tabular data compiled to: '{CSV_OUTPUT_PATH}' ({len(df)} sections mapped).")
    else:
        print("[X] Finished process, but no text content records were extracted.")

if __name__ == "__main__":
    main()