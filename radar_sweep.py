import os
import pandas as pd
import requests
import time

# 1. Configuration & API Keys
LEGISCAN_KEY = os.getenv('LEGISCAN_API_KEY')

STATE_COORDS = {
    'AL': [32.806671, -86.79113], 'AK': [61.370716, -152.404419], 'AZ': [33.729759, -111.431221],
    'AR': [34.969704, -92.373123], 'CA': [36.116203, -119.681564], 'CO': [39.059811, -105.311104],
    'CT': [41.597782, -72.755371], 'DE': [39.318523, -75.507141], 'DC': [38.897438, -77.026817],
    'FL': [27.766279, -81.686783], 'GA': [33.040619, -83.643074], 'HI': [21.094318, -157.498337],
    'ID': [44.240459, -114.478828], 'IL': [40.349457, -88.986137], 'IN': [39.849426, -86.258278],
    'IA': [42.011539, -93.210526], 'KS': [38.526600, -96.726486], 'KY': [37.668140, -84.670067],
    'LA': [31.169546, -91.867805], 'ME': [44.693947, -69.381927], 'MD': [39.063946, -76.802101],
    'MA': [42.230171, -71.530106], 'MI': [43.326618, -84.536064], 'MN': [45.694454, -93.900192],
    'MS': [32.741646, -89.678696], 'MO': [38.456085, -92.288368], 'MT': [46.921925, -110.454353],
    'NE': [41.125370, -98.268082], 'NV': [38.313515, -117.055374], 'NH': [43.452492, -71.563896],
    'NJ': [40.298904, -74.521011], 'NM': [34.840515, -106.248482], 'NY': [42.165726, -74.948051],
    'NC': [35.630066, -79.806419], 'ND': [47.528912, -99.784012], 'OH': [40.388783, -82.764915],
    'OK': [35.565342, -96.928917], 'OR': [44.572021, -122.070938], 'PA': [40.590752, -77.209755],
    'RI': [41.680893, -71.511780], 'SC': [33.856892, -80.945007], 'SD': [44.299782, -99.438828],
    'TN': [35.747845, -86.692345], 'TX': [31.054487, -97.563461], 'UT': [40.150032, -111.862434],
    'VT': [44.045876, -72.710686], 'VA': [37.769337, -78.169968], 'WA': [47.400902, -121.490494],
    'WV': [38.491227, -80.954457], 'WI': [44.268543, -89.616508], 'WY': [42.755966, -107.302490],
    'PR': [18.220800, -66.590100]
}

def categorize_theme(content):
    """Assigns specific policy nuance based on keywords."""
    content = content.lower()
    if 'accessory dwelling' in content or 'adu' in content:
        return 'ADU Reform'
    if 'lot split' in content or 'subdivision' in content:
        return 'Administrative Lot Splits'
    if 'parking' in content:
        return 'Parking Minimums'
    if 'building code' in content or 'technical code' in content:
        return 'Building Code Adjustments'
    if 'transit oriented' in content or 'tod' in content:
        return 'Transit-Oriented Development'
    if 'middle housing' in content or 'duplex' in content or 'triplex' in content:
        return 'Middle Housing'
    return 'General Zoning/Housing'

def fetch_by_state(state_code):
    url = f"https://api.legiscan.com/?key={LEGISCAN_KEY}&op=getMasterList&state={state_code}"
    bills = []
    # Keywords that trigger the capture of the bill
    keywords = [
        'zoning', 'accessory dwelling', 'adu', 'lot split', 
        'middle housing', 'parking', 'building code', 'density'
    ]
    
    try:
        res = requests.get(url).json()
        masterlist = res.get('masterlist', {})
        for idx in masterlist:
            if idx == 'session': continue
            item = masterlist[idx]
            
            title = item.get('title', '')
            desc = item.get('description', '')
            content = f"{title} {desc}".lower()
            
            if any(k in content for k in keywords):
                coords = STATE_COORDS.get(state_code)
                bills.append({
                    'State': state_code,
                    'Identifier': item.get('number'),
                    # Apply the nuance function here
                    'Theme': categorize_theme(content),
                    'Summary': title,
                    'Status': item.get('last_action', 'Active'),
                    'Link': item.get('url'),
                    'Lat': coords[0],
                    'Lon': coords[1],
                    'Source': f'LegiScan {state_code}'
                })
        return bills
    except Exception as e:
        print(f"  Error for {state_code}: {e}")
        return []

if __name__ == "__main__":
    if not LEGISCAN_KEY:
        print("CRITICAL: LEGISCAN_API_KEY is missing.")
        exit(1)

    file_path = 'legislation_master.csv'
    all_rows = []
    
    print(f"Starting national sweep for {len(STATE_COORDS)} jurisdictions...")
    for state in STATE_COORDS.keys():
        print(f"Scanning {state}...")
        found = fetch_by_state(state)
        if found:
            print(f"  --> Success: Found {len(found)} relevant bills.")
            all_rows.extend(found)
        time.sleep(0.5)
    
    if all_rows:
        new_df = pd.DataFrame(all_rows)
        # Sort and save
        new_df.drop_duplicates(subset=['Link']).to_csv(file_path, index=False)
        print(f"\n✅ SWEEP COMPLETE: Wrote {len(new_df)} bills with nuanced themes.")
