"""
Vouchsafe — Audit Reconciliation Tool
Core module: database, parsers, reconciliation engines, formatters.

All business logic lives here. The Streamlit UI in app.py imports from this.
"""

from __future__ import annotations

import json
import re
import sqlite3
import shutil
import secrets
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

# Optional PDF support (Form 26AS often comes as PDF)
try:
    import pdfplumber  # type: ignore
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# ---------------------------------------------------------------------------
# PATHS — everything sits next to the script, so the folder is portable
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "audit.db"

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            gstin TEXT,
            pan TEXT,
            fy TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reconciliations (
            id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            recon_type TEXT NOT NULL,
            period TEXT,
            summary_json TEXT,
            data_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS challans (
            id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            ctype TEXT,
            cin TEXT,
            bsr TEXT,
            payment_date TEXT,
            amount REAL,
            period TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_size INTEGER,
            file_type TEXT,
            tag TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_recon_client ON reconciliations(client_id);
        CREATE INDEX IF NOT EXISTS idx_challans_client ON challans(client_id);
        CREATE INDEX IF NOT EXISTS idx_docs_client ON documents(client_id);
    """)
    # Lightweight migration: add accounting_system column to existing clients tables
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(clients)").fetchall()]
    if "accounting_system" not in cols:
        conn.execute("ALTER TABLE clients ADD COLUMN accounting_system TEXT DEFAULT 'Tally'")
    conn.commit()
    conn.close()


def new_id() -> str:
    return secrets.token_hex(8)


# ----------------- Clients -----------------
def list_clients() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_client(cid: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_client(name: str, gstin: str = "", pan: str = "", fy: str = "FY 2024-25",
               accounting_system: str = "Tally") -> str:
    cid = new_id()
    conn = get_conn()
    conn.execute(
        "INSERT INTO clients (id, name, gstin, pan, fy, accounting_system) VALUES (?, ?, ?, ?, ?, ?)",
        (cid, name.strip(), gstin.strip().upper(), pan.strip().upper(),
         fy.strip(), accounting_system),
    )
    conn.commit()
    conn.close()
    return cid


def update_client(cid: str, name: str, gstin: str, pan: str, fy: str,
                  accounting_system: str = "Tally") -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE clients SET name=?, gstin=?, pan=?, fy=?, accounting_system=? WHERE id=?",
        (name.strip(), gstin.strip().upper(), pan.strip().upper(),
         fy.strip(), accounting_system, cid),
    )
    conn.commit()
    conn.close()


def delete_client(cid: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM clients WHERE id = ?", (cid,))
    conn.commit()
    conn.close()


# ----------------- Reconciliations -----------------
def save_recon(client_id: str, recon_type: str, period: str, summary: dict, data: dict) -> str:
    """
    Saves a reconciliation. `data` should be a dict of DataFrames-as-dicts
    (we cap each section at 10,000 rows to keep the DB lean).
    """
    rid = new_id()
    # Truncate large data sections
    capped = {}
    for k, v in data.items():
        if isinstance(v, list):
            capped[k] = v[:10000]
        else:
            capped[k] = v
    conn = get_conn()
    # Delete previous recon of same type+period for this client (so we always have the latest)
    conn.execute(
        "DELETE FROM reconciliations WHERE client_id=? AND recon_type=? AND period=?",
        (client_id, recon_type, period),
    )
    conn.execute(
        "INSERT INTO reconciliations (id, client_id, recon_type, period, summary_json, data_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (rid, client_id, recon_type, period, json.dumps(summary), json.dumps(capped, default=str)),
    )
    conn.commit()
    conn.close()
    return rid


def list_recons(client_id: Optional[str] = None) -> list[dict]:
    conn = get_conn()
    if client_id:
        rows = conn.execute(
            "SELECT * FROM reconciliations WHERE client_id=? ORDER BY created_at DESC",
            (client_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM reconciliations ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["summary"] = json.loads(d["summary_json"] or "{}")
        out.append(d)
    return out


def get_recon(rid: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM reconciliations WHERE id=?", (rid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["summary"] = json.loads(d["summary_json"] or "{}")
    d["data"] = json.loads(d["data_json"] or "{}")
    return d


def delete_recon(rid: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM reconciliations WHERE id=?", (rid,))
    conn.commit()
    conn.close()


# ----------------- Challans -----------------
def add_challan(client_id: str, ctype: str, cin: str, bsr: str,
                payment_date: str, amount: float, period: str, notes: str) -> str:
    cid = new_id()
    conn = get_conn()
    conn.execute(
        "INSERT INTO challans (id, client_id, ctype, cin, bsr, payment_date, amount, period, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, client_id, ctype, cin.strip(), bsr.strip(), payment_date, float(amount), period, notes),
    )
    conn.commit()
    conn.close()
    return cid


def list_challans(client_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM challans WHERE client_id=? ORDER BY payment_date DESC, created_at DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_challan(challan_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM challans WHERE id=?", (challan_id,))
    conn.commit()
    conn.close()


# ----------------- Documents -----------------
def save_document(client_id: str, uploaded_file, tag: str = "General") -> str:
    """Save uploaded file to disk and record metadata in DB."""
    did = new_id()
    client_dir = UPLOADS_DIR / client_id
    client_dir.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", uploaded_file.name)
    stored_path = client_dir / f"{did}_{safe_name}"
    with open(stored_path, "wb") as f:
        shutil.copyfileobj(uploaded_file, f) if hasattr(uploaded_file, "read") else f.write(uploaded_file)
    conn = get_conn()
    conn.execute(
        "INSERT INTO documents (id, client_id, filename, stored_path, file_size, file_type, tag) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (did, client_id, uploaded_file.name, str(stored_path),
         stored_path.stat().st_size, uploaded_file.type or "", tag),
    )
    conn.commit()
    conn.close()
    return did


def list_documents(client_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM documents WHERE client_id=? ORDER BY uploaded_at DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_document(doc_id: str) -> None:
    conn = get_conn()
    row = conn.execute("SELECT stored_path FROM documents WHERE id=?", (doc_id,)).fetchone()
    if row:
        try:
            Path(row["stored_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()


def update_document_tag(doc_id: str, tag: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE documents SET tag=? WHERE id=?", (tag, doc_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# FORMATTERS — Indian conventions
# ---------------------------------------------------------------------------
def inr(n) -> str:
    """Format with Indian grouping: 1,23,456.78"""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    int_part, dec_part = f"{n:.2f}".split(".")
    if len(int_part) > 3:
        last_three = int_part[-3:]
        rest = int_part[:-3]
        # Insert commas every 2 digits in the rest
        rest_grouped = re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", rest)
        int_part = f"{rest_grouped},{last_three}"
    return f"{sign}₹{int_part}.{dec_part}"


def fmt_date(d) -> str:
    if d is None or d == "" or (isinstance(d, float) and pd.isna(d)):
        return "—"
    if isinstance(d, (datetime, date)):
        return d.strftime("%d/%m/%Y")
    if isinstance(d, str):
        try:
            return pd.to_datetime(d, dayfirst=True).strftime("%d/%m/%Y")
        except Exception:
            return d
    return str(d)


# ---------------------------------------------------------------------------
# COLUMN MATCHING — handle the many ways Tally / portal name the same field
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def find_col(df: pd.DataFrame, *keywords: str) -> Optional[str]:
    """Return the first column whose normalised name CONTAINS any keyword."""
    norms = {_norm(c): c for c in df.columns}
    for kw in keywords:
        k = _norm(kw)
        for n, original in norms.items():
            if k in n:
                return original
    return None


def find_header_row(file, sheet_name=0, max_scan=10, must_contain=("gstin", "supplier", "invoice")) -> int:
    """
    GST portal & some Tally exports have headers in row 5 or 6, not row 1.
    Scan first `max_scan` rows looking for one that contains audit-relevant keywords.
    """
    raw = pd.read_excel(file, sheet_name=sheet_name, header=None, nrows=max_scan + 5)
    for i in range(min(max_scan, len(raw))):
        row_vals = [_norm(v) for v in raw.iloc[i].astype(str).values]
        joined = "|".join(row_vals)
        hits = sum(1 for kw in must_contain if kw in joined)
        if hits >= 2:
            return i
    return 0


# ---------------------------------------------------------------------------
# FILE PARSERS
# ---------------------------------------------------------------------------
def read_excel_smart(file, sheet_name=None) -> pd.DataFrame:
    """Read an Excel file, auto-detecting header row."""
    if sheet_name is None:
        xls = pd.ExcelFile(file)
        sheet_name = xls.sheet_names[0]
    header_row = find_header_row(file, sheet_name=sheet_name)
    df = pd.read_excel(file, sheet_name=sheet_name, header=header_row)
    df = df.dropna(how="all").dropna(how="all", axis=1)
    return df


def read_any(file, **kwargs) -> pd.DataFrame:
    """Read csv/xlsx/xls based on file name."""
    name = getattr(file, "name", str(file)).lower()
    if name.endswith(".csv"):
        return pd.read_csv(file, **kwargs).dropna(how="all").dropna(how="all", axis=1)
    return read_excel_smart(file, **kwargs)


def _num(s):
    """Robust number parsing: handles ₹, commas, parentheses for negatives."""
    if pd.isna(s) or s == "":
        return 0.0
    txt = str(s).strip().replace("₹", "").replace(",", "").replace(" ", "")
    m = re.match(r"^\((.+)\)$", txt)
    if m:
        txt = "-" + m.group(1)
    try:
        return float(txt)
    except ValueError:
        return 0.0


def _norm_invoice(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def _norm_gstin(s) -> str:
    return re.sub(r"\s", "", str(s).upper())[:15]


# ----------------- GSTR-2B (portal excel, look for B2B sheet) -----------------
def parse_gstr2b(file) -> pd.DataFrame:
    xls = pd.ExcelFile(file)
    # Prefer the B2B sheet (not B2BA which is amendments)
    sheet = None
    for s in xls.sheet_names:
        sl = s.lower().strip()
        if sl == "b2b" or sl.startswith("b2b ") or sl == "b2b invoices":
            sheet = s
            break
    if sheet is None:
        # Fallback: any sheet containing "b2b" but not "b2ba"
        for s in xls.sheet_names:
            if "b2b" in s.lower() and "b2ba" not in s.lower().replace(" ", ""):
                sheet = s
                break
    if sheet is None:
        sheet = xls.sheet_names[0]
    df = read_excel_smart(file, sheet_name=sheet)
    return _map_gst_invoices(df, source="GSTR-2B")


def parse_purchase_register(file) -> pd.DataFrame:
    df = read_any(file)
    return _map_gst_invoices(df, source="Books")


def parse_sales_register(file) -> pd.DataFrame:
    df = read_any(file)
    return _map_gst_invoices(df, source="Books")


def parse_gstr1(file) -> pd.DataFrame:
    return parse_gstr2b(file)  # Same shape from portal


def _map_gst_invoices(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Maps any GST-flavoured invoice dataframe to the standard schema.
    Handles column-name variants from:
      - GST Portal (GSTIN of supplier, Invoice Number, Taxable Value, Integrated Tax …)
      - Tally    (Party Name, Voucher No, Bill No, Assessable Value, IGST, CGST …)
      - Zoho     (Vendor Name / Customer Name, Bill Number / Invoice Number,
                  Vendor GSTIN / Customer GSTIN, Taxable Amount, IGST, CGST …)
      - QuickBooks / Busy / generic CSV
    """
    out = pd.DataFrame()
    gstin_col = find_col(df, "gstinofsupplier", "gstinofrecipient",
                         "vendorgstin", "customergstin", "partygstin",
                         "suppliergstin", "gstin", "supplier")
    name_col = find_col(df, "tradename", "legalname",
                        "vendorname", "customername",
                        "partyname", "suppliername", "ledgername", "name")
    inv_col = find_col(df, "invoicenumber", "invoiceno", "billnumber", "billno",
                       "voucherno", "documentnumber", "reference")
    date_col = find_col(df, "invoicedate", "documentdate", "billdate",
                        "voucherdate", "date")
    taxable_col = find_col(df, "taxablevalue", "taxableamount",
                           "assessablevalue", "taxable")
    igst_col = find_col(df, "integratedtax", "igst", "integrated")
    cgst_col = find_col(df, "centraltax", "cgst", "central")
    sgst_col = find_col(df, "statetax", "sgst", "utgst", "state")
    cess_col = find_col(df, "cess")
    total_col = find_col(df, "invoicevalue", "totalvalue",
                         "billtotal", "invoicetotal", "grosstotal",
                         "totalamount", "total", "amount")

    out["gstin"] = df[gstin_col].apply(_norm_gstin) if gstin_col else ""
    out["supplier_name"] = df[name_col].astype(str).str.strip() if name_col else ""
    out["invoice_no"] = df[inv_col].apply(_norm_invoice) if inv_col else ""
    out["invoice_no_raw"] = df[inv_col].astype(str).str.strip() if inv_col else ""
    out["invoice_date"] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce") if date_col else pd.NaT
    out["taxable_value"] = df[taxable_col].apply(_num) if taxable_col else 0.0
    out["igst"] = df[igst_col].apply(_num) if igst_col else 0.0
    out["cgst"] = df[cgst_col].apply(_num) if cgst_col else 0.0
    out["sgst"] = df[sgst_col].apply(_num) if sgst_col else 0.0
    out["cess"] = df[cess_col].apply(_num) if cess_col else 0.0
    out["total"] = df[total_col].apply(_num) if total_col else 0.0
    out["source"] = source

    # Drop rows that have no GSTIN AND no invoice number — likely junk
    out = out[(out["gstin"].str.len() > 0) | (out["invoice_no"].str.len() > 0)].reset_index(drop=True)
    return out


def aggregate_invoice_lines(df: pd.DataFrame) -> pd.DataFrame:
    """
    Some accounting systems (notably Zoho's 'Bills Detail' or per-line GST reports)
    export ONE ROW PER LINE ITEM of an invoice. Same invoice number, multiple rows.

    This collapses duplicates by (gstin + invoice_no), summing the money columns.

    WARNING: this also hides the audit signal of an invoice being booked twice.
    Use the toggle in the UI only when you know your export is line-item-detailed.
    """
    if df is None or df.empty:
        return df
    grouped = df.groupby(["gstin", "invoice_no"], as_index=False, dropna=False).agg({
        "supplier_name": "first",
        "invoice_no_raw": "first",
        "invoice_date": "first",
        "taxable_value": "sum",
        "igst": "sum",
        "cgst": "sum",
        "sgst": "sum",
        "cess": "sum",
        "total": "sum",
        "source": "first",
    })
    return grouped


# ----------------- Form 26AS -----------------
def parse_26as(file) -> pd.DataFrame:
    """Parse Form 26AS — handles excel and (best-effort) PDF."""
    name = getattr(file, "name", str(file)).lower()
    if name.endswith(".pdf"):
        return _parse_26as_pdf(file)
    # Excel: try to find the largest sheet (since 26AS has many small sections)
    xls = pd.ExcelFile(file)
    biggest, biggest_len = None, 0
    for s in xls.sheet_names:
        n = len(pd.read_excel(file, sheet_name=s, header=None))
        if n > biggest_len:
            biggest, biggest_len = s, n
    df = read_excel_smart(file, sheet_name=biggest)
    return _map_26as(df, source="26AS")


def _parse_26as_pdf(file) -> pd.DataFrame:
    if not HAS_PDF:
        raise RuntimeError(
            "PDF parsing requires pdfplumber. Install with: pip install pdfplumber\n"
            "Or export Form 26AS as Excel from the TRACES portal."
        )
    all_rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                if not tbl or len(tbl) < 2:
                    continue
                hdr = [(c or "").strip() for c in tbl[0]]
                joined = "|".join(_norm(c) for c in hdr)
                # Look for TDS section header (Part A typically)
                if "tan" in joined and ("amount" in joined or "tds" in joined):
                    for row in tbl[1:]:
                        all_rows.append(dict(zip(hdr, row)))
    df = pd.DataFrame(all_rows)
    return _map_26as(df, source="26AS")


def parse_tds_ledger(file) -> pd.DataFrame:
    df = read_any(file)
    return _map_26as(df, source="Books")


def _map_26as(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Handles column-name variants from:
      - TRACES (TAN of Deductor, Name of Deductor, Section, Amount Paid/Credited,
                Tax Deducted, Date of Booking)
      - Tally  (Party Name, TAN, Section, Amount, TDS Amount, Date)
      - Zoho   (Vendor Name, Vendor TAN, Section, Taxable Amount, TDS Amount, Date)
    """
    out = pd.DataFrame()
    tan_col = find_col(df, "tanofdeductor", "vendortan", "deductortan",
                       "partytan", "tan")
    name_col = find_col(df, "nameofdeductor", "deductorname",
                        "vendorname", "partyname", "deductor", "ledger", "name")
    section_col = find_col(df, "sectionunderwhich", "section", "natureofpayment")
    paid_col = find_col(df, "amountpaid", "amountcredited",
                        "taxableamount", "grossamount",
                        "invoiceamount", "transactionamount", "amount")
    tds_col = find_col(df, "taxdeducted", "tdsdeducted", "tdsamount", "tds")
    date_col = find_col(df, "dateofbookingreceipt", "dateofbooking",
                        "transactiondate", "voucherdate", "invoicedate",
                        "paymentdate", "date")
    status_col = find_col(df, "statusofbooking", "status")

    out["tan"] = df[tan_col].astype(str).str.upper().str.strip() if tan_col else ""
    out["deductor_name"] = df[name_col].astype(str).str.strip() if name_col else ""
    out["section"] = df[section_col].astype(str).str.strip() if section_col else ""
    out["amount_paid"] = df[paid_col].apply(_num) if paid_col else 0.0
    out["tds_amount"] = df[tds_col].apply(_num) if tds_col else 0.0
    out["date"] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce") if date_col else pd.NaT
    out["status"] = df[status_col].astype(str).str.strip() if status_col else ""
    out["source"] = source

    out = out[(out["tan"].str.len() > 0) | (out["tds_amount"].abs() > 0)].reset_index(drop=True)
    return out


# ----------------- Bank Statement -----------------
def parse_bank_statement(file) -> pd.DataFrame:
    df = read_any(file)
    return _map_bank(df, source="Bank")


def parse_bank_ledger(file) -> pd.DataFrame:
    df = read_any(file)
    return _map_bank(df, source="Books")


def _norm_txn_type(s) -> str:
    """Normalise transaction-type strings to 'CR' or 'DR'.
    Handles 'Credit'/'Debit', 'Deposit'/'Withdrawal', 'CR'/'DR' from Zoho/Tally/banks."""
    if s is None or pd.isna(s):
        return ""
    t = str(s).upper().strip()
    if t in ("CR", "CREDIT", "DEPOSIT", "DEP", "C"):
        return "CR"
    if t in ("DR", "DEBIT", "WITHDRAWAL", "WITHDRAW", "WTH", "D"):
        return "DR"
    return ""


def _map_bank(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Handles column-name variants from:
      - Bank statements (Date, Narration, Withdrawal Amt, Deposit Amt, Balance)
      - Tally Bank Ledger (Date, Particulars, Voucher No, Debit, Credit)
      - Zoho Books bank feed (Date, Reference Number, Description, Deposits,
                              Withdrawals OR single Amount + Transaction Type)
    """
    out = pd.DataFrame()
    date_col = find_col(df, "transactiondate", "valuedate", "voucherdate",
                        "txndate", "date")
    desc_col = find_col(df, "narration", "particulars", "description", "remarks")
    ref_col = find_col(df, "referencenumber", "chequeno", "utrnumber",
                       "voucherno", "reference", "refno")
    dr_col = find_col(df, "withdrawals", "withdrawal", "debit",
                      "withdrawalamount") or find_col(df, "dr")
    cr_col = find_col(df, "deposits", "deposit", "credit",
                      "depositamount") or find_col(df, "cr")
    amt_col = find_col(df, "amount", "transactionamount")
    type_col = find_col(df, "transactiontype", "txntype", "type")
    bal_col = find_col(df, "balance", "closingbalance", "runningbalance")

    out["date"] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce") if date_col else pd.NaT
    out["description"] = df[desc_col].astype(str).str.strip() if desc_col else ""
    out["reference"] = df[ref_col].astype(str).str.strip() if ref_col else ""

    if dr_col and cr_col:
        # Two-column form (most banks, Tally, Zoho's Deposits/Withdrawals export)
        dr = df[dr_col].apply(_num)
        cr = df[cr_col].apply(_num)
        out["amount"] = (dr + cr).abs()
        out["type"] = ["DR" if d > 0 else ("CR" if c > 0 else "") for d, c in zip(dr, cr)]
    elif amt_col and type_col:
        # Single-amount + explicit type column (Zoho's "Transaction Type")
        amt = df[amt_col].apply(_num)
        out["amount"] = amt.abs()
        out["type"] = df[type_col].apply(_norm_txn_type)
    elif amt_col:
        # Signed amount, infer type from sign
        amt = df[amt_col].apply(_num)
        out["amount"] = amt.abs()
        out["type"] = ["DR" if a < 0 else "CR" for a in amt]
    else:
        out["amount"] = 0.0
        out["type"] = ""

    out["balance"] = df[bal_col].apply(_num) if bal_col else 0.0
    out["source"] = source
    out = out[(out["date"].notna()) & (out["amount"] > 0)].reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# RECONCILIATION ENGINES
# ---------------------------------------------------------------------------
def reconcile_gst(portal_df: pd.DataFrame, books_df: pd.DataFrame, tolerance: float = 1.0) -> dict:
    """
    Match invoices on (GSTIN, normalized invoice number).
    Returns four DataFrames: matched, mismatch, only_portal, only_books.
    """
    if portal_df.empty or books_df.empty:
        return {"matched": pd.DataFrame(), "mismatch": pd.DataFrame(),
                "only_portal": portal_df.copy(), "only_books": books_df.copy()}

    p = portal_df.copy().reset_index(drop=True)
    b = books_df.copy().reset_index(drop=True)
    p["_pid"] = p.index
    b["_bid"] = b.index
    p["_key"] = p["gstin"] + "|" + p["invoice_no"]
    b["_key"] = b["gstin"] + "|" + b["invoice_no"]

    # Greedy 1-to-1 pairing on key to handle duplicates correctly
    matched_rows, mismatch_rows = [], []
    used_b = set()
    b_by_key = {k: list(grp.index) for k, grp in b.groupby("_key")}

    matched_p_ids = set()
    for _, prow in p.iterrows():
        candidates = b_by_key.get(prow["_key"], [])
        free = next((bid for bid in candidates if bid not in used_b), None)
        if free is None:
            continue
        used_b.add(free)
        matched_p_ids.add(prow["_pid"])
        brow = b.loc[free]
        diffs = {
            "diff_taxable": _num(prow["taxable_value"]) - _num(brow["taxable_value"]),
            "diff_igst": _num(prow["igst"]) - _num(brow["igst"]),
            "diff_cgst": _num(prow["cgst"]) - _num(brow["cgst"]),
            "diff_sgst": _num(prow["sgst"]) - _num(brow["sgst"]),
            "diff_total": _num(prow["total"]) - _num(brow["total"]),
        }
        is_exact = all(abs(v) <= tolerance for k, v in diffs.items() if k != "diff_total")
        row = {
            "supplier_name": prow["supplier_name"] or brow["supplier_name"],
            "gstin": prow["gstin"],
            "invoice_no": prow["invoice_no_raw"],
            "invoice_date": prow["invoice_date"],
            "portal_taxable": prow["taxable_value"],
            "book_taxable": brow["taxable_value"],
            "portal_igst": prow["igst"],
            "book_igst": brow["igst"],
            "portal_cgst": prow["cgst"],
            "book_cgst": brow["cgst"],
            "portal_sgst": prow["sgst"],
            "book_sgst": brow["sgst"],
            "portal_total": prow["total"],
            "book_total": brow["total"],
            **diffs,
        }
        (matched_rows if is_exact else mismatch_rows).append(row)

    only_portal = p[~p["_pid"].isin(matched_p_ids)].drop(columns=["_pid", "_key"])
    only_books = b[~b["_bid"].isin(used_b)].drop(columns=["_bid", "_key"])
    return {
        "matched": pd.DataFrame(matched_rows),
        "mismatch": pd.DataFrame(mismatch_rows),
        "only_portal": only_portal.reset_index(drop=True),
        "only_books": only_books.reset_index(drop=True),
    }


def reconcile_26as(portal_df: pd.DataFrame, books_df: pd.DataFrame, tolerance: float = 1.0) -> dict:
    """Match on TAN, with TDS amount as primary and amount-paid as secondary."""
    if portal_df.empty or books_df.empty:
        return {"matched": pd.DataFrame(), "mismatch": pd.DataFrame(),
                "only_26as": portal_df.copy(), "only_books": books_df.copy()}

    p = portal_df.copy().reset_index(drop=True)
    b = books_df.copy().reset_index(drop=True)
    p["_pid"] = p.index
    b["_bid"] = b.index

    matched_rows, mismatch_rows = [], []
    used_b = set()
    b_by_tan = {tan: list(grp.index) for tan, grp in b.groupby("tan")}

    matched_p_ids = set()
    for _, prow in p.iterrows():
        candidates = b_by_tan.get(prow["tan"], [])
        # Prefer candidate with closest TDS amount, then closest amount paid
        best = None
        best_diff = None
        for bid in candidates:
            if bid in used_b:
                continue
            brow = b.loc[bid]
            tds_diff = abs(_num(prow["tds_amount"]) - _num(brow["tds_amount"]))
            paid_diff = abs(_num(prow["amount_paid"]) - _num(brow["amount_paid"]))
            score = tds_diff + paid_diff * 0.01
            if best is None or score < best_diff:
                best, best_diff = bid, score
        if best is None:
            continue
        used_b.add(best)
        matched_p_ids.add(prow["_pid"])
        brow = b.loc[best]
        diffs = {
            "diff_amount_paid": _num(prow["amount_paid"]) - _num(brow["amount_paid"]),
            "diff_tds": _num(prow["tds_amount"]) - _num(brow["tds_amount"]),
        }
        paid_tol = max(tolerance, abs(_num(prow["amount_paid"])) * 0.01)
        is_exact = abs(diffs["diff_tds"]) <= tolerance and abs(diffs["diff_amount_paid"]) <= paid_tol
        row = {
            "deductor_name": prow["deductor_name"] or brow["deductor_name"],
            "tan": prow["tan"],
            "section": prow["section"] or brow["section"],
            "date": prow["date"],
            "portal_amount_paid": prow["amount_paid"],
            "book_amount_paid": brow["amount_paid"],
            "portal_tds": prow["tds_amount"],
            "book_tds": brow["tds_amount"],
            **diffs,
        }
        (matched_rows if is_exact else mismatch_rows).append(row)

    only_26as = p[~p["_pid"].isin(matched_p_ids)].drop(columns=["_pid"])
    only_books = b[~b["_bid"].isin(used_b)].drop(columns=["_bid"])
    return {
        "matched": pd.DataFrame(matched_rows),
        "mismatch": pd.DataFrame(mismatch_rows),
        "only_26as": only_26as.reset_index(drop=True),
        "only_books": only_books.reset_index(drop=True),
    }


def reconcile_bank(bank_df: pd.DataFrame, books_df: pd.DataFrame,
                   tolerance: float = 1.0, day_window: int = 3) -> dict:
    """Match transactions on (type, amount within tolerance, date within window)."""
    if bank_df.empty or books_df.empty:
        return {"matched": pd.DataFrame(), "only_bank": bank_df.copy(), "only_books": books_df.copy()}

    bk = bank_df.copy().reset_index(drop=True)
    bo = books_df.copy().reset_index(drop=True)
    bk["_id"] = bk.index
    bo["_id"] = bo.index

    matched_rows = []
    used_bo = set()
    matched_bk_ids = set()

    # Iterate bank → find best book match within window
    for _, brow in bk.iterrows():
        best = None
        best_day_diff = None
        for _, orow in bo.iterrows():
            if orow["_id"] in used_bo:
                continue
            if brow["type"] and orow["type"] and brow["type"] != orow["type"]:
                continue
            if abs(_num(brow["amount"]) - _num(orow["amount"])) > tolerance:
                continue
            if pd.isna(brow["date"]) or pd.isna(orow["date"]):
                continue
            dd = abs((brow["date"] - orow["date"]).days)
            if dd > day_window:
                continue
            if best is None or dd < best_day_diff:
                best, best_day_diff = orow["_id"], dd
        if best is not None:
            used_bo.add(best)
            matched_bk_ids.add(brow["_id"])
            orow = bo.loc[best]
            matched_rows.append({
                "bank_date": brow["date"],
                "book_date": orow["date"],
                "type": brow["type"],
                "amount": brow["amount"],
                "bank_desc": brow["description"],
                "book_desc": orow["description"],
                "bank_ref": brow["reference"],
                "book_ref": orow["reference"],
            })

    only_bank = bk[~bk["_id"].isin(matched_bk_ids)].drop(columns=["_id"])
    only_books = bo[~bo["_id"].isin(used_bo)].drop(columns=["_id"])
    return {
        "matched": pd.DataFrame(matched_rows),
        "only_bank": only_bank.reset_index(drop=True),
        "only_books": only_books.reset_index(drop=True),
    }


# ---------------------------------------------------------------------------
# DATAFRAME -> JSON-SAFE (for persisting reconciliations)
# ---------------------------------------------------------------------------
def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to JSON-safe list of dicts (handles dates, NaN)."""
    if df is None or df.empty:
        return []
    d = df.copy()
    for col in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[col]):
            d[col] = d[col].dt.strftime("%Y-%m-%d")
    return json.loads(d.to_json(orient="records", date_format="iso"))


def records_to_df(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)
