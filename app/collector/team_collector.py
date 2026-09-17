from app.models import TeamStats


class TeamCollector:

    def collect(self, data) -> TeamStats:

        fixtures = data["fixtures"]

        wins = fixtures["wins"]

        draws = fixtures["draws"]

        loses = fixtures["loses"]

        goals = data["goals"]

        return TeamStats(

            team_id=data["team"]["id"],

            league_id=data["league"]["id"],

            season=data["league"]["season"],

            played=fixtures["played"]["total"],

            wins=wins["total"],

            draws=draws["total"],

            losses=loses["total"],

            goals_for=goals["for"]["total"]["total"],

            goals_against=goals["against"]["total"]["total"],

            home_played=fixtures["played"]["home"],

            home_wins=wins["home"],

            home_draws=draws["home"],

            home_losses=loses["home"],

            away_played=fixtures["played"]["away"],

            away_wins=wins["away"],

            away_draws=draws["away"],

            away_losses=loses["away"],

            form=data.get("form", "")
        )