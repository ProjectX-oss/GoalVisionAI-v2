from app.database import Database

from .engine import RealDomainAnalysisEngine
from .policy import LabSelectionPolicy
from .repository import SQLiteRealMatchLabRepository
from .service import RealMatchLabAnalysisService


def build_real_match_lab_analysis_service(
    database: Database, *, policy: LabSelectionPolicy = LabSelectionPolicy()
) -> RealMatchLabAnalysisService:
    repository = SQLiteRealMatchLabRepository(database)
    return RealMatchLabAnalysisService(
        repository, RealDomainAnalysisEngine(database, policy)
    )
