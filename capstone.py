import pandas as pd
import streamlit as st
import altair as alt

st.set_page_config(
    page_title="COVID-19 Country Dashboard",
    page_icon="🦠",
    layout="wide",
)

BASE_URL = (
    "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/"
    "csse_covid_19_data/csse_covid_19_time_series/"
)

DATASETS = {
    "Confirmed": BASE_URL + "time_series_covid19_confirmed_global.csv",
    "Deaths": BASE_URL + "time_series_covid19_deaths_global.csv",
    "Recovered": BASE_URL + "time_series_covid19_recovered_global.csv",
}

DEFAULT_COUNTRIES = ["US", "India", "Brazil"]


@st.cache_data(show_spinner=False)
def load_dataset(metric_name: str) -> pd.DataFrame:
    url = DATASETS[metric_name]
    last_error = None

    for enc in ["utf-8", "cp1252", "latin-1", "ISO-8859-1"]:
        try:
            df = pd.read_csv(url, encoding=enc, low_memory=False)
            break
        except UnicodeDecodeError as e:
            last_error = e
    else:
        raise RuntimeError(f"Could not decode dataset: {last_error}")

    id_cols = ["Province/State", "Country/Region", "Lat", "Long"]
    date_cols = [c for c in df.columns if c not in id_cols]

    country_df = (
        df.groupby("Country/Region", dropna=False)[date_cols]
        .sum()
        .reset_index()
        .rename(columns={"Country/Region": "Country"})
    )

    long_df = country_df.melt(
        id_vars="Country",
        value_vars=date_cols,
        var_name="Date",
        value_name=metric_name,
    )
    long_df["Date"] = pd.to_datetime(long_df["Date"])
    return long_df


@st.cache_data(show_spinner=False)
def build_master_data() -> pd.DataFrame:
    merged = None
    for metric in DATASETS:
        metric_df = load_dataset(metric)
        if merged is None:
            merged = metric_df
        else:
            merged = merged.merge(metric_df, on=["Country", "Date"], how="outer")

    merged = merged.fillna(0).sort_values(["Country", "Date"]).reset_index(drop=True)

    for metric in DATASETS:
        merged[f"Daily {metric}"] = (
            merged.groupby("Country")[metric]
            .diff()
            .fillna(merged[metric])
            .clip(lower=0)
        )

    return merged


def get_value_column(view_mode: str, metric: str) -> str:
    return metric if view_mode == "Cumulative" else f"Daily {metric}"


def format_big_number(value: float) -> str:
    try:
        value = float(value)
    except Exception:
        return "—"

    if abs(value) >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{value/1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value/1_000:.1f}K"
    return f"{int(round(value)):,}"


st.title("🦠 COVID-19 Country Dashboard")
st.markdown(
    """
Compare COVID-19 trends across countries with the Johns Hopkins CSSE global time-series data.
Use the sidebar to add countries, switch between daily and cumulative counts, and filter the date range.
"""
)

st.info(
    "Data source: Johns Hopkins University CSSE global time-series repository. "
    "This repository is archived, so the app reflects the historical data available there."
)

master_df = build_master_data()
all_countries = sorted(master_df["Country"].dropna().unique().tolist())

with st.sidebar:
    st.header("Dashboard controls")

    selected_metric = st.selectbox(
        "Metric",
        ["Confirmed", "Deaths", "Recovered"],
        index=0,
    )

    selected_view = st.radio(
        "Count type",
        ["Daily", "Cumulative"],
        horizontal=True,
    )

    selected_countries = st.multiselect(
        "Countries to compare",
        options=all_countries,
        default=[c for c in DEFAULT_COUNTRIES if c in all_countries],
        help="Choose one or more countries. You can search and add as many as you like.",
    )

    min_date = master_df["Date"].min().date()
    max_date = master_df["Date"].max().date()

    date_range = st.slider(
        "Date range",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
    )

    show_table = st.checkbox("Show data table", value=True)
    show_download = st.checkbox("Show download button", value=True)

if not selected_countries:
    st.warning("Please select at least one country from the sidebar.")
    st.stop()

value_col = get_value_column(selected_view, selected_metric)

filtered_df = master_df[
    (master_df["Date"].dt.date >= date_range[0])
    & (master_df["Date"].dt.date <= date_range[1])
    & (master_df["Country"].isin(selected_countries))
].copy()

latest_date = filtered_df["Date"].max()
latest_df = filtered_df[filtered_df["Date"] == latest_date].copy()
latest_df = latest_df.sort_values(value_col, ascending=False)

total_latest_value = latest_df[value_col].sum()
top_country = latest_df.iloc[0]["Country"] if not latest_df.empty else "—"
top_country_value = latest_df.iloc[0][value_col] if not latest_df.empty else 0
num_countries = latest_df["Country"].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Metric", selected_metric)
c2.metric("Count type", selected_view)
c3.metric("Countries selected", num_countries)
c4.metric(f"Combined latest {selected_view.lower()} total", format_big_number(total_latest_value))

c5, c6 = st.columns(2)
c5.metric("Latest date in filtered data", latest_date.strftime("%Y-%m-%d"))
c6.metric("Top country on latest date", f"{top_country} ({format_big_number(top_country_value)})")

chart = (
    alt.Chart(filtered_df)
    .mark_line(point=True)
    .encode(
        x=alt.X("Date:T", title="Date"),
        y=alt.Y(f"{value_col}:Q", title=f"{selected_view} {selected_metric}"),
        color=alt.Color("Country:N", title="Country"),
        tooltip=[
            alt.Tooltip("Country:N"),
            alt.Tooltip("Date:T", title="Date"),
            alt.Tooltip(f"{value_col}:Q", title=f"{selected_view} {selected_metric}", format=","),
        ],
    )
    .properties(height=520)
    .interactive()
)

left, right = st.columns([2.2, 1])

with left:
    st.subheader("Trend chart")
    st.altair_chart(chart, use_container_width=True)

with right:
    st.subheader("Latest snapshot")
    snapshot_df = latest_df[["Country", value_col]].rename(
        columns={value_col: f"Latest {selected_view} {selected_metric}"}
    )
    st.dataframe(snapshot_df, use_container_width=True, hide_index=True)

st.subheader("Summary")
summary_df = (
    filtered_df.groupby("Country")[value_col]
    .agg(["min", "max", "mean"])
    .reset_index()
)

summary_df.columns = ["Country", "Minimum", "Maximum", "Average"]
summary_df["Minimum"] = summary_df["Minimum"].round(0).astype(int)
summary_df["Maximum"] = summary_df["Maximum"].round(0).astype(int)
summary_df["Average"] = summary_df["Average"].round(1)
st.dataframe(summary_df, use_container_width=True, hide_index=True)

if show_table:
    st.subheader("Detailed data")
    display_df = filtered_df[["Country", "Date", value_col]].rename(
        columns={value_col: f"{selected_view} {selected_metric}"}
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if show_download:
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download filtered data as CSV",
            data=csv,
            file_name="covid_country_dashboard_filtered.csv",
            mime="text/csv",
        )