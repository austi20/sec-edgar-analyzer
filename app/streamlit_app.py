"""Streamlit app: Overview, Company, Data.

Reads committed parquet files only -- never hits the SEC API at request time.
"""

import streamlit as st

st.set_page_config(page_title="SEC EDGAR Financial Statement Analyzer", layout="wide")


@st.cache_data
def load_ratios():
    raise NotImplementedError


def overview_page():
    """Peer-set ratio heatmap."""
    raise NotImplementedError


def company_page():
    """5-year ratio trends, DuPont waterfall, the LLM summary."""
    raise NotImplementedError


def data_page():
    """The tidy table with a CSV download button."""
    raise NotImplementedError
