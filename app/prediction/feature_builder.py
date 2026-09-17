from app.models import FeatureVector, FormSnapshot


class FeatureBuilder:

    MAX_GOALS_PER_GAME = 3.0
    MAX_POINTS_PER_GAME = 3.0

    def build(
        self,
        snapshot: FormSnapshot,
    ) -> FeatureVector:

        if snapshot.games == 0:

            return FeatureVector(

                team_id=snapshot.team_id,

                form=0.0,
                attack=0.0,
                defense=0.0,
                momentum=0.0,

                home_strength=0.0,
                away_strength=0.0,

                win_rate=0.0,
                points_per_game=0.0,

                goals_for=0.0,
                goals_against=0.0,
                goal_difference=0.0,

                league_position=0.0,

                rest_days=0.0,

                clean_sheet_rate=0.0,
                failed_to_score_rate=0.0,

                home_points_per_game=0.0,
                away_points_per_game=0.0,

                recent_goal_difference=0.0,
                recent_points_per_game=0.0,
            )

        goals_for_pg = snapshot.goals_for / snapshot.games
        goals_against_pg = snapshot.goals_against / snapshot.games
        points_pg = snapshot.points / snapshot.games

        goal_difference = goals_for_pg - goals_against_pg

        clean_sheet_rate = (
            snapshot.clean_sheets / snapshot.games
            if snapshot.games
            else 0.0
        )

        failed_to_score_rate = (
            snapshot.failed_to_score / snapshot.games
            if snapshot.games
            else 0.0
        )

        home_strength = (
            snapshot.home_wins / snapshot.home_games
            if snapshot.home_games
            else 0.0
        )

        away_strength = (
            snapshot.away_wins / snapshot.away_games
            if snapshot.away_games
            else 0.0
        )

        home_ppg = (
            (
                snapshot.home_wins * 3
                + snapshot.home_draws
            )
            / snapshot.home_games
            if snapshot.home_games
            else 0.0
        )

        away_ppg = (
            (
                snapshot.away_wins * 3
                + snapshot.away_draws
            )
            / snapshot.away_games
            if snapshot.away_games
            else 0.0
        )

        return FeatureVector(

            team_id=snapshot.team_id,

            form=snapshot.win_rate,

            attack=min(
                goals_for_pg / self.MAX_GOALS_PER_GAME,
                1.0,
            ),

            defense=max(
                0.0,
                1.0 - (
                    goals_against_pg
                    / self.MAX_GOALS_PER_GAME
                ),
            ),

            momentum=min(
                snapshot.momentum / 5.0,
                1.0,
            ),

            home_strength=home_strength,

            away_strength=away_strength,

            win_rate=snapshot.win_rate,

            points_per_game=min(
                points_pg / self.MAX_POINTS_PER_GAME,
                1.0,
            ),

            goals_for=goals_for_pg,

            goals_against=goals_against_pg,

            goal_difference=max(
                min(goal_difference / 3.0, 1.0),
                -1.0,
            ),

            league_position=0.0,

            # Rest Days vēl nav implementēts
            rest_days=0.0,

            clean_sheet_rate=clean_sheet_rate,

            failed_to_score_rate=failed_to_score_rate,

            home_points_per_game=min(
                home_ppg / self.MAX_POINTS_PER_GAME,
                1.0,
            ),

            away_points_per_game=min(
                away_ppg / self.MAX_POINTS_PER_GAME,
                1.0,
            ),

            recent_goal_difference=max(
                min(goal_difference / 3.0, 1.0),
                -1.0,
            ),

            recent_points_per_game=min(
                points_pg / self.MAX_POINTS_PER_GAME,
                1.0,
            ),
        )