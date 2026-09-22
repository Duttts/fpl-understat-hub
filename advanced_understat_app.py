import pandas as pd
import streamlit as st
from understatapi import UnderstatClient

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Understat Advanced Metrics Hub", page_icon="📊", layout="wide"
)

st.title("📊 Understat Advanced Analytics Hub")
st.markdown(
    "A companion dashboard pulling underlying player and team metrics directly"
    " from Understat."
)

# --- 2. SEASON SELECTOR ---
# Understat uses starting years (e.g., 2026 = 2026/27, 2025 = 2025/26)
selected_season = st.sidebar.selectbox(
    "Select Season",
    options=[2026, 2025, 2024, 2023],
    format_func=lambda x: f"{x}/{x+1-2000}",
    index=0,
)


# --- 3. LOAD UNDERSTAT DATA ---
@st.cache_data(ttl=1800)  # Caches for 30 mins so live match data refreshes
def load_understat_data(season_year=2026):
    try:
        with UnderstatClient() as understat:
            player_data = understat.league(league="EPL").get_player_data(
                season=season_year
            )
            team_data = understat.league(league="EPL").get_team_data(
                season=season_year
            )

            if not player_data:
                st.warning(
                    f"Understat hasn't published aggregated player data for"
                    f" the {season_year}/{season_year+1-2000} season yet. Try"
                    " selecting a completed season or check back after"
                    " matchday metrics finalize."
                )
                return None

            return {"playersData": player_data, "teamsData": team_data}

    except Exception as e:
        st.error(f"Error fetching data from Understat: {e}")
        return None


with st.spinner("Fetching advanced underlying metrics from Understat..."):
    data = load_understat_data(selected_season)

if not data or "playersData" not in data or not data["playersData"]:
    st.info(
        "No data available for the selected season. Switch seasons in the sidebar"
        " or clear your cache."
    )
else:
    # --- CREATE TABS ---
    tab1, tab2 = st.tabs(["⚽ Player Metrics", "🛡️ Team Vulnerability (xGA)"])

    # ==========================================
    # TAB 1: PLAYER METRICS & THRESHOLD FILTERS
    # ==========================================
    with tab1:
        df_players = pd.DataFrame(data["playersData"])

        # Convert numeric columns
        numeric_cols = [
            "games",
            "time",
            "goals",
            "xG",
            "shots",
            "assists",
            "xA",
            "key_passes",
            "yellow_cards",
            "red_cards",
            "npg",
            "npxG",
            "xGChain",
            "xGBuildup",
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
        min_shots = st.sidebar.number_input(
            "Min Total Shots", min_value=0.0, value=0.0, step=1.0
        )
        min_xg = st.sidebar.number_input(
            "Min Expected Goals (xG)", min_value=0.0, value=0.0, step=0.05
        )
        min_key_passes = st.sidebar.number_input(
            "Min Key Passes", min_value=0.0, value=0.0, step=1.0
        )
        min_xa = st.sidebar.number_input(
            "Min Expected Assists (xA)", min_value=0.0, value=0.0, step=0.05
        )
        min_xg_chain = st.sidebar.number_input(
            "Min xG Chain (Overall Involvement)",
            min_value=0.0,
            value=0.0,
            step=0.5,
        )

        # Apply Filters
        filtered_df = df_players.copy()
        if selected_team != "All":
            filtered_df = filtered_df[filtered_df["team_title"] == selected_team]
        if selected_position != "All":
            filtered_df = filtered_df[filtered_df["position"] == selected_position]
        if min_minutes > 0:
            filtered_df = filtered_df[filtered_df["time"] >= min_minutes]
        if min_shots > 0:
            filtered_df = filtered_df[filtered_df["shots"] >= min_shots]
        if min_xg > 0:
            filtered_df = filtered_df[filtered_df["xG"] >= min_xg]
        if min_key_passes > 0:
            filtered_df = filtered_df[filtered_df["key_passes"] >= min_key_passes]
        if min_xa > 0:
            filtered_df = filtered_df[filtered_df["xA"] >= min_xa]
        if min_xg_chain > 0:
            filtered_df = filtered_df[filtered_df["xGChain"] >= min_xg_chain]

        display_columns = [
            "player_name",
            "team_title",
            "position",
            "time",
            "goals",
            "xG",
            "shots",
            "assists",
            "xA",
            "key_passes",
            "xGChain",
            "xGBuildup",
        ]

        filtered_df = filtered_df.sort_values(by="xG", ascending=False).reset_index(
            drop=True
        )

        st.subheader(
            f"Advanced Metrics Leaderboard ({len(filtered_df)} players matched)"
        )

        if not filtered_df.empty:
            renamed_df = filtered_df[display_columns].rename(
                columns={
                    "player_name": "Player",
                    "team_title": "Team",
                    "position": "Pos",
                    "time": "Mins",
                    "goals": "Goals",
                    "xG": "xG",
                    "shots": "Shots",
                    "assists": "Assists",
                    "xA": "xA",
                    "key_passes": "Key Passes",
                    "xGChain": "xG Chain",
                    "xGBuildup": "xG Buildup",
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
        st.markdown(
            "Ranked by **Expected Goals Against (xGA)**. Teams at the top are"
            " conceding the highest quality chances defensively, making them prime"
            " targets for your attacking transfers."
        )

        if "teamsData" in data and data["teamsData"]:
            teams_list = []
            for team_id, team_info in data["teamsData"].items():
                team_name = team_info.get("title")
                history = team_info.get("history", [])

                matches_played = len(history)
                x_g_against = sum(match.get("xGA", 0) for match in history)
                goals_against = sum(match.get("a", 0) for match in history)

                teams_list.append(
                    {
                        "Team": team_name,
                        "Matches": matches_played,
                        "Goals Conceded": goals_against,
                        "xGA (Expected Conceded)": round(x_g_against, 2),
                    }
                )

            df_teams_summary = pd.DataFrame(teams_list)
            if not df_teams_summary.empty:
                df_teams_summary = df_teams_summary.sort_values(
                    by="xGA (Expected Conceded)", ascending=False
                ).reset_index(drop=True)
                st.dataframe(df_teams_summary, use_container_width=True)
            else:
                st.info("Team match statistics are still compiling for this season.")
        else:
            st.info("Team data block not found.")
