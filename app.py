from datetime import datetime
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

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
        match_date = datetime.strptime(match_date_str, '%Y%m%d').date()
        
        # Get competition
        competition_element = row.find("td", {"data-stat": "comp"})
        competition = competition_element.text.strip()

        # Only add matches from the Pro League that have been played
        if (match_date < today and competition == "Pro League A"):
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
    st.write(selected_team)
    st.write(match_data)
    st.write(match_report_link)

    # GET SUMMARY DATA
    events_wrap_div = soup.find("div", {"id": "events_wrap"})
    #st.write(events_wrap_div)
    # Get team logos
    team_logos = events_wrap_div.find("div").find("div").find_all("img")
    home_logo = team_logos[0]["src"]
    away_logo = team_logos[1]["src"]
    st.write(home_logo)
    st.write(away_logo)

    # Get events
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
            event_minute = event.find("div").text.strip().split("’")[0].split("+")[0]
            player_name = event.find("a").text.strip()
            team = "Home" if event.get("class")[1] == "a" else "Away"
            events_list.append({
                "event_minute": event_minute,
                "event_type": event_type,
                "player_name": player_name,
                "team": team
            })

    events_df = pd.DataFrame(events_list)
    st.write(events_df)

    # GET SHOTS DATA