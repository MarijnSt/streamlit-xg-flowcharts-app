import pandas as pd

def get_team_colors():
    team_colors_data = {
        'team_name': [
            'Anderlecht', 'Antwerp', 'Beerschot', 'Cercle Brugge', 'Charleroi', 'Club Brugge', 'Dender', 
            'Genk', 'Gent', 'Kortrijk', 'Mechelen', 'OH Leuven', 'Sint-Truiden', 'Standard Liège', 
            'Union SG', 'Westerlo'
        ],
        'team_color': [
            '#4c2484', '#d3072a', '#714394', '#60B22C', '#000000', '#008dcc', '#27579b', 
            '#04407E', '#004794', '#CA2027', '#E41B13', '#36bd00', '#ffd13a', '#e31f13', 
            '#fdd516', '#198fd9'
        ]
    }
    return pd.DataFrame(team_colors_data)