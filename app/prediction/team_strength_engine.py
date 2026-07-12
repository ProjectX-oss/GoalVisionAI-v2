from app.models import FeatureVector, TeamStrength


class TeamStrengthEngine:

    def calculate(
        self,
        features: FeatureVector,
    ) -> TeamStrength:

        return TeamStrength(

            # Core
            attack=round(
                features.attack * 100,
                2,
            ),

            defense=round(
                features.defense * 100,
                2,
            ),

            form=round(
                features.form * 100,
                2,
            ),

            momentum=round(
                features.momentum * 100,
                2,
            ),

            # Venue
            home=round(
                features.home_strength * 100,
                2,
            ),

            away=round(
                features.away_strength * 100,
                2,
            ),

            # Goals
            goal_difference=round(
                features.goal_difference * 100,
                2,
            ),

            clean_sheet=round(
                features.clean_sheet_rate * 100,
                2,
            ),

            failed_to_score=round(
                (1.0 - features.failed_to_score_rate) * 100,
                2,
            ),

            # League
            league_position=round(
                features.league_position * 100,
                2,
            ),

            # Home / Away PPG
            home_points=round(
                features.home_points_per_game * 100,
                2,
            ),

            away_points=round(
                features.away_points_per_game * 100,
                2,
            ),

            # Recent trend
            recent_goal_difference=round(
                ((features.recent_goal_difference + 1) / 2) * 100,
                2,
            ),

            recent_points=round(
                features.recent_points_per_game * 100,
                2,
            ),
        )