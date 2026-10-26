# BEL Tender Priority & Sentiment Intelligence Tool (v4.0)

Auto-extracts 20 procurement parameters from tender PDFs and ranks tenders with a
5-axis MCDA priority score.

## Setup
    python -m venv venv
    venv\Scripts\activate        (Windows)   |   source venv/bin/activate (Mac/Linux)
    pip install -r requirements.txt

## Run
    streamlit run app.py         # opens http://localhost:8501

## Try it with dummy data
    python sample_tenders/make_sample.py
    # then upload the two PDFs created in sample_tenders/

## Files
- app.py        Streamlit UI (uploader, KPI strip, leaderboard, deep-dive, CSV export, cache)
- extractor.py  TOC scan (PyMuPDF) + text extraction (pdfplumber) + 60+ regex patterns
- scorer.py     MCDA score: Financial 30%, Time 25%, Technical 20%, Compliance 15%, Logistics 10%
- tender_cache.json  auto-created on first run
