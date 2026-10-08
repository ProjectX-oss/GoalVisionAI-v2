"""Operator package changes only LIVE routing; no production resources in tests."""
import importlib.util
from pathlib import Path
import pytest

@pytest.fixture
def updater():
    path=Path(__file__).parents[1]/"operations/live-quote-age/update.py"
    spec=importlib.util.spec_from_file_location("age_installer_test",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nonroot_apply_is_rejected_before_validation(updater, monkeypatch):
    monkeypatch.setattr(updater.os,"geteuid",lambda:1001)
    monkeypatch.setattr(updater,"validate",lambda *a:pytest.fail("validate before root guard"))
    with pytest.raises(SystemExit,match="ROOT_REQUIRED"):
        updater.main(["--apply"])


def test_read_only_default_cannot_mutate(updater,monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(updater,"validate",lambda _:({},tmp_path/"release","BASE"))
    monkeypatch.setattr(updater,"apply",lambda _:pytest.fail("unexpected apply"))
    updater.main([])
    assert "PLAN_VALIDATED" in capsys.readouterr().out


def test_live_only_environment_and_overlay_allowlist(updater):
    env=updater.environment(Path("/opt/synthetic"))
    assert env.endswith(b"GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC=1\n")
    assert env.count(b"GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC=")==1
    assert env.startswith(updater.h.environment(Path("/opt/synthetic")))
    assert all(name.startswith(("app/live_lab/","app/adaptive_lab/")) for name in updater.FILES)
    assert "goalvision-lab-v2-discover.service" in updater.PROTECTED
    assert updater.SERVICE not in updater.PROTECTED


def fake(updater,monkeypatch,tmp_path,fail_reload=False,active=True):
    target=tmp_path/"release"
    override=tmp_path/"unit.d"/"age.conf"
    monkeypatch.setattr(updater,"OVERRIDE",override)
    base={"EnvironmentFiles":str(updater.BASE/"release.env")+" (ignore_errors=no)",
          "WorkingDirectory":"/home/arvis/GoalVisionAI","DropInPaths":""}
    meta={"base_route":base}
    state={"active":active,"reloads":0}
    commands=[]
    def routes(units):
        assert units==(updater.SERVICE,)
        value=base if not override.exists() else {**base,
          "EnvironmentFiles":str(target/"release.env")+" (ignore_errors=no)",
          "DropInPaths":str(override)}
        return {updater.SERVICE:value}
    def control(*args):
        commands.append(args)
        if args==("stop",updater.TIMER):state["active"]=False
        elif args==("start",updater.TIMER):state["active"]=True
        elif args==("daemon-reload",):
            state["reloads"]+=1
            if fail_reload and state["reloads"]==1:
                raise RuntimeError("INJECTED")
        else:raise AssertionError(args)
    def prop(unit,key):
        assert key=="ActiveState"
        return "active" if unit==updater.TIMER and state["active"] else "inactive"
    monkeypatch.setattr(updater.h,"routes",routes)
    monkeypatch.setattr(updater.h,"control",control)
    monkeypatch.setattr(updater.h,"property_of",prop)
    monkeypatch.setattr(updater.h,"disabled_worker",lambda:None)
    monkeypatch.setattr(updater,"verify_protected",lambda _:None)
    return target,meta,state,commands


@pytest.mark.parametrize("active",[True,False])
def test_route_preserves_timer_activity_without_starting_service(updater,monkeypatch,tmp_path,active):
    target,meta,state,commands=fake(updater,monkeypatch,tmp_path,active=active)
    updater.route(target,meta)
    assert updater.current_mode(target,meta)=="ENABLED"
    assert state["active"] is active
    assert not any(arg.endswith(".service") for c in commands for arg in c)
    assert all(c==("daemon-reload",) or c[-1]==updater.TIMER for c in commands)


def test_failed_install_restores_only_its_partial_route(updater,monkeypatch,tmp_path):
    target,meta,state,commands=fake(updater,monkeypatch,tmp_path,fail_reload=True)
    with pytest.raises(RuntimeError,match="INJECTED"):
        updater.route(target,meta)
    assert updater.current_mode(target,meta)=="BASE"
    assert not updater.OVERRIDE.exists() and state["active"]


def test_override_or_link_drift_fails_closed(updater,monkeypatch,tmp_path):
    target,meta,_,_=fake(updater,monkeypatch,tmp_path)
    updater.OVERRIDE.parent.mkdir()
    updater.OVERRIDE.write_text("unreviewed")
    with pytest.raises(ValueError,match="PARTIAL_OR_UNREVIEWED"):
        updater.current_mode(target,meta)
    updater.OVERRIDE.unlink()
    updater.OVERRIDE.symlink_to(tmp_path/"absent")
    with pytest.raises(ValueError,match="BASE_LIVE_ROUTE_DRIFT"):
        updater.current_mode(target,meta)
