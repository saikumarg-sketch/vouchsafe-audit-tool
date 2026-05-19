# Vouchsafe — Audit Reconciliation Tool

A desktop audit tool for Indian CA firms. Runs locally on your laptop, stores everything in a single SQLite file, never sends your client data anywhere.

## What it does

- **GSTR-2B vs Purchase Register** — match ITC claimed in books against what suppliers uploaded
- **GSTR-1 vs Sales Register** — confirm every outward supply was reported
- **GSTR-3B vs Books** — tie headline 3B to trial balance, line by line
- **Form 26AS vs TDS Ledger** — recover unclaimed credits, flag deductors who haven't filed
- **Bank Reconciliation** — date-window matching with cheque clearing tolerance
- **Challan Repository** — log GST/TDS/IT/PF challans per client
- **Document Vault** — store engagement letters, notices, working papers per client
- **Dashboard** — practice-wide view of all clients, reconciliations, mismatches

All client data persists in `data/audit.db` (SQLite) and `data/uploads/` (your files).

---

## One-Time Setup

### 1. Install Python

Download **Python 3.10 or newer** from [python.org/downloads](https://www.python.org/downloads/).

> ⚠️ **Windows users:** During installation, tick **"Add Python to PATH"** at the bottom of the first screen. Otherwise the `python` command won't work in the terminal.

Verify in a terminal (Command Prompt on Windows, Terminal on Mac/Linux):

```bash
python --version
```

You should see `Python 3.10.x` or higher.

### 2. Download this folder

Place the `audit_tool` folder anywhere on your computer (e.g. `C:\Users\YourName\Documents\audit_tool` on Windows, `~/Documents/audit_tool` on Mac).

### 3. Open a terminal in this folder

- **Windows:** Open the folder in File Explorer → click in the address bar → type `cmd` → Enter
- **Mac:** Right-click the folder → New Terminal at Folder
- **Linux:** `cd ~/Documents/audit_tool`

### 4. Create a virtual environment (recommended, isolates dependencies)

```bash
python -m venv venv
```

**Activate it:**

- **Windows:** `venv\Scripts\activate`
- **Mac/Linux:** `source venv/bin/activate`

Your prompt should now start with `(venv)`.

### 5. Install dependencies

```bash
pip install -r requirements.txt
```

This installs Streamlit, pandas, openpyxl (Excel reader), and pdfplumber (for Form 26AS PDF support). Takes a minute or two.

---

## Running the App

Inside the folder, with venv activated:

```bash
streamlit run app.py
```

The app opens automatically at **http://localhost:8501** in your browser. Leave the terminal window open — closing it stops the app.

To stop: press `Ctrl+C` in the terminal.

---

## Daily Use

After the one-time setup, every time you want to use the tool:

1. Open the `audit_tool` folder in a terminal
2. Activate venv:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
3. Run: `streamlit run app.py`

### Tip: One-click launcher (Windows)

Create a file called `run.bat` in the folder with this content:

```bat
@echo off
cd /d "%~dp0"
call venv\Scripts\activate
streamlit run app.py
```

Double-click `run.bat` to launch the app any time.

### Tip: One-click launcher (Mac/Linux)

Create a file called `run.sh`:

```bash
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
streamlit run app.py
```

Make it executable: `chmod +x run.sh` — then double-click or run `./run.sh`.

---

## File Format Notes

The parsers auto-detect column names, so most Tally, Zoho Books and portal exports work out of the box. If a file fails to parse:

- **Tally CSV with junk header rows:** export to Excel instead, or delete the first few non-data rows
- **GSTR-2B:** download the Excel from the portal (not the JSON). The B2B sheet is auto-detected
- **Form 26AS:** Excel works best. PDF parsing is supported but accuracy depends on the PDF — for important work, prefer Excel export from TRACES
- **Bank statements:** expect columns like *Date / Transaction Date*, *Narration / Particulars*, *Debit / Withdrawal*, *Credit / Deposit*. If your bank gives a weird format, open in Excel and rename headers

### Working with Zoho Books

Tag the client as **"Zoho Books"** in the Clients tab. Then for each reconciliation, export from Zoho as follows:

| Reconciliation | Zoho report to export |
|---|---|
| GSTR-2B vs Purchase Reg. | *Reports → Purchases → Bills Details* |
| GSTR-1 vs Sales Reg. | *Reports → Sales → Invoice Details* |
| 3B vs Books | *Reports → Taxes → GST Summary* (read figures, enter manually) |
| 26AS vs TDS Ledger | *Reports → Taxes → TDS Summary* or *TDS Withheld* |
| Bank Reconciliation | *Banking → [select account] → Export* |

**Important — line-item exports:** if you export a *detailed* report that has one row per line item of an invoice (rather than one row per invoice), tick the **"Aggregate duplicate invoices"** checkbox in the reconciliation view. The tool will sum rows that share the same GSTIN + Invoice Number before matching. Leave it OFF for Tally — duplicate invoices in Tally usually mean a double-booking error you want to catch.

Zoho column names handled out of the box: *Vendor Name, Customer Name, Vendor GSTIN, Customer GSTIN, Bill Number, Invoice Number, Bill Date, Invoice Date, Taxable Amount, IGST, CGST, SGST, CESS, Total*, plus Zoho's bank columns *Deposits, Withdrawals, Reference Number*, and the *Transaction Type* column with "Credit"/"Debit" values.

---

## Backing Up Your Data

Everything is in the `data/` folder. To back up:

- **Quick:** Zip the entire `audit_tool` folder
- **Just the data:** Copy `data/audit.db` and `data/uploads/` to a backup drive
- **Restore:** Drop the files back in the same location

It is safe to back up while the app is running (SQLite handles this), but the app should be stopped for the safest backup.

---

## Troubleshooting

**`'streamlit' is not recognized` (Windows) / `command not found: streamlit`**
→ The venv isn't activated. Run `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux) first.

**`ModuleNotFoundError: No module named 'pandas'`**
→ Dependencies didn't install. Make sure venv is active, then run `pip install -r requirements.txt` again.

**Port 8501 already in use**
→ Another Streamlit app is running. Either close it, or run on a different port: `streamlit run app.py --server.port 8502`

**App opens to a blank page**
→ Wait 5–10 seconds on first launch — Streamlit is starting up. If still blank, refresh the browser.

**Reconciliation finds zero matches**
→ Your column names probably weren't auto-detected. Open both files in Excel and verify the column headers contain recognisable terms like "GSTIN", "Invoice No", "Taxable Value". Re-save and try again.

---

## What's Next

When you outgrow this single-user setup, the same `core.py` logic can be lifted into:
- A FastAPI backend serving multiple users on your office network
- A cloud-hosted version with proper authentication
- A packaged Windows executable using PyInstaller

The reconciliation engines and parsers don't change — only the UI layer.
