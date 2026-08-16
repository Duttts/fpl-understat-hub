import pandas as pd
import streamlit as st
from understatapi import UnderstatClient

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Understat Advanced Metrics Hub", page_icon="📊", layout="wide"
)

st.title("📊 Understat Advanced Player & Shot Hub")
st.markdown(
    "A stripped-back companion dashboard pulling underlying metrics (xG, xA,"
    " shots, and key passes) directly from Understat."
)


# --- 2. LOAD UNDERSTAT DATA ---
@st.cache_data(ttl=3600)
def load_understat_players(season_year="2025"):
  try:
    with UnderstatClient() as understat:
      # Fetch EPL player data for the given season
      player_data = understat.league(league="EPL").get_player_data(
          season=season_year
      )
      if player_data:
        df = pd.DataFrame(player_data)
        return df
  except Exception as e:
    st.error(
        f"Failed to fetch data from Understat: {e}. Make sure 'understatapi'"
        " is installed (`pip install understatapi`)."
    )
    return pd.DataFrame()
  return pd.DataFrame()


with st.spinner("Fetching advanced underlying metrics from Understat..."):
  # Using 2025/2026 season (adjust season string as needed)
  df_understat = load_understat_players("2025")

if df_understat.empty:
  st.warning(
      "No data returned. If the season hasn't populated yet, try changing the"
      " season year in the code."
  )
else:
  # Convert numeric columns from string to proper floats/ints
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
    if col in df_understat.columns:
      df_understat[col] = pd.to_numeric(df_understat[col], errors="coerce").fillna(
          0
      )

  # --- 3. SIDEBAR THRESHOLD FILTERS ---
  st.sidebar.header("🔍 Advanced Filters")
  st.sidebar.markdown(
      "Enter minimum thresholds. Players matching or exceeding these numbers"
      " will appear."
  )

  # Team filter
  teams = ["All"] + sorted(df_understat["team_title"].unique().tolist())
  selected_team = st.sidebar.selectbox("Filter by Team", teams)

  # Position filter
  positions = ["All"] + sorted(df_understat["position"].unique().tolist())
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

  # --- 4. APPLY FILTERS ---
  filtered_df = df_understat.copy()

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

  # Clean up column layout for display
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

  # Sort by xG descending by default
  filtered_df = filtered_df.sort_values(by="xG", ascending=False).reset_index(
      drop=True
  )

  # --- 5. RENDER RESULTS ---
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
