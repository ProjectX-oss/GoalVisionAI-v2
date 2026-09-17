from app.models import TeamRating, TeamStrength

from .feature_registry import FEATURES


class RatingEngine:

    GOAL_DIFFERENCE_WEIGHT = 0.10
    CLEAN_SHEET_WEIGHT = 0.08
    FAILED_TO_SCORE_WEIGHT = 0.08
    LEAGUE_POSITION_WEIGHT = 0.10
    HOME_POINTS_WEIGHT = 0.07
    AWAY_POINTS_WEIGHT = 0.05
    RECENT_GOALS_WEIGHT = 0.06
    RECENT_POINTS_WEIGHT = 0.06

    def calculate(
        self,
        strength: TeamStrength,
        is_home: bool,
    ) -> TeamRating:

        total = 0.0

        for feature, weight in FEATURES:

            value = feature.calculate(strength)

            name = feature.__class__.__name__

            if name == "HomeFeature" and not is_home:
                continue

            if name == "AwayFeature" and is_home:
                continue

            total += value * weight

        total += (
            strength.goal_difference
            * self.GOAL_DIFFERENCE_WEIGHT
        )

        total += (
            strength.clean_sheet
            * self.CLEAN_SHEET_WEIGHT
        )

        total += (
            strength.failed_to_score
            * self.FAILED_TO_SCORE_WEIGHT
        )

        total += (
            strength.league_position
            * self.LEAGUE_POSITION_WEIGHT
        )

        if is_home:

            total += (
                strength.home_points
                * self.HOME_POINTS_WEIGHT
            )

        else:

            total += (
                strength.away_points
                * self.AWAY_POINTS_WEIGHT
            )

        total += (
            strength.recent_goal_difference
            * self.RECENT_GOALS_WEIGHT
        )

        total += (
            strength.recent_points
            * self.RECENT_POINTS_WEIGHT
        )

        return TeamRating(

            form=round(strength.form, 2),

            attack=round(strength.attack, 2),

            defense=round(strength.defense, 2),

            momentum=round(strength.momentum, 2),

            total=round(total, 2),
        )