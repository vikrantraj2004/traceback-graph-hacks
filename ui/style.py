"""Visual theme for the Streamlit UI: a dark, dense, quiet look with thin borders and one accent.
Pure presentation. No data or logic lives here."""
import html

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }
.stApp { background: radial-gradient(900px 420px at 78% -8%, rgba(16,185,129,.16), transparent 62%),
                      radial-gradient(700px 380px at 5% 0%, rgba(5,150,105,.10), transparent 60%), #050A08; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }
section[data-testid="stSidebar"] { background: #07100C; border-right: 1px solid #12281C; }

h1 { font-size: 1.6rem !important; font-weight: 600 !important; letter-spacing: -0.02em; }
h1 { background: linear-gradient(90deg,#EEF6F1,#6EE7B7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
h2, h3 { font-weight: 600 !important; letter-spacing: -0.01em; color: #EEF6F1; }
h3 { font-size: 1.05rem !important; }
[data-testid="stCaptionContainer"] { color: #86A396; }

/* metrics as quiet cards */
[data-testid="stMetric"] {
  background: linear-gradient(180deg, #0B1812, #08120D); border: 1px solid #14301F;
  border-left: 2px solid #10B981; border-radius: 10px; padding: 14px 16px;
}
[data-testid="stMetricLabel"] { color: #86A396; font-size: 0.78rem; }
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; }

/* bordered containers (action cards) */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: #09130E; border: 1px solid #14301F !important; border-radius: 10px;
}
[data-testid="stExpander"] { border: 1px solid #14301F; border-radius: 10px; background: #09130E; }
[data-testid="stForm"] { border: 1px solid #14301F; border-radius: 10px; background: #09130E; }

/* tabs */
button[data-baseweb="tab"] { font-weight: 500; color: #86A396; }
button[data-baseweb="tab"][aria-selected="true"] { color: #EEF6F1; }

/* inputs and buttons */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
  background: #07100C !important; border-color: #17382A !important; border-radius: 8px !important;
}
.stButton > button, .stFormSubmitButton > button {
  border-radius: 8px; border: 1px solid #1B4030; font-weight: 500; background: #0C1913;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: linear-gradient(135deg, #10B981, #059669); border-color: #34D399; color: #03140C;
  font-weight: 600; box-shadow: 0 0 18px rgba(16,185,129,.28);
}
.stButton > button:hover, .stFormSubmitButton > button:hover { border-color: #34D399; color: #D7F5E6; }
code, pre { font-size: 0.82rem !important; }
[data-testid="stCodeBlock"] { border: 1px solid #14301F; border-radius: 8px; }

/* status pills */
.tb-pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 999px;
  font-size: 0.74rem; font-weight: 500; border: 1px solid; line-height: 1.5; white-space: nowrap; }
.tb-pill i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; display: inline-block; }
.tb-red    { color: #F2747A; background: rgba(242,116,122,.10); border-color: rgba(242,116,122,.30); }
.tb-orange { color: #F0A35A; background: rgba(240,163,90,.10);  border-color: rgba(240,163,90,.30); }
.tb-yellow { color: #E5C65C; background: rgba(229,198,92,.10);  border-color: rgba(229,198,92,.30); }
.tb-green  { color: #5FCB8B; background: rgba(95,203,139,.10);  border-color: rgba(95,203,139,.30); }
.tb-blue   { color: #34D399; background: rgba(52,211,153,.12); border-color: rgba(52,211,153,.32); }
.tb-grey   { color: #8FAE9F; background: rgba(154,160,170,.10); border-color: rgba(154,160,170,.28); }

.tb-hero { display:flex; align-items:baseline; gap:12px; margin-bottom: 2px; }
.tb-hero .mark { width: 10px; height: 10px; border-radius: 3px; background: linear-gradient(135deg,#34D399,#059669); box-shadow: 0 0 12px rgba(52,211,153,.6); display:inline-block; }
.tb-sub { color:#86A396; font-size:0.9rem; margin-bottom: 1.4rem; }
.tb-row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin: 4px 0 8px; }
.tb-chip { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:0.78rem; color:#C4DDD0;
  background:#0E1E16; border:1px solid #17382A; border-radius:6px; padding:1px 7px; }
</style>
"""

PILL_KIND = {
    "CONFIRMED": ("tb-red", "Confirmed"),
    "POTENTIAL": ("tb-orange", "Potential"),
    "UNKNOWN_PROVENANCE": ("tb-yellow", "Unknown provenance"),
    "NOT_LINKED": ("tb-green", "Not linked"),
    "PROPOSED": ("tb-blue", "Proposed"),
    "APPROVED": ("tb-green", "Approved"),
    "REJECTED": ("tb-grey", "Rejected"),
}


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def pill(status):
    """HTML status pill. All text is escaped; unknown statuses render as a grey pill."""
    cls, label = PILL_KIND.get(status, ("tb-grey", str(status)))
    return f'<span class="tb-pill {cls}"><i></i>{html.escape(label)}</span>'


def chip(text):
    return f'<span class="tb-chip">{html.escape(str(text))}</span>'


def header(title, subtitle):
    st.markdown(f'<div class="tb-hero"><span class="mark"></span><h1 style="margin:0">'
                f'{html.escape(title)}</h1></div><div class="tb-sub">{html.escape(subtitle)}</div>',
                unsafe_allow_html=True)
