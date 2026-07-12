class H2HAnalyzer:

    def analyze(
        self,
        home_team_id: int,
        away_team_id: int,
        fixtures: list,
    ) -> float:

        if not fixtures:
            return 0.5

        home_points = 0

        for fixture in fixtures:

            home = fixture["teams"]["home"]["id"]

            home_goals = fixture["goals"]["home"] or 0
            away_goals = fixture["goals"]["away"] or 0

            if home == home_team_id:

                team_goals = home_goals
                opponent_goals = away_goals

            else:

                team_goals = away_goals
                opponent_goals = home_goals

            if team_goals > opponent_goals:
                home_points += 3

            elif team_goals == opponent_goals:
                home_points += 1

        return round(
            home_points / (len(fixtures) * 3),
            3,
        )