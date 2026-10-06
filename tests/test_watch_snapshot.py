"""Current policy accounting remains separate; as-of and signed bias are exact."""
from datetime import timedelta
import importlib.util
from pathlib import Path
import pytest
from tests.adaptive_lab.test_performance_snapshot import Ledger,single
from tests.adaptive_lab.conftest import START

spec=importlib.util.spec_from_file_location('watch_snapshot',Path(__file__).parents[1]/'operations/watch-reconciliation/snapshot.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def test_cohorts_bias_void_and_future_results_do_not_mix():
    ledger=Ledger()
    single(ledger,'a','WON',probability='.8')['single_selection_policy']='OLD'
    single(ledger,'b','LOST',probability='.6')['single_selection_policy']='CURRENT'
    single(ledger,'c','VOID',probability='.6')['single_selection_policy']='CURRENT'
    value=mod.performance(ledger,now=START+timedelta(days=1))
    assert value['cohorts']['SINGLE']['OLD']['flat_roi']==.5
    assert value['cohorts']['SINGLE']['CURRENT']['flat_roi']==-.5
    assert value['cohorts']['SINGLE']['CURRENT']['probability_observations']==1
    assert value['SINGLE']['calibration_bias_predicted_minus_observed']==pytest.approx(.2)
    before=mod.performance(ledger,now=START+timedelta(hours=1))
    assert before['SINGLE']['pending']==3
    assert before['SINGLE']['calibration_bias_predicted_minus_observed'] is None
    assert before['segments_with_30_settled']=={'SINGLE':[],'COMBO':[]}


@pytest.mark.parametrize('script',['snapshot.py','incremental_report.py'])
def test_standalone_entrypoint_from_foreign_cwd_without_pythonpath(tmp_path,script):
    import subprocess,sys
    path=Path(__file__).parents[1]/'operations/watch-reconciliation'/script
    code="import sys,socket,runpy; deny=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('NETWORK_FORBIDDEN')); socket.socket.connect=deny; socket.create_connection=deny;sys.argv=[sys.argv[1],'--help'];runpy.run_path(sys.argv[0],run_name='__main__')"
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(path)],cwd=tmp_path,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert '--as-of' in result.stdout
