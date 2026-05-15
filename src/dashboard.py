"""Estonia AI exposure explorer — Streamlit dashboard.

Reads the v2 pipeline outputs (matrices/, summaries/, scores_long, weights_long, geometry)
and lets the user explore them by geography level, metric, and ISCO occupation filter.

Run locally:
    streamlit run src/dashboard.py
"""
from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from common import (
    GEOMETRY_DIR, MATRICES_DIR, OMAV_REMAP, RAW, SCORES_DIR, SUMMARIES_DIR,
    parse_rl21154_location_code,
)

# ----- Constants ---------------------------------------------------------------------

ISCO1_LABELS = {
    "1": "Managers", "2": "Professionals", "3": "Technicians",
    "4": "Clerical", "5": "Service & Sales", "6": "Skilled Agric",
    "7": "Skilled Trades", "8": "Plant Operators", "9": "Elementary",
}
ISCO1_COLORS = {
    "1": "#1f77b4", "2": "#ff7f0e", "3": "#2ca02c", "4": "#d62728",
    "5": "#9467bd", "6": "#8c564b", "7": "#e377c2", "8": "#7f7f7f",
    "9": "#bcbd22",
}
METRIC_DISPLAY = {
    "exposure": ("Exposure",        "Purples"),
    "opportunity": ("Opportunity",  "Blues"),
    "risk": ("Risk",                "Reds"),
    "people_affected": ("People affected", "YlOrRd"),
}

# ----- Page config -------------------------------------------------------------------

st.set_page_config(
    page_title="Estonia AI exposure explorer",
    page_icon="🇪🇪",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ----- Cached loaders ----------------------------------------------------------------

@st.cache_data
def load_combos() -> list[tuple[str, str]]:
    """Discover (model, scenario) pairs from matrix files on disk."""
    combos = []
    for p in sorted(MATRICES_DIR.glob("matrix_*.csv")):
        df = pd.read_csv(p, nrows=1)
        combos.append((df["model"].iloc[0], df["scenario"].iloc[0]))
    return combos


@st.cache_data
def load_matrix(model: str, scenario: str) -> pd.DataFrame:
    path = MATRICES_DIR / f"matrix_{model}_{scenario}.csv"
    df = pd.read_csv(path, dtype={"location_code": str, "code": str})

    parsed = df["location_code"].apply(
        lambda c: parse_rl21154_location_code(c) if isinstance(c, str) and len(c) == 14
        else (None, None, None, None)
    )
    df["maakond_code"] = parsed.apply(lambda t: t[0])
    df["omav_code"] = parsed.apply(lambda t: t[1])
    df["asust_code"] = parsed.apply(lambda t: t[2])
    df["type_suffix"] = parsed.apply(lambda t: t[3])

    df["isco1"] = df["code"].astype(str).str[0]
    df["people_affected"] = df["employed"] * df["exposure"]
    return df


@st.cache_data
def load_summary(model: str, scenario: str) -> pd.DataFrame:
    return pd.read_csv(SUMMARIES_DIR / f"maakond_summary_{model}_{scenario}.csv")


@st.cache_data
def load_scores_long() -> pd.DataFrame:
    return pd.read_csv(SCORES_DIR / "scores_long.csv", dtype={"code": str})


@st.cache_data
def load_maakond_geo() -> gpd.GeoDataFrame:
    g = gpd.read_file(RAW / "maakond.geojson")
    g["maakond_name"] = g["MNIMI"].str.replace(" maakond", "", regex=False).str.upper() + " MAAKOND"
    return g[["maakond_name", "MNIMI", "geometry"]]


@st.cache_data
def load_municipality_geo() -> gpd.GeoDataFrame:
    g = gpd.read_file(GEOMETRY_DIR / "estonia_municipalities_combined.geojson")
    return g[["join_code", "join_type", "label", "MKOOD", "MNIMI", "geometry"]]


# ----- Aggregation helpers -----------------------------------------------------------

def aggregate_to_maakond(filtered: pd.DataFrame) -> pd.DataFrame:
    """Aggregate matrix rows to per-maakond totals (employment-weighted scores)."""
    mk = filtered[filtered["location_name"].str.endswith("MAAKOND", na=False)].copy()
    if mk.empty:
        return pd.DataFrame()
    mk["opp_w"] = mk["opportunity"] * mk["employed"]
    mk["risk_w"] = mk["risk"] * mk["employed"]
    mk["exp_w"] = mk["exposure"] * mk["employed"]
    agg = mk.groupby("location_name").agg(
        total_employed=("employed", "sum"),
        opp_w=("opp_w", "sum"),
        risk_w=("risk_w", "sum"),
        exp_w=("exp_w", "sum"),
        people_affected=("people_affected", "sum"),
    ).reset_index()
    agg["exposure"] = agg["exp_w"] / agg["total_employed"]
    agg["opportunity"] = agg["opp_w"] / agg["total_employed"]
    agg["risk"] = agg["risk_w"] / agg["total_employed"]
    agg["maakond_name"] = agg["location_name"]
    return agg


def aggregate_to_municipality(filtered: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to per-municipality + per-linnaosa totals using EHAK code parsing."""
    df = filtered[filtered["type_suffix"].isin(["01", "L4", "M4", "L6"])].copy()
    if df.empty:
        return pd.DataFrame()
    df["omav_code"] = df["omav_code"].replace(OMAV_REMAP)
    df["join_code"] = df.apply(
        lambda r: r["asust_code"] if r["type_suffix"] == "L6" else r["omav_code"],
        axis=1,
    )
    # Drop Tallinn and Kohtla-Järve city aggregates (use their linnaosa instead)
    df = df[~((df["omav_code"].isin(["0784", "0321"])) & (df["type_suffix"] != "L6"))]

    df["opp_w"] = df["opportunity"] * df["employed"]
    df["risk_w"] = df["risk"] * df["employed"]
    df["exp_w"] = df["exposure"] * df["employed"]

    agg = df.groupby(["join_code", "location_name"]).agg(
        total_employed=("employed", "sum"),
        opp_w=("opp_w", "sum"),
        risk_w=("risk_w", "sum"),
        exp_w=("exp_w", "sum"),
        people_affected=("people_affected", "sum"),
    ).reset_index()
    agg["exposure"] = agg["exp_w"] / agg["total_employed"]
    agg["opportunity"] = agg["opp_w"] / agg["total_employed"]
    agg["risk"] = agg["risk_w"] / agg["total_employed"]
    agg["label"] = agg["location_name"].str.lstrip(".").str.strip()
    return agg


def locality_detail(filtered: pd.DataFrame, location_name: str, top_n: int) -> pd.DataFrame:
    """Top-N occupations within a single location, by people-affected."""
    sub = filtered[filtered["location_name"] == location_name].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["aug_people"] = sub["employed"] * sub["opportunity"]
    sub["auto_people"] = sub["employed"] * sub["risk"]
    sub = sub.sort_values("people_affected", ascending=False).head(top_n)
    sub["label"] = sub["code_label"].str.lstrip(".").str.strip()
    return sub[["label", "code", "employed", "exposure",
                "opportunity", "risk", "people_affected",
                "aug_people", "auto_people"]]


# ----- Sidebar -----------------------------------------------------------------------

def render_sidebar(combos):
    st.sidebar.title("Estonia AI exposure")
    st.sidebar.caption("v2 explorer — interactive view of the pipeline outputs.")

    model_options = sorted({m for m, _ in combos})
    scenario_options = sorted({s for _, s in combos})
    model = st.sidebar.selectbox("Model", model_options, index=0)
    scenario = st.sidebar.selectbox("Scenario", scenario_options, index=0)

    geo_level = st.sidebar.radio(
        "Geography",
        ["maakond (15 counties)", "municipality + linnaosa (~90)"],
        index=0,
    )
    geo_level_key = "maakond" if geo_level.startswith("maakond") else "municipality"

    metric = st.sidebar.selectbox(
        "Colour choropleth by",
        list(METRIC_DISPLAY.keys()),
        format_func=lambda x: METRIC_DISPLAY[x][0],
        index=0,
    )

    isco1_filter = st.sidebar.multiselect(
        "ISCO major groups (optional filter)",
        options=list(ISCO1_LABELS.keys()),
        format_func=lambda x: f"{x} {ISCO1_LABELS[x]}",
    )

    top_n = st.sidebar.slider("Top N occupations to show", 5, 25, 10)

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Data: REL2021 (Statistics Estonia) × Felten AIOE × Anthropic Economic Index (March 2026)."
    )
    st.sidebar.caption(
        f"Source: [github.com/luukasilves/oska-emtak](https://github.com/luukasilves/oska-emtak)"
    )

    return {
        "model": model, "scenario": scenario,
        "geo_level": geo_level_key, "metric": metric,
        "isco1_filter": isco1_filter, "top_n": top_n,
    }


# ----- Renderers ---------------------------------------------------------------------

def render_kpi_strip(filtered: pd.DataFrame, full: pd.DataFrame):
    """4 KPI cards based on the national-total subset of `filtered`."""
    nat = filtered[filtered["location_name"] == "Kogu Eesti"]
    if nat.empty:
        st.warning("No 'Kogu Eesti' total rows in filtered data.")
        return
    total_employed = int(nat["employed"].sum())
    weighted_exp = (nat["exposure"] * nat["employed"]).sum() / max(total_employed, 1)
    people_affected = int((nat["exposure"] * nat["employed"]).sum())

    # top-quartile-exposure threshold computed on the UNFILTERED national distribution
    full_nat = full[full["location_name"] == "Kogu Eesti"]
    q75 = full_nat["exposure"].quantile(0.75)
    top_q_share = nat.loc[nat["exposure"] >= q75, "employed"].sum() / max(total_employed, 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Employed (filtered)", f"{total_employed:,}")
    c2.metric("Weighted exposure", f"{weighted_exp:.3f}")
    c3.metric("People affected", f"{people_affected:,}",
              help="Sum of employed × exposure")
    c4.metric("In top-quartile occs", f"{top_q_share:.0%}",
              help="Share of filtered employment in occupations above the 75th percentile of exposure (computed on unfiltered national distribution)")


def render_map_tab(filtered: pd.DataFrame, full: pd.DataFrame, ctrl: dict):
    render_kpi_strip(filtered, full)
    st.markdown("---")

    metric = ctrl["metric"]
    metric_label, cmap = METRIC_DISPLAY[metric]

    # Aggregate based on geography
    if ctrl["geo_level"] == "maakond":
        agg = aggregate_to_maakond(filtered)
        geo = load_maakond_geo()
        merged = geo.merge(agg, on="maakond_name", how="left")
        merged["label"] = merged["MNIMI"]
        key_field = "maakond_name"
    else:
        agg = aggregate_to_municipality(filtered)
        geo = load_municipality_geo()
        merged = geo.merge(agg[["join_code", "total_employed", "exposure",
                                "opportunity", "risk", "people_affected",
                                "location_name", "label"]],
                            on="join_code", how="left", suffixes=("_geo", ""))
        merged["label"] = merged["label"].fillna(merged["label_geo"])
        key_field = "join_code"

    if merged[metric].isna().all():
        st.warning(f"No data to display for metric '{metric}'.")
        return

    # Build folium map
    m = folium.Map(location=[58.6, 25.0], zoom_start=7, tiles="cartodbpositron")
    # Drop rows with NaN metric to keep choropleth happy
    plot_df = merged.dropna(subset=[metric])
    folium.Choropleth(
        geo_data=plot_df.to_json(),
        data=plot_df,
        columns=[key_field, metric],
        key_on=f"feature.properties.{key_field}",
        fill_color=cmap,
        fill_opacity=0.75,
        line_opacity=0.4,
        legend_name=f"{metric_label} ({'absolute' if metric == 'people_affected' else 'score 0–1'})",
        nan_fill_color="lightgray",
    ).add_to(m)
    # Add hover tooltip + click handler via GeoJson layer
    tooltip_fields = ["label", "total_employed", metric]
    tooltip_aliases = ["Locality", "Employed", metric_label]
    folium.GeoJson(
        plot_df.to_json(),
        style_function=lambda f: {"fillOpacity": 0, "color": "transparent"},
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields, aliases=tooltip_aliases, localize=True
        ),
        name="hover",
    ).add_to(m)

    map_state = st_folium(m, width=None, height=520, returned_objects=["last_object_clicked"])

    # Selected locality from click — best effort: match by clicked lat/lng to nearest polygon
    selected_name = None
    if map_state and map_state.get("last_object_clicked"):
        lat = map_state["last_object_clicked"]["lat"]
        lng = map_state["last_object_clicked"]["lng"]
        point = gpd.GeoSeries.from_xy([lng], [lat], crs="EPSG:4326")
        hits = plot_df[plot_df.geometry.contains(point.iloc[0])]
        if not hits.empty:
            selected_name = hits.iloc[0]["location_name"] if "location_name" in hits.columns else hits.iloc[0]["label"]
            # For maakond view, location_name lives in agg
            if ctrl["geo_level"] == "maakond":
                selected_name = hits.iloc[0]["maakond_name"]

    # Detail panel
    st.markdown("### Locality detail")
    if not selected_name:
        st.caption("Click a region on the map to see its top occupations.")
        return

    st.markdown(f"**{selected_name}**")
    detail = locality_detail(filtered, selected_name, ctrl["top_n"])
    if detail.empty:
        st.info(f"No matrix rows for {selected_name}.")
        return

    c1, c2 = st.columns([1, 2])
    with c1:
        total = int(detail["employed"].sum())
        st.metric("Total employed (top-N)", f"{total:,}")
        st.metric("Mean exposure", f"{detail['exposure'].mean():.3f}")
        st.metric("People affected (top-N)", f"{int(detail['people_affected'].sum()):,}")

    with c2:
        long = detail.melt(
            id_vars=["label"],
            value_vars=["aug_people", "auto_people"],
            var_name="kind", value_name="people",
        )
        long["kind"] = long["kind"].map({"aug_people": "Opportunity", "auto_people": "Risk"})
        fig = px.bar(
            long, x="people", y="label", color="kind", orientation="h",
            color_discrete_map={"Opportunity": "#2E86AB", "Risk": "#D62828"},
            labels={"people": "People (employed × score)", "label": "", "kind": ""},
            title=f"Top {len(detail)} occupations in {selected_name}",
        )
        fig.update_layout(barmode="stack", height=400, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)


def render_occupations_tab(filtered: pd.DataFrame, ctrl: dict):
    st.markdown("### National-level occupational view")
    nat = filtered[filtered["location_name"] == "Kogu Eesti"].copy()
    if nat.empty:
        st.warning("No national rows in filtered data.")
        return

    nat["label"] = nat["code_label"].str.lstrip(".").str.strip()
    nat["isco_major"] = nat["isco1"].map(ISCO1_LABELS)

    # Scatter: opp vs risk, size = employed, color = isco1
    fig1 = px.scatter(
        nat, x="opportunity", y="risk", size="employed",
        color="isco_major", hover_name="label",
        color_discrete_map={ISCO1_LABELS[k]: v for k, v in ISCO1_COLORS.items()},
        labels={"opportunity": "Opportunity (augmentation-weighted exposure)",
                "risk": "Risk (automation-weighted exposure)",
                "isco_major": "ISCO Major Group"},
        title="Occupations on the Opportunity × Risk plane (sized by national employment)",
        size_max=60,
    )
    fig1.update_layout(height=520)
    st.plotly_chart(fig1, use_container_width=True)

    # Top-N people-affected bar
    nat["aug_people"] = nat["employed"] * nat["opportunity"]
    nat["auto_people"] = nat["employed"] * nat["risk"]
    top = nat.nlargest(ctrl["top_n"], "people_affected")
    long = top.melt(
        id_vars=["label"], value_vars=["aug_people", "auto_people"],
        var_name="kind", value_name="people",
    )
    long["kind"] = long["kind"].map({"aug_people": "Opportunity", "auto_people": "Risk"})
    fig2 = px.bar(
        long, x="people", y="label", color="kind", orientation="h",
        color_discrete_map={"Opportunity": "#2E86AB", "Risk": "#D62828"},
        labels={"people": "People (employed × score)", "label": "", "kind": ""},
        title=f"Top {ctrl['top_n']} occupations nationally by people-affected",
    )
    fig2.update_layout(barmode="stack", height=520, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig2, use_container_width=True)


def render_aei_tab(scores_long: pd.DataFrame, model: str):
    st.markdown("### AEI augmentation vs automation breakdown")
    st.caption(
        f"Per-ISCO-2 split of how Claude conversations were used: augmentation patterns "
        f"(task iteration + learning + validation) vs automation patterns "
        f"(directive + feedback loop). Source: Anthropic Economic Index, March 2026 release. "
        f"Model: **{model}**."
    )

    sub = scores_long[(scores_long["model"] == model) &
                      (scores_long["metric"].isin(["augmentation_share", "automation_share"]))]
    if sub.empty:
        st.warning(f"No AEI shares registered for model '{model}'.")
        return

    pivot = sub.pivot(index="code", columns="metric", values="value").reset_index()
    pivot = pivot.sort_values("augmentation_share", ascending=True)

    fig = px.bar(
        pivot, y="code", x=["augmentation_share", "automation_share"],
        orientation="h",
        color_discrete_map={"augmentation_share": "#2E86AB", "automation_share": "#D62828"},
        labels={"value": "Share of classified collaboration", "code": "ISCO-2", "variable": ""},
        title="Augmentation share (blue) vs automation share (red) per ISCO-2 occupation group",
    )
    fig.update_layout(barmode="stack", height=720,
                      legend={"orientation": "h", "yanchor": "bottom", "y": 1.02})
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    **How to read this:**

    Anthropic classifies each Claude conversation by its collaboration pattern. We aggregate
    these per O*NET task → SOC-6 → ISCO-2 to estimate, for each occupational group, what
    share of AI usage tends to be augmentative vs automative.

    - **Augmentation patterns** (blue): task iteration, learning, validation — user and AI
      go back and forth; AI assists rather than replaces.
    - **Automation patterns** (red): directive, feedback loop — user gives a task and AI
      executes it (single-shot or with minor correction).
    - **Excluded from the denominator**: none, not_classified.

    **Important caveat:** the current model (`felten_aei`) uses AEI's *1P API* usage data,
    which skews more directive/programmatic (~80% automation globally) than the Claude.ai
    consumer data (where conversations tilt augmentation-heavier). A future
    `felten_aei_consumer` model variant would shift the distribution. See the README's
    "Future model variants" section.

    Low-confidence cells (fewer than 10 matched O*NET tasks) fall back to the ISCO 1-digit
    group mean, or the global mean if the whole ISCO-1 group is low-confidence. Several
    Elementary occupations (ISCO 91-96) and small Skilled-Agric/Trades groups fall into this.
    """)


def render_data_tab(filtered: pd.DataFrame):
    st.markdown("### Filtered matrix data")
    st.caption(f"{len(filtered):,} rows after filters.")
    st.dataframe(filtered, use_container_width=True, height=600)
    st.download_button(
        "Download as CSV",
        data=filtered.to_csv(index=False),
        file_name="matrix_filtered.csv",
        mime="text/csv",
    )


# ----- Main --------------------------------------------------------------------------

def main():
    combos = load_combos()
    if not combos:
        st.error("No matrix files found in `data/processed/matrices/`. "
                 "Run `python3 src/build_matrix.py` first.")
        return

    ctrl = render_sidebar(combos)

    matrix = load_matrix(ctrl["model"], ctrl["scenario"])
    if ctrl["isco1_filter"]:
        filtered = matrix[matrix["isco1"].isin(ctrl["isco1_filter"])]
    else:
        filtered = matrix

    st.title("🇪🇪 Estonia AI exposure explorer")
    st.caption(
        f"**Model:** `{ctrl['model']}`  |  **Scenario:** `{ctrl['scenario']}`  "
        f"|  **Geography:** {ctrl['geo_level']}  |  **Metric:** {METRIC_DISPLAY[ctrl['metric']][0]}"
        + (f"  |  **ISCO filter:** {', '.join(ctrl['isco1_filter'])}" if ctrl["isco1_filter"] else "")
    )

    tabs = st.tabs(["🗺️ Map", "👥 Occupations", "🤝 AEI breakdown", "📊 Data"])
    with tabs[0]:
        render_map_tab(filtered, matrix, ctrl)
    with tabs[1]:
        render_occupations_tab(filtered, ctrl)
    with tabs[2]:
        render_aei_tab(load_scores_long(), ctrl["model"])
    with tabs[3]:
        render_data_tab(filtered)


if __name__ == "__main__":
    main()
