from app.backtest.loader import BacktestLoader
from app.backtest.report import BacktestReport
from app.backtest.scorer import BacktestScorer


class BacktestRunner:

    def __init__(self):

        self.loader = BacktestLoader()
        self.scorer = BacktestScorer()
        self.report = BacktestReport()

    async def run(
        self,
        league_id: int,
        season: int,
    ):

        history = await self.loader.load(
            league_id,
            season,
        )

        print(
            f"Loaded {len(history)} matches."
        )

        # Prediction Engine tiks pieslēgts nākamajā etapā

        result = self.scorer.score([])

        self.report.print(result)

        await self.loader.close()