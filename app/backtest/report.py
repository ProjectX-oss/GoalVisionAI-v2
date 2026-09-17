from app.backtest.result import BacktestResult


class BacktestReport:

    def print(
        self,
        result: BacktestResult,
    ):

        print()

        print("=" * 50)

        print("GoalVision Backtest")

        print("=" * 50)

        print(f"Matches           : {result.matches}")

        print(f"Correct           : {result.correct}")

        print(f"Accuracy          : {result.accuracy:.2f}%")

        print()

        print(f"HIGH Predictions  : {result.high_confidence}")

        print(f"HIGH Correct      : {result.high_correct}")

        print(
            f"HIGH Accuracy     : {result.high_accuracy:.2f}%"
        )

        print("=" * 50)

        print()