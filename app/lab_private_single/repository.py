"""Independent private SINGLE ledger; never a public or learning ledger."""
from pathlib import Path

from app.lab_combo.repository import ComboRepository
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

FILENAME = "private-single-170.db"


def ledger_path() -> Path:
    return Path.cwd() / "var/lab_combo" / FILENAME


class PrivateSingleRepository(ComboRepository):
    def __init__(self, path: Path) -> None:
        if path.name != FILENAME or path.is_symlink():
            raise ValueError("PRIVATE_SINGLE_LEDGER_REQUIRED")
        super().__init__(path)

    def claim_publication(self, kind: str, prediction: dict, claim: dict) -> bool:
        """One private selection per fixture, including ambiguous prior sends."""
        if kind != "single_prediction":
            raise ValueError("PRIVATE_SINGLE_ONLY")
        key = "PRIVATE_SINGLE_FIXTURE:" + str(prediction["fixture_id"])
        identity = kind + ":" + prediction["prediction_id"]
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            if self.get("economic_claim", key) or self.get("claim", identity):
                return False
            for record, record_id, document in (
                ("economic_claim", key, {"publication_identity": identity, "economic_key": key}),
                ("claim", identity, claim),
            ):
                self.connection.execute("INSERT INTO evidence VALUES (?,?,?,?)",
                    (record, record_id, fingerprint(document), canonical_json(document)))
        return True
