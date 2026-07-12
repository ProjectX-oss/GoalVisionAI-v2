class DefenseAnalyzer:

    def analyze(self, form):

        if form.games == 0:
            return 0.0

        conceded = form.goals_against / form.games

        score = max(
            0,
            (3.0 - conceded) / 3.0
        )

        return score * 100