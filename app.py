from datetime import datetime
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from team_colors import get_team_colors

st.title("Belgian Pro League xG Flowcharts")

# GET TEAM DATA
@st.cache_data
def get_team_data():
    competition_url = "https://fbref.com/en/comps/37/Belgian-Pro-League-Stats"
    response = requests.get(competition_url)
    soup = BeautifulSoup(response.text, 'html.parser')

    table = soup.find('table', {'id': 'results2024-2025371_overall'})
    teams_data = []
    for row in table.find("tbody").find_all("tr"):
        team_cell = row.find("td", {"data-stat": "team"})
        team_name = team_cell.text.strip()
        if team_name:
            team_url = team_cell.find("a")["href"]
            teams_data.append({
                "team_name": team_name, 
                "team_url": f"https://fbref.com/{team_url}", 
            })

    teams_df = pd.DataFrame(teams_data)
    return teams_df

teams_df = get_team_data()
selected_team = st.selectbox(
    "Select a team", 
    sorted(teams_df["team_name"].tolist()),
    index=None
)

# GET MATCHES DATA FOR SELECTED TEAM
@st.cache_data
def get_matches_data(team_url, today):
    response = requests.get(team_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', {'id': 'matchlogs_for'})
    matches_data = []

    for row in table.find("tbody").find_all("tr"):
        # Get match date
        date_element = row.find("th", {"data-stat": "date"})
        match_date_str = date_element.get("csk")
        match_date = datetime.strptime(match_date_str, '%Y%m%d').date().strftime('%Y-%m-%d')
        parsed_date = datetime.strptime(match_date, '%Y-%m-%d').date()

        # Get competition
        competition_element = row.find("td", {"data-stat": "comp"})
        competition = competition_element.text.strip()

        # Only add matches from the Pro League that have been played
        if (parsed_date < today and competition == "Pro League A"):
            # Get match opponent
            match_opponent = row.find("td", {"data-stat": "opponent"}).text.strip()

            # Get venue
            match_venue_str = row.find("td", {"data-stat": "venue"}).text.strip()
            match_venue = "(H)" if "Home" in match_venue_str else "(A)"

            # Get goals
            goals_for = row.find("td", {"data-stat": "goals_for"}).text.strip()
            goals_against = row.find("td", {"data-stat": "goals_against"}).text.strip()
            score = f"{goals_for} - {goals_against}" if match_venue == "(H)" else f"{goals_against} - {goals_for}"

            # Get link to match report
            match_report_link_href = row.find("td", {"data-stat": "match_report"}).find("a")["href"]
            match_report_link = f"https://fbref.com{match_report_link_href}"

            # Set label for selectbox
            match_label = f"{match_date} {match_opponent} {match_venue} {score}"

            matches_data.append({
                "match_date": match_date,
                "match_opponent": match_opponent,
                "match_venue": match_venue,
                "score": score,
                "match_label": match_label,
                "match_report_link": match_report_link
            })

    matches_df = pd.DataFrame(matches_data)
    return matches_df

if selected_team:
    today = datetime.now().date()
    team_url = teams_df.loc[teams_df["team_name"] == selected_team]["team_url"].values[0]
    matches_df = get_matches_data(team_url, today)
    
    selected_match = st.selectbox(
        "Select a match", 
        matches_df['match_label'].tolist(),
        index=None
    )

if selected_team and selected_match:
    match_data = matches_df.loc[matches_df["match_label"] == selected_match].iloc[0]
    match_report_link = match_data["match_report_link"]
    response = requests.get(match_report_link)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Get team info
    home_team = selected_team if match_data["match_venue"] == "(H)" else match_data["match_opponent"]
    away_team = selected_team if match_data["match_venue"] == "(A)" else match_data["match_opponent"]

    # GET SHOTS DATA
    all_shots_df = pd.read_html(match_report_link, attrs={"id": "shots_all"}, header=1)[0]
    # Filter out spacer rows
    shots_df = all_shots_df.loc[all_shots_df["Minute"].notna(), ["Minute", "Player", "Squad", "xG", "Outcome"]].reset_index(drop=True)
    # Rename columns for consistency
    shots_df.columns = ["event_minute", "player_name", "team_name", "xg", "outcome"]
    # Handle extra time shots
    shots_df["event_minute"] = shots_df["event_minute"].apply(lambda x: int(float(x.split("+")[0]) if "+" in str(x) else int(float(x))))

    def create_team_shots_df(shots_df, team_name):
        # Filter for team, sort by minute and reset index
        df = shots_df.loc[shots_df["team_name"] == team_name].sort_values(by="event_minute").reset_index(drop=True)
        # Add a column for the cumulative xG
        df["cumulative_xg"] = df["xg"].cumsum()
        # Add start and end records to fill in the gaps in the chart
        start_record = pd.DataFrame({
            "event_minute": [0], 
            "player_name": [None], 
            "team_name": [team_name], 
            "xg": [0], 
            "outcome": [None], 
            "cumulative_xg": [0]
        })
        end_record = pd.DataFrame({
            "event_minute": [90], 
            "player_name": [None], 
            "team_name": [team_name], 
            "xg": [0], 
            "outcome": [None], 
            "cumulative_xg": [df["cumulative_xg"].max()]
        })
        return pd.concat([start_record, df, end_record], ignore_index=True)

    # Create dataframes for home and away teams
    home_shots_df = create_team_shots_df(shots_df, home_team)
    away_shots_df = create_team_shots_df(shots_df, away_team)

    # GET SUMMARY EVENTS
    events_wrap_div = soup.find("div", {"id": "events_wrap"})
    events_list = []
    summary_events = events_wrap_div.find_all("div", {"class": "event"})
    for event in summary_events:
        # init event type
        event_type = None
        # check for goal
        if "goal" in event.text.lower():
            event_type = "Goal"
        # check for own goal
        if "own goal" in event.text.lower():
            event_type = "Own goal"
        # check for penalty goal
        if "penalty kick" in event.text.lower():
            event_type = "Goal"
        # check for red card
        if "red card" in event.text.lower() or "second yellow card" in event.text.lower():
            event_type = "Red card"

        if event_type:
            event_minute = int(event.find("div").text.strip().split("’")[0].split("+")[0])
            player_name = event.find("a").text.strip()
            team = home_team if event.get("class")[1] == "a" else away_team
            shots_df = home_shots_df if team == home_team else away_shots_df
            cumulative_xg = shots_df.loc[shots_df["event_minute"] <= int(event_minute), "cumulative_xg"].max()

            events_list.append({
                "event_minute": event_minute,
                "event_type": event_type,
                "player_name": player_name,
                "team_name": team,
                "cumulative_xg": cumulative_xg
            })

    events_df = pd.DataFrame(events_list)

    # CREATE FLOWCHART
    background_color = "#f2f4ee"
    black_color = "#0a0c08"
    grey_color = "#7D7C84"

    # init flowchart
    fig, ax = plt.subplots(figsize = (10, 5))
    fig.set_facecolor(background_color)
    ax.set_facecolor(background_color)
    plt.rcParams['font.family'] = 'Gill Sans'
    plt.rcParams.update({
        'text.color': black_color,
        'axes.labelcolor': grey_color,
        'axes.edgecolor': grey_color,
        'xtick.color': grey_color,
        'ytick.color': grey_color,
        'grid.color': grey_color,
    })

    # team colors
    team_colors_df = get_team_colors()
    home_color = team_colors_df.loc[team_colors_df["team_name"] == home_team, "team_color"].iloc[0]
    away_color = team_colors_df.loc[team_colors_df["team_name"] == away_team, "team_color"].iloc[0]

    # plt customizations
    plt.xticks([0, 15, 30, 45, 60, 75, 90])
    plt.xlabel("Minute")
    plt.ylabel("Cumulative xG")
    plt.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # display the team names and score
    ax.text(0.35, 1.15, home_team, color=home_color, fontsize=16, ha='right', transform=ax.transAxes)
    ax.text(0.5, 1.15, match_data["score"], fontsize=16, ha='center', transform=ax.transAxes)
    ax.text(0.65, 1.15, away_team, color=away_color, fontsize=16, ha='left', transform=ax.transAxes)

    # game information
    ax.text(0.5, 1.10, datetime.strptime(match_data["match_date"], '%Y-%m-%d').strftime("%d-%m-%Y"), alpha=0.6, fontsize=9, ha="center", transform=ax.transAxes)
    ax.text(0.5, 1.06, "Jupiler Pro League", alpha=0.6, fontsize=9, ha="center", transform=ax.transAxes)

    # logo's
    home_logo = mpimg.imread(f"static/logo-{home_team.lower().replace(' ', '-')}.png")
    home_imagebox = OffsetImage(home_logo, zoom=0.45)
    home_ab = AnnotationBbox(home_imagebox, (0.05, 1.15), xycoords='axes fraction', frameon=False)
    ax.add_artist(home_ab)
    away_logo = mpimg.imread(f"static/logo-{away_team.lower().replace(' ', '-')}.png")
    away_imagebox = OffsetImage(away_logo, zoom=0.45)
    away_ab = AnnotationBbox(away_imagebox, (0.95, 1.15), xycoords='axes fraction', frameon=False)
    ax.add_artist(away_ab)

    # xG for teams
    home_total_xg = home_shots_df["cumulative_xg"].max()
    away_total_xg = away_shots_df["cumulative_xg"].max()
    ax.text(0.35, 1.10, f"{home_total_xg:.2f} xG", color=home_color, alpha=0.6, fontsize=9, ha='right', transform=ax.transAxes)
    ax.text(0.65, 1.10, f"{away_total_xg:.2f} xG", color=away_color, alpha=0.6, fontsize=9, ha='left', transform=ax.transAxes)

    # xG steps
    ax.step(x = home_shots_df["event_minute"], y = home_shots_df["cumulative_xg"], where="post", color=home_color)
    ax.step(x = away_shots_df["event_minute"], y = away_shots_df["cumulative_xg"], where="post", color=away_color)

    # add event markers
    def add_event_markers(df, team_name, team_color):
        team_events_df = df.loc[df["team_name"] == team_name]
        for _, row in team_events_df.iterrows():
            # goals
            if row["event_type"] == "Goal" or row["event_type"] == "Own goal":
                # mark goal on xG chart
                ax.scatter(x = row["event_minute"], y = row["cumulative_xg"], color = team_color, marker = "o")
                # annotate goal
                alpha_value = 1 if row["event_type"] == "Goal" else 0.5
                text = row["player_name"]
                if row["event_type"] == "Own goal":
                    text += " (OG)"
                ax.annotate(text, (row["event_minute"], row["cumulative_xg"]), color=team_color, alpha=alpha_value, fontsize=8, ha="right", xytext=(-5, 7.5), textcoords="offset points")
            # red cards
            if row["event_type"] == "Red card":
                ax.axvline(x = row["event_minute"], color = "red", linestyle = "--", linewidth = 1.1, alpha = 0.2)
                ax.text(
                    x=row["event_minute"] + 1, y= 0.63,
                    s=row["player_name"],
                    color="red",
                    fontsize=9,
                    ha='left',
                    alpha= 0.5
                )

    if not events_df.empty:
        add_event_markers(events_df, home_team, home_color)
        add_event_markers(events_df, away_team, away_color)
    # show plot
    st.pyplot(fig)
