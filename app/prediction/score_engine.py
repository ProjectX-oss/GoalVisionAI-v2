from app.models import TeamStats
from . import weights


class ScoreEngine:

    def calculate(self, stats: TeamStats) -> float:

        score = 0.0

        if stats.played == 0:
            return score

        win_rate = stats.wins / stats.played

        attack = stats.goals_for / stats.played

        defense = 1 - (stats.goals_against / max(stats.played * 3, 1))

        home_rate = 0

        if stats.home_played > 0:
            home_rate = stats.home_wins / stats.home_played

        score += win_rate * weights.FORM_WEIGHT

        score += min(attack / 3, 1) * weights.ATTACK_WEIGHT

        score += max(defense, 0) * weights.DEFENSE_WEIGHT

        score += home_rate * weights.HOME_ADVANTAGE_WEIGHT

        return round(score, 2)
