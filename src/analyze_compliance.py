import os
import re
import pandas as pd

# --- CONFIGURATION ---
CSV_INPUT_PATH = "el_paso_zoning_text_master.csv"
COMPLIANCE_REPORT_PATH = "el_paso_compliance_audit_report.csv"

# Define the State-Level Mandate Thresholds to test local code against
STATE_MANDATES = {
    "parking_decoupling": {
        "bill_id": "SB 15 Framework (Parking Caps)",
        "max_allowable_parking_per_unit": 1.0,
        "keywords": ["parking requirement", "off-street parking", "parking space", "stalls"]
    },
    "lot_size_reform": {
        "bill_id": "SB 15 Framework (Minimum Lot Area)",
        "max_allowable_min_lot_size_sqft": 2500,
        "keywords": ["minimum lot area", "lot area per dwelling", "minimum square feet", "sq. ft. per unit"]
    },
    "commercial_conversions": {
        "bill_id": "SB 840 Framework (Commercial-to-Residential)",
        "mandate_intent": "Allow multifamily housing in commercial/office zones by-right without rezoning.",
        "keywords": ["permitted use", "commercial district", "office district", "special permit", "prohibited"]
    },
    "adu_streamlining": {
        "bill_id": "Statewide ADU Mandate",
        "mandate_intent": "Permit accessory dwelling units administratively; eliminate subjective design restrictions and owner-occupancy requirements.",
        "keywords": ["accessory building", "secondary unit", "accessory dwelling", "owner occupancy", "architectural compatibility"]
    }
}

def load_zoning_data(file_path):
    """Loads the master scraped code dataset from the ingestion script."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"[X] Master zoning text data file '{file_path}' not found. Please run ingestion first.")
    return pd.read_csv(file_path)

def extract_numerical_metric(text, pattern_regex, default_val=None):
    """
    Attempts to pull structural numerical patterns (like parking counts or square footages)
    out of raw municipal statutory paragraphs using regex matches.
    """
    matches = re.findall(pattern_regex, text, re.IGNORECASE)
    if matches:
        try:
            # Grab the first match and extract digits/decimals
            num_str = re.findall(r"[-+]?\d*\.\d+|\d+", matches[0])
            if num_str:
                return float(num_str[0])
        except ValueError:
            pass
    return default_val

def generate_amendment_draft(category, section_heading, bill_id):
    """Drafts targeted overriding statutory text tailored to the specific code break."""
    base_override = f"/* AMENDMENT REQUIRED FOR COMPLIANCE WITH {bill_id.upper()} */\n"
    
    if category == "parking_decoupling":
        return base_override + (
            f"Notwithstanding alternative ratios established in {section_heading}, "
            "no residential development qualifying under State Law shall be required to provide "
            "more than 1.0 off-street parking space per dwelling unit."
        )
    elif category == "lot_size_reform":
        return base_override + (
            f"Developments complying with state lot-split statutes are exempt from the standard limits of {section_heading}. "
            "Minimum lot sizing is capped at a maximum ceiling of 2,500 sq. ft."
        )
    elif category == "commercial_conversions":
        return base_override + (
            f"Multifamily or residential mixed-use spaces are deemed a Permitted Use (P) inside "
            f"traditionally non-residential districts outlined in {section_heading}, provided civil codes are satisfied."
        )
    elif category == "adu_streamlining":
        return base_override + (
            "Accessory dwelling units are subject exclusively to objective, administrative ministerial approval. "
            "All subjective architectural styling reviews and owner-occupancy covenant mandates are hereby repealed."
        )
    return "Administrative code review text modification required."

def evaluate_compliance(df):
    """
    Iterates through the ingested municipal code line-by-line and triggers evaluation flags
    where local constraints violate the incoming state policy profiles.
    """
    audit_results = []
    
    print(f"[*] Commencing Statutory Compliance Audit across {len(df)} local code nodes...")
    
    for _, row in df.iterrows():
        clean_text = str(row.get('clean_text', ''))
        heading = str(row.get('heading', ''))
        title = str(row.get('title', ''))
        node_id = row.get('node_id', 'Unknown')
        
        # Systematically match text block keywords against state mandate profiles
        for category, rules in STATE_MANDATES.items():
            matched_keywords = [kw for kw in rules['keywords'] if kw in clean_text.lower()]
            
            # If a high dense match cluster occurs (2 or more distinct structural keywords), evaluate thresholds
            if len(matched_keywords) >= 2:
                status = "Compliant"
                notes = "Keywords identified, but explicit legislative restriction threshold holds baseline."
                detected_metric = None
                
                # Evaluation Path A: Parking Metric Check
                if category == "parking_decoupling":
                    # Look for variations like "1.5 spaces", "2 spaces per unit", etc.
                    detected_metric = extract_numerical_metric(clean_text, r"(\d+(\.\d+)?\s*(?=space|stall))", 1.0)
                    if detected_metric and detected_metric > rules['max_allowable_parking_per_unit']:
                        status = "Non-Compliant: Overhaul Required"
                        notes = f"Local parking metric threshold ({detected_metric} spaces) exceeds state ceiling constraint ({rules['max_allowable_parking_per_unit']})."
                
                # Evaluation Path B: Sizing Metric Check
                elif category == "lot_size_reform":
                    # Look for layout markers like "5,000 sq ft", "6000 square feet"
                    detected_metric = extract_numerical_metric(clean_text, r"(\d{1,3}(?:,\d{3})*|\d+)\s*(?=sq|square feet)", 2500)
                    if detected_metric and detected_metric > rules['max_allowable_min_lot_size_sqft']:
                        status = "Non-Compliant: Overhaul Required"
                        notes = f"Local lot space base requirement ({detected_metric} sqft) forces restriction beyond state cap ({rules['max_allowable_min_lot_size_sqft']} sqft)."
                
                # Evaluation Path C: Permitted Zoning Context Checks (Textual Barriers)
                else:
                    # Uses like ADU and Conversions frequently rely on textual procedural blocks ("Special Permit Required", "Owner must occupy")
                    if any(trigger in clean_text.lower() for trigger in ["special permit", "conditional use", "owner-occupancy", "prohibited"]):
                        status = "Non-Compliant: Overhaul Required"
                        notes = f"Discretionary review mechanisms or structural usage limits found inside local text block."
                
                # Process the fix if flagged as Non-Compliant
                amendment = generate_amendment_draft(category, f"{heading} {title}".strip(), rules['bill_id']) if "Non-Compliant" in status else ""
                
                audit_results.append({
                    "municode_node_id": node_id,
                    "code_section": heading,
                    "section_title": title,
                    "state_bill_focus": rules['bill_id'],
                    "policy_category": category,
                    "matched_indicators": ", ".join(matched_keywords),
                    "detected_local_value": detected_metric if detected_metric else "Procedural Block",
                    "compliance_status": status,
                    "legal_assessment_notes": notes,
                    "recommended_text_amendment": amendment
                })
                
    return pd.DataFrame(audit_results)

def main():
    try:
        zoning_df = load_zoning_data(CSV_INPUT_PATH)
        report_df = evaluate_compliance(zoning_df)
        
        # Deduplicate matches hitting the exact same node/category combination
        report_df.drop_duplicates(subset=["municode_node_id", "policy_category"], inplace=True)
        
        # Filter and prioritize actionable updates
        report_df.sort_values(by="compliance_status", ascending=False, inplace=True)
        report_df.to_csv(COMPLIANCE_REPORT_PATH, index=False, encoding='utf-8')
        
        print(f"\n[+++] COMPLIANCE ANALYSIS RUN COMPLETE [+++]")
        print(f"-> Total preemption points analyzed: {len(report_df)}")
        print(f"-> Non-compliant elements discovered: {len(report_df[report_df['compliance_status'].str.contains('Non-Compliant')])}")
        print(f"-> Comprehensive compliance sheet compiled to: '{COMPLIANCE_REPORT_PATH}'")
        
    except Exception as e:
        print(f"[X] Operational Crash Encountered during evaluation execution: {e}")

if __name__ == "__main__":
    main()
