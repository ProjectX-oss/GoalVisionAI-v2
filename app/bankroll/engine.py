from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.results import ResolutionStatus

from .config import BankrollConfig
from .exceptions import (
    InsufficientBalanceError,
    InvalidOddsError,
    ProductBankrollMismatchError,
)
from .models import (
    BankrollAccount,
    BankrollProduct,
    BankrollSettlementInput,
    BankrollSettlementResult,
    BankrollSnapshot,
    BankrollTransaction,
    StakeRecommendation,
    StakeTier,
)
from .repository import BankrollRepository


class OfficialBankrollSettlementEngine:
    def __init__(
        self,
        config: BankrollConfig,
        repository: BankrollRepository,
    ) -> None:
        self._config = config
        self._repository = repository

    def recommend_stake(self, tier: StakeTier) -> StakeRecommendation:
        account = self._official_account()
        percentage = self._config.percentage_for(tier)
        stake = self._money(account.balance * percentage)
        if stake <= Decimal("0") or stake > account.balance:
            raise InsufficientBalanceError(
                "Official bankroll cannot fund the recommended stake."
            )
        return StakeRecommendation(
            product_id=BankrollProduct.OFFICIAL,
            tier=tier,
            percentage=percentage,
            public_stars=self._config.stars_for(tier),
            opening_balance=account.balance,
            stake=stake,
            currency=self._config.currency,
            rule_version=self._config.rule_version,
        )

    def settle(
        self,
        settlement: BankrollSettlementInput,
    ) -> BankrollSettlementResult:
        self._validate_product(settlement.product_id)
        existing = self._repository.get_transaction(
            settlement.product_id,
            settlement.prediction_id,
        )
        if existing is not None:
            return self._transaction_result(
                existing,
                captured_at=settlement.settled_at,
                applied=False,
            )

        if settlement.status in {
            ResolutionStatus.PENDING,
            ResolutionStatus.UNRESOLVED,
        }:
            return self._result(settlement, transaction=None, applied=False)
        if settlement.status not in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        }:
            raise ValueError("Unsupported bankroll settlement status.")

        odds = self._validate_odds(settlement.odds)
        recommendation = self.recommend_stake(settlement.stake_tier)
        gross_return, profit_loss = self._returns(
            settlement.status,
            recommendation.stake,
            odds,
        )
        closing_balance = self._money(
            recommendation.opening_balance + profit_loss
        )
        if closing_balance < Decimal("0"):
            raise InsufficientBalanceError("Settlement would overdraw bankroll.")
        transaction = BankrollTransaction(
            product_id=settlement.product_id,
            prediction_id=settlement.prediction_id,
            fixture_id=settlement.fixture_id,
            opening_balance=recommendation.opening_balance,
            stake=recommendation.stake,
            odds=odds,
            gross_return=gross_return,
            profit_loss=profit_loss,
            closing_balance=closing_balance,
            settlement_status=settlement.status,
            stake_tier=settlement.stake_tier,
            settled_at=settlement.settled_at,
            currency=self._config.currency,
            rule_version=self._config.rule_version,
        )
        created = self._repository.store_transaction(transaction)
        stored = self._repository.get_transaction(
            settlement.product_id,
            settlement.prediction_id,
        )
        if stored is None:
            raise RuntimeError("Stored bankroll transaction could not be loaded.")
        return self._transaction_result(
            stored,
            captured_at=settlement.settled_at,
            applied=created,
        )

    def snapshot(self, captured_at: datetime) -> BankrollSnapshot:
        account = self._official_account()
        if captured_at.tzinfo is None:
            raise ValueError("Snapshot timestamp must be timezone-aware.")
        return BankrollSnapshot(
            product_id=account.product_id,
            currency=account.currency,
            starting_balance=account.starting_balance,
            balance=account.balance,
            transaction_count=len(
                self._repository.transaction_history(account.product_id)
            ),
            captured_at=captured_at,
        )

    def _result(
        self,
        settlement: BankrollSettlementInput,
        transaction: BankrollTransaction | None,
        applied: bool,
    ) -> BankrollSettlementResult:
        return BankrollSettlementResult(
            product_id=settlement.product_id,
            prediction_id=settlement.prediction_id,
            fixture_id=settlement.fixture_id,
            status=settlement.status,
            applied=applied,
            transaction=transaction,
            snapshot=self.snapshot(settlement.settled_at),
        )

    def _transaction_result(
        self,
        transaction: BankrollTransaction,
        captured_at: datetime,
        applied: bool,
    ) -> BankrollSettlementResult:
        return BankrollSettlementResult(
            product_id=transaction.product_id,
            prediction_id=transaction.prediction_id,
            fixture_id=transaction.fixture_id,
            status=transaction.settlement_status,
            applied=applied,
            transaction=transaction,
            snapshot=self.snapshot(captured_at),
        )

    def _official_account(self) -> BankrollAccount:
        account = self._repository.load_account(BankrollProduct.OFFICIAL)
        if (
            account.product_id is not self._config.product_id
            or account.currency != self._config.currency
            or account.starting_balance != self._config.starting_balance
        ):
            raise ProductBankrollMismatchError(
                "Repository account does not match Official bankroll config."
            )
        return account

    def _validate_product(self, product_id: BankrollProduct) -> None:
        if product_id is not BankrollProduct.OFFICIAL:
            raise ProductBankrollMismatchError(
                "Official settlement cannot update another product bankroll."
            )

    def _validate_odds(self, odds: Decimal | None) -> Decimal:
        if odds is None or not isinstance(odds, Decimal):
            raise InvalidOddsError("Terminal settlements require Decimal odds.")
        if not odds.is_finite() or odds <= Decimal("1"):
            raise InvalidOddsError("Decimal odds must be finite and greater than 1.")
        return odds

    def _returns(
        self,
        status: ResolutionStatus,
        stake: Decimal,
        odds: Decimal,
    ) -> tuple[Decimal, Decimal]:
        if status is ResolutionStatus.WON:
            gross_return = self._money(stake * odds)
            return gross_return, self._money(gross_return - stake)
        if status is ResolutionStatus.LOST:
            return Decimal("0.00"), -stake
        return stake, Decimal("0.00")

    def _money(self, value: Decimal) -> Decimal:
        return value.quantize(self._config.money_quantum, rounding=ROUND_HALF_UP)


def create_official_account(config: BankrollConfig) -> BankrollAccount:
    return BankrollAccount(
        product_id=config.product_id,
        currency=config.currency,
        starting_balance=config.starting_balance,
        balance=config.starting_balance,
    )
