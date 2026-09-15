# LAB_V2_SHADOW

This package is the manual, bounded V2 Phase 1 comparison path. It contains no
Telegram integration and cannot publish.

```bash
python -m app.lab_v2_shadow audit
python -m app.lab_v2_shadow rehearse --max-calls 40 --horizon-days 3
```

`audit` is read-only. `rehearse` performs one current/upcoming provider run,
persists only isolated shadow evidence beneath `var/lab_v2/`, and always
reports zero Telegram sends. There is deliberately no timer unit or `--send`
option.

See `docs/LAB_V2_PHASE1_PI_COVERAGE_SHADOW.md` for policy, evidence and the
first bounded rehearsal.
