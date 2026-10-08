"""Offline regression harness: fake credentials and denied outbound sockets."""
DEFAULT_TESTS = ['tests/adaptive_lab/test_live.py', 'tests/adaptive_lab/test_evening_live.py', 'tests/adaptive_lab/test_live_quote_age_policy.py', 'tests/adaptive_lab/test_quota_contention.py', 'tests/adaptive_lab/test_settlement_preflight_reserve.py', 'tests/adaptive_lab/test_no_combo_learning.py', 'tests/adaptive_lab/test_calendar_research.py', 'tests/adaptive_lab/test_calendar_monitor.py', 'tests/adaptive_lab/test_calibration_research.py', 'tests/adaptive_lab/test_shadow_chronology.py', 'tests/adaptive_lab/test_devig_research.py', 'tests/adaptive_lab/test_devig_integration.py', 'tests/adaptive_lab/test_performance_snapshot.py', 'tests/test_live_combo_research.py', 'tests/test_prematch_quality_evidence.py', 'tests/test_combo_double_170.py', 'tests/test_combo_aggregate_order.py', 'tests/test_lab_combo_early_loss.py', 'tests/test_lab_combo_integrity.py', 'tests/test_settlement_replies.py', 'tests/test_lab_delivery_accounting.py', 'tests/test_final_review_queue.py', 'tests/test_dixon_coles_incremental.py', 'tests/test_prematch_combo_leg_odds_floor.py', 'tests/test_lab_accuracy_combo.py']
import os,sys,socket
from pathlib import Path
def denied(*args,**kwargs): raise AssertionError('OUTBOUND_NETWORK_DENIED')
socket.socket.connect=denied
socket.socket.connect_ex=denied
socket.create_connection=denied
repo=Path(__file__).resolve().parents[2]; os.chdir(repo); sys.path.insert(0,str(repo))
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ.pop('GOALVISION_LAB_EVENING_MODE',None)
os.environ.pop('GOALVISION_LIVE_API_FEED_QUOTES',None)
os.environ['FOOTBALL_API_KEY']='offline-test-placeholder'
os.environ['TELEGRAM_BOT_TOKEN']='offline-test-placeholder'
os.environ.pop('GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC',None)
import pytest
raise SystemExit(pytest.main(['-q','--tb=short','-p','no:cacheprovider',*(sys.argv[1:] or DEFAULT_TESTS)]))
