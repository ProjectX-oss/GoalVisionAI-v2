"""Cross-platform numerical provenance regressions for activation fixtures."""

from contextlib import ExitStack
from decimal import ROUND_DOWN, ROUND_UP, localcontext
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from app.database import Database
from app.historical_model_training.fingerprint import sha256_fingerprint as training_hash
from app.historical_model_training.numerics import (
    deterministic_exp, deterministic_log, deterministic_sqrt,
)
from app.model_activation.fingerprint import sha256_fingerprint
from app.model_operations_rehearsal.fixtures import seed_lab_fixture
from app.model_operations_rehearsal.execution import CommandCapture, _redact_capture


class ModelActivationDeterminismTests(unittest.TestCase):
    def test_captured_database_arguments_are_redacted_for_both_path_styles(self) -> None:
        for path in ("/srv/rehearsal/foundation.db", r"C:\rehearsal\foundation.db"):
            capture = CommandCapture(
                name="foundation-bootstrap",
                arguments=("bootstrap-champion", "--database", path),
                exit_code=0, stdout="", parsed_json=None,
            )
            redacted = _redact_capture(capture, Path("disposable.db"))
            self.assertEqual(redacted.arguments[-1], "<DISPOSABLE_DB>")

    def test_numerical_results_ignore_host_libm_and_decimal_context(self) -> None:
        cases = (
            (deterministic_exp, -0.1, "0x1.cf46d99d52b3ap-1"),
            (deterministic_log, 0.1, "-0x1.26bb1bbb55515p+1"),
            (deterministic_sqrt, 2.0, "0x1.6a09e667f3bcdp+0"),
        )
        with ExitStack() as stack:
            for name in ("exp", "log", "sqrt", "pow"):
                stack.enter_context(patch(f"math.{name}", side_effect=AssertionError("host libm used")))
            for rounding in (ROUND_DOWN, ROUND_UP):
                with localcontext() as context:
                    context.prec = 6
                    context.rounding = rounding
                    for operation, value, expected in cases:
                        with self.subTest(operation=operation.__name__, rounding=rounding):
                            self.assertEqual(operation(value).hex(), expected)
                            self.assertEqual(operation(float.fromhex(value.hex())).hex(), expected)

    def test_fingerprints_still_distinguish_adjacent_float_values(self) -> None:
        value = 0.15580020197851585
        self.assertNotEqual(training_hash(value), training_hash(math.nextafter(value, math.inf)))

    def test_fixture_fingerprint_is_independent_of_host_math_and_json_layout(self) -> None:
        database = Database(":memory:")
        try:
            with ExitStack() as stack:
                for name in ("exp", "log", "sqrt", "pow"):
                    stack.enter_context(patch(f"math.{name}", side_effect=AssertionError("host libm used")))
                manifest = seed_lab_fixture(database)
            expected = "0fd137a185fbedf434ccab82868ac3b0f996d5835dbdeb76309dd04a6f42ead3"
            self.assertEqual(sha256_fingerprint(manifest), expected)
            # Text transport can change newlines, indentation, and dictionary
            # insertion order; parsed immutable material must retain its hash.
            for newline in ("\n", "\r\n"):
                parsed = json.loads(manifest.as_json().replace("\n", newline))
                self.assertEqual(sha256_fingerprint(dict(reversed(tuple(parsed.items())))), expected)
        finally:
            database.close()
