import json
import re
import pandas as pd
import requests
import streamlit as st
from thefuzz import fuzz, process

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Unified FPL Analytics Hub", page_icon="📊", layout="wide"
)

st.title("📊 Unified FPL Advanced Analytics Hub")
st.markdown(
    "A companion dashboard merging Understat (Shot xG & xGChain) and FBref"
    " (Touches in Box, SCA, Progressive Actions) into a single master table."
)

# --- 2. SEASON SELECTOR ---
selected_season = st.sidebar.selectbox(
    "Select Season",
    options=[2026, 2025, 2024, 2023],
    format_func=lambda x: (
        f"{x}/{x+1-2000} (Current Season)"
        if x == 2026
        else f"{x}/{x+1-2000}"
    ),
    index=0,
)

# Standard Browser Headers to Bypass Scraper Blocks
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# --- 3. DIRECT RAW JSON PARSER FOR UNDERSTAT ---
def fetch_understat_data(season_year):
    """Directly extracts Understat's underlying JSON data embedded in page scripts.

    Handles current active season (no trailing year) vs archived seasons.
    """
    # Active current season uses the main URL root
    if season_year == 2026:
        url = "https://understat.com/league/EPL"
    else:
        url = f"https://understat.com/league/EPL/{season_year}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None, None

        # Extract JSON strings embedded in JavaScript
        players_match = re.search(
            r"playersData\s*=\s*JSON\.parse\('([^']+)'\)", response.text
        )
        teams_match = re.search(
            r"datesData\s*=\s*JSON\.parse\('([^']+)'\)", response.text
        )

        players_data, teams_data = None, None

        if players_match:
            raw_hex = players_match.group(1)
            clean_json = bytes(raw_hex, "utf-8").decode("unicode_escape")
            players_data = json.loads(clean_json)

        if teams_match:
            raw_hex = teams_match.group(1)
            clean_json = bytes(raw_hex, "utf-8").decode("unicode_escape")
            teams_data = json.loads(clean_json)

        return players_data, teams_data
    except Exception as e:
        st.error(f"Error connecting to Understat: {e}")
        return None, None


# --- 4. SAFE FBREF PARSER ---
def fetch_fbref_data(season_year):
    """Safely attempts to parse FBref stats table without breaking on block/timeout."""
    if season_year == 2026:
        url = "https://fbref.com/en/squads/epl/stats/"
    else:
        url = f"https://fbref.com/en/squads/epl/{season_year}/stats/"

    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
        if response.status_code == 200:
            tables = pd.read_html(response.text)
            if tables:
                df = tables[0]
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [
                        "_".join(c).strip() if c[1] else c[0]
                        for c in df.columns
                    ]
                p_col = [c for c in df.columns if "player" in c.lower()]
                if p_col:
                    df["player_clean"] = (
                        df[p_col[0]].astype(str).str.lower().str.strip()
                    )
                    return df
    except Exception:
        pass
    return pd.DataFrame()


# --- 5. FUZZY MERGE ENGINE ---
def merge_metrics(df_understat, df_fbref, threshold=75):
    """Merges Understat and FBref data tables using name fuzzy-matching."""
    if df_fbref.empty or "player_clean" not in df_fbref.columns:
        for col in ["touches_box", "prog_carries", "sca", "sca_dead"]:
            df_understat[col] = 0
        return df_understat

    fbref_names = df_fbref["player_clean"].dropna().unique().tolist()
    merged_rows = []

    for _, u_row in df_understat.iterrows():
        u_name = u_row.get("player_clean", "")

        best_match, score, _ = (
            process.extractOne(
                u_name, fbref_names, scorer=fuzz.token_sort_ratio
            )
            if fbref_names
            else (None, 0, None)
        )

        row_dict = u_row.to_dict()

        if score >= threshold and best_match:
            fb_matches = df_fbref[df_fbref["player_clean"] == best_match]
            if not fb_matches.empty:
                f_row = fb_matches.iloc[0]

                row_dict["touches_box"] = f_row.get(
                    "Touches_Att Pen", f_row.get("touches_att_pen", 0)
                )
                row_dict["prog_carries"] = f_row.get(
                    "Carries_PrgC", f_row.get("progressive_carries", 0)
                )
                row_dict["sca"] = f_row.get("SCA_SCA", f_row.get("sca", 0))
                row_dict["sca_dead"] = f_row.get(
                    "SCA Types_Dead", f_row.get("sca_dead", 0)
                )
        else:
            row_dict["touches_box"] = 0
            row_dict["prog_carries"] = 0
            row_dict["sca"] = 0
            row_dict["sca_dead"] = 0

        merged_rows.append(row_dict)

    return pd.DataFrame(merged_rows)


# --- 6. CACHED DATA LOAD PIPELINE ---
@st.cache_data(ttl=1800)
def load_all_data(season_year):
    p_data, t_data = fetch_understat_data(season_year)

    if not p_data:
        return None

    df_u = pd.DataFrame(p_data)
    df_u["player_clean"] = (
        df_u["player_name"].astype(str).str.lower().str.strip()
    )

    df_fb = fetch_fbref_data(season_year)
    merged_df = merge_metrics(df_u, df_fb)

    return {"playersData": merged_df, "teamsData": t_data}


# Execute App Logic
with st.spinner("Fetching data from metrics providers..."):
    data = load_all_data(selected_season)

if not data or "playersData" not in data or data["playersData"].empty:
    st.warning(
        "Could not load player data for this season. Please pick another"
        " season or clear the app cache."
    )
else:
    tab1, tab2 = st.tabs(
        ["⚽ Unified Player Metrics", "🛡️ Team Vulnerability (xGA)"]
    )

    # ==========================================
    # TAB 1: UNIFIED PLAYER METRICS
    # ==========================================
    with tab1:
        df_players = pd.DataFrame(data["playersData"])

        num_cols = [
            "games",
            "time",
            "goals",
            "xG",
            "shots",
            "assists",
            "xA",
            "key_passes",
            "xGChain",
            "xGBuildup",
            "touches_box",
            "prog_carries",
            "sca",
            "sca_dead",
        ]
        for c in num_cols:
            if c in df_players.columns:
                df_players[c] = pd.to_numeric(
                    df_players[c], errors="coerce"
                ).fillna(0)

        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Player Threshold Filters")

        teams = ["All"] + sorted(df_players["team_title"].unique().tolist())
        selected_team = st.sidebar.selectbox("Filter by Team", teams)

        positions = ["All"] + sorted(df_players["position"].unique().tolist())
        selected_position = st.sidebar.selectbox("Filter by Position", positions)

        min_minutes = st.sidebar.number_input(
            "Min Minutes Played", min_value=0, value=0, step=90
        )
        min_xg = st.sidebar.number_input(
            "Min Expected Goals (xG)", min_value=0.0, value=0.0, step=0.05
        )
        min_box_touches = st.sidebar.number_input(
            "Min Touches in Box (FBref)", min_value=0, value=0, step=5
        )

        filtered_df = df_players.copy()
        if selected_team != "All":
            filtered_df = filtered_df[filtered_df["team_title"] == selected_team]
        if selected_position != "All":
            filtered_df = filtered_df[filtered_df["position"] == selected_position]
        if min_minutes > 0:
            filtered_df = filtered_df[filtered_df["time"] >= min_minutes]
        if min_xg > 0:
            filtered_df = filtered_df[filtered_df["xG"] >= min_xg]
        if min_box_touches > 0:
            filtered_df = filtered_df[
                filtered_df["touches_box"] >= min_box_touches
            ]

        display_columns = [
            "player_name",
            "team_title",
            "position",
            "time",
            "goals",
            "xG",
            "assists",
            "xA",
            "xGChain",
            "touches_box",
            "prog_carries",
            "sca",
            "sca_dead",
        ]

        for col in display_columns:
            if col not in filtered_df.columns:
                filtered_df[col] = 0

        filtered_df = filtered_df.sort_values(by="xG", ascending=False).reset_index(
            drop=True
        )

        st.subheader(
            f"Unified Metrics Leaderboard ({len(filtered_df)} players matched)"
        )

        if not filtered_df.empty:
            renamed_df = filtered_df[display_columns].rename(
                columns={
                    "player_name": "Player",
                    "team_title": "Team",
                    "position": "Pos",
                    "time": "Mins",
                    "goals": "Goals",
                    "xG": "xG (Understat)",
                    "assists": "Assists",
                    "xA": "xA (Understat)",
                    "xGChain": "xG Chain",
                    "touches_box": "Box Touches (FBref)",
                    "prog_carries": "Prog Carries (FBref)",
                    "sca": "SCA Total (FBref)",
                    "sca_dead": "Set-Piece SCA (FBref)",
                }
            )
            st.dataframe(renamed_df, use_container_width=True)
        else:
            st.warning(
                "No players match your threshold filters. Try lowering your criteria."
            )

    # ==========================================
    # TAB 2: TEAM VULNERABILITY (xGA)
    # ==========================================
    with tab2:
        st.subheader("🛡️ Team Defensive Vulnerability Analysis")

        if "teamsData" in data and data["teamsData"]:
            teams_list = []
            for match in data["teamsData"]:
                if isinstance(match, dict):
                    h_team = match.get("h", {}).get("title")
                    a_team = match.get("a", {}).get("title")
                    h_xg = float(match.get("xG", {}).get("h", 0))
                    a_xg = float(match.get("xG", {}).get("a", 0))

                    teams_list.append({"Team": h_team, "xGA": a_xg})
                    teams_list.append({"Team": a_team, "xGA": h_xg})

            if teams_list:
                df_teams_summary = (
                    pd.DataFrame(teams_list)
                    .groupby("Team")
                    .agg(Matches=("xGA", "count"), xGA=("xGA", "sum"))
                    .reset_index()
                )

                df_teams_summary["xGA"] = df_teams_summary["xGA"].round(2)
                df_teams_summary = df_teams_summary.sort_values(
                    by="xGA", ascending=False
                ).reset_index(drop=True)
                st.dataframe(df_teams_summary, use_container_width=True)
