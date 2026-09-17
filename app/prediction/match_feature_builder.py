from app.models import (
    FeatureVector,
    MatchFeatures,
)


class MatchFeatureBuilder:

    def build(
        self,
        home: FeatureVector,
        away: FeatureVector,
    ) -> MatchFeatures:

        return MatchFeatures(

            home=home,

            away=away,

            standings_difference=0.0,

            goal_difference=(
                home.goals_for
                - away.goals_for
            ),

            form_difference=(
                home.form
                - away.form
            ),

            momentum_difference=(
                home.momentum
                - away.momentum
            ),

            home_advantage=(
                home.home_strength
                - away.away_strength
            ),
        )