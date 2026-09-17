from app.backtest.result import BacktestResult


class BacktestScorer:

    def score(
        self,
        predictions,
    ) -> BacktestResult:

        matches = len(predictions)

        correct = 0

        high = 0
        high_correct = 0

        for prediction, winner in predictions:

            ok = prediction.winner == winner

            if ok:
                correct += 1

            if prediction.confidence == "HIGH":

                high += 1

                if ok:
                    high_correct += 1

        accuracy = (
            correct / matches * 100
            if matches
            else 0
        )

        high_accuracy = (
            high_correct / high * 100
            if high
            else 0
        )

        return BacktestResult(

            matches=matches,

            correct=correct,

            accuracy=round(
                accuracy,
                2,
            ),

            high_confidence=high,

            high_correct=high_correct,

            high_accuracy=round(
                high_accuracy,
                2,
            ),
        )