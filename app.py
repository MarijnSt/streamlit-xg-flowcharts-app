import matplotlib.colors
from datetime import datetime
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from team_colors import get_team_colors
from matplotlib import font_manager

# PAGE CONFIG
st.set_page_config(
    page_title="Belgian Pro League xG",
    page_icon="⚽️",
)

# CONSTANTS
FBREF_BASE_URL = "https://fbref.com"
COMPETITION_URL = "https://fbref.com/en/comps/37/Belgian-Pro-League-Stats"
VIZ_BACKGROUND_COLOR = "#f2f4ee"
VIZ_BLACK_COLOR = "#0a0c08"
VIZ_GREY_COLOR = "#7D7C84"

# CACHED FUNCTIONS
@st.cache_data
def get_teams_df():
    response = requests.get(COMPETITION_URL)
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
                "team_url": f"{FBREF_BASE_URL}/{team_url}", 
            })

    teams_df = pd.DataFrame(teams_data)
    return teams_df

@st.cache_data
def get_matches_df(team_url, today):
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

            # Get xG for and against
            xg_for = row.find("td", {"data-stat": "xg_for"}).text.strip()
            xg_against = row.find("td", {"data-stat": "xg_against"}).text.strip()

            # Get link to match report
            match_report_link_href = row.find("td", {"data-stat": "match_report"}).find("a")["href"]
            match_report_link = f"{FBREF_BASE_URL}{match_report_link_href}"

            # Set label for selectbox
            match_label = f"{match_date} {match_opponent} {match_venue} {score}"

            matches_data.append({
                "match_date": match_date,
                "match_opponent": match_opponent,
                "match_venue": match_venue,
                "score": score,
                "xg_for": float(xg_for) if xg_for else None,
                "xg_against": float(xg_against) if xg_against else None,
                "match_label": match_label,
                "match_report_link": match_report_link
            })

    matches_df = pd.DataFrame(matches_data)
    return matches_df

@st.cache_data
def get_shots_df(match_report_link):
    all_shots_df = pd.read_html(match_report_link, attrs={"id": "shots_all"}, header=1)[0]
    # Filter out spacer rows
    shots_df = all_shots_df.loc[all_shots_df["Minute"].notna(), ["Minute", "Player", "Squad", "xG", "Outcome"]].reset_index(drop=True)
    # Rename columns for consistency
    shots_df.columns = ["event_minute", "player_name", "team_name", "xg", "outcome"]
    # Handle extra time shots
    shots_df["event_minute"] = shots_df["event_minute"].apply(lambda x: int(float(x.split("+")[0]) if "+" in str(x) else int(float(x))))
    return shots_df

@st.cache_data
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

@st.cache_data
def get_events_df(match_report_link, home_team, away_team):
    response = requests.get(match_report_link)
    soup = BeautifulSoup(response.text, 'html.parser')
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

    return pd.DataFrame(events_list)

@st.cache_data
def init_visualisation():
    fig, ax = plt.subplots(figsize = (10, 5))
    fig.set_facecolor(VIZ_BACKGROUND_COLOR)
    ax.set_facecolor(VIZ_BACKGROUND_COLOR)
    font_manager.fontManager.addfont('static/GillSans.ttf')
    prop = font_manager.FontProperties(fname='static/GillSans.ttf')
    plt.rcParams['font.family'] = prop.get_name()
    plt.rcParams.update({
        'text.color': VIZ_BLACK_COLOR,
        'axes.labelcolor': matplotlib.colors.to_rgba(VIZ_GREY_COLOR, alpha=0.3),
        'axes.edgecolor': VIZ_GREY_COLOR,
        'xtick.color': VIZ_GREY_COLOR,
        'ytick.color': VIZ_GREY_COLOR,
        'grid.color': VIZ_GREY_COLOR,
    })
    plt.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_alpha(0.3)
    ax.spines['bottom'].set_alpha(0.3)
    ax.tick_params(axis='y', colors=matplotlib.colors.to_rgba(VIZ_GREY_COLOR, alpha=0.3))
    ax.tick_params(axis='x', colors=matplotlib.colors.to_rgba(VIZ_GREY_COLOR, alpha=0.3))
    return fig, ax

@st.cache_data
def create_trendline(home_team, match_data):
    fig, ax = init_visualisation()

    # plt customizations
    plt.xticks([])
    ax.spines['bottom'].set_visible(False)

    # team colors
    team_colors_df = get_team_colors()
    team_color = team_colors_df.loc[team_colors_df["team_name"] == home_team, "team_color"].iloc[0]
    against_color = matplotlib.colors.to_rgba(team_color, alpha=0.25)

    # add logo
    home_logo = mpimg.imread(f"static/logo-{home_team.lower().replace(' ', '-')}.png")
    home_imagebox = OffsetImage(home_logo, zoom=0.45)
    home_ab = AnnotationBbox(home_imagebox, (0.95, 1.15), xycoords='axes fraction', frameon=False)
    ax.add_artist(home_ab)

    # add title
    title = f"{home_team} xG Trendline"
    subtitle = "Jupiler Pro League 2024-2025"
    ax.text(0.5, 1.15, title, color=team_color, fontsize=16, ha='center', transform=ax.transAxes)
    ax.text(0.5, 1.10, subtitle, color=team_color, fontsize=12, ha='center', transform=ax.transAxes)

    # plot trendline
    plt.plot(match_data["xg_for"], label="xG for", color=team_color)
    plt.plot(match_data["xg_against"], label="xG against", color=against_color, alpha=0.2)

    # scatter xG values for and against for each game
    plt.scatter(y=match_data["xg_for"], x=match_data.index, label="xG for", s=20, facecolors=VIZ_BACKGROUND_COLOR, edgecolors=team_color, zorder=10)
    plt.scatter(y=match_data["xg_against"], x=match_data.index, label="xG against", s=20, facecolors=VIZ_BACKGROUND_COLOR, edgecolors=against_color, zorder=10)

    # Add opponent logos on x-axis with debug print
    #plt.subplots_adjust(bottom=0.2)  # Move this up before adding logos
    for idx, opponent in enumerate(match_data["match_opponent"]):
        try:
            logo_path = f"static/logo-{opponent.lower().replace(' ', '-')}.png"
            opponent_logo = mpimg.imread(logo_path)
            opponent_imagebox = OffsetImage(opponent_logo, zoom=0.15, alpha=0.5)
            opponent_ab = AnnotationBbox(opponent_imagebox, (idx, -0.05), 
                                       xycoords=('data', 'axes fraction'),
                                       frameon=False)
            ax.add_artist(opponent_ab)
        except Exception as e:
            print(f"Error loading logo for {opponent}: {str(e)}")  # Debug print

    # add text under x-axis
    # plt.text(0.45, -0.1, "xG for", color=team_color, fontsize=12, ha='center', transform=ax.transAxes)
    # plt.text(0.55, -0.1, "xG against", color=against_color, fontsize=12, ha='center', transform=ax.transAxes)
    return fig

@st.cache_data
def create_match_visualisation(home_team, away_team, match_data, home_shots_df, away_shots_df, events_df):
    fig, ax = init_visualisation()

    # plt customizations
    plt.xticks([0, 15, 30, 45, 60, 75, 90])
    plt.xlabel("Minute")
    plt.ylabel("Cumulative xG")

    # team colors
    team_colors_df = get_team_colors()
    home_color = team_colors_df.loc[team_colors_df["team_name"] == home_team, "team_color"].iloc[0]
    away_color = team_colors_df.loc[team_colors_df["team_name"] == away_team, "team_color"].iloc[0]

    # plot team names and score
    ax.text(0.35, 1.15, home_team, color=home_color, fontsize=16, ha='right', transform=ax.transAxes)
    ax.text(0.5, 1.15, match_data["score"], fontsize=16, ha='center', transform=ax.transAxes)
    ax.text(0.65, 1.15, away_team, color=away_color, fontsize=16, ha='left', transform=ax.transAxes)

    # plot game information
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

    # plot xG for teams
    home_total_xg = home_shots_df["cumulative_xg"].max()
    away_total_xg = away_shots_df["cumulative_xg"].max()
    ax.text(0.35, 1.10, f"{home_total_xg:.2f} xG", color=home_color, alpha=0.6, fontsize=9, ha='right', transform=ax.transAxes)
    ax.text(0.65, 1.10, f"{away_total_xg:.2f} xG", color=away_color, alpha=0.6, fontsize=9, ha='left', transform=ax.transAxes)

    # xG steps
    ax.step(x = home_shots_df["event_minute"], y = home_shots_df["cumulative_xg"], where="post", color=home_color)
    ax.step(x = away_shots_df["event_minute"], y = away_shots_df["cumulative_xg"], where="post", color=away_color)

    # plot event markers
    def add_event_markers(df, team_name, team_color):
        team_events_df = df.loc[df["team_name"] == team_name]
        for _, row in team_events_df.iterrows():
            # set variables
            match row["event_type"]:
                case "Goal":
                    color = team_color
                    text = row["player_name"]
                    marker = "o"
                case "Own goal":
                    color = team_color
                    text = row["player_name"] + " (OG)"
                    marker = "o"
                case "Red card":
                    color = "red"
                    text = row["player_name"]
                    marker = "x"

            # add event marker
            ax.scatter(
                x = row["event_minute"],
                y = row["cumulative_xg"],
                color = color,
                marker = marker,
                alpha = 0.5
            )

            # annotate event
            ax.annotate(
                text = text,
                xy = (row["event_minute"], row["cumulative_xg"]),
                color = color,
                alpha = 1,
                fontsize = 8,
                ha = "right",
                xytext = (-5, 7.5),
                textcoords = "offset points"
            )

    if not events_df.empty:
        add_event_markers(events_df, home_team, home_color)
        add_event_markers(events_df, away_team, away_color)

    return fig

# STREAMLIT APP
st.title("Belgian Pro League xG")

teams_df = get_teams_df()
selected_team = st.selectbox(
    "Select a team", 
    sorted(teams_df["team_name"].tolist()),
    index=None
)

if selected_team:
    today = datetime.now().date()
    team_url = teams_df.loc[teams_df["team_name"] == selected_team]["team_url"].values[0]
    matches_df = get_matches_df(team_url, today)

    # plot trendline
    fig = create_trendline(selected_team, matches_df)
    st.pyplot(fig)
    
    selected_match = st.selectbox(
        "Select a match", 
        matches_df['match_label'].tolist(),
        index=None
    )

if selected_team and selected_match:
    match_data = matches_df.loc[matches_df["match_label"] == selected_match].iloc[0]
    match_report_link = match_data["match_report_link"]

    # Get team names
    home_team = selected_team if match_data["match_venue"] == "(H)" else match_data["match_opponent"]
    away_team = selected_team if match_data["match_venue"] == "(A)" else match_data["match_opponent"]

    # Get shots dataframe
    shots_df = get_shots_df(match_report_link)

    # Create dataframes for home and away teams xg steps on flowchart
    home_shots_df = create_team_shots_df(shots_df, home_team)
    away_shots_df = create_team_shots_df(shots_df, away_team)

    # Create events dataframe for event markers on flowchart
    events_df = get_events_df(match_report_link, home_team, away_team)

    # Create visualisation
    fig = create_match_visualisation(home_team, away_team, match_data, home_shots_df, away_shots_df, events_df)

    # Show plot
    st.pyplot(fig)