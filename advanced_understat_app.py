import pandas as pd
import requests
import streamlit as st
from understat import Understat

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Football Analytics Dashboard",
    page_icon="⚽",
    layout="wide",
)


# ==========================================
# DATA FETCHING & HELPER FUNCTIONS
# ==========================================
@st.cache_data(ttl=3600)
def load_league_data(league="EPL", season=2023):
    """Fetches main season data for all players in a league."""
    # Example placeholder using Understat API structure or wrapper
    # Replace/integrate with your existing Understat loader function if different
    try:
        url = f"https://understat.com/main/get_data/{league}/{season}"
        # If using understat wrapper or custom parser:
        # adjust according to your specific data pipeline
    except Exception as e:
        st.error(f"Error loading league data: {e}")
        return {}


@st.cache_data(ttl=3600)
def load_player_shot_data(player_id):
    """Fetches raw shot/match history log for a specific player."""
    try:
        # Standard shot data loader logic
        # Replace with your project's exact implementation if needed
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def map_position_category(pos):
    """Maps raw position strings to general position categories."""
    if not isinstance(pos, str):
        return "Unknown"
    pos = pos.upper()
    if any(p in pos for p in ["GK"]):
        return "Goalkeeper"
    if any(p in pos for p in ["DF", "CB", "LB", "RB", "WB"]):
        return "Defense"
    if any(p in pos for p in ["MF", "CM", "DM", "AM", "LM", "RM"]):
        return "Midfield"
    if any(p in pos for p in ["FW", "ST", "CF", "LW", "RW"]):
        return "Forward"
    return "Other"


def get_player_recent_match_stats(player_id, selected_season, last_n_games=4):
    """Fetches a player's shot/match history to aggregate metrics

    for their last N played matches.
    """
    shots_df = load_player_shot_data(player_id)

    default_stats = {
        "recent_m": 0,
        "recent_shots": 0,
        "recent_xg": 0.0,
        "recent_goals": 0,
        "recent_xa": 0.0,
        "recent_key_passes": 0,
    }

    if shots_df.empty or "season" not in shots_df.columns:
        return default_stats

    shots_df["season"] = pd.to_numeric(shots_df["season"], errors="coerce")
    shots_df = shots_df[shots_df["season"] == selected_season].copy()

    if shots_df.empty:
        return default_stats

    # Convert numeric fields
    for col in ["xG", "xA", "key_passes"]:
        if col in shots_df.columns:
            shots_df[col] = pd.to_numeric(
                shots_df[col], errors="coerce"
            ).fillna(0.0)
        else:
            shots_df[col] = 0.0

    # Get the last N distinct matches played
    match_dates = (
        shots_df[["match_id", "date"]]
        .drop_duplicates()
        .sort_values(by="date", ascending=False)
    )
    recent_matches = match_dates.head(last_n_games)["match_id"].tolist()

    recent_shots_df = shots_df[shots_df["match_id"].isin(recent_matches)]

    games_played = len(recent_matches)
    total_shots = len(recent_shots_df)
    total_xg = recent_shots_df["xG"].sum()
    total_goals = (recent_shots_df["result"] == "Goal").sum()

    total_xa = (
        recent_shots_df["xA"].sum() if "xA" in recent_shots_df.columns else 0.0
    )
    total_kp = (
        recent_shots_df["key_passes"].sum()
        if "key_passes" in recent_shots_df.columns
        else 0
    )

    return {
        "recent_m": games_played,
        "recent_shots": total_shots,
        "recent_xg": round(total_xg, 2),
        "recent_goals": total_goals,
        "recent_xa": round(total_xa, 2),
        "recent_key_passes": int(total_kp),
    }


# ==========================================
# SIDEBAR CONTROL PANEL
# ==========================================
st.sidebar.title("⚽ Dashboard Settings")
selected_league = st.sidebar.selectbox(
    "Select League", ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"]
)
selected_season = st.sidebar.number_input(
    "Select Season", min_value=2014, max_value=2025, value=2023
)

# Load base data
data = load_league_data(selected_league, selected_season)

st.title(f"📊 {selected_league} ({selected_season}/{selected_season+1}) Metrics")

# Navigation Tabs
tab1, tab2 = st.tabs(["Player Leaderboard", "Team / Other Analytics"])


# ==========================================
# TAB 1: ADVANCED METRICS LEADERBOARD (SEASON + RECENT FORM)
# ==========================================
with tab1:
    st.subheader("⚽ Advanced Metrics Leaderboard")

    if "playersData" in data and data["playersData"]:
        df_players = pd.DataFrame(data["playersData"])

        # Basic numeric parsing
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
        ]
        for col in numeric_cols:
            if col in df_players.columns:
                df_players[col] = pd.to_numeric(
                    df_players[col], errors="coerce"
                ).fillna(0)

        df_players["Pos_Categories"] = df_players["position"].apply(
            map_position_category
        )

        # Filters
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Filters")
        teams = ["All"] + sorted(df_players["team_title"].unique().tolist())
        selected_team = st.sidebar.selectbox("Filter by Team", teams)

        selected_position = st.sidebar.selectbox(
            "Filter by Position",
            options=["All", "Forward", "Midfield", "Defense", "Goalkeeper"],
        )

        min_minutes = st.sidebar.number_input(
            "Min Minutes Played", min_value=0, value=90, step=90
        )

        # Filter dataframe
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

        filtered_df = filtered_df.sort_values(
            by="shots", ascending=False
        ).reset_index(drop=True)

        # Rolling Window Controls
        st.markdown("---")
        col_m1, col_m2 = st.columns([1, 1])
        with col_m1:
            n_games = st.slider(
                "📅 Rolling Match Window (Last N Games)",
                min_value=2,
                max_value=10,
                value=4,
            )
        with col_m2:
            top_p_count = st.slider(
                "⚡ Number of Top Players to Calculate Recent Form For",
                min_value=5,
                max_value=50,
                value=20,
                help=(
                    "Fetching recent match logs requires individual API calls."
                    " Limit this to top N players to keep the app fast."
                ),
            )

        st.markdown("---")

        if filtered_df.empty:
            st.warning("No players match your selected filters.")
        else:
            # Process recent match form for top N players in current selection
            top_players = filtered_df.head(top_p_count).copy()

            with st.spinner(
                f"Fetching match logs and compiling last {n_games} games stats"
                f" for top {len(top_players)} players..."
            ):
                recent_list = []
                for p_id in top_players["id"]:
                    stats = get_player_recent_match_stats(
                        p_id, selected_season, last_n_games=n_games
                    )
                    recent_list.append(stats)

                recent_df = pd.DataFrame(recent_list)
                combined_df = pd.concat(
                    [top_players.reset_index(drop=True), recent_df], axis=1
                )

                # Calculated rolling averages
                combined_df["Shots/G (Recent)"] = (
                    combined_df["recent_shots"]
                    / combined_df["recent_m"].replace(0, 1)
                ).round(2)
                combined_df["xG/G (Recent)"] = (
                    combined_df["recent_xg"]
                    / combined_df["recent_m"].replace(0, 1)
                ).round(2)

                # Main Display Columns: Full Season side-by-side with Rolling Window
                display_columns = [
                    "player_name",
                    "team_title",
                    "position",
                    "games",  # Season Games
                    "shots",  # Season Shots
                    "xG",  # Season xG
                    "key_passes",  # Season Key Passes
                    "xA",  # Season xA
                    "recent_m",  # Last N Games Played
                    "recent_shots",  # Shots in Last N
                    "Shots/G (Recent)",  # Shots/Game in Last N
                    "recent_xg",  # xG in Last N
                    "recent_goals",  # Goals in Last N
                    "recent_key_passes",  # Key Passes in Last N
                ]

                column_names = {
                    "player_name": "Player",
                    "team_title": "Team",
                    "position": "Pos",
                    "games": "Season Apps",
                    "shots": "Season Shots",
                    "xG": "Season xG",
                    "key_passes": "Season KP",
                    "xA": "Season xA",
                    "recent_m": f"Apps (L{n_games})",
                    "recent_shots": f"Shots (L{n_games})",
                    "Shots/G (Recent)": f"Shots/G (L{n_games})",
                    "recent_xg": f"xG (L{n_games})",
                    "recent_goals": f"Goals (L{n_games})",
                    "recent_key_passes": f"KP (L{n_games})",
                }

                st.write(
                    f"### Leaderboard: Full Season vs. Recent Form (Last"
                    f" {n_games} Games)"
                )
                st.dataframe(
                    combined_df[display_columns].rename(columns=column_names),
                    use_container_width=True,
                )
    else:
        st.info("Load data or select a valid league to view leaderboard.")


# ==========================================
# TAB 2: OTHER ANALYTICS / PLACEHOLDER
# ==========================================
with tab2:
    st.subheader("Team & Additional Analytics")
    st.write(
        "Additional charts, shot maps, or team statistics can be placed here."
    )
