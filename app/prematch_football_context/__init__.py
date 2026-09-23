"""Inactive, pure PREMATCH Football Context Phase A computational foundation.

Use contracts.ContextInput with explicit supplied evidence, then calculate_context.
No registry, environment flags, provider, clock, database or runtime imports.
Predictive benefit and prospective V2 coverage have not been established.
"""
from .calculations import calculate_context, result_fingerprint
from .policy import CONTRACT, FEATURE_NAMES, semantic_manifest
from .fingerprint import semantic_fingerprint

__all__ = ('CONTRACT', 'FEATURE_NAMES', 'calculate_context', 'result_fingerprint',
           'semantic_manifest', 'semantic_fingerprint')
