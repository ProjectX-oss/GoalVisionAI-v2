class MomentumAnalyzer:

    WEIGHTS = [1, 2, 3, 4, 5]

    def analyze(
        self,
        team_id: int,
        fixtures: list,
    ) -> float:

        if not fixtures:
            return 0.0

        score = 0.0

        max_score = sum(self.WEIGHTS) * 3

        ordered = list(reversed(fixtures))

        for weight, fixture in zip(self.WEIGHTS, ordered):

            home = fixture["teams"]["home"]["id"]
            away = fixture["teams"]["away"]["id"]

            hg = fixture["goals"]["home"] or 0
            ag = fixture["goals"]["away"] or 0

            if team_id == home:

                gf = hg
                ga = ag

            else:

                gf = ag
                ga = hg

            if gf > ga:

                score += weight * 3

            elif gf == ga:

                score += weight

        return (score / max_score) * 100