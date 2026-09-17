from datetime import datetime

from app.models import HistoricalMatch


class HistoryCollector:

    def collect(
        self,
        fixtures,
    ):

        matches = []

        for fixture in fixtures:

            matches.append(

                HistoricalMatch(

                    fixture_id=fixture["fixture"]["id"],

                    league_id=fixture["league"]["id"],

                    season=fixture["league"]["season"],

                    home_team_id=fixture["teams"]["home"]["id"],

                    away_team_id=fixture["teams"]["away"]["id"],

                    home_goals=fixture["goals"]["home"] or 0,

                    away_goals=fixture["goals"]["away"] or 0,

                    kickoff=datetime.fromisoformat(
                        fixture["fixture"]["date"].replace(
                            "Z",
                            "+00:00",
                        )
                    ),

                    status=fixture["fixture"]["status"]["short"],
                )

            )

        return matches