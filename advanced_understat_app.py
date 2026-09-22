import codecs
import json
import re
import cloudscraper
import pandas as pd
import streamlit as st

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
# Note: Understat uses the starting year for seasons:
# 2026 = 2026/27, 2025 = 2025/26, 2024 = 2024/25
selected_season = st.sidebar.selectbox(
    "Select Season",
    options=["2026", "2025", "2024", "2023"],
    format_func=lambda x: f"{x}/{int(x)+1-2000}",
    index=0,
)


# --- 3. LOAD UNDERSTAT DATA (PLAYERS & TEAMS) ---
@st.cache_data(ttl=3600)
def load_understat_data(season_year="2026"):
    url = f"https://understat.com/league/EPL/{season_year}"
    try:
        # Create a CloudScraper instance to bypass Cloudflare
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url)

        if response.status_code != 200:
            st.error(
                f"Failed to connect to Understat (Status code:"
                f" {response.status_code})"
            )
            return None

        data_payload = {}

        # Look for JavaScript JSON.parse script blocks
        for key in ["playersData", "teamsData"]:
            pattern = rf"{key}\s*=\s*JSON\.parse\('([^']+)'\)"
            match = re.search(pattern, response.text)

            if match:
                raw_hex_data = match.group(1)
                # Decode \x20 hex sequences used by Understat into valid JSON text
                decoded_json = codecs.decode(raw_hex_data, "unicode_escape")
                data_payload[key] = json.loads(decoded_json)

        return data_payload
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None


with st.spinner("Fetching advanced underlying metrics from Understat..."):
    data = load_understat_data(selected_season)

if not data or "playersData" not in data or not data["playersData"]:
    st.warning(
        "No data returned for this season selection. The selected season may"
        " not have started or Understat has not populated this feed yet."
    )
else:
    tab1, tab2 = st.tabs(["⚽ Player Metrics", "🛡️ Team Vulnerability (xGA)"])

    # TAB 1: PLAYER METRICS
    with tab1:
        df_players = pd.DataFrame(data["playersData"])

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

        filtered_df = df_players.copy()
        if selected_team != "All":
            filtered_df = filtered_df[filtered_df["team_title"] == selected_team]
        if selected_position != "All":
            filtered_df = filtered_df[filtered_df["position"] == selected_position]
        if min_minutes > 0:
            filtered_df = filtered_df[filtered_df["time"] >= min_minutes]
        if min_xg > 0:
            filtered_df = filtered_df[filtered_df["xG"] >= min_xg]

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
            st.dataframe(filtered_df[display_columns], use_container_width=True)

    # TAB 2: TEAM VULNERABILITY
    with tab2:
        st.subheader("🛡️ Team Defensive Vulnerability Analysis")
        if "teamsData" in data and data["teamsData"]:
            teams_list = []
            for team_id, team_info in data["teamsData"].items():
                team_name = team_info.get("title")
                history = team_info.get("history", [])

                x_g_against = sum(match.get("xGA", 0) for match in history)
                goals_against = sum(match.get("a", 0) for match in history)

                teams_list.append(
                    {
                        "Team": team_name,
                        "Matches": len(history),
                        "Goals Conceded": goals_against,
                        "xGA": round(x_g_against, 2),
                    }
                )

            df_teams = pd.DataFrame(teams_list).sort_values(
                by="xGA", ascending=False
            )
            st.dataframe(df_teams, use_container_width=True)
