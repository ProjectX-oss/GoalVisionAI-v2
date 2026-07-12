from app.logger import logger
from app.models import LeagueTable


class StandingsCollector:

    def collect(self, data):

        table = {}

        if not data:

            logger.warning(
                "Standings API returned empty response."
            )

            return table

        league = data[0].get("league")

        if not league:

            logger.warning(
                "League data missing in standings response."
            )

            return table

        standings = league.get("standings")

        if not standings:

            logger.warning(
                "Standings missing for league."
            )

            return table

        for row in standings[0]:

            team = LeagueTable(

                team_id=row["team"]["id"],

                position=row["rank"],

                played=row["all"]["played"],

                points=row["points"],

                wins=row["all"]["win"],

                draws=row["all"]["draw"],

                losses=row["all"]["lose"],

                goals_for=row["all"]["goals"]["for"],

                goals_against=row["all"]["goals"]["against"],

                goal_difference=row["goalsDiff"],
            )

            table[team.team_id] = team

        return table