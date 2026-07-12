from app.models import TeamContext


class TeamRepository:

    def __init__(self):

        self._teams: dict[int, TeamContext] = {}

    def save(
        self,
        context: TeamContext,
    ):

        self._teams[
            context.team_id
        ] = context

    def get(
        self,
        team_id: int,
    ) -> TeamContext:

        return self._teams[team_id]

    def has(
        self,
        team_id: int,
    ) -> bool:

        return team_id in self._teams

    def clear(self):

        self._teams.clear()

    def all(self):

        return self._teams.values()