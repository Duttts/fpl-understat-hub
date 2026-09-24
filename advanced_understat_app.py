import asyncio
import aiohttp
import pandas as pd
import plotly.express as px
import streamlit as st
from understat import Understat

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Understat Recent Form Hub (Last 5 GWs)",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Understat Recent Form Hub")
st.markdown(
    "Analyze underlying player metrics, shot maps, and team stats strictly"
    " based on **each team's last 5 completed matches**."
)

# --- 2. SEASON SELECTOR ---
selected_season = st.sidebar.selectbox(
    "Select Season",
    options=[2026, 2025, 2024, 2023],
    format_func=lambda x: f"{x}/{x+1-2000}",
    index=0,
)

# Sidebar toggle for window length
gw_window = st.sidebar.slider(
    "Recent Match Window",
    min_value=3,
    max_value=10,
    value=5,
    help="Filters all metrics to only include data from each team's last N matches.",
)


# --- HELPER FUNCTIONS ---
def map_position_category(raw_pos):
    if not isinstance(raw_pos, str):
        return ["Other"]
    categories = set()
    if "D" in raw_pos:
        categories.add("Defense")
    if "M" in raw_pos:
        categories.add("Midfield")
    if "F" in raw_pos:
        categories.add("Forward")
    if "GK" in raw_pos:
        categories.add("Goalkeeper")
    return list(categories) if categories else ["Other"]


def classify_shot_zone(x, y):
    if x >= 0.94 and 0.37 <= y <= 0.63:
        return "Six-Yard Box"
    elif x >= 0.83 and 0.21 <= y <= 0.79:
        return "Penalty Area"
    else:
        return "Outside Box"


# --- ASYNC FETCHERS ---
async def fetch_recent_league_data(season_year, recent_matches_count=5):
    async with aiohttp.ClientSession() as session:
        understat = Understat(session)

        # 1. Fetch finished match results to determine recent match IDs per team
        results = await understat.get_league_results("EPL", season_year)
        if not results:
            return None

        df_results = pd.DataFrame(results)
        df_results["datetime"] = pd.to_datetime(df_results["datetime"])
        df_results = df_results.sort_values("datetime")

        # Extract last N match IDs per team
        recent_match_ids = set()
        team_last_n_matches = {}

        # Collect unique teams
        all_teams = set(df_results["h"].apply(lambda x: x["title"])).union(
            set(df_results["a"].apply(lambda x: x["title"]))
        )

        for team in all_teams:
            team_matches = df_results[
                (df_results["h"].apply(lambda x: x["title"]) == team)
                | (df_results["a"].apply(lambda x: x["title"]) == team)
            ].tail(recent_matches_count)

            team_last_n_matches[team] = team_matches
            recent_match_ids.update(team_matches["id"].tolist())

        # 2. Fetch league player data
        player_data = await understat.get_league_players("EPL", season_year)

        return {
            "playersData": player_data,
            "recentMatchIds": recent_match_ids,
            "results": df_results,
            "teamLastN": team_last_n_matches,
        }


async def fetch_player_shots(player_id):
    async with aiohttp.ClientSession() as session:
        understat = Understat(session)
        shots = await understat.get_player_shots(player_id)
        return shots


# --- 3. DATA LOADERS ---
@st.cache_data(ttl=1800)
def load_understat_data(season_year=2026, window=5):
    try:
        data = asyncio.run(fetch_recent_league_data(season_year, window))
        if not data or "playersData" not in data:
            st.warning("No data available for the selected season.")
            return None
        return data
    except Exception as e:
        st.error(f"Error fetching data from Understat: {e}")
        return None


@st.cache_data(ttl=1800)
def load_player_shot_data(player_id):
    try:
        shots = asyncio.run(fetch_player_shots(player_id))
        return pd.DataFrame(shots) if shots else pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching shot data: {e}")
        return pd.DataFrame()


with st.spinner(
    f"Filtering data for the last {gw_window} matches per team..."
):
    data = load_understat_data(selected_season, gw_window)

if not data:
    st.info("No data available for the selected parameters.")
else:
    recent_match_ids = data["recentMatchIds"]

    tab1, tab2, tab3 = st.tabs(
        ["⚽ Player Recent Metrics", "🎯 Recent Shot Maps", "🛡️ Recent Team xGA"]
    )

    # ==========================================
    # TAB 1: PLAYER RECENT METRICS
    # ==========================================
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

        # Calculate Per 90 metrics
        df_players["xG_p90"] = (
            df_players["xG"] / df_players["time"].replace(0, 1)
        ) * 90
        df_players["xA_p90"] = (
            df_players["xA"] / df_players["time"].replace(0, 1)
        ) * 90
        df_players["shots_p90"] = (
            df_players["shots"] / df_players["time"].replace(0, 1)
        ) * 90
        df_players["key_passes_p90"] = (
            df_players["key_passes"] / df_players["time"].replace(0, 1)
        ) * 90

        df_players["Pos_Categories"] = df_players["position"].apply(
            map_position_category
        )

        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Filters")

        teams = ["All"] + sorted(df_players["team_title"].unique().tolist())
        selected_team = st.sidebar.selectbox("Filter by Team", teams)

        selected_position = st.sidebar.selectbox(
            "Filter by Position",
            options=["All", "Forward", "Midfield", "Defense", "Goalkeeper"],
        )

        min_minutes = st.sidebar.number_input(
            "Min Minutes Played", min_value=0, value=60, step=30
        )
        min_shots = st.sidebar.number_input(
            "Min Total Shots", min_value=0.0, value=0.0, step=1.0
        )
        min_xg = st.sidebar.number_input(
            "Min xG", min_value=0.0, value=0.0, step=0.1
        )

        filtered_df = df_players.copy()

        if selected_team != "All":
            filtered_df = filtered_df[
                filtered_df["team_title"] == selected_team
            ]

        if selected_position != "All":
            filtered_df = filtered_df[
                filtered_df["Pos_Categories"].apply(
                    lambda x: selected_position in x
                )
            ]

        if min_minutes > 0:
            filtered_df = filtered_df[filtered_df["time"] >= min_minutes]
        if min_shots > 0:
            filtered_df = filtered_df[filtered_df["shots"] >= min_shots]
        if min_xg > 0:
            filtered_df = filtered_df[filtered_df["xG"] >= min_xg]

        display_columns = [
            "player_name",
            "team_title",
            "position",
            "time",
            "shots",
            "shots_p90",
            "goals",
            "xG",
            "xG_p90",
            "assists",
            "xA",
            "key_passes",
        ]
        column_rename = {
            "player_name": "Player",
            "team_title": "Team",
            "position": "Pos",
            "time": "Mins",
            "shots": "Shots",
            "shots_p90": "Shots/90",
            "goals": "Goals",
            "xG": "xG",
            "xG_p90": "xG/90",
            "assists": "Assists",
            "xA": "xA",
            "key_passes": "Key Passes",
        }

        for c in ["xG", "xG_p90", "xA", "shots_p90"]:
            filtered_df[c] = filtered_df[c].round(2)

        filtered_df = filtered_df.sort_values(
            by="shots", ascending=False
        ).reset_index(drop=True)

        st.subheader(
            f"Player Metrics Leaderboard ({len(filtered_df)} players)"
        )

        if not filtered_df.empty:
            st.dataframe(
                filtered_df[display_columns].rename(columns=column_rename),
                use_container_width=True,
            )
        else:
            st.warning("No players match your filters.")

    # ==========================================
    # TAB 2: RECENT SHOT MAPS (STRICTLY LAST N GWs)
    # ==========================================
    with tab2:
        st.subheader(
            f"🎯 Player Shot Map (Last {gw_window} Team Matches Only)"
        )

        player_options = (
            df_players.sort_values("shots", ascending=False)["player_name"]
            .unique()
            .tolist()
        )
        selected_player_name = st.selectbox(
            "Select Player", options=player_options, index=0
        )

        player_info = df_players[
            df_players["player_name"] == selected_player_name
        ].iloc[0]
        player_id = player_info["id"]

        with st.spinner(f"Loading recent shots for {selected_player_name}..."):
            df_shots = load_player_shot_data(player_id)

        if df_shots.empty:
            st.warning(f"No shot data found for {selected_player_name}.")
        else:
            df_shots["season"] = pd.to_numeric(
                df_shots["season"], errors="coerce"
            )
            df_shots = df_shots[df_shots["season"] == selected_season].copy()

            # STRICT FILTER: Keep only shots from the recent match IDs window
            df_recent_shots = df_shots[
                df_shots["match_id"].isin(recent_match_ids)
            ].copy()

            if df_recent_shots.empty:
                st.info(
                    f"**{selected_player_name}** recorded 0 shots in his team's last {gw_window} matches."
                )
            else:
                df_recent_shots["X"] = pd.to_numeric(
                    df_recent_shots["X"], errors="coerce"
                )
                df_recent_shots["Y"] = pd.to_numeric(
                    df_recent_shots["Y"], errors="coerce"
                )
                df_recent_shots["xG"] = pd.to_numeric(
                    df_recent_shots["xG"], errors="coerce"
                ).round(3)

                total_recent_shots = len(df_recent_shots)
                total_recent_xg = df_recent_shots["xG"].sum()
                recent_goals = (df_recent_shots["result"] == "Goal").sum()

                c1, c2, c3 = st.columns(3)
                c1.metric(
                    f"Shots (Last {gw_window} Games)", f"{total_recent_shots}"
                )
                c2.metric(f"xG (Last {gw_window} Games)", f"{total_recent_xg:.2f}")
                c3.metric(
                    f"Goals (Last {gw_window} Games)", f"{recent_goals}"
                )

                st.markdown("---")

                fig = px.scatter(
                    df_recent_shots,
                    x="Y",
                    y="X",
                    color="result",
                    size="xG",
                    size_max=18,
                    hover_data=["minute", "xG", "shotType", "situation", "date"],
                    labels={"Y": "Pitch Width", "X": "Pitch Length"},
                    title=f"{selected_player_name} - Shots in Last {gw_window} Matches",
                )

                fig.update_xaxes(range=[0, 1], showgrid=False, zeroline=False)
                fig.update_yaxes(
                    range=[0.5, 1.05], showgrid=False, zeroline=False
                )

                fig.update_layout(
                    height=500,
                    plot_bgcolor="#1e1e1e",
                    paper_bgcolor="#1e1e1e",
                    font=dict(color="white"),
                )

                st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # TAB 3: RECENT TEAM xGA (DEFENSIVE VULNERABILITY)
    # ==========================================
    with tab3:
        st.subheader(f"🛡️ Defensive xGA (Last {gw_window} Games)")
        st.markdown(
            f"Teams sorted by Expected Goals Against (xGA) over their **last {gw_window} matches only**."
        )

        team_last_n = data["teamLastN"]
        recent_teams_list = []

        for team_name, df_team_matches in team_last_n.items():
            if not df_team_matches.empty:
                xga_total = 0
                ga_total = 0

                for _, row in df_team_matches.iterrows():
                    if row["h"]["title"] == team_name:
                        xga_total += float(row["xG"]["a"])
                        ga_total += int(row["goals"]["a"])
                    else:
                        xga_total += float(row["xG"]["h"])
                        ga_total += int(row["goals"]["h"])

                matches_count = len(df_team_matches)
                recent_teams_list.append(
                    {
                        "Team": team_name,
                        "Matches": matches_count,
                        "Goals Conceded": ga_total,
                        "Recent xGA": round(xga_total, 2),
                        "xGA / Match": round(
                            xga_total / max(matches_count, 1), 2
                        ),
                    }
                )

        df_recent_teams = pd.DataFrame(recent_teams_list)
        if not df_recent_teams.empty:
            df_recent_teams = df_recent_teams.sort_values(
                by="Recent xGA", ascending=False
            ).reset_index(drop=True)
            st.dataframe(df_recent_teams, use_container_width=True)
