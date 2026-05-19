"""Estonia AI exposure explorer — Streamlit dashboard.

Reads the v2 pipeline outputs (matrices/, summaries/, scores_long, weights_long, geometry)
and lets the user explore them by geography level, metric, and ISCO occupation filter.

Run locally:
    streamlit run src/dashboard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path so `from common import ...` works regardless of how
# Streamlit launches the script (some Streamlit Cloud setups don't auto-add it).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from common import (
    GEOMETRY_DIR, MATRICES_DIR, OMAV_REMAP, RAW, SCORES_DIR, SUMMARIES_DIR,
    load_isco_labels, parse_rl21154_location_code,
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
def load_tier_flags() -> pd.DataFrame | None:
    path = SUMMARIES_DIR / "tier_flags_isco4.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype={"isco4_code": str, "isco2_code": str})
    df["isco4_code"] = df["isco4_code"].str.zfill(4)
    df["isco_major"] = df["isco4_code"].str[0]
    return df


@st.cache_data
def load_palgad_workers() -> pd.DataFrame | None:
    """ISCO-4 × maakond headcounts from palgad.stat.ee 2025 Q4 admin records."""
    path = RAW / "palgad_stat_ee" / "workers_long.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df = df.dropna(subset=["isco4"])
    df["isco4_code"] = df["isco4"].astype(int).astype(str).str.zfill(4)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    df = df[df["gender"].isin(["M", "F"])]
    grouped = (df.groupby(["isco4_code", "name_et", "county_name"], as_index=False)["count"]
                 .sum())
    grouped["isco2_code"] = grouped["isco4_code"].str[:2]
    grouped["isco_major"] = grouped["isco4_code"].str[0]
    return grouped


@st.cache_data
def load_barometer() -> pd.DataFrame | None:
    path = RAW / "tootukassa_barometer" / "barometer_long.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["isco4_code"] = df["isco4"].astype(int).astype(str).str.zfill(4)
    df["indicator"] = pd.to_numeric(df["indicator"], errors="coerce")
    df["isco2_code"] = df["isco4_code"].str[:2]
    df["isco_major"] = df["isco4_code"].str[0]
    return df


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


@st.cache_data
def build_isco4_table(scores_long: pd.DataFrame) -> pd.DataFrame:
    """Wide ISCO-4 table — one row per code, one set of columns per model.

    Adds a `divergence` column = std-dev of normalised exposure across models,
    surfacing occupations where the indices disagree.
    """
    labels = load_isco_labels()
    isco4_titles = labels[4]
    isco2_titles = labels[2]

    sub = scores_long[scores_long["taxonomy"].isin(("isco3", "isco4"))].copy()
    if sub.empty:
        return pd.DataFrame()

    # Pivot to (code × model × metric) → wide
    sub["col"] = sub["metric"] + "_" + sub["model"]
    wide = sub.pivot_table(index=["taxonomy", "code"], columns="col",
                           values="value", aggfunc="first").reset_index()

    wide["isco4_title_en"] = wide["code"].map(isco4_titles).fillna(
        wide["code"].astype(str).str[:3].map(labels[3])).fillna(wide["code"])
    wide["isco2_parent"] = wide["code"].astype(str).str[:2]
    wide["isco2_label"] = wide["isco2_parent"].map(isco2_titles).fillna("")
    wide["isco_major"] = wide["code"].astype(str).str[0]

    exposure_cols = [c for c in wide.columns if c.startswith("exposure_")]
    if exposure_cols:
        ex = wide[exposure_cols].apply(pd.to_numeric, errors="coerce")
        wide["mean_exposure"] = ex.mean(axis=1)
        wide["divergence"] = ex.std(axis=1)
    else:
        wide["mean_exposure"] = pd.NA
        wide["divergence"] = pd.NA

    front = ["code", "isco4_title_en", "isco2_parent", "isco2_label",
             "isco_major", "mean_exposure", "divergence"]
    rest = [c for c in wide.columns if c not in front + ["taxonomy"]]
    return wide[front + rest]


TIER_QUINTILE_ORDER = ["Robust High", "Contested High", "Mixed", "Consensus Low", "Insufficient coverage"]
TIER_COLORS = {
    "Robust High": "#b30000", "Contested High": "#e34a33", "Mixed": "#fdcc8a",
    "Consensus Low": "#2c7fb8", "Insufficient coverage": "#cccccc",
}


def render_isco4_tab(scores_long: pd.DataFrame):
    st.markdown("### ISCO-4 detailed-occupation view (multi-index + tier flags)")

    tier = load_tier_flags()
    if tier is None or tier.empty:
        st.info("No `tier_flags_isco4.csv` found. Run `python3 src/build_tier_flags.py` "
                "to produce the cross-model ensemble table, then refresh.")
        table = build_isco4_table(scores_long)
        if not table.empty:
            st.dataframe(table, use_container_width=True, height=540)
        return

    st.caption(
        "One row per ISCO-08 4-digit code. Joins the three ISCO-4-native exposure "
        "models (felten_aei_isco4, ilo_wp140, demirev_ai_products), Estonian "
        "employment from palgad.stat.ee, and Töötukassa national balance/demand. "
        "**Tier labels** rest on inter-model agreement (see `TIER_FLAGS.md`)."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        tier_choice = st.selectbox(
            "Tier framing",
            ["quintile", "ensemble"],
            format_func=lambda x: f"tier_label_{x}",
            help="Quintile counts top/bottom-quintile membership across models. "
                 "Ensemble thresholds on standardized z-score + dispersion.",
        )
        tier_col = f"tier_label_{tier_choice}"
    with c2:
        tier_filter = st.multiselect(
            "Tier filter",
            options=TIER_QUINTILE_ORDER,
            default=[],
        )
    with c3:
        majors = sorted(tier["isco_major"].unique())
        chosen_majors = st.multiselect(
            "ISCO major group",
            options=majors,
            format_func=lambda x: f"{x} {ISCO1_LABELS.get(x, '')}",
        )
    with c4:
        q = st.text_input("Search title (English)").strip().lower()

    view = tier.copy()
    if tier_filter:
        view = view[view[tier_col].isin(tier_filter)]
    if chosen_majors:
        view = view[view["isco_major"].isin(chosen_majors)]
    if q:
        view = view[view["isco4_label"].fillna("").str.lower().str.contains(q, na=False)]

    view = view.sort_values(["ensemble_z_mean", "employment_estonia"],
                            ascending=[False, False], na_position="last")

    # Top KPI strip
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Occupations shown", f"{len(view):,}")
    k2.metric("Estonia employment (filtered)", f"{int(view['employment_estonia'].sum()):,}")
    rh = (view[tier_col] == "Robust High").sum()
    ch = (view[tier_col] == "Contested High").sum()
    k3.metric("Robust High in view", f"{rh}")
    k4.metric("Contested High in view", f"{ch}")

    # Tier distribution bar (always over the filtered view)
    dist = view[tier_col].value_counts().reindex(TIER_QUINTILE_ORDER).fillna(0).astype(int)
    fig_tier = px.bar(
        x=dist.values, y=dist.index, orientation="h",
        labels={"x": "ISCO-4 count", "y": ""},
        color=dist.index, color_discrete_map=TIER_COLORS,
        title=f"Tier distribution ({tier_col})",
    )
    fig_tier.update_layout(height=260, showlegend=False)
    st.plotly_chart(fig_tier, use_container_width=True)

    # Scatter: ensemble z vs divergence, sized by employment, coloured by tier
    plot_df = view.dropna(subset=["ensemble_z_mean", "ensemble_z_sd"]).copy()
    if not plot_df.empty:
        plot_df["size_emp"] = plot_df["employment_estonia"].clip(lower=20)
        fig_sc = px.scatter(
            plot_df, x="ensemble_z_mean", y="ensemble_z_sd",
            size="size_emp", color=tier_col,
            color_discrete_map=TIER_COLORS,
            hover_name="isco4_label",
            hover_data={"isco4_code": True, "employment_estonia": True,
                        "size_emp": False, tier_col: True},
            labels={"ensemble_z_mean": "Ensemble mean z (exposure consensus →)",
                    "ensemble_z_sd": "Dispersion across models (↑ disagreement)"},
            title="Where models agree (low dispersion) vs disagree (high dispersion)",
            size_max=40,
        )
        fig_sc.update_layout(height=440,
                             legend={"orientation": "h", "yanchor": "bottom", "y": 1.02})
        st.plotly_chart(fig_sc, use_container_width=True)

    # Detailed table
    display_cols = [
        "isco4_code", "isco4_label", "isco2_label", "employment_estonia",
        "ensemble_z_mean", "ensemble_z_sd", "n_models",
        "felten_aei_isco4_exposure", "ilo_wp140_exposure", "demirev_ai_products_exposure",
        "top_quintile_count", "bottom_quintile_count",
        tier_col,
        "tootukassa_balance_national", "tootukassa_demand_national",
        "notes",
    ]
    display_cols = [c for c in display_cols if c in view.columns]
    st.dataframe(view[display_cols], use_container_width=True, height=480)

    st.download_button(
        "Download filtered tier-flags CSV",
        data=view.to_csv(index=False),
        file_name="tier_flags_isco4_filtered.csv",
        mime="text/csv",
    )

    with st.expander("How to read tier framings"):
        st.markdown("""
- **`tier_label_quintile`** counts how many of the 3 models place this code in
  their top (or bottom) quintile. "Robust High" = top-quintile in ≥ 2 of 3
  AND dispersion below the median of top-quintile codes.
- **`tier_label_ensemble`** thresholds the standardized ensemble z-score
  (`ensemble_z_mean ≥ +1.0` for Robust High, with the same dispersion check).
  Stricter — picks ~7 vs ~33 under the quintile rule.
- **Augmentation/automation split is *not* collapsed into a tier label**:
  cross-model Spearman on that axis is ~0, so any single labeling would be a
  political choice masquerading as analytics. Raw per-model values stay in
  `scores_long.csv`.
- **Töötukassa balance/demand** are independent of the exposure tier
  (national-level only here; per-county view in the Barometer tab).
        """)


def render_isco4_maakond_tab():
    st.markdown("### ISCO-4 × maakond — Estonian employment (palgad.stat.ee 2025 Q4)")
    workers = load_palgad_workers()
    if workers is None or workers.empty:
        st.info("`data/raw/palgad_stat_ee/workers_long.csv` not found. Run "
                "`python3 scripts/scrape_palgad_stat_ee.py --counties=each` to populate.")
        return

    # 15 maakonnad in canonical order
    MAAKOND_ORDER = [
        "Harju maakond", "Hiiu maakond", "Ida-Viru maakond", "Jõgeva maakond",
        "Järva maakond", "Lääne maakond", "Lääne-Viru maakond", "Põlva maakond",
        "Pärnu maakond", "Rapla maakond", "Saare maakond", "Tartu maakond",
        "Valga maakond", "Viljandi maakond", "Võru maakond",
    ]
    counties = workers[workers["county_name"].isin(MAAKOND_ORDER)].copy()
    national = workers[workers["county_name"] == "Kogu Eesti"].copy()

    st.caption(
        f"Source: palgad.stat.ee admin records (TÖR/MTA), 2025 Q4. "
        f"{counties['isco4_code'].nunique()} ISCO-4 codes × {len(MAAKOND_ORDER)} maakonnad. "
        f"Cells <20 workers are suppressed at source and shown as 0."
    )

    c1, c2 = st.columns([1, 2])
    with c1:
        majors = sorted(counties["isco_major"].unique())
        chosen_majors = st.multiselect(
            "ISCO major group",
            options=majors,
            format_func=lambda x: f"{x} {ISCO1_LABELS.get(x, '')}",
            key="isco4_mk_major",
        )
    with c2:
        q = st.text_input(
            "Search by occupation (Estonian title from palgad.stat.ee)",
            key="isco4_mk_search",
        ).strip().lower()

    view = counties.copy()
    if chosen_majors:
        view = view[view["isco_major"].isin(chosen_majors)]
    if q:
        view = view[view["name_et"].fillna("").str.lower().str.contains(q, na=False)]
    nat_view = national[national["isco4_code"].isin(view["isco4_code"].unique())]

    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("ISCO-4 codes in view", f"{view['isco4_code'].nunique():,}")
    k2.metric("National total (filtered)", f"{int(nat_view['count'].sum()):,}")
    k3.metric("County total (filtered, sum of 15)", f"{int(view['count'].sum()):,}")

    # Heatmap: top-N ISCO-4 by national employment × 15 maakonnad
    top_n = st.slider("Top N ISCO-4 codes (by national employment) for heatmap",
                      10, 50, 25, key="isco4_mk_top_n")
    top_codes = (nat_view.sort_values("count", ascending=False)
                          .head(top_n)["isco4_code"].tolist())
    if top_codes:
        pivot = (view[view["isco4_code"].isin(top_codes)]
                 .pivot_table(index="isco4_code", columns="county_name",
                              values="count", aggfunc="sum", fill_value=0))
        pivot = pivot.reindex(columns=[c for c in MAAKOND_ORDER if c in pivot.columns])
        pivot = pivot.reindex(top_codes)
        # Build label index for readability
        label_map = (view.drop_duplicates("isco4_code").set_index("isco4_code")["name_et"]
                     .to_dict())
        pivot.index = [f"{c} · {label_map.get(c, '')}" for c in pivot.index]
        fig_hm = px.imshow(
            pivot, aspect="auto", color_continuous_scale="YlOrRd",
            labels={"color": "Employed"},
            title=f"Top-{top_n} ISCO-4 occupations × 15 maakonnad",
        )
        fig_hm.update_layout(height=520, xaxis={"side": "top"})
        st.plotly_chart(fig_hm, use_container_width=True)

    # Single-code drill-down
    st.markdown("---")
    st.markdown("#### Drill into one occupation")
    code_options = (view.sort_values("count", ascending=False)
                        .drop_duplicates("isco4_code")[["isco4_code", "name_et"]])
    if code_options.empty:
        st.info("No codes match the current filters.")
        return
    picked = st.selectbox(
        "ISCO-4 code",
        options=code_options["isco4_code"].tolist(),
        format_func=lambda c: f"{c} — {code_options.set_index('isco4_code').loc[c, 'name_et']}",
        key="isco4_mk_pick",
    )
    sub = view[view["isco4_code"] == picked].set_index("county_name")["count"]
    sub = sub.reindex(MAAKOND_ORDER).fillna(0).astype(int)
    fig_bar = px.bar(
        x=sub.index, y=sub.values,
        labels={"x": "", "y": "Employed (2025 Q4)"},
        title=f"{picked} — {code_options.set_index('isco4_code').loc[picked, 'name_et']}",
    )
    fig_bar.update_layout(height=340)
    st.plotly_chart(fig_bar, use_container_width=True)


BAROMETER_BALANCE_LABELS = {
    1: "1 — Major surplus", 2: "2 — Surplus",
    3: "3 — Balanced", 4: "4 — Shortage", 5: "5 — Major shortage",
}
BAROMETER_DEMAND_LABELS = {
    1: "1 — Much less", 2: "2 — Less",
    3: "3 — Same", 4: "4 — More", 5: "5 — Much more",
}


def render_barometer_tab():
    st.markdown("### Töötukassa barometer — labour balance & demand at ISCO-4 × maakond")
    bar = load_barometer()
    if bar is None or bar.empty:
        st.info("`data/raw/tootukassa_barometer/barometer_long.csv` not found. Run "
                "`python3 scripts/scrape_tootukassa_barometer.py` first.")
        return

    periods = sorted(bar["period_id"].unique().tolist())
    st.caption(
        f"Source: Töötukassa OSKA barometer, period {periods}. Indicator scale 1–5: "
        "for **balance**, 1=major surplus → 5=major shortage; "
        "for **demand**, 1=much less hiring → 5=much more hiring. "
        f"{bar['isco4_code'].nunique()} ISCO-4 codes × 16 locations (Kogu Eesti + 15 maakonnad)."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        rating_type = st.radio(
            "Indicator",
            options=["LABOUR_BALANCE", "LABOUR_DEMAND"],
            format_func=lambda x: "Balance (surplus ↔ shortage)" if x == "LABOUR_BALANCE"
                                 else "Demand (less ↔ more hiring)",
            key="barometer_type",
        )
    with c2:
        majors = sorted(bar["isco_major"].dropna().unique())
        chosen_majors = st.multiselect(
            "ISCO major group",
            options=majors,
            format_func=lambda x: f"{x} {ISCO1_LABELS.get(x, '')}",
            key="barometer_major",
        )
    with c3:
        q = st.text_input(
            "Search by occupation (Estonian title)",
            key="barometer_search",
        ).strip().lower()

    sub = bar[bar["rating_type"] == rating_type].copy()
    if chosen_majors:
        sub = sub[sub["isco_major"].isin(chosen_majors)]
    if q:
        sub = sub[sub["occupation_et"].fillna("").str.lower().str.contains(q, na=False)]

    if sub.empty:
        st.warning("No rows after filters.")
        return

    MAAKOND_ORDER = [
        "Kogu Eesti", "Harju maakond", "Hiiu maakond", "Ida-Viru maakond",
        "Jõgeva maakond", "Järva maakond", "Lääne maakond", "Lääne-Viru maakond",
        "Põlva maakond", "Pärnu maakond", "Rapla maakond", "Saare maakond",
        "Tartu maakond", "Valga maakond", "Viljandi maakond", "Võru maakond",
    ]
    label_lookup = BAROMETER_BALANCE_LABELS if rating_type == "LABOUR_BALANCE" else BAROMETER_DEMAND_LABELS

    # National-only distribution chart
    nat = sub[sub["location_name"] == "Kogu Eesti"].copy()
    nat["bucket"] = nat["indicator"].round().astype("Int64").map(label_lookup)
    nat_dist = (nat.groupby("bucket").size().reindex(list(label_lookup.values()))
                  .fillna(0).astype(int))
    fig_dist = px.bar(
        x=nat_dist.index, y=nat_dist.values,
        color=nat_dist.index,
        color_discrete_map={
            label_lookup[1]: "#2c7fb8", label_lookup[2]: "#7fcdbb",
            label_lookup[3]: "#ffffcc", label_lookup[4]: "#fdae61",
            label_lookup[5]: "#d7191c",
        },
        labels={"x": "Indicator bucket", "y": "ISCO-4 codes"},
        title=f"National distribution of {rating_type.replace('_', ' ').lower()} per ISCO-4 code",
    )
    fig_dist.update_layout(height=320, showlegend=False)
    st.plotly_chart(fig_dist, use_container_width=True)

    # Heatmap — most-distinctive codes (max-min indicator across maakonnad)
    pivot = (sub.pivot_table(index=["isco4_code", "occupation_et"],
                             columns="location_name",
                             values="indicator", aggfunc="first")
             .reset_index())
    pivot["range"] = (pivot[[c for c in MAAKOND_ORDER if c in pivot.columns and c != "Kogu Eesti"]]
                      .max(axis=1)
                      - pivot[[c for c in MAAKOND_ORDER if c in pivot.columns and c != "Kogu Eesti"]]
                        .min(axis=1))
    top_n = st.slider("Show top-N most regionally-varying ISCO-4 codes", 10, 60, 30,
                      key="barometer_top_n")
    pivot = pivot.sort_values("range", ascending=False).head(top_n)
    pivot["row_label"] = pivot["isco4_code"] + " · " + pivot["occupation_et"].fillna("").str[:60]
    heat_cols = [c for c in MAAKOND_ORDER if c in pivot.columns]
    heat = pivot.set_index("row_label")[heat_cols]
    fig_hm = px.imshow(
        heat, aspect="auto",
        color_continuous_scale="RdBu_r" if rating_type == "LABOUR_BALANCE" else "RdYlGn",
        zmin=1, zmax=5,
        labels={"color": "Indicator (1-5)"},
        title=f"Most regionally-varying ISCO-4 codes for {rating_type.replace('_', ' ').lower()}",
    )
    fig_hm.update_layout(height=560, xaxis={"side": "top"})
    st.plotly_chart(fig_hm, use_container_width=True)

    # Raw data table
    st.markdown("---")
    show_cols = ["isco4_code", "occupation_et", "location_name", "indicator", "rating_type"]
    st.dataframe(sub[show_cols].sort_values(["isco4_code", "location_name"]),
                 use_container_width=True, height=300)
    st.download_button(
        "Download filtered barometer CSV",
        data=sub[show_cols].to_csv(index=False),
        file_name="barometer_filtered.csv",
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

    tabs = st.tabs([
        "🗺️ Map (ISCO-2)",
        "👥 Occupations",
        "🤝 AEI breakdown",
        "🔬 ISCO-4 detail + tiers",
        "🏛️ ISCO-4 × maakond",
        "🌡️ Töötukassa barometer",
        "📊 Data",
    ])
    scores_long = load_scores_long()
    with tabs[0]:
        render_map_tab(filtered, matrix, ctrl)
    with tabs[1]:
        render_occupations_tab(filtered, ctrl)
    with tabs[2]:
        render_aei_tab(scores_long, ctrl["model"])
    with tabs[3]:
        render_isco4_tab(scores_long)
    with tabs[4]:
        render_isco4_maakond_tab()
    with tabs[5]:
        render_barometer_tab()
    with tabs[6]:
        render_data_tab(filtered)


if __name__ == "__main__":
    main()
