from dataclasses import dataclass
from decimal import Decimal

from .models import BankrollProduct, StakeTier


@dataclass(frozen=True, slots=True)
class BankrollConfig:
    product_id: BankrollProduct
    currency: str
    starting_balance: Decimal
    tier_percentages: tuple[tuple[StakeTier, Decimal], ...]
    public_stars: tuple[tuple[StakeTier, int], ...]
    money_quantum: Decimal = Decimal("0.01")
    rule_version: str = "official-bankroll-v1"

    def __post_init__(self) -> None:
        if self.product_id is not BankrollProduct.OFFICIAL:
            raise ValueError("This framework config supports Official only.")
        if self.starting_balance != Decimal("10000.00"):
            raise ValueError("Official starting bankroll must be EUR 10,000.")
        if self.currency != "EUR":
            raise ValueError("Official bankroll currency must be EUR.")
        if self.money_quantum != Decimal("0.01"):
            raise ValueError("Official money calculations must round to cents.")
        percentages = dict(self.tier_percentages)
        stars = dict(self.public_stars)
        required = set(StakeTier)
        if len(percentages) != len(self.tier_percentages) or set(percentages) != required:
            raise ValueError("Stake percentages must cover every tier exactly once.")
        if len(stars) != len(self.public_stars) or set(stars) != required:
            raise ValueError("Public stars must cover every tier exactly once.")
        ordered = tuple(percentages[tier] for tier in StakeTier)
        if any(not isinstance(value, Decimal) for value in ordered):
            raise TypeError("Stake percentages must be Decimal values.")
        if not all(Decimal("0.01") <= value <= Decimal("0.03") for value in ordered):
            raise ValueError("Stake percentages must remain between 1% and 3%.")
        if ordered != tuple(sorted(ordered)) or len(set(ordered)) != len(ordered):
            raise ValueError("Stake percentages must increase by tier.")
        if stars != {
            StakeTier.STANDARD: 3,
            StakeTier.STRONG: 4,
            StakeTier.ELITE: 5,
        }:
            raise ValueError("Public stake ratings must map to 3, 4, and 5 stars.")
        if not self.rule_version.strip():
            raise ValueError("Bankroll rule version must not be empty.")

    def percentage_for(self, tier: StakeTier) -> Decimal:
        return dict(self.tier_percentages)[tier]

    def stars_for(self, tier: StakeTier) -> int:
        return dict(self.public_stars)[tier]


DEFAULT_OFFICIAL_BANKROLL_CONFIG = BankrollConfig(
    product_id=BankrollProduct.OFFICIAL,
    currency="EUR",
    starting_balance=Decimal("10000.00"),
    tier_percentages=(
        (StakeTier.STANDARD, Decimal("0.01")),
        (StakeTier.STRONG, Decimal("0.02")),
        (StakeTier.ELITE, Decimal("0.03")),
    ),
    public_stars=(
        (StakeTier.STANDARD, 3),
        (StakeTier.STRONG, 4),
        (StakeTier.ELITE, 5),
    ),
)
