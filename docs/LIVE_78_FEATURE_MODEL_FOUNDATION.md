# Live 78-Feature Model Foundation

## Contract authority

`app.model_input_builder.LIVE_MODEL_INPUT_CONTRACT` is derived from
`GOALVISION_MODEL_INPUT_V1`, which in turn is derived from the ordered Feature
Store registry. The foundation never maintains a second list of 78 names.

- Schema: `goalvision_model_input_v1`
- Schema name/version: `goalvision_model_input` / `v1`
- Compatibility: `official_prediction_model_input_v1`
- Count: 78
- Required baselines: home/away recent points, goals scored, and goals
  conceded per match
- Missingness: one boolean per ordered value; required baselines may not be
  missing
- Numeric serialization: finite `Decimal` values use deterministic canonical
  JSON; runtime preprocessing converts only after schema validation
- Fingerprinting: schema metadata and fingerprint-version identity are hashed
  separately from each value-bearing model-input fingerprint

Legacy 145-position artifacts remain valid only for their historical contract.
They cannot be remapped, padded, truncated, reordered, aliased, or declared
compatible with this contract.

### Exact ordered feature names

The following documentation snapshot is generated from
`LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names`; it is not a runtime authority:

1. `home_recent_points_per_match`
2. `away_recent_points_per_match`
3. `home_recent_goals_scored_per_match`
4. `home_recent_goals_conceded_per_match`
5. `home_recent_xg_for_per_match`
6. `home_recent_xg_against_per_match`
7. `away_recent_goals_scored_per_match`
8. `away_recent_goals_conceded_per_match`
9. `away_recent_xg_for_per_match`
10. `away_recent_xg_against_per_match`
11. `home_recent_clean_sheet_rate`
12. `home_recent_failed_to_score_rate`
13. `away_recent_clean_sheet_rate`
14. `away_recent_failed_to_score_rate`
15. `home_team_home_points_per_match`
16. `away_team_away_points_per_match`
17. `home_goals_scored_at_home_per_match`
18. `away_goals_scored_away_per_match`
19. `home_goals_conceded_at_home_per_match`
20. `away_goals_conceded_away_per_match`
21. `home_venue_xg_for_per_match`
22. `away_venue_xg_for_per_match`
23. `home_venue_xg_against_per_match`
24. `away_venue_xg_against_per_match`
25. `home_season_points_per_match`
26. `home_season_goal_difference_per_match`
27. `home_season_xg_difference_per_match`
28. `away_season_points_per_match`
29. `away_season_goal_difference_per_match`
30. `away_season_xg_difference_per_match`
31. `normalized_league_position_difference`
32. `home_season_matches_played`
33. `away_season_matches_played`
34. `recent_form_difference`
35. `attacking_strength_difference`
36. `defensive_strength_difference`
37. `recent_xg_difference`
38. `venue_strength_difference`
39. `rest_days_difference`
40. `missing_player_difference`
41. `fixture_congestion_difference`
42. `combined_recent_goals_per_match`
43. `combined_recent_xg_per_match`
44. `combined_goal_concession_rate`
45. `combined_clean_sheet_rate`
46. `combined_failed_to_score_rate`
47. `head_to_head_btts_rate`
48. `head_to_head_over_2_5_rate`
49. `home_confirmed_lineup_indicator`
50. `home_probable_lineup_indicator`
51. `home_injuries_count`
52. `home_suspensions_count`
53. `home_missing_key_players_count`
54. `home_goalkeeper_available_indicator`
55. `away_confirmed_lineup_indicator`
56. `away_probable_lineup_indicator`
57. `away_injuries_count`
58. `away_suspensions_count`
59. `away_missing_key_players_count`
60. `away_goalkeeper_available_indicator`
61. `neutral_venue_indicator`
62. `derby_indicator`
63. `home_fixture_congestion_count`
64. `home_rest_days`
65. `away_fixture_congestion_count`
66. `away_rest_days`
67. `competition_stage_encoding`
68. `snapshot_completeness_score`
69. `home_recent_form_sample_size`
70. `away_recent_form_sample_size`
71. `home_venue_sample_size`
72. `away_venue_sample_size`
73. `home_season_sample_size`
74. `away_season_sample_size`
75. `xg_availability_indicator`
76. `lineup_availability_indicator`
77. `injury_data_availability_indicator`
78. `head_to_head_availability_indicator`

## Historical derivation and leakage controls

The live-contract projection uses only matches strictly before target kickoff.
It derives recent form, venue form, season-to-date, xG, head-to-head, rest, and
fixture-congestion facts, then runs the canonical Feature Store extractor.
Equal-kickoff, future, and target-as-source facts fail closed.

The current import does not contain pre-kickoff lineups, injuries, suspensions,
goalkeeper status, league position, derby identity, or competition stage.
Those optional values remain missing in training rows. The deterministic
coverage report classifies every canonical feature as directly derived,
historically aggregated, or optional and legitimately missing. Required
baseline absence rejects the row.

Neutral-venue state is never guessed. The controlled rehearsal explicitly
declares its generated home-ground fixtures non-neutral. A reviewed-real source
without a reliable neutral-venue flag retains this optional feature as missing;
the absence is reported in coverage and preprocessing rather than converted to
false.

Training uses TRAIN-only median imputation and scaling. Features missing across
all TRAIN rows receive an explicit internal constant with a parallel
missingness indicator; the persisted preprocessing artifact records both.
VALIDATION is evaluation/calibration-only and TEST remains isolated until
backtesting.

## Artifact chain

The controlled staging chain builds two independent compatible artifacts and
runs the existing calibration, TEST-only backtest, comparison, promotion,
shadow, activation, rollback, and resolver services. Shadow inputs supply
explicit controlled pre-match availability facts to meet the unchanged 95%
activation evidence threshold. These facts are not introduced into historical
training.

Runtime inference verifies the canonical schema declaration and preprocessing
order. The Real Match Lab applies the persisted historical calibrators together
with their bounded-simplex, monotonic totals, and exact-complement policies,
persists the resulting canonical assembly, evaluates immutable odds, and
creates either one deterministic preview or an honest no-selection result.

## Safety and rollback

All rehearsals use disposable staging databases and explicit clocks.
Production activation, scheduling, automatic promotion, automatic rollback,
fixture discovery, bankroll mutation, Official publication, and Telegram sends
remain disabled. Activation and rollback retain exact confirmations, append-only
history, replay/conflict handling, audit preflight, and runtime resolution.

Retain the canonical JSON evidence with its source/staging hashes and audit
fingerprint. To roll back in staging, inspect the current generation, prepare a
rollback to a prior compatible generation, review the plan fingerprint, and
execute with the existing exact rollback confirmation.

## Remaining limitations

The controlled source is deterministic synthetic staging history, not evidence
of real-world predictive quality. Historical neutrality is currently limited
to the normal home/away source contract. A reviewed external dataset should
add explicit neutral-venue, league-position, competition-stage, and
pre-kickoff availability provenance before production consideration.
