"""
Vouchsafe — Audit Reconciliation Tool
Streamlit UI.  Run with:  streamlit run app.py
"""

import io
from datetime import datetime, date

import pandas as pd
import streamlit as st

import core

# ---------------------------------------------------------------------------
# PAGE CONFIG + STYLING
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Vouchsafe — Audit Reconciliation",
    page_icon="📒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialise DB on first run
core.init_db()

# Custom CSS — editorial, restrained, serif headlines, tabular nums
st.markdown("""
<style>
    .stApp { background: #FAFAF7; }
    h1, h2, h3, h4 { font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif !important;
                     letter-spacing: -0.01em; color: #1C1917; }
    h1 { font-weight: 500 !important; }
    .stMetric { background: white; padding: 1rem; border-radius: 6px; border: 1px solid #E7E5E4; }
    .stMetric label { font-size: 0.7rem !important; text-transform: uppercase; letter-spacing: 0.12em;
                      color: #78716C !important; font-weight: 500; }
    .stMetric [data-testid="stMetricValue"] { font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
                                                font-weight: 400; font-variant-numeric: tabular-nums;
                                                color: #1C1917; font-size: 1.6rem; }
    .stMetric [data-testid="stMetricDelta"] { font-size: 0.75rem; }
    .eyebrow { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.18em;
               color: #78716C; font-weight: 500; margin-bottom: -0.5rem; }
    .accent { color: #9A3412; }
    .stDataFrame { font-variant-numeric: tabular-nums; }
    .stButton button { border-radius: 4px; font-weight: 500; }
    div[data-testid="stSidebar"] { background: white; border-right: 1px solid #E7E5E4; }
    div[data-testid="stSidebar"] h1 { font-size: 1.4rem; margin-bottom: 0; }
    .stFileUploader label { font-size: 0.8rem; }
    section[data-testid="stFileUploaderDropzone"] { background: #FAFAF7; border-style: dashed; }
    .stTabs [data-baseweb="tab"] { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("active_client_id", None)
ss.setdefault("view", "Dashboard")
# Module-specific dataframes parsed in this session
for k in ["gst2b_portal", "gst2b_books", "gst2b_result",
          "gst1_portal", "gst1_books", "gst1_result",
          "tds_portal", "tds_books", "tds_result",
          "bank_bank", "bank_books", "bank_result"]:
    ss.setdefault(k, None)


# ---------------------------------------------------------------------------
# SIDEBAR — NAVIGATION + ACTIVE CLIENT
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("# 📒 Vouchsafe")
    st.caption("AUDIT  ·  RECONCILIATION")
    st.write("")

    views = [
        ("Dashboard", "📊"),
        ("Clients", "👥"),
        ("— GST —", None),
        ("2B vs Purchase Reg.", "📄"),
        ("GSTR-1 vs Sales Reg.", "📄"),
        ("3B vs Books", "📄"),
        ("— TDS / Bank —", None),
        ("26AS vs TDS Ledger", "📑"),
        ("Bank Reconciliation", "🏦"),
        ("— Records —", None),
        ("Challans", "🧾"),
        ("Documents", "📁"),
    ]
    for label, icon in views:
        if icon is None:
            st.markdown(f"<div style='font-size:0.65rem;text-transform:uppercase;letter-spacing:0.15em;"
                        f"color:#A8A29E;padding-top:0.8rem;padding-bottom:0.2rem;padding-left:0.5rem;'>"
                        f"{label.strip(' —')}</div>", unsafe_allow_html=True)
            continue
        is_active = ss.view == label
        if st.button(
            f"{icon}  {label}",
            key=f"nav_{label}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            ss.view = label
            st.rerun()

    st.write("")
    st.caption(f"DB · {core.DB_PATH.name}")


# ---------------------------------------------------------------------------
# TOP BAR — Active client selector
# ---------------------------------------------------------------------------
def render_top_bar():
    clients = core.list_clients()
    col1, col2, col3 = st.columns([3, 2, 2])
    with col1:
        if not clients:
            st.markdown("<div class='eyebrow'>Active Client</div>"
                        "<div style='color:#A8A29E;font-style:italic;'>no clients yet — add one in Clients</div>",
                        unsafe_allow_html=True)
        else:
            options = {f"{c['name']}  ·  {c['gstin'] or 'No GSTIN'}": c["id"] for c in clients}
            if ss.active_client_id not in [c["id"] for c in clients]:
                ss.active_client_id = clients[0]["id"]
            current_key = next(k for k, v in options.items() if v == ss.active_client_id)
            st.markdown("<div class='eyebrow'>Active Client</div>", unsafe_allow_html=True)
            choice = st.selectbox("Active client", list(options.keys()),
                                  index=list(options.keys()).index(current_key),
                                  label_visibility="collapsed")
            if options[choice] != ss.active_client_id:
                ss.active_client_id = options[choice]
                # Clear module state when client changes
                for k in list(ss.keys()):
                    if any(k.startswith(p) for p in ("gst2b_", "gst1_", "tds_", "bank_")):
                        ss[k] = None
                st.rerun()
    with col3:
        st.markdown(f"<div style='text-align:right;color:#A8A29E;font-size:0.75rem;"
                    f"text-transform:uppercase;letter-spacing:0.1em;padding-top:1rem;'>"
                    f"Today · {datetime.now().strftime('%d %b %Y')}</div>",
                    unsafe_allow_html=True)
    st.divider()


def get_active_client():
    if not ss.active_client_id:
        return None
    return core.get_client(ss.active_client_id)


def require_client():
    c = get_active_client()
    if not c:
        st.warning("Please add and select a client first (Clients tab).")
        st.stop()
    return c


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
def view_dashboard():
    st.markdown("<div class='eyebrow'>Overview</div>", unsafe_allow_html=True)
    st.title("Practice Dashboard")
    st.caption("A consolidated view of every client, every reconciliation, every challan filed across your firm.")
    st.write("")

    clients = core.list_clients()
    recons = core.list_recons()
    total_challans = 0
    for c in clients:
        total_challans += len(core.list_challans(c["id"]))

    matched = mismatch = unmatched = 0
    for r in recons:
        s = r["summary"]
        matched += s.get("matched", 0)
        mismatch += s.get("mismatch", 0)
        unmatched += (s.get("only_portal", 0) + s.get("only_books", 0)
                      + s.get("only_26as", 0) + s.get("only_bank", 0))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Clients", len(clients))
    c2.metric("Reconciliations", len(recons), help=f"{matched + mismatch + unmatched} line items reviewed")
    c3.metric("Mismatches", mismatch)
    c4.metric("Challans Logged", total_challans)

    st.write("")
    left, right = st.columns([2, 1])
    with left:
        st.markdown("### Recent Reconciliations")
        if not recons:
            st.info("No reconciliations yet. Add a client, upload a portal file and your Tally export to begin.")
        else:
            rows = []
            for r in recons[:8]:
                client = core.get_client(r["client_id"])
                rows.append({
                    "Client": client["name"] if client else "—",
                    "Type": r["recon_type"],
                    "Period": r["period"] or "—",
                    "Matched": r["summary"].get("matched", 0),
                    "Mismatch": r["summary"].get("mismatch", 0),
                    "Saved": pd.to_datetime(r["created_at"]).strftime("%d/%m/%Y %H:%M"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with right:
        st.markdown("### Quick Actions")
        quick = [
            ("📄 GSTR-2B vs PR", "2B vs Purchase Reg."),
            ("📄 GSTR-1 vs SR", "GSTR-1 vs Sales Reg."),
            ("📄 3B vs Books", "3B vs Books"),
            ("📑 26AS vs Ledger", "26AS vs TDS Ledger"),
            ("🏦 Bank Recon", "Bank Reconciliation"),
            ("🧾 Add Challan", "Challans"),
        ]
        for label, target in quick:
            if st.button(label, key=f"q_{target}", use_container_width=True):
                ss.view = target
                st.rerun()


# ---------------------------------------------------------------------------
# CLIENTS
# ---------------------------------------------------------------------------
def view_clients():
    st.markdown("<div class='eyebrow'>Roster</div>", unsafe_allow_html=True)
    st.title("Clients")

    with st.expander("➕  Add New Client", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Entity Name *", key="new_client_name")
            gstin = st.text_input("GSTIN", key="new_client_gstin", max_chars=15)
            accounting_system = st.selectbox(
                "Accounting System",
                ["Tally", "Zoho Books", "QuickBooks", "Busy", "Other"],
                key="new_client_acct",
                help="So you know which export format to use for this client.",
            )
        with col2:
            pan = st.text_input("PAN", key="new_client_pan", max_chars=10)
            fy = st.text_input("Financial Year", value="FY 2024-25", key="new_client_fy")
        if st.button("Save Client", type="primary"):
            if not name.strip():
                st.error("Entity name is required")
            else:
                core.add_client(name, gstin, pan, fy, accounting_system)
                st.success(f"Added {name}")
                st.rerun()

    clients = core.list_clients()
    if not clients:
        st.info("No clients yet. Add your first audit client above.")
        return

    rows = []
    for c in clients:
        rc = core.list_recons(c["id"])
        ch = core.list_challans(c["id"])
        rows.append({
            "Entity": c["name"],
            "System": c.get("accounting_system") or "Tally",
            "GSTIN": c["gstin"] or "—",
            "PAN": c["pan"] or "—",
            "FY": c["fy"] or "—",
            "Recons": len(rc),
            "Challans": len(ch),
            "Active": "✓" if c["id"] == ss.active_client_id else "",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Manage existing
    st.markdown("### Manage Client")
    sel_name = st.selectbox("Select a client to edit/delete",
                            options=[c["name"] for c in clients])
    sel_client = next(c for c in clients if c["name"] == sel_name)
    col1, col2 = st.columns(2)
    with col1:
        e_name = st.text_input("Name", value=sel_client["name"], key=f"e_name_{sel_client['id']}")
        e_gstin = st.text_input("GSTIN", value=sel_client["gstin"] or "", key=f"e_gst_{sel_client['id']}")
        systems = ["Tally", "Zoho Books", "QuickBooks", "Busy", "Other"]
        current_sys = sel_client.get("accounting_system") or "Tally"
        if current_sys not in systems:
            systems.insert(0, current_sys)
        e_acct = st.selectbox(
            "Accounting System",
            systems,
            index=systems.index(current_sys),
            key=f"e_acct_{sel_client['id']}",
        )
    with col2:
        e_pan = st.text_input("PAN", value=sel_client["pan"] or "", key=f"e_pan_{sel_client['id']}")
        e_fy = st.text_input("FY", value=sel_client["fy"] or "", key=f"e_fy_{sel_client['id']}")
    bcol1, bcol2, bcol3 = st.columns([1, 1, 4])
    if bcol1.button("💾 Save", key=f"save_{sel_client['id']}"):
        core.update_client(sel_client["id"], e_name, e_gstin, e_pan, e_fy, e_acct)
        st.success("Updated")
        st.rerun()
    if bcol2.button("🗑 Delete", key=f"del_{sel_client['id']}", type="secondary"):
        core.delete_client(sel_client["id"])
        if ss.active_client_id == sel_client["id"]:
            ss.active_client_id = None
        st.warning("Deleted")
        st.rerun()


# ---------------------------------------------------------------------------
# GENERIC RECON HELPERS
# ---------------------------------------------------------------------------
def upload_pair(label_left: str, label_right: str, accept=["xlsx", "xls", "csv"], key_prefix=""):
    """Render two file uploaders side by side. Returns (file_left, file_right)."""
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"<div class='eyebrow'>{label_left}</div>", unsafe_allow_html=True)
        left = st.file_uploader(label_left, type=accept, key=f"{key_prefix}_left",
                                label_visibility="collapsed")
    with col2:
        st.markdown(f"<div class='eyebrow'>{label_right}</div>", unsafe_allow_html=True)
        right = st.file_uploader(label_right, type=accept, key=f"{key_prefix}_right",
                                 label_visibility="collapsed")
    return left, right


def format_df_for_display(df: pd.DataFrame, money_cols: list[str] = None,
                          date_cols: list[str] = None) -> pd.DataFrame:
    """Format DataFrame for display with INR money columns and DD/MM/YYYY dates."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for col in (money_cols or []):
        if col in out.columns:
            out[col] = out[col].apply(core.inr)
    for col in (date_cols or []):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y").fillna("—")
    return out


def csv_download(df: pd.DataFrame, filename: str, label: str = "Download CSV"):
    if df is None or df.empty:
        return
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, csv_bytes, file_name=filename, mime="text/csv")


# ---------------------------------------------------------------------------
# GSTR-2B vs PURCHASE REGISTER
# ---------------------------------------------------------------------------
def view_gst2b():
    client = require_client()
    st.markdown("<div class='eyebrow'>GST Reconciliation</div>", unsafe_allow_html=True)
    st.title("GSTR-2B vs Purchase Register")
    st.caption(f"For **{client['name']}** · Match ITC claimed in books against what suppliers actually uploaded.")

    # System-aware upload label
    system = client.get("accounting_system") or "Tally"
    books_label = f"Purchase Register ({system} export)"
    if system == "Zoho Books":
        st.caption("💡 **Zoho tip:** Use *Reports → Purchases → Bills Details* (one row per bill). "
                   "If you exported a line-item report, tick the aggregation box below.")

    left_file, right_file = upload_pair(
        "GSTR-2B (excel from GST portal)",
        books_label,
        key_prefix="gst2b",
    )

    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        period = st.text_input("Period", value="", placeholder="Apr 2024", key="gst2b_period")
    with col2:
        tolerance = st.number_input("Amount Tolerance (₹)", min_value=0.0, value=1.0, step=1.0, key="gst2b_tol")
    with col3:
        st.write("")
        aggregate = st.checkbox(
            "Aggregate duplicate invoices",
            value=(system == "Zoho Books"),
            key="gst2b_agg",
            help="Sums rows that share the same GSTIN + Invoice Number. "
                 "Use for Zoho line-item exports. Otherwise leave OFF — "
                 "duplicates may indicate a double-booking you WANT to catch.",
        )
    with col4:
        st.write("")
        st.write("")
        run = st.button("▶ Run Reconciliation", type="primary", use_container_width=True,
                        disabled=not (left_file and right_file))

    if run and left_file and right_file:
        with st.spinner("Parsing files and matching invoices…"):
            try:
                ss.gst2b_portal = core.parse_gstr2b(left_file)
                ss.gst2b_books = core.parse_purchase_register(right_file)
                if aggregate:
                    ss.gst2b_portal = core.aggregate_invoice_lines(ss.gst2b_portal)
                    ss.gst2b_books = core.aggregate_invoice_lines(ss.gst2b_books)
                ss.gst2b_result = core.reconcile_gst(ss.gst2b_portal, ss.gst2b_books, tolerance)
            except Exception as e:
                st.error(f"Parsing failed: {e}")
                return

    if ss.gst2b_portal is not None:
        st.caption(f"✓ Parsed: GSTR-2B {len(ss.gst2b_portal)} rows · Purchase Reg. {len(ss.gst2b_books)} rows")

    result = ss.gst2b_result
    if not result:
        st.info("Upload both files and click Run. We auto-detect column names like "
                "'GSTIN of supplier', 'Invoice Number', 'Taxable Value' etc.")
        return

    matched = result["matched"]
    mismatch = result["mismatch"]
    only_portal = result["only_portal"]
    only_books = result["only_books"]

    # ITC at risk = tax in books-only invoices
    itc_at_risk = 0.0
    if not only_books.empty:
        itc_at_risk = (only_books["igst"].sum() + only_books["cgst"].sum() + only_books["sgst"].sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Matched", len(matched))
    c2.metric("Mismatch", len(mismatch))
    c3.metric("Only in 2B", len(only_portal), help="supplier filed, not booked")
    c4.metric("Only in Books", len(only_books), help="ITC may be at risk")
    c5.metric("ITC at risk", core.inr(itc_at_risk))

    tabs = st.tabs([
        f"⚠️  Mismatch ({len(mismatch)})",
        f"❌  Only in Books ({len(only_books)})",
        f"📥  Only in 2B ({len(only_portal)})",
        f"✓  Matched ({len(matched)})",
    ])

    money_cols_match = ["portal_taxable", "book_taxable", "portal_igst", "book_igst",
                        "portal_cgst", "book_cgst", "portal_sgst", "book_sgst",
                        "portal_total", "book_total",
                        "diff_taxable", "diff_igst", "diff_cgst", "diff_sgst", "diff_total"]
    money_cols_side = ["taxable_value", "igst", "cgst", "sgst", "total"]

    with tabs[0]:
        if mismatch.empty:
            st.success("No value mismatches.")
        else:
            display = format_df_for_display(mismatch,
                                             money_cols=money_cols_match,
                                             date_cols=["invoice_date"])
            st.dataframe(display, use_container_width=True, hide_index=True)
            csv_download(mismatch, f"gst2b_mismatch_{period or 'export'}.csv")

    with tabs[1]:
        if only_books.empty:
            st.success("All booked invoices appear in 2B.")
        else:
            display = format_df_for_display(only_books,
                                             money_cols=money_cols_side,
                                             date_cols=["invoice_date"])
            st.dataframe(display, use_container_width=True, hide_index=True)
            csv_download(only_books, f"gst2b_only_books_{period or 'export'}.csv")

    with tabs[2]:
        if only_portal.empty:
            st.success("All 2B invoices are in books.")
        else:
            display = format_df_for_display(only_portal,
                                             money_cols=money_cols_side,
                                             date_cols=["invoice_date"])
            st.dataframe(display, use_container_width=True, hide_index=True)
            csv_download(only_portal, f"gst2b_only_portal_{period or 'export'}.csv")

    with tabs[3]:
        if matched.empty:
            st.info("No matched invoices.")
        else:
            display = format_df_for_display(matched,
                                             money_cols=money_cols_match,
                                             date_cols=["invoice_date"])
            st.dataframe(display, use_container_width=True, hide_index=True)
            csv_download(matched, f"gst2b_matched_{period or 'export'}.csv")

    st.divider()
    sc1, sc2 = st.columns([1, 5])
    if sc1.button("💾  Save to Client Record", type="primary", use_container_width=True):
        summary = {"matched": len(matched), "mismatch": len(mismatch),
                   "only_portal": len(only_portal), "only_books": len(only_books),
                   "itc_at_risk": float(itc_at_risk)}
        data = {
            "matched": core.df_to_records(matched),
            "mismatch": core.df_to_records(mismatch),
            "only_portal": core.df_to_records(only_portal),
            "only_books": core.df_to_records(only_books),
        }
        core.save_recon(client["id"], "GSTR-2B vs PR", period or "Unspecified", summary, data)
        st.success("Saved to client record.")


# ---------------------------------------------------------------------------
# GSTR-1 vs SALES REGISTER  (similar mechanics; outward direction)
# ---------------------------------------------------------------------------
def view_gst1():
    client = require_client()
    st.markdown("<div class='eyebrow'>GST Reconciliation</div>", unsafe_allow_html=True)
    st.title("GSTR-1 vs Sales Register")
    st.caption(f"For **{client['name']}** · Confirm every outward supply in books was reported on the portal.")

    system = client.get("accounting_system") or "Tally"
    sales_label = f"Sales Register ({system} export)"
    if system == "Zoho Books":
        st.caption("💡 **Zoho tip:** Use *Reports → Sales → Invoice Details* (one row per invoice). "
                   "If your export has one row per line item, tick the aggregation box below.")

    left_file, right_file = upload_pair(
        "GSTR-1 (filed return excel)",
        sales_label,
        key_prefix="gst1",
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        period = st.text_input("Period", placeholder="Apr 2024", key="gst1_period")
    with col2:
        tolerance = st.number_input("Tolerance (₹)", min_value=0.0, value=1.0, step=1.0, key="gst1_tol")
    with col3:
        st.write("")
        aggregate = st.checkbox(
            "Aggregate duplicate invoices",
            value=(system == "Zoho Books"),
            key="gst1_agg",
            help="Sums rows that share the same GSTIN + Invoice Number. Useful for Zoho line-item exports.",
        )
    with col4:
        st.write("")
        st.write("")
        run = st.button("▶ Run Reconciliation", type="primary", use_container_width=True,
                        disabled=not (left_file and right_file))

    if run and left_file and right_file:
        with st.spinner("Parsing and matching…"):
            try:
                ss.gst1_portal = core.parse_gstr1(left_file)
                ss.gst1_books = core.parse_sales_register(right_file)
                if aggregate:
                    ss.gst1_portal = core.aggregate_invoice_lines(ss.gst1_portal)
                    ss.gst1_books = core.aggregate_invoice_lines(ss.gst1_books)
                ss.gst1_result = core.reconcile_gst(ss.gst1_portal, ss.gst1_books, tolerance)
            except Exception as e:
                st.error(f"Parsing failed: {e}")
                return

    result = ss.gst1_result
    if not result:
        st.info("Upload both files and click Run. Same engine as GSTR-2B but for outward supplies.")
        return

    matched, mismatch, only_portal, only_books = (
        result["matched"], result["mismatch"], result["only_portal"], result["only_books"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matched", len(matched))
    c2.metric("Mismatch", len(mismatch))
    c3.metric("In Books, Not Filed", len(only_books), help="reporting gap")
    c4.metric("Only on Portal", len(only_portal))

    tabs = st.tabs([
        f"⚠️  Mismatch ({len(mismatch)})",
        f"❌  In Books, Not Filed ({len(only_books)})",
        f"📥  Only on Portal ({len(only_portal)})",
        f"✓  Matched ({len(matched)})",
    ])
    money_match = ["portal_taxable", "book_taxable", "portal_total", "book_total", "diff_total"]
    money_side = ["taxable_value", "igst", "cgst", "sgst", "total"]

    with tabs[0]:
        if mismatch.empty: st.success("No mismatches.")
        else:
            st.dataframe(format_df_for_display(mismatch, money_match, ["invoice_date"]),
                         use_container_width=True, hide_index=True)
            csv_download(mismatch, f"gst1_mismatch_{period or 'export'}.csv")
    with tabs[1]:
        if only_books.empty: st.success("All sales reported.")
        else:
            st.dataframe(format_df_for_display(only_books, money_side, ["invoice_date"]),
                         use_container_width=True, hide_index=True)
            csv_download(only_books, f"gst1_unreported_{period or 'export'}.csv")
    with tabs[2]:
        if only_portal.empty: st.success("Empty.")
        else:
            st.dataframe(format_df_for_display(only_portal, money_side, ["invoice_date"]),
                         use_container_width=True, hide_index=True)
    with tabs[3]:
        if matched.empty: st.info("No matches.")
        else:
            st.dataframe(format_df_for_display(matched, money_match, ["invoice_date"]),
                         use_container_width=True, hide_index=True)

    st.divider()
    if st.button("💾  Save to Client Record", type="primary"):
        summary = {"matched": len(matched), "mismatch": len(mismatch),
                   "only_portal": len(only_portal), "only_books": len(only_books)}
        data = {
            "matched": core.df_to_records(matched),
            "mismatch": core.df_to_records(mismatch),
            "only_portal": core.df_to_records(only_portal),
            "only_books": core.df_to_records(only_books),
        }
        core.save_recon(client["id"], "GSTR-1 vs SR", period or "Unspecified", summary, data)
        st.success("Saved.")


# ---------------------------------------------------------------------------
# GSTR-3B vs BOOKS — manual line-item entry
# ---------------------------------------------------------------------------
def view_gst3b():
    client = require_client()
    st.markdown("<div class='eyebrow'>GST Reconciliation</div>", unsafe_allow_html=True)
    st.title("GSTR-3B vs Books")
    st.caption(f"For **{client['name']}** · Tie the headline 3B return to your trial balance.")

    period = st.text_input("Period", placeholder="Apr 2024", key="gst3b_period")

    fields = [
        ("Outward — Taxable Value", "outward_taxable"),
        ("Outward — IGST", "outward_igst"),
        ("Outward — CGST", "outward_cgst"),
        ("Outward — SGST / UTGST", "outward_sgst"),
        ("Inward — Taxable Value", "inward_taxable"),
        ("ITC — IGST", "itc_igst"),
        ("ITC — CGST", "itc_cgst"),
        ("ITC — SGST", "itc_sgst"),
    ]

    st.write("")
    h1, h2, h3, h4 = st.columns([3, 2, 2, 2])
    h1.markdown("**Particulars**")
    h2.markdown("**As per Books (₹)**")
    h3.markdown("**As filed in 3B (₹)**")
    h4.markdown("**Difference**")
    st.divider()

    book_vals = {}
    filed_vals = {}
    diffs = {}
    for label, key in fields:
        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
        c1.write(label)
        book_vals[key] = c2.number_input(" ", value=0.0, step=1.0,
                                          key=f"book_{key}", label_visibility="collapsed")
        filed_vals[key] = c3.number_input(" ", value=0.0, step=1.0,
                                           key=f"filed_{key}", label_visibility="collapsed")
        d = filed_vals[key] - book_vals[key]
        diffs[key] = d
        c4.markdown(f"<div style='text-align:right;padding-top:0.5rem;font-variant-numeric:tabular-nums;"
                    f"color:{'#B45309' if abs(d) > 1 else '#A8A29E'};font-weight:{'600' if abs(d) > 1 else '400'};'>"
                    f"{core.inr(d) if abs(d) > 0.01 else '—'}</div>", unsafe_allow_html=True)

    st.divider()
    if st.button("💾  Save to Client Record", type="primary"):
        total_diff = sum(abs(v) for v in diffs.values())
        summary = {"matched": 8 if total_diff < 1 else 0, "mismatch": 0 if total_diff < 1 else 8,
                   "only_portal": 0, "only_books": 0}
        data = {"book": book_vals, "filed": filed_vals, "diffs": diffs}
        core.save_recon(client["id"], "GSTR-3B vs Books", period or "Unspecified", summary, data)
        st.success("Saved.")


# ---------------------------------------------------------------------------
# 26AS vs TDS LEDGER
# ---------------------------------------------------------------------------
def view_tds():
    client = require_client()
    st.markdown("<div class='eyebrow'>TDS Reconciliation</div>", unsafe_allow_html=True)
    st.title("Form 26AS vs TDS Ledger")
    st.caption(f"For **{client['name']}** · Recover unclaimed TDS credits, flag deductors who haven't filed.")

    if not core.HAS_PDF:
        st.info("ℹ️ For PDF Form 26AS support, install pdfplumber: `pip install pdfplumber`. "
                "Otherwise export 26AS as Excel from the TRACES portal.")

    system = client.get("accounting_system") or "Tally"
    ledger_label = f"TDS Ledger ({system} export)"
    if system == "Zoho Books":
        st.caption("💡 **Zoho tip:** Use *Reports → Taxes → TDS Summary* "
                   "or *TDS Withheld* — both export with Vendor TAN, Section, "
                   "Taxable Amount and TDS Amount columns.")

    left_file, right_file = upload_pair(
        "Form 26AS (excel from TRACES, or PDF)",
        ledger_label,
        accept=["xlsx", "xls", "csv", "pdf"],
        key_prefix="tds",
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.text_input("Period", value="FY 2024-25", key="tds_period")
    with col2:
        tolerance = st.number_input("TDS Tolerance (₹)", min_value=0.0, value=1.0, step=1.0, key="tds_tol")
    with col3:
        st.write("")
        st.write("")
        run = st.button("▶ Run Reconciliation", type="primary", use_container_width=True,
                        disabled=not (left_file and right_file))

    if run and left_file and right_file:
        with st.spinner("Parsing and matching…"):
            try:
                ss.tds_portal = core.parse_26as(left_file)
                ss.tds_books = core.parse_tds_ledger(right_file)
                ss.tds_result = core.reconcile_26as(ss.tds_portal, ss.tds_books, tolerance)
            except Exception as e:
                st.error(f"Parsing failed: {e}")
                return

    result = ss.tds_result
    if not result:
        st.info("Upload both files and click Run. We match on TAN with TDS amount + amount paid as corroboration.")
        return

    matched, mismatch, only_26as, only_books = (
        result["matched"], result["mismatch"], result["only_26as"], result["only_books"])
    unclaimed = only_26as["tds_amount"].sum() if not only_26as.empty else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Matched", len(matched))
    c2.metric("Mismatch", len(mismatch))
    c3.metric("Only in 26AS", len(only_26as), help="unclaimed credit available")
    c4.metric("Only in Books", len(only_books), help="deductor hasn't filed")
    c5.metric("Unclaimed TDS", core.inr(unclaimed))

    tabs = st.tabs([
        f"⚠️  Mismatch ({len(mismatch)})",
        f"📥  Only in 26AS ({len(only_26as)})",
        f"❌  Only in Books ({len(only_books)})",
        f"✓  Matched ({len(matched)})",
    ])
    money_match = ["portal_amount_paid", "book_amount_paid", "portal_tds", "book_tds",
                   "diff_amount_paid", "diff_tds"]
    money_side = ["amount_paid", "tds_amount"]

    with tabs[0]:
        if mismatch.empty: st.success("No mismatches.")
        else:
            st.dataframe(format_df_for_display(mismatch, money_match, ["date"]),
                         use_container_width=True, hide_index=True)
            csv_download(mismatch, f"tds_mismatch_{period}.csv")
    with tabs[1]:
        if only_26as.empty: st.success("Empty.")
        else:
            st.dataframe(format_df_for_display(only_26as, money_side, ["date"]),
                         use_container_width=True, hide_index=True)
            csv_download(only_26as, f"tds_unclaimed_{period}.csv")
    with tabs[2]:
        if only_books.empty: st.success("All booked TDS appears in 26AS.")
        else:
            st.dataframe(format_df_for_display(only_books, money_side, ["date"]),
                         use_container_width=True, hide_index=True)
            csv_download(only_books, f"tds_followup_{period}.csv")
    with tabs[3]:
        if matched.empty: st.info("No matches.")
        else:
            st.dataframe(format_df_for_display(matched, money_match, ["date"]),
                         use_container_width=True, hide_index=True)

    st.divider()
    if st.button("💾  Save to Client Record", type="primary"):
        summary = {"matched": len(matched), "mismatch": len(mismatch),
                   "only_26as": len(only_26as), "only_books": len(only_books),
                   "unclaimed_tds": float(unclaimed)}
        data = {
            "matched": core.df_to_records(matched),
            "mismatch": core.df_to_records(mismatch),
            "only_26as": core.df_to_records(only_26as),
            "only_books": core.df_to_records(only_books),
        }
        core.save_recon(client["id"], "Form 26AS vs TDS", period, summary, data)
        st.success("Saved.")


# ---------------------------------------------------------------------------
# BANK RECONCILIATION
# ---------------------------------------------------------------------------
def view_bank():
    client = require_client()
    st.markdown("<div class='eyebrow'>Bank Reconciliation</div>", unsafe_allow_html=True)
    st.title("Bank Statement vs Bank Ledger")
    st.caption(f"For **{client['name']}** · Configurable date window handles cheque clearing delays.")

    system = client.get("accounting_system") or "Tally"
    book_label = f"Bank Ledger ({system} export)"
    if system == "Zoho Books":
        st.caption("💡 **Zoho tip:** Use *Banking → [account] → Export* — works with both "
                   "Deposits/Withdrawals columns and the single-Amount + Type column format.")

    left_file, right_file = upload_pair(
        "Bank Statement (.csv / .xlsx)",
        book_label,
        key_prefix="bank",
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        period = st.text_input("Period", placeholder="Apr 2024", key="bank_period")
    with col2:
        tolerance = st.number_input("Tolerance (₹)", min_value=0.0, value=1.0, step=1.0, key="bank_tol")
    with col3:
        days = st.number_input("Date Window (days)", min_value=0, max_value=30, value=3, key="bank_days")
    with col4:
        st.write("")
        st.write("")
        run = st.button("▶ Run", type="primary", use_container_width=True,
                        disabled=not (left_file and right_file))

    if run and left_file and right_file:
        with st.spinner("Parsing and matching…"):
            try:
                ss.bank_bank = core.parse_bank_statement(left_file)
                ss.bank_books = core.parse_bank_ledger(right_file)
                ss.bank_result = core.reconcile_bank(ss.bank_bank, ss.bank_books, tolerance, days)
            except Exception as e:
                st.error(f"Parsing failed: {e}")
                return

    result = ss.bank_result
    if not result:
        st.info("Upload a CSV/XLSX bank statement and your bank ledger from Tally. "
                "We expect columns like Date/Transaction Date, Narration/Particulars, Debit/Withdrawal, Credit/Deposit.")
        return

    matched, only_bank, only_books = result["matched"], result["only_bank"], result["only_books"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Matched", len(matched))
    c2.metric("Only in Bank", len(only_bank), help="uncleared in books")
    c3.metric("Only in Books", len(only_books), help="uncleared at bank")

    tabs = st.tabs([
        f"❌  Only in Bank ({len(only_bank)})",
        f"❌  Only in Books ({len(only_books)})",
        f"✓  Matched ({len(matched)})",
    ])
    with tabs[0]:
        if only_bank.empty: st.success("All bank entries cleared.")
        else:
            st.dataframe(format_df_for_display(only_bank, ["amount", "balance"], ["date"]),
                         use_container_width=True, hide_index=True)
            csv_download(only_bank, f"bank_only_bank_{period or 'export'}.csv")
    with tabs[1]:
        if only_books.empty: st.success("All book entries cleared.")
        else:
            st.dataframe(format_df_for_display(only_books, ["amount", "balance"], ["date"]),
                         use_container_width=True, hide_index=True)
            csv_download(only_books, f"bank_only_books_{period or 'export'}.csv")
    with tabs[2]:
        if matched.empty: st.info("No matches.")
        else:
            st.dataframe(format_df_for_display(matched, ["amount"], ["bank_date", "book_date"]),
                         use_container_width=True, hide_index=True)

    st.divider()
    if st.button("💾  Save to Client Record", type="primary"):
        summary = {"matched": len(matched), "mismatch": 0,
                   "only_bank": len(only_bank), "only_books": len(only_books)}
        data = {
            "matched": core.df_to_records(matched),
            "only_bank": core.df_to_records(only_bank),
            "only_books": core.df_to_records(only_books),
        }
        core.save_recon(client["id"], "Bank Recon", period or "Unspecified", summary, data)
        st.success("Saved.")


# ---------------------------------------------------------------------------
# CHALLANS
# ---------------------------------------------------------------------------
def view_challans():
    client = require_client()
    st.markdown("<div class='eyebrow'>Repository</div>", unsafe_allow_html=True)
    st.title("Challans")
    st.caption(f"Tax challans for **{client['name']}**")

    with st.expander("➕  Add New Challan", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            ctype = st.selectbox("Type", ["GST", "TDS", "Income Tax", "PT/PF/ESI", "Other"])
            cin = st.text_input("CIN / Challan No.", key="new_ch_cin")
        with col2:
            bsr = st.text_input("BSR Code", key="new_ch_bsr")
            payment_date = st.date_input("Payment Date", value=date.today(), key="new_ch_date").strftime("%d/%m/%Y")
        with col3:
            amount = st.number_input("Amount (₹)", min_value=0.0, step=1.0, key="new_ch_amt")
            period = st.text_input("Period", placeholder="Apr 2024", key="new_ch_period")
        notes = st.text_input("Notes (optional)", key="new_ch_notes")
        if st.button("Save Challan", type="primary"):
            if not cin.strip() or amount <= 0:
                st.error("CIN and Amount are required.")
            else:
                core.add_challan(client["id"], ctype, cin, bsr, payment_date, amount, period, notes)
                st.success("Challan added.")
                st.rerun()

    list_ = core.list_challans(client["id"])
    if not list_:
        st.info("No challans logged for this client yet.")
        return

    total = sum(c["amount"] for c in list_)
    by_type = {}
    for c in list_:
        by_type[c["ctype"]] = by_type.get(c["ctype"], 0) + c["amount"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Logged", len(list_))
    c2.metric("Total Value", core.inr(total))
    c3.metric("GST", core.inr(by_type.get("GST", 0)))
    c4.metric("TDS / IT", core.inr(by_type.get("TDS", 0) + by_type.get("Income Tax", 0)))

    df = pd.DataFrame([{
        "Type": c["ctype"], "CIN": c["cin"], "BSR": c["bsr"] or "—",
        "Date": c["payment_date"] or "—", "Period": c["period"] or "—",
        "Amount": core.inr(c["amount"]), "Notes": c["notes"] or "—",
        "id": c["id"],
    } for c in list_])
    st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)

    # Delete UI
    with st.expander("🗑  Delete a Challan"):
        if list_:
            choice = st.selectbox("Select",
                                   options=[f"{c['ctype']} · {c['cin']} · {core.inr(c['amount'])}" for c in list_],
                                   key="del_ch_sel")
            idx = [f"{c['ctype']} · {c['cin']} · {core.inr(c['amount'])}" for c in list_].index(choice)
            if st.button("Confirm Delete", type="secondary"):
                core.delete_challan(list_[idx]["id"])
                st.warning("Deleted")
                st.rerun()


# ---------------------------------------------------------------------------
# DOCUMENTS
# ---------------------------------------------------------------------------
def view_documents():
    client = require_client()
    st.markdown("<div class='eyebrow'>Vault</div>", unsafe_allow_html=True)
    st.title("Documents")
    st.caption(f"Supporting paperwork for **{client['name']}** — engagement letters, notices, working papers.")

    upload = st.file_uploader("Upload document", type=None, key="doc_upload")
    tag = st.selectbox("Tag", ["General", "Engagement", "Statement", "Notice", "Reply", "Working Paper", "Other"])
    if upload and st.button("Save to Vault", type="primary"):
        core.save_document(client["id"], upload, tag=tag)
        st.success(f"Saved {upload.name}")
        st.rerun()

    docs = core.list_documents(client["id"])
    if not docs:
        st.info("Vault is empty for this client.")
        return

    rows = []
    for d in docs:
        size_kb = d["file_size"] / 1024 if d["file_size"] else 0
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"
        rows.append({
            "File": d["filename"], "Tag": d["tag"], "Size": size_str,
            "Type": d["file_type"] or "—",
            "Uploaded": pd.to_datetime(d["uploaded_at"]).strftime("%d/%m/%Y %H:%M"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Action selector
    with st.expander("📥  Download or 🗑 Delete"):
        choice = st.selectbox("Select file", options=[d["filename"] for d in docs], key="doc_sel")
        sel = next(d for d in docs if d["filename"] == choice)
        col1, col2, col3 = st.columns(3)
        try:
            with open(sel["stored_path"], "rb") as f:
                col1.download_button("Download", f.read(), file_name=sel["filename"])
        except FileNotFoundError:
            col1.error("File missing on disk")
        new_tag = col2.selectbox("Re-tag",
                                  ["General", "Engagement", "Statement", "Notice", "Reply", "Working Paper", "Other"],
                                  index=["General", "Engagement", "Statement", "Notice", "Reply", "Working Paper", "Other"].index(sel["tag"] or "General"),
                                  key="doc_retag")
        if col2.button("Update Tag"):
            core.update_document_tag(sel["id"], new_tag)
            st.success("Re-tagged")
            st.rerun()
        if col3.button("Delete", type="secondary"):
            core.delete_document(sel["id"])
            st.warning("Deleted")
            st.rerun()


# ---------------------------------------------------------------------------
# MAIN ROUTER
# ---------------------------------------------------------------------------
render_top_bar()

routes = {
    "Dashboard": view_dashboard,
    "Clients": view_clients,
    "2B vs Purchase Reg.": view_gst2b,
    "GSTR-1 vs Sales Reg.": view_gst1,
    "3B vs Books": view_gst3b,
    "26AS vs TDS Ledger": view_tds,
    "Bank Reconciliation": view_bank,
    "Challans": view_challans,
    "Documents": view_documents,
}
routes.get(ss.view, view_dashboard)()
