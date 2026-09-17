"""Input snapshot fingerprint construction."""

from dataclasses import replace

from .fingerprint import sha256_fingerprint


def fingerprint_input_snapshot(snapshot):
    core = {
        "vector_id": snapshot.model_input_vector_id,
        "vector_fingerprint": snapshot.model_input_fingerprint,
        "match_id": snapshot.match_id,
        "feature_schema_version": snapshot.feature_schema_version,
        "feature_schema_fingerprint": snapshot.feature_schema_fingerprint,
        "feature_provenance_fingerprint": snapshot.feature_provenance_fingerprint,
        "ordered_feature_names": snapshot.ordered_feature_names,
        "ordered_feature_values": snapshot.ordered_feature_values,
        "missingness_mask": snapshot.missingness_mask,
        "ordered_missing_features": snapshot.ordered_missing_features,
        "completeness_score": snapshot.completeness_score,
    }
    return replace(snapshot, input_snapshot_fingerprint=sha256_fingerprint(core))
