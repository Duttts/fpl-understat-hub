import json
import urllib.parse
from bs4 import BeautifulSoup
import pandas as pd
import requests
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
selected_season = st.sidebar.selectbox(
    "Select Season Year", ["2025", "2024", "2023"], index=0
)


# --- 3. LOAD UNDERSTAT DATA (PLAYERS & TEAMS) ---
@st.cache_data(ttl=3600)
def load_understat_data(season_year="2025"):
  url = f"https://understat.com/league/EPL/{season_year}"
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
      st.error(
          f"Failed to connect to Understat (Status code:"
          f" {response.status_code})"
      )
      return None

    soup = BeautifulSoup(response.text, "html.parser")
    data_payload = {}

    for script in soup.find_all("script"):
      if script.string:
        for key in ["playersData", "teamsData"]:
          if key in script.string:
            try:
              start_idx = script.string.index("('") + 2
              end_idx = script.string.rindex("')")
              encoded_data = script.string[start_idx:end_idx]
              decoded_json = urllib.parse.unquote(encoded_data)
              data_payload[key] = json.loads(decoded_json)
            except Exception:
              continue

    return data_payload
  except Exception as e:
    st.error(f"Error fetching data: {e}")
    return None


with st.spinner("Fetching advanced underlying metrics from Understat..."):
  data = load_understat_data(selected_season)

if not data or "playersData" not in data or not data["playersData"]:
  st.warning(
      "No data returned yet for this season selection. Once the first matches"
      " have concluded and Understat populates the feed, metrics will appear"
      " here."
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

    # Sidebar Filters (Only active/visible when on Tab 1 or globally applied)
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
      # Understat teamsData is a dict where keys are team IDs, values contain history/stats
      teams_list = []
      for team_id, team_info in data["teamsData"].items():
        team_name = team_info.get("title")
        # Understat stores match history inside a 'history' list for each team
        history = team_info.get("history", [])

        # Aggregate cumulative stats from match history
        matches_played = len(history)
        x_g_against = sum(match.get("xGA", 0) for match in history)
        goals_against = sum(match.get("a", 0) for match in history)
        shots_against = sum(match.get("shots", {}).get("against", 0) for match in history)
        
        teams_list.append({
            "Team": team_name,
            "Matches": matches_played,
            "Goals Conceded": goals_against,
            "xGA (Expected Conceded)": round(x_g_against, 2),
        })

      df_teams_summary = pd.DataFrame(teams_list)
      if not df_teams_summary.empty:
        df_teams_summary = df_teams_summary.sort_values(
            by="xGA (Expected Conceded)", ascending=False
        ).reset_index(drop=True)
        st.dataframe(df_teams_summary, use_container_width=True)
      else:
        st.info("Team match statistics are still compiling for this season.")
    else:
      st.info("Team data block not found yet.")
