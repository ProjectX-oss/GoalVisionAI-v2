from app.models import FormSnapshot


class FormAnalyzer:

    def analyze(
        self,
        team_id: int,
        fixtures: list,
    ) -> FormSnapshot:

        wins = 0
        draws = 0
        losses = 0

        goals_for = 0
        goals_against = 0

        home_games = 0
        away_games = 0

        home_wins = 0
        home_draws = 0
        home_losses = 0

        away_wins = 0
        away_draws = 0
        away_losses = 0

        clean_sheets = 0
        failed_to_score = 0

        points = 0
        momentum_points = 0

        games = len(fixtures)

        for index, fixture in enumerate(
            reversed(fixtures),
            start=1,
        ):

            home_team = fixture["teams"]["home"]["id"]
            away_team = fixture["teams"]["away"]["id"]

            home_goals = fixture["goals"]["home"] or 0
            away_goals = fixture["goals"]["away"] or 0

            if team_id == home_team:

                gf = home_goals
                ga = away_goals

                is_home = True

                home_games += 1

            else:

                gf = away_goals
                ga = home_goals

                is_home = False

                away_games += 1

            goals_for += gf
            goals_against += ga

            if ga == 0:
                clean_sheets += 1

            if gf == 0:
                failed_to_score += 1

            if gf > ga:

                wins += 1
                points += 3
                momentum_points += index * 3

                if is_home:
                    home_wins += 1
                else:
                    away_wins += 1

            elif gf == ga:

                draws += 1
                points += 1
                momentum_points += index

                if is_home:
                    home_draws += 1
                else:
                    away_draws += 1

            else:

                losses += 1

                if is_home:
                    home_losses += 1
                else:
                    away_losses += 1

        if games == 0:

            return FormSnapshot(

                team_id=team_id,

                games=0,

                wins=0,
                draws=0,
                losses=0,

                goals_for=0,
                goals_against=0,

                goal_difference=0,

                home_games=0,
                away_games=0,

                home_wins=0,
                home_draws=0,
                home_losses=0,

                away_wins=0,
                away_draws=0,
                away_losses=0,

                clean_sheets=0,
                failed_to_score=0,

                points=0,

                attack=0.0,
                defense=0.0,
                win_rate=0.0,
                momentum=0.0,
            )

        return FormSnapshot(

            team_id=team_id,

            games=games,

            wins=wins,
            draws=draws,
            losses=losses,

            goals_for=goals_for,
            goals_against=goals_against,

            goal_difference=goals_for - goals_against,

            home_games=home_games,
            away_games=away_games,

            home_wins=home_wins,
            home_draws=home_draws,
            home_losses=home_losses,

            away_wins=away_wins,
            away_draws=away_draws,
            away_losses=away_losses,

            clean_sheets=clean_sheets,
            failed_to_score=failed_to_score,

            points=points,

            attack=goals_for / games,

            defense=goals_against / games,

            win_rate=wins / games,

            momentum=round(
                momentum_points / (games * 3),
                2,
            ),
        )