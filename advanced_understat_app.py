import asyncio
import nest_asyncio
import pandas as pd
import soccerdata as sd
import streamlit as st
from thefuzz import fuzz, process
from understat import Understat

# Apply nest_asyncio to safely manage event loops inside Streamlit
nest_asyncio.apply()

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
    format_func=lambda x: f"{x}/{x+1-2000}",
    index=0,
)


# --- 3. ASYNC UNDERSTAT FETCHERS ---
async def fetch_understat_players(season_year):
    import aiohttp

    async with aiohttp.ClientSession() as session:
        understat = Understat(session)
        players = await understat.get_league_players(
            "EPL", season=str(season_year)
        )
        return players


async def fetch_understat_teams(season_year):
    import aiohttp

    async with aiohttp.ClientSession() as session:
        understat = Understat(session)
        teams = await understat.get_league_results(
            "EPL", season=str(season_year)
        )
        return teams


# --- 4. FUZZY MERGE HELPER FUNCTION ---
def merge_understat_and_fbref(df_understat, df_fbref, threshold=75):
    """Merges Understat and FBref DataFrames on player names using fuzzy matching."""
    if df_fbref.empty:
        return df_understat

    fbref_names = df_fbref["player_clean"].dropna().unique().tolist()
    merged_rows = []

    for _, u_row in df_understat.iterrows():
        u_name = u_row["player_clean"]

        # Extract top fuzzy match candidate from FBref name list
        best_match, score, _ = process.extractOne(
            u_name, fbref_names, scorer=fuzz.token_sort_ratio
        )

        row_dict = u_row.to_dict()

        if score >= threshold:
            fbref_matches = df_fbref[df_fbref["player_clean"] == best_match]
            if not fbref_matches.empty:
                f_row = fbref_matches.iloc[0]

                # Extract FBref metric fields safely across flat or multi-level columns
                row_dict["touches_box"] = f_row.get(
                    ("Touches", "Att Pen"),
                    f_row.get(
                        "touches_att_pen", f_row.get("Touches_Att Pen", 0)
                    ),
                )
                row_dict["prog_carries"] = f_row.get(
                    ("Carries", "PrgC"),
                    f_row.get(
                        "progressive_carries",
                        f_row.get("Carries_PrgC", f_row.get("PrgC", 0)),
                    ),
                )
                row_dict["sca"] = f_row.get(
                    ("SCA", "SCA"), f_row.get("sca", f_row.get("SCA_SCA", 0))
                )
                row_dict["sca_dead"] = f_row.get(
                    ("SCA Types", "Dead"),
                    f_row.get(
                        "sca_dead",
                        f_row.get(
                            "SCA Types_Dead", f_row.get("SCA_Dead", 0)
                        ),
                    ),
                )
        else:
            row_dict["touches_box"] = 0
            row_dict["prog_carries"] = 0
            row_dict["sca"] = 0
            row_dict["sca_dead"] = 0

        merged_rows.append(row_dict)

    return pd.DataFrame(merged_rows)


# --- 5. DATA LOADER ---
@st.cache_data(ttl=1800)
def load_combined_data(season_year=2026):
    data_payload = {}

    # A. Fetch Understat Data asynchronously
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        player_data = loop.run_until_complete(
            fetch_understat_players(season_year)
        )
        team_data = loop.run_until_complete(fetch_understat_teams(season_year))

        if not player_data:
            st.warning(
                f"Understat has not published aggregated data for"
                f" {season_year}/{season_year+1-2000} yet."
            )
            return None

        df_understat = pd.DataFrame(player_data)
        data_payload["teamsData"] = team_data
    except Exception as e:
        st.error(f"Error fetching Understat data: {e}")
        return None

    # B. Fetch FBref Data via soccerdata
    df_fbref = pd.DataFrame()
    try:
        fbref = sd.FBref(leagues="ENG-Premier League", seasons=season_year)

        df_fb_std = (
            fbref.read_player_season_stats(stat_type="standard")
            .reset_index()
        )
        df_fb_gca = (
            fbref.read_player_season_stats(stat_type="gca")
            .reset_index()
        )

        # Standardize column headers if multi-index
        if isinstance(df_fb_std.columns, pd.MultiIndex):
            df_fb_std.columns = [
                "_".join(col).strip() if col[1] else col[0]
                for col in df_fb_std.columns
            ]
        if isinstance(df_fb_gca.columns, pd.MultiIndex):
            df_fb_gca.columns = [
                "_".join(col).strip() if col[1] else col[0]
                for col in df_fb_gca.columns
            ]

        # Standardize FBref player name column
        player_col = [
            col for col in df_fb_std.columns if "player" in col.lower()
        ]
        if player_col:
            df_fb_std["player_clean"] = (
                df_fb_std[player_col[0]].astype(str).str.lower().str.strip()
            )
            df_fbref = df_fb_std
    except Exception as e:
        st.info(
            f"FBref metrics are currently building or unavailable for this"
            f" season: {e}"
        )

    # Standardize Understat player names
    df_understat["player_clean"] = (
        df_understat["player_name"].astype(str).str.lower().str.strip()
    )

    # C. Perform Fuzzy Merge
    data_payload["playersData"] = merge_understat_and_fbref(
        df_understat, df_fbref
    )
    return data_payload


# Load cached dataset
with st.spinner("Fetching & merging metrics from Understat + FBref..."):
    data = load_combined_data(selected_season)

if not data or "playersData" not in data or data["playersData"].empty:
    st.info(
        "No data available for the selected season. Try clearing your Streamlit"
        " cache or select another season."
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

        # Convert numeric columns safely
        numeric_cols = [
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
        for col in numeric_cols:
            if col in df_players.columns:
                df_players[col] = pd.to_numeric(
                    df_players[col], errors="coerce"
                ).fillna(0)

        # Sidebar Filters
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Player Threshold Filters")

        teams = ["All"] + sorted(df_players["team_title"].unique().tolist())
        selected_team = st.sidebar.selectbox("Filter by Team", teams)

        positions = ["All"] + sorted(df_players["position"].unique().tolist())
        selected_position = st.sidebar.selectbox("Filter by Position", positions)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Numerical Thresholds (>=)")
        min_minutes = st.sidebar.number_input(
            "Min Minutes Played", min_value=0, value=0, step=90
        )
        min_xg = st.sidebar.number_input(
            "Min Expected Goals (xG)", min_value=0.0, value=0.0, step=0.05
        )
        min_box_touches = st.sidebar.number_input(
            "Min Touches in Box (FBref)", min_value=0, value=0, step=5
        )

        # Filter Logic
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
    # TAB 2: TEAM VULNERABILITY (DEFENSIVE METRICS)
    # ==========================================
    with tab2:
        st.subheader("🛡️ Team Defensive Vulnerability Analysis")

        if "teamsData" in data and data["teamsData"]:
            teams_list = []
            for match in data["teamsData"]:
                h_team = match.get("h", {}).get("title")
                a_team = match.get("a", {}).get("title")
                h_xg = float(match.get("xG", {}).get("h", 0))
                a_xg = float(match.get("xG", {}).get("a", 0))

                # Accumulate xGA (Expected Goals Allowed) for each team
                teams_list.append({"Team": h_team, "xGA": a_xg})
                teams_list.append({"Team": a_team, "xGA": h_xg})

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
