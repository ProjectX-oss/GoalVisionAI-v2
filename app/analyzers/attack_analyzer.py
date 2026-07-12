class AttackAnalyzer:

    def analyze(self, form):

        if form.games == 0:
            return 0.0

        goals_per_game = form.goals_for / form.games

        return min(goals_per_game / 3.0, 1.0) * 100