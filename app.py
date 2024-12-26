import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

st.title("Belgian Pro League xG Flowcharts")

# GET TEAM LIST
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
        team_logo = team_cell.find("img")["src"]
        teams_data.append({
            "team_name": team_name, 
            "team_url": f"https://fbref.com/{team_url}", 
            "team_logo": team_logo
        })

teams_df = pd.DataFrame(teams_data)

selected_team = st.selectbox(
    "Select a team", 
    sorted(teams_df["team_name"].tolist()),
    index=None
)

if selected_team:
    team_url = teams_df.loc[teams_df["team_name"] == selected_team]["team_url"].values[0]
    st.write(team_url)