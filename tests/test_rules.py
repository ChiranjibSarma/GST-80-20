"""Small rule tests for the single approved calculation entry point."""
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.calc import calculate as public_calculate, summarise, report_table
from app.engine.golden import calculate as golden_calculate, INELIGIBLE_KEYWORDS


def main():
    assert public_calculate is golden_calculate, "A second calculator is active"
    d = date(2026, 7, 1)
    daybook = [{
        "Date": d, "Voucher_Type": "Journal", "Voucher_No": 1,
        "Particulars": "CGST expense", "Fixed_Group_Name": "Current Assets",
        "Parent_Group_Name": "Other", "Debit": 100.0, "Credit": 0.0,
        "Bill_No": "", "Bill_Date": None, "Cost_Centre": "Project A",
        "Narration": "Source-only narration",
    }]
    voucher = [
        {"Voucher_Date": d, "Voucher_Type": "Journal", "Voucher_No": 1,
         "Particulars": "Vendor A", "Debit_Amount": 0.0,
         "Credit_Amount": 100.0, "Status": "Approved"},
        {"Voucher_Date": d, "Voucher_Type": "Journal", "Voucher_No": 1,
         "Particulars": "RCM payable", "Debit_Amount": 0.0,
         "Credit_Amount": 0.0, "Status": "Approved"},
    ]
    creditors = [{"Account_Name": "Vendor A", "Group_Name": "Sundry Creditors",
                  "GSTIN": "INVALID"}]
    result = public_calculate(daybook, voucher, creditors, {
        "include_fixed_groups": ["Current Assets"],
        "exclude_parent_groups": [],
        # Stored settings must not supersede the approved Python constants.
        "ineligible_keywords": [],
    })
    assert "CGST" in INELIGIBLE_KEYWORDS
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["formula_key"] == "CGST"
    assert row["eligibility"] == "Ineligible"  # RCM does not override the keyword
    assert row["gst_status"] == "Registered"  # populated GST No. is enough
    assert row["rcm"] is True
    assert row["narration"] == ""  # the approved workbook intentionally leaves it blank
    assert row["source_narration"] == "Source-only narration"
    # Report!H2 applies ABS to each net GST bucket, not to the signed total.
    negative_mix = summarise([
        {"head": "Expenses", "eligibility": "Eligible", "gst_status": "Registered",
         "closing": -100.0},
        {"head": "Expenses", "eligibility": "Eligible", "gst_status": "Unregistered",
         "closing": 25.0},
    ])
    assert negative_mix["pct"] == 80.0
    report = report_table([row])
    assert [(line["elig"], line["status"]) for line in report] == [
        ("Eligible", "Registered"), ("Eligible", "Unregistered"),
        ("Eligible", "Eligible total"),
        ("Ineligible", "Registered"), ("Ineligible", "Unregistered"),
        ("Ineligible", "Ineligible total"),
    ]
    print("PASS: only the Python-aligned calculator is public; source rules govern classification")


if __name__ == "__main__":
    main()
