from app.features import (
    AttackFeature,
    AwayFeature,
    DefenseFeature,
    FormFeature,
    HomeFeature,
    MomentumFeature,
)
from .weights import (
    ATTACK_WEIGHT,
    AWAY_WEIGHT,
    DEFENSE_WEIGHT,
    FORM_WEIGHT,
    HOME_WEIGHT,
    MOMENTUM_WEIGHT,
)


FEATURES = [

    (FormFeature(), FORM_WEIGHT),

    (AttackFeature(), ATTACK_WEIGHT),

    (DefenseFeature(), DEFENSE_WEIGHT),

    (MomentumFeature(), MOMENTUM_WEIGHT),

    (HomeFeature(), HOME_WEIGHT),

    (AwayFeature(), AWAY_WEIGHT),

]