from datetime import datetime
from decimal import Decimal

from app.results import ResolvedPredictionResult

from .engine import OfficialBankrollSettlementEngine
from .models import (
    BankrollProduct,
    BankrollSettlementInput,
    BankrollSettlementResult,
    StakeTier,
)


class OfficialResultBankrollSettlementService:
    """Maps an existing prediction result into explicit Official settlement."""

    def __init__(self, engine: OfficialBankrollSettlementEngine) -> None:
        self._engine = engine

    def settle_result(
        self,
        result: ResolvedPredictionResult,
        stake_tier: StakeTier,
        odds: Decimal | None,
        evaluated_at: datetime,
    ) -> BankrollSettlementResult:
        timestamp = result.resolved_at or evaluated_at
        return self._engine.settle(
            BankrollSettlementInput(
                product_id=BankrollProduct.OFFICIAL,
                prediction_id=result.prediction_id,
                fixture_id=result.fixture_id,
                status=result.status,
                stake_tier=stake_tier,
                odds=odds,
                settled_at=timestamp,
            )
        )
