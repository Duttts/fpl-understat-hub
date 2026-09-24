import asyncio
import aiohttp
import pandas as pd
import plotly.express as px
import streamlit as st
from understat import Understat

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Understat Advanced Metrics Hub", page_icon="📊", layout="wide"
)

st.title("📊 Understat Advanced Analytics Hub")
st.markdown(
    "A companion dashboard pulling underlying player, team, and shot zone"
    " metrics directly from Understat."
)

# --- 2. SEASON SELECTOR ---
selected_season = st.sidebar.selectbox(
    "Select Season",
    options=[2026, 2025, 2024, 2023],
    format_func=lambda x: f"{x}/{x+1-2000}",
    index=0,
)


# --- HELPER FUNCTIONS ---
def map_position_category(raw_pos):
    """Maps Understat position strings into simplified broad categories."""
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
    """Classifies Understat normalized X (0 to 1) and Y (0 to 1) coordinates into zones."""
    if x >= 0.94 and 0.37 <= y <= 0.63:
        return "Six-Yard Box"
    elif x >= 0.83 and 0.21 <= y <= 0.79:
        return "Penalty Area"
    else:
        return "Outside Box"


# --- ASYNC FETCHERS ---
async def fetch_league_data(season_year):
    async with aiohttp.ClientSession() as session:
        understat = Understat(session)
        player_data = await understat.get_league_players("EPL", season_year)
        
        # FIX: Use get_league_results instead of get_league_data
        team_results = await understat.get_league_results("EPL", season_year)
        
        return {
            "playersData": player_data,
            "teamsData": team_results
        }

async def fetch_player_shots(player_id):
    async with aiohttp.ClientSession() as session:
        understat = Understat(session)
        shots = await understat.get_player_shots(player_id)
        return shots


# --- 3. DATA LOADERS ---
@st.cache_data(ttl=1800)
def load_understat_data(season_year=2026):
    try:
        data = asyncio.run(fetch_league_data(season_year))
        if not data or "playersData" not in data or not data["playersData"]:
            st.warning(
                "Understat hasn't published aggregated player data for the"
                f" {season_year}/{season_year+1-2000} season yet."
            )
            return None
        return data
    except Exception as e:
        st.error(f"Error fetching data from Understat: {e}")
        return None


@st.cache_data(ttl=1800)
def load_player_shot_data(player_id):
    """Fetches raw shot logs for a specific player ID."""
    try:
        shots = asyncio.run(fetch_player_shots(player_id))
        return pd.DataFrame(shots) if shots else pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching shot data: {e}")
        return pd.DataFrame()


with st.spinner("Fetching advanced underlying metrics from Understat..."):
    data = load_understat_data(selected_season)

if not data or "playersData" not in data or not data["playersData"]:
    st.info("No data available for the selected season.")
else:
    # --- CREATE TABS ---
    tab1, tab2, tab3 = st.tabs(
        ["⚽ Player Metrics", "🎯 Shot Maps & Form", "🛡️ Team Vulnerability (xGA)"]
    )

    # ==========================================
    # TAB 1: PLAYER METRICS & THRESHOLD FILTERS
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

        # Basic Per 90 metrics
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
        df_players["xGChain_p90"] = (
            df_players["xGChain"] / df_players["time"].replace(0, 1)
        ) * 90
        df_players["xGBuildup_p90"] = (
            df_players["xGBuildup"] / df_players["time"].replace(0, 1)
        ) * 90

        df_players["Pos_Categories"] = df_players["position"].apply(
            map_position_category
        )

        # Sidebar Filters
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Player Threshold Filters")

        show_per90 = st.sidebar.toggle(
            "Show Per 90 Metrics",
            value=False,
            help="Toggle table display to Per 90 stats.",
        )

        teams = ["All"] + sorted(df_players["team_title"].unique().tolist())
        selected_team = st.sidebar.selectbox("Filter by Team", teams)

        selected_position = st.sidebar.selectbox(
            "Filter by Position",
            options=["All", "Forward", "Midfield", "Defense", "Goalkeeper"],
        )

        st.sidebar.markdown("---")
        st.sidebar.subheader("Numerical Thresholds (>=)")
        min_minutes = st.sidebar.number_input(
            "Min Minutes Played", min_value=0, value=90, step=90
        )

        if not show_per90:
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
                "Min xG Chain", min_value=0.0, value=0.0, step=0.5
            )
        else:
            min_shots_p90 = st.sidebar.number_input(
                "Min Shots /90", min_value=0.0, value=0.0, step=0.5
            )
            min_xg_p90 = st.sidebar.number_input(
                "Min xG /90", min_value=0.0, value=0.0, step=0.05
            )
            min_key_passes_p90 = st.sidebar.number_input(
                "Min Key Passes /90", min_value=0.0, value=0.0, step=0.5
            )
            min_xa_p90 = st.sidebar.number_input(
                "Min xA /90", min_value=0.0, value=0.0, step=0.05
            )
            min_xg_chain_p90 = st.sidebar.number_input(
                "Min xG Chain /90", min_value=0.0, value=0.0, step=0.1
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

        if not show_per90:
            if min_shots > 0:
                filtered_df = filtered_df[filtered_df["shots"] >= min_shots]
            if min_xg > 0:
                filtered_df = filtered_df[filtered_df["xG"] >= min_xg]
            if min_key_passes > 0:
                filtered_df = filtered_df[
                    filtered_df["key_passes"] >= min_key_passes
                ]
            if min_xa > 0:
                filtered_df = filtered_df[filtered_df["xA"] >= min_xa]
            if min_xg_chain > 0:
                filtered_df = filtered_df[
                    filtered_df["xGChain"] >= min_xg_chain
                ]
        else:
            if min_shots_p90 > 0:
                filtered_df = filtered_df[
                    filtered_df["shots_p90"] >= min_shots_p90
                ]
            if min_xg_p90 > 0:
                filtered_df = filtered_df[filtered_df["xG_p90"] >= min_xg_p90]
            if min_key_passes_p90 > 0:
                filtered_df = filtered_df[
                    filtered_df["key_passes_p90"] >= min_key_passes_p90
                ]
            if min_xa_p90 > 0:
                filtered_df = filtered_df[filtered_df["xA_p90"] >= min_xa_p90]
            if min_xg_chain_p90 > 0:
                filtered_df = filtered_df[
                    filtered_df["xGChain_p90"] >= min_xg_chain_p90
                ]

        if not show_per90:
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
            column_rename = {
                "player_name": "Player",
                "team_title": "Team",
                "position": "Raw Pos",
                "time": "Mins",
                "goals": "Goals",
                "xG": "xG",
                "shots": "Total Shots",
                "assists": "Assists",
                "xA": "xA",
                "key_passes": "Key Passes",
                "xGChain": "xG Chain",
                "xGBuildup": "xG Buildup",
            }
            sort_metric = "xG"
        else:
            display_columns = [
                "player_name",
                "team_title",
                "position",
                "time",
                "goals",
                "xG_p90",
                "shots_p90",
                "assists",
                "xA_p90",
                "key_passes_p90",
                "xGChain_p90",
                "xGBuildup_p90",
            ]
            column_rename = {
                "player_name": "Player",
                "team_title": "Team",
                "position": "Raw Pos",
                "time": "Mins",
                "goals": "Goals",
                "xG_p90": "xG/90",
                "shots_p90": "Shots/90",
                "assists": "Assists",
                "xA_p90": "xA/90",
                "key_passes_p90": "KP/90",
                "xGChain_p90": "xGChain/90",
                "xGBuildup_p90": "xGBuildup/90",
            }
            sort_metric = "xG_p90"

        float_cols = [
            c
            for c in display_columns
            if c in filtered_df.columns
            and c not in ["time", "goals", "assists"]
        ]
        for col in float_cols:
            filtered_df[col] = filtered_df[col].round(2)

        filtered_df = filtered_df.sort_values(
            by=sort_metric, ascending=False
        ).reset_index(drop=True)

        mode_text = "Per 90" if show_per90 else "Totals"
        st.subheader(
            f"Advanced Metrics Leaderboard - {mode_text} ({len(filtered_df)}"
            " players matched)"
        )

        if not filtered_df.empty:
            renamed_df = filtered_df[display_columns].rename(
                columns=column_rename
            )
            st.dataframe(renamed_df, use_container_width=True)
        else:
            st.warning("No players match your threshold filters.")

    # ==========================================
    # TAB 2: SHOT MAPS & FORM INDICATOR
    # ==========================================
    with tab2:
        st.subheader("🎯 Player Shot Map & 5-Game Form Indicator")
        st.markdown(
            "Analyze shot locations, shot quality ($xG$), and recent **rolling 5-game form** (Last 3 matches vs. Previous 2 matches)."
        )

        player_options = (
            df_players.sort_values("xG", ascending=False)["player_name"]
            .unique()
            .tolist()
        )

        selected_player_name = st.selectbox(
            "Select Player for Shot & Form Analysis", options=player_options, index=0
        )

        player_info = df_players[
            df_players["player_name"] == selected_player_name
        ].iloc[0]
        player_id = player_info["id"]

        with st.spinner(f"Loading shot map & match logs for {selected_player_name}..."):
            df_shots = load_player_shot_data(player_id)

        if df_shots.empty:
            st.warning(
                f"No shot location data returned for {selected_player_name}."
            )
        else:
            # Filter for selected season
            df_shots["season"] = pd.to_numeric(
                df_shots["season"], errors="coerce"
            )
            df_shots = df_shots[
                df_shots["season"] == selected_season
            ].copy()

            if df_shots.empty:
                st.info(
                    f"No recorded shots for {selected_player_name} in the"
                    f" {selected_season}/{selected_season+1-2000} season."
                )
            else:
                # Convert shot columns
                df_shots["X"] = pd.to_numeric(df_shots["X"], errors="coerce")
                df_shots["Y"] = pd.to_numeric(df_shots["Y"], errors="coerce")
                df_shots["xG"] = pd.to_numeric(
                    df_shots["xG"], errors="coerce"
                ).round(3)
                df_shots["Shot_Zone"] = df_shots.apply(
                    lambda r: classify_shot_zone(r["X"], r["Y"]), axis=1
                )
                df_shots["date"] = pd.to_datetime(df_shots["date"])

                # --- 📈 RECENT FORM CALCULATIONS (LAST 3 VS PREVIOUS 2 GAMES) ---
                st.markdown("---")
                st.markdown("### 📈 Recent 5-Game Shot Form Indicator")

                # Get unique matches chronologically
                match_group = (
                    df_shots.groupby(["match_id", "date"])
                    .agg(
                        Shots=("id", "count"),
                        xG=("xG", "sum"),
                        Goals=("result", lambda s: (s == "Goal").sum()),
                    )
                    .reset_index()
                    .sort_values("date")
                )

                total_matches = len(match_group)

                if total_matches < 5:
                    st.info(
                        f"**{selected_player_name}** has recorded shots in"
                        f" {total_matches} match(es) this season. At least 5 matches"
                        " with shots are required for full 3-vs-2 rolling form comparison."
                    )
                else:
                    last_5 = match_group.tail(5).copy().reset_index(drop=True)

                    # Split: First 2 games vs Last 3 games
                    prev_2 = last_5.iloc[0:2]
                    last_3 = last_5.iloc[2:5]

                    avg_shots_prev_2 = prev_2["Shots"].mean()
                    avg_shots_last_3 = last_3["Shots"].mean()

                    shots_diff = avg_shots_last_3 - avg_shots_prev_2
                    pct_change = (
                        (shots_diff / max(avg_shots_prev_2, 0.1)) * 100
                    )

                    last_3_xg = last_3["xG"].sum()
                    last_3_goals = last_3["Goals"].sum()

                    c1, c2, c3, c4 = st.columns(4)

                    with c1:
                        st.metric(
                            label="Last 3 Games Avg Shots",
                            value=f"{avg_shots_last_3:.2f} / game",
                            delta=(
                                f"{shots_diff:+.2f} / game ({pct_change:+.0f}%) vs prev 2 games"
                            ),
                        )

                    with c2:
                        st.metric(
                            label="Prev 2 Games Avg Shots",
                            value=f"{avg_shots_prev_2:.2f} / game",
                        )

                    with c3:
                        st.metric(
                            label="Last 3 Games xG",
                            value=f"{last_3_xg:.2f}",
                        )

                    with c4:
                        st.metric(
                            label="Last 3 Games Goals",
                            value=f"{last_3_goals}",
                        )

                    # Form trend callout
                    if shots_diff > 0.2:
                        st.success(
                            f"🔥 **HOT FORM:** {selected_player_name} is averaging **{shots_diff:+.2f} more shots/game** over his last 3 matches compared to his previous 2."
                        )
                    elif shots_diff < -0.2:
                        st.warning(
                            f"📉 **COOLING DOWN:** {selected_player_name} is averaging **{abs(shots_diff):.2f} fewer shots/game** over his last 3 matches compared to his previous 2."
                        )
                    else:
                        st.info(
                            f"➖ **STABLE FORM:** {selected_player_name}'s shot volume over the last 3 matches matches his previous 2 games."
                        )

                st.markdown("---")

                # Split layout: Pitch Map & Zone Summary
                col_map, col_stats = st.columns([3, 2])

                with col_map:
                    st.markdown("##### 📍 Attacking Half Shot Pitch")

                    fig = px.scatter(
                        df_shots,
                        x="Y",
                        y="X",
                        color="result",
                        size="xG",
                        size_max=18,
                        hover_data=[
                            "minute",
                            "xG",
                            "shotType",
                            "situation",
                            "h_team",
                            "a_team",
                        ],
                        labels={
                            "Y": "Pitch Width",
                            "X": "Pitch Length",
                            "result": "Outcome",
                        },
                        title=f"{selected_player_name} Shot Locations (Attacking Right)",
                    )

                    fig.update_xaxes(range=[0, 1], showgrid=False, zeroline=False)
                    fig.update_yaxes(
                        range=[0.5, 1.05], showgrid=False, zeroline=False
                    )

                    fig.add_shape(
                        type="rect",
                        x0=0.21,
                        y0=0.83,
                        x1=0.79,
                        y1=1.0,
                        line=dict(color="gray", dash="dash"),
                    )
                    fig.add_shape(
                        type="rect",
                        x0=0.37,
                        y0=0.94,
                        x1=0.63,
                        y1=1.0,
                        line=dict(color="gray", dash="dash"),
                    )

                    fig.update_layout(
                        height=500,
                        plot_bgcolor="#1e1e1e",
                        paper_bgcolor="#1e1e1e",
                        font=dict(color="white"),
                    )

                    st.plotly_chart(fig, use_container_width=True)

                with col_stats:
                    st.markdown("##### 📊 Shot Performance by Zone")

                    zone_summary = (
                        df_shots.groupby("Shot_Zone")
                        .agg(
                            Shots=("id", "count"),
                            Goals=("result", lambda s: (s == "Goal").sum()),
                            xG=("xG", "sum"),
                            Avg_xG_Per_Shot=("xG", "mean"),
                        )
                        .reset_index()
                    )

                    # Compute combined In-Box metric for quick summary
                    in_box_df = zone_summary[
                        zone_summary["Shot_Zone"].isin(
                            ["Penalty Area", "Six-Yard Box"]
                        )
                    ]
                    if not in_box_df.empty:
                        combined_row = pd.DataFrame(
                            [
                                {
                                    "Shot_Zone": "📦 Inside Box (Total)",
                                    "Shots": in_box_df["Shots"].sum(),
                                    "Goals": in_box_df["Goals"].sum(),
                                    "xG": in_box_df["xG"].sum(),
                                    "Avg_xG_Per_Shot": in_box_df[
                                        "xG"
                                    ].sum()
                                    / max(in_box_df["Shots"].sum(), 1),
                                }
                            ]
                        )
                        zone_summary = pd.concat(
                            [zone_summary, combined_row], ignore_index=True
                        )

                    zone_summary["xG"] = zone_summary["xG"].round(2)
                    zone_summary["Avg_xG_Per_Shot"] = zone_summary[
                        "Avg_xG_Per_Shot"
                    ].round(2)
                    zone_summary["Conversion %"] = (
                        (zone_summary["Goals"] / zone_summary["Shots"]) * 100
                    ).round(1)

                    st.dataframe(zone_summary, use_container_width=True)

                    st.markdown("##### 🦶 Shot Type / Body Part")
                    shot_type_counts = (
                        df_shots["shotType"].value_counts().reset_index()
                    )
                    shot_type_counts.columns = ["Shot Type", "Count"]
                    st.dataframe(shot_type_counts, use_container_width=True)

    # ==========================================
    # TAB 3: TEAM VULNERABILITY (DEFENSIVE METRICS)
    # ==========================================
    with tab3:
        st.subheader("🛡️ Team Defensive Vulnerability Analysis")
        st.markdown(
            "Ranked by **Expected Goals Against (xGA)**. Teams at the top are"
            " conceding the highest quality chances defensively."
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
                        "xGA / Match": round(
                            x_g_against / max(matches_played, 1), 2
                        ),
                    }
                )

            df_teams_summary = pd.DataFrame(teams_list)
            if not df_teams_summary.empty:
                df_teams_summary = df_teams_summary.sort_values(
                    by="xGA (Expected Conceded)", ascending=False
                ).reset_index(drop=True)
                st.dataframe(df_teams_summary, use_container_width=True)
            else:
                st.info("Team match statistics are still compiling.")
        else:
            st.info("Team data block not found.")
