"""Reusable chart builders with branded styling."""
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import pandas as pd
from .branding import CHART_PALETTE, COLORS

_LAYOUT_DEFAULTS = dict(
    font=dict(family="Source Sans 3, sans-serif", color=COLORS["text"]),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#e8e8e8", zerolinecolor="#d4d4d4"),
    yaxis=dict(gridcolor="#e8e8e8", zerolinecolor="#d4d4d4"),
    margin=dict(l=50, r=30, t=50, b=40),
    colorway=CHART_PALETTE,
)


def _apply_defaults(fig, title=None, height=400):
    fig.update_layout(**_LAYOUT_DEFAULTS, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(
            family="Libre Baskerville, serif", size=16, color=COLORS["secondary"])))
    return fig


def branded_histogram(series, title="", nbins=50, log=False):
    vals = np.log1p(series) if log else series
    fig = go.Figure(go.Histogram(x=vals, nbinsx=nbins,
                                  marker_color=COLORS["primary"], opacity=0.85))
    xlab = f"log1p({series.name})" if log else (series.name or "")
    fig.update_layout(xaxis_title=xlab, yaxis_title="Count")
    return _apply_defaults(fig, title)


def branded_scatter(x, y, color=None, title="", labels=None):
    fig = px.scatter(x=x, y=y, color=color, labels=labels or {},
                     color_continuous_scale=["#d4e6cd", COLORS["primary"], COLORS["secondary"]],
                     color_discrete_sequence=CHART_PALETTE, opacity=0.5)
    return _apply_defaults(fig, title, height=450)


def branded_heatmap(matrix, labels, title=""):
    fig = go.Figure(go.Heatmap(
        z=matrix, x=labels, y=labels,
        colorscale=[[0, "#e8f0e3"], [0.5, "#ffffff"], [1, COLORS["primary"]]],
        zmid=0, text=np.round(matrix, 2), texttemplate="%{text}",
        textfont=dict(size=9)))
    fig.update_layout(xaxis=dict(tickangle=45))
    return _apply_defaults(fig, title, height=550)


def branded_bar(x, y, title="", orientation="h", color=None):
    if color is not None:
        fig = px.bar(x=x, y=y, orientation=orientation, color=color,
                     color_discrete_sequence=CHART_PALETTE)
    else:
        fig = go.Figure(go.Bar(x=x, y=y, orientation=orientation,
                               marker_color=COLORS["primary"], opacity=0.85))
    return _apply_defaults(fig, title)


def branded_radar(categories, values_dict, title=""):
    fig = go.Figure()
    for i, (name, vals) in enumerate(values_dict.items()):
        fig.add_trace(go.Scatterpolar(
            r=list(vals) + [vals[0]], theta=list(categories) + [categories[0]],
            fill="toself", name=name, opacity=0.6,
            line=dict(color=CHART_PALETTE[i % len(CHART_PALETTE)])))
    fig.update_layout(polar=dict(
        radialaxis=dict(visible=True, range=[0, 1], gridcolor="#e8e8e8"),
        angularaxis=dict(gridcolor="#e8e8e8")),
        showlegend=True)
    return _apply_defaults(fig, title, height=500)


def branded_pie(labels, values, title=""):
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.4,
                            marker=dict(colors=CHART_PALETTE),
                            textinfo="label+percent", textposition="outside"))
    return _apply_defaults(fig, title, height=400)


def elbow_chart(elbow_df, title="Elbow Analysis"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=elbow_df["k"], y=elbow_df["inertia"], mode="lines+markers",
                              name="Inertia", line=dict(color=COLORS["primary"], width=2),
                              yaxis="y"))
    fig.add_trace(go.Scatter(x=elbow_df["k"], y=elbow_df["silhouette"], mode="lines+markers",
                              name="Silhouette", line=dict(color=COLORS["info"], width=2),
                              yaxis="y2"))
    fig.update_layout(
        xaxis=dict(title="k (Number of Clusters)", dtick=1),
        yaxis=dict(title=dict(text="Inertia", font=dict(color=COLORS["primary"])), side="left"),
        yaxis2=dict(title=dict(text="Silhouette Score", font=dict(color=COLORS["info"])),
                    side="right", overlaying="y"),
        legend=dict(x=0.5, y=1.12, orientation="h", xanchor="center"))
    return _apply_defaults(fig, title, height=400)
