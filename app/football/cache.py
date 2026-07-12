class TeamCache:

    def __init__(self):

        self._cache = {}

    def has(
        self,
        team_id: int,
    ) -> bool:

        return team_id in self._cache

    def get(
        self,
        team_id: int,
    ):

        return self._cache.get(team_id)

    def save(
        self,
        team_id: int,
        fixtures,
    ):

        self._cache[team_id] = fixtures

    def clear(self):

        self._cache.clear()