# API-Football league IDs mapped to normalized relative strength ratings.
# Keep all rating updates in this table and validate them before prediction use.
LEAGUE_STRENGTH_RATINGS: dict[int, float] = {
    39: 1.00,   # Premier League
    140: 0.95,  # La Liga
    78: 0.92,   # Bundesliga
    135: 0.92,  # Serie A
    61: 0.88,   # Ligue 1
    88: 0.78,   # Eredivisie
    94: 0.76,   # Primeira Liga
    144: 0.70,  # Belgian Pro League
    203: 0.68,  # Super Lig
    253: 0.65,  # Major League Soccer
}

UNKNOWN_LEAGUE_STRENGTH = 0.50
