"""KPI display and metric card helpers."""
import streamlit as st
from .branding import metric_card, COLORS


def kpi_row(metrics: list[dict]):
    """Display a row of metric cards. Each dict: {label, value, delta?}."""
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            metric_card(m["label"], m["value"], m.get("delta"))


def segment_card(name, size, pct, top_features: list[str], color_idx=0):
    """Mini profile card for a user segment."""
    palette = [COLORS["primary"], COLORS["info"], COLORS["error"],
               COLORS["accent"], COLORS["warning"], "#8e44ad", "#e67e22", "#34495e"]
    c = palette[color_idx % len(palette)]
    features_html = "".join(f"<li>{f}</li>" for f in top_features[:4])
    st.markdown(f'''
    <div style="background:white;border:1px solid #d4e6cd;border-left:5px solid {c};
                border-radius:6px;padding:1rem;margin:0.5rem 0;">
        <h3 style="margin:0 0 0.3rem 0;color:{c};font-size:1.1rem;">{name}</h3>
        <div style="color:#6b8f6b;font-size:0.85rem;">{size:,} users ({pct:.1f}%)</div>
        <ul style="margin:0.5rem 0 0 1rem;padding:0;font-size:0.85rem;color:#2c3e2d;">
            {features_html}
        </ul>
    </div>''', unsafe_allow_html=True)
