"""FamilySearch-inspired branding and theming for the dashboard."""
import streamlit as st

COLORS = {
    "primary": "#3b8520",
    "secondary": "#1a4314",
    "accent": "#5ba639",
    "bg": "#f7f9f4",
    "card_bg": "#ffffff",
    "text": "#2c3e2d",
    "border": "#d4e6cd",
    "muted": "#6b8f6b",
    "warning": "#d4a843",
    "error": "#c0392b",
    "info": "#2980b9",
}

CHART_PALETTE = ["#3b8520", "#2980b9", "#c0392b", "#8e44ad", "#d4a843",
                 "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b"]
SEQUENTIAL = ["#e8f5e2", "#c8e6c9", "#a5d6a7", "#81c784", "#66bb6a",
              "#4caf50", "#43a047", "#388e3c", "#2e7d32", "#1b5e20"]


def apply_branding():
    st.markdown('''<style>
    @import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Source+Sans+3:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Source Sans 3', sans-serif; color: #2c3e2d; }
    .block-container { padding-top: 1rem !important; }
    header[data-testid="stHeader"] { height: 2.5rem !important; }
    h1, h2, h3 { font-family: 'Libre Baskerville', serif; color: #1a4314; letter-spacing: -0.02em; }
    h1 { font-size: 2rem; }
    h2 { font-size: 1.5rem; border-bottom: 2px solid #d4e6cd; padding-bottom: 0.4rem; margin-top: 2rem; }
    h3 { font-size: 1.15rem; }

    .metric-card {
        background: white; border: 1px solid #d4e6cd; border-radius: 8px;
        padding: 1rem 1.2rem; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .metric-card .label { font-size: 0.8rem; color: #6b8f6b; text-transform: uppercase;
                          letter-spacing: 0.05em; margin-bottom: 0.2rem; }
    .metric-card .value { font-size: 1.7rem; font-weight: 700; color: #1a4314; }
    .metric-card .delta { font-size: 0.8rem; margin-top: 0.15rem; }

    blockquote {
        border-left: 4px solid #3b8520; padding: 1rem 1.5rem; background: #e8f0e3;
        font-style: italic; font-family: 'Libre Baskerville', serif; color: #2c3e2d;
        margin: 1.5rem 0; border-radius: 0 6px 6px 0;
    }
    blockquote .attribution { font-style: normal; font-weight: 600; display: block;
                              margin-top: 0.5rem; text-align: right; font-size: 0.9rem; }

    /* ── Sidebar ───────────────────────────────────────────────── */
    [data-testid="stSidebar"] { background-color: #1a4314; }

    /* Collapse button — float over header */
    [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        height: auto !important; min-height: 0 !important;
        padding: 0.3rem 0.3rem 0 0 !important; margin: 0 !important;
        position: absolute !important; top: 0.4rem; right: 0.4rem; z-index: 10;
    }

    /* Kill spacing on all sidebar wrappers */
    [data-testid="stSidebar"] div {
        padding-top: 0 !important; margin-top: 0 !important; min-height: 0 !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        display: flex !important; flex-direction: column !important;
        gap: 0 !important; padding: 0 !important;
    }
    [data-testid="stSidebar"] > div:first-child > div:has(.sidebar-header) { order: -1 !important; }
    [data-testid="stSidebarUserContent"] { padding: 0 1rem !important; margin: 0 !important; }
    [data-testid="stSidebarNav"] { margin: 0 !important; padding: 0.3rem 0 0 0 !important; }
    [data-testid="stSidebarNav"] ul { padding-top: 0 !important; margin-top: 0 !important; }
    section[data-testid="stSidebar"] > div { padding-top: 0 !important; }

    /* All sidebar text */
    [data-testid="stSidebar"] * { color: #e8f0e3 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #ffffff !important; }

    /* Sidebar header */
    .sidebar-header {
        padding: 1.2rem 1rem 0.5rem 1rem; text-align: left;
        border-bottom: 1px solid rgba(255,255,255,0.15); margin: 2.5rem 0 0 0;
    }
    .sidebar-header .title { font-family: 'Libre Baskerville', serif;
        font-size: 1.3rem; font-weight: 700; color: #ffffff !important;
        margin: 0 0 0.2rem 0; line-height: 1.3; }
    .sidebar-header .subtitle { font-size: 0.85rem; color: #a8d5a0 !important;
        margin: 0 0 0.6rem 0; font-weight: 400; }
    .sidebar-header .tags { font-size: 0.7rem; color: rgba(255,255,255,0.5) !important;
        text-transform: uppercase; letter-spacing: 0.08em; }

    /* Nav page links */
    [data-testid="stSidebarNav"] a { color: #e8f0e3 !important; text-decoration: none !important; }
    [data-testid="stSidebarNav"] a:hover { color: #ffffff !important; }
    [data-testid="stSidebarNav"] a span { color: #d4e6cd !important; font-weight: 500;
        font-size: 0.92rem !important; }
    [data-testid="stSidebarNav"] a[aria-current="page"] span,
    [data-testid="stSidebarNav"] li[class*="active"] a span { color: #ffffff !important; font-weight: 700; }
    [data-testid="stSidebarNav"] a[aria-current="page"],
    [data-testid="stSidebarNav"] li[class*="active"] {
        background-color: rgba(91, 166, 57, 0.25) !important; border-radius: 6px;
    }
    [data-testid="stSidebarNav"] a svg,
    [data-testid="stSidebarNav"] a img { opacity: 0.4 !important; }
    [data-testid="stSidebarNav"] a:hover svg,
    [data-testid="stSidebarNav"] a:hover img { opacity: 0.7 !important; }

    /* ── Sidebar tab buttons ───────────────────────────────── */
    .sidebar-tabs {
        display: flex; gap: 0; margin: 0.4rem 0 0.2rem 0;
        border-bottom: 2px solid rgba(255,255,255,0.15);
    }
    .sidebar-tabs .tab-btn {
        flex: 1; padding: 0.4rem 0; text-align: center; cursor: pointer;
        font-size: 0.78rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.06em; color: rgba(255,255,255,0.5); background: none;
        border: none; border-bottom: 2px solid transparent;
        margin-bottom: -2px; transition: all 0.15s;
    }
    .sidebar-tabs .tab-btn:hover { color: rgba(255,255,255,0.8); }
    .sidebar-tabs .tab-btn.active {
        color: #ffffff; border-bottom-color: #5ba639;
    }

    /* Hide nav when Controls tab is active */
    .sidebar-hide-nav [data-testid="stSidebarNav"] { display: none !important; }

    /* ── Main content ──────────────────────────────────────── */
    .streamlit-expanderHeader { font-family: 'Libre Baskerville', serif; }
    div[data-testid="stExpander"] { border: 1px solid #d4e6cd; border-radius: 8px; }
    .stTabs [data-baseweb="tab"] { font-family: 'Source Sans 3', sans-serif; font-weight: 600; }
    .stTabs [aria-selected="true"] { border-bottom-color: #3b8520 !important; color: #3b8520; }
    .insight-box { background: #e8f0e3; border-left: 4px solid #3b8520;
                   padding: 1rem; border-radius: 0 6px 6px 0; margin: 0.8rem 0; }
    .warning-box { background: #fef9e7; border-left: 4px solid #d4a843;
                   padding: 1rem; border-radius: 0 6px 6px 0; margin: 0.8rem 0; }
    </style>''', unsafe_allow_html=True)

    # Always render sidebar header
    _sidebar_header()


def sidebar_tab() -> str:
    """Render sidebar tab buttons (Nav / Controls). Returns 'nav' or 'controls'.
    When 'controls' is active, the auto-nav is hidden via CSS class injection."""

    if "_sidebar_mode" not in st.session_state:
        st.session_state["_sidebar_mode"] = "nav"

    # Render tab buttons as HTML + use hidden Streamlit buttons for click handling
    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("Navigate", key="_tab_nav", use_container_width=True,
                      type="primary" if st.session_state["_sidebar_mode"] == "nav" else "secondary"):
            st.session_state["_sidebar_mode"] = "nav"
            st.rerun()
    with c2:
        if st.button("Controls", key="_tab_ctrl", use_container_width=True,
                      type="primary" if st.session_state["_sidebar_mode"] == "controls" else "secondary"):
            st.session_state["_sidebar_mode"] = "controls"
            st.rerun()

    mode = st.session_state["_sidebar_mode"]

    # Hide nav links when Controls is active
    if mode == "controls":
        st.sidebar.markdown(
            '<style>[data-testid="stSidebarNav"]{display:none!important}</style>',
            unsafe_allow_html=True)
    else:
        st.sidebar.caption("Select a page above to navigate.")

    return mode


def sidebar_header():
    """Public alias."""
    _sidebar_header()


def metric_card(label, value, delta=None):
    d = ""
    if delta:
        color = "#3b8520" if str(delta).startswith("+") or str(delta).startswith("$") else "#c0392b"
        d = f'<div class="delta" style="color:{color}">{delta}</div>'
    st.markdown(f'<div class="metric-card"><div class="label">{label}</div>'
                f'<div class="value">{value}</div>{d}</div>', unsafe_allow_html=True)


def section_header(title, subtitle=None):
    sub = f'<p style="color:#6b8f6b;font-size:0.95rem;margin-top:-0.5rem;">{subtitle}</p>' if subtitle else ""
    st.markdown(f'<h2>{title}</h2>{sub}', unsafe_allow_html=True)


def fisher_quote():
    st.markdown('''<blockquote>
    "We have the duty of formulating, of summarizing, and of communicating our
    conclusions, in intelligible form, in recognition of the right of other free minds
    to utilize them in making their own decisions."
    <span class="attribution">&mdash; R.A. Fisher</span>
    </blockquote>''', unsafe_allow_html=True)


def _sidebar_header():
    """Render the branded sidebar header above the page navigator."""
    st.sidebar.markdown('''
    <div class="sidebar-header">
        <div class="title">FamilySearch</div>
        <div class="subtitle">User Segmentation Analysis</div>
        <div class="tags">Data Scientist Exercise</div>
        <div class="tags">Machine Learning &bull; Clustering &bull; EDA</div>
    </div>
    ''', unsafe_allow_html=True)


def insight_box(text):
    st.markdown(f'<div class="insight-box">{text}</div>', unsafe_allow_html=True)


def warning_box(text):
    st.markdown(f'<div class="warning-box">{text}</div>', unsafe_allow_html=True)
