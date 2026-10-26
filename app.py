"""
app.py  -  BEL Tender Priority & Sentiment Intelligence Tool (v4.0)
Run:  streamlit run app.py   ->   http://localhost:8501
"""
import hashlib
import json
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from extractor import PARAM_ORDER, process_pdf
from scorer import WEIGHTS, score_tender

CACHE_FILE = "tender_cache.json"

STATUS_COLORS = {
    "Favourable": "#C6EFCE", "Moderate": "#FFEB9C", "Caution": "#FFD8A8",
    "High Risk": "#FFC7CE", "CRITICAL": "#FF9B9B", "CRITICAL (Expired)": "#FF9B9B",
}

st.set_page_config(page_title="BEL Tender Intelligence", page_icon="🛡️", layout="wide")


# ------------------------------- cache -------------------------------------- #
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def cache_key(name, size):
    return hashlib.md5(f"{name}|{size}".encode("utf-8")).hexdigest()


# ------------------------------ processing ---------------------------------- #
def analyse(uploaded_file, cache):
    data = uploaded_file.getvalue()
    key = cache_key(uploaded_file.name, len(data))
    if key in cache:
        return cache[key], True                               # cache-hit path
    result = process_pdf(data)                                # steps 2-5
    result["score"] = score_tender(result["params"])
    result["filename"] = uploaded_file.name
    cache[key] = result
    save_cache(cache)
    return result, False


def build_table(results):
    rows = []
    for r in results:
        p, s = r["params"], r["score"]
        rows.append({
            "Tender": r["filename"],
            "Tender No": p["tender_number"],
            "Customer": p["customer"],
            "Equipment": p["equipment"],
            "Deadline": p["deadline"],
            "Days Left": s["days_left"] if s["days_left"] is not None else "-",
            "Score": s["priority_score"],
            "Status": s["status"],
            "Flag": s["flag"],
        })
    df = pd.DataFrame(rows).sort_values("Score", ascending=True).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))          # lowest score = needs attention first
    return df


def colour_rows(row):
    colour = STATUS_COLORS.get(row["Status"], "")
    return [f"background-color: {colour}; color: #111"] * len(row)


# --------------------------------- charts ----------------------------------- #
def gauge(score, status):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        title={"text": f"Priority Score - {status}"},
        gauge={"axis": {"range": [0, 100]},
               "bar": {"color": "#1F4E79"},
               "steps": [{"range": [0, 35], "color": "#FFC7CE"},
                         {"range": [35, 55], "color": "#FFD8A8"},
                         {"range": [55, 75], "color": "#FFEB9C"},
                         {"range": [75, 100], "color": "#C6EFCE"}]}))
    fig.update_layout(height=320, margin=dict(t=60, b=10, l=30, r=30))
    return fig


def radar(axes):
    names = list(axes.keys())
    vals = [axes[n] for n in names]
    fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=names + names[:1],
                                    fill="toself", line_color="#1F4E79"))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), showlegend=False,
                      height=320, margin=dict(t=40, b=30, l=60, r=60),
                      title="5-Axis Breakdown (higher = more favourable)")
    return fig


# ----------------------------------- UI ------------------------------------- #
st.title("🛡️ BEL Tender Priority & Sentiment Intelligence Tool")
st.caption("Bharat Electronics Limited · Panchkula Unit · Procurement Division · v4.0")

with st.sidebar:
    st.header("Upload Tenders")
    files = st.file_uploader("Tender PDFs", type=["pdf"], accept_multiple_files=True)
    st.markdown("---")
    st.subheader("Scoring Weights")
    for axis, w in WEIGHTS.items():
        st.write(f"**{axis}** - {int(w * 100)}%")
    st.markdown("---")
    if st.button("🗑️ Clear cache"):
        save_cache({})
        st.success("Cache cleared")

if not files:
    st.info("Upload one or more tender PDFs in the sidebar to begin.")
    st.stop()

cache = load_cache()
results, hits = [], 0
progress = st.progress(0.0, text="Processing tenders...")
for i, f in enumerate(files):
    try:
        res, hit = analyse(f, cache)
        results.append(res)
        hits += int(hit)
    except Exception as e:                                   # one bad PDF must not kill the run
        st.error(f"Could not process {f.name}: {e}")
    progress.progress((i + 1) / len(files), text=f"Processed {i + 1}/{len(files)}")
progress.empty()

if not results:
    st.stop()
if hits:
    st.caption(f"⚡ {hits} of {len(files)} file(s) served from cache")

df = build_table(results)

# KPI strip
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Tenders", len(df))
k2.metric("Critical / Urgent", int(df["Status"].str.startswith("CRITICAL").sum()))
k3.metric("Average Score", f"{df['Score'].mean():.1f}")
k4.metric("Lowest Score", f"{df['Score'].min():.1f}")

# Leaderboard
st.subheader("📋 Leaderboard")
st.caption("Sorted by score, lowest first (highest risk / most attention needed).")
st.dataframe(df.style.apply(colour_rows, axis=1), use_container_width=True, hide_index=True)
st.download_button("📥 Export leaderboard (CSV)",
                   df.to_csv(index=False).encode("utf-8"),
                   file_name="bel_tender_leaderboard.csv", mime="text/csv")

# Deep dive
st.subheader("🔬 Tender Deep-Dive")
choice = st.selectbox("Select tender", [r["filename"] for r in results])
sel = next(r for r in results if r["filename"] == choice)
s, p, m = sel["score"], sel["params"], sel["meta"]

if s["flag"] in ("CRITICAL", "URGENT", "EXPIRED"):
    st.error(f"⏰ {s['flag']}: {s['days_left']} day(s) to deadline ({p['deadline']})")

c1, c2 = st.columns(2)
c1.plotly_chart(gauge(s["priority_score"], s["status"]), use_container_width=True)
c2.plotly_chart(radar(s["axes"]), use_container_width=True)

st.caption(f"Pages processed: {m['pages_processed']} of {m['total_pages']} · "
           f"TOC used: {'Yes' if m['used_toc'] else 'No'} · "
           f"Parameters found: {m['params_found']}/20")

pt = pd.DataFrame({"Parameter": [k.replace("_", " ").title() for k in PARAM_ORDER],
                   "Extracted Value": [p[k] for k in PARAM_ORDER]})
st.dataframe(pt, use_container_width=True, hide_index=True)

with st.expander("🧾 Raw JSON"):
    st.json(sel)
