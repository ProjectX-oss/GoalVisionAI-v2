"""No systemd controls: stale preparation and foreign routes must fail closed."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def prepared(tmp_path):
    path = Path(__file__).parents[2]/"operations/admin-autorepair/update_mixed_delivery.py"
    spec = importlib.util.spec_from_file_location("health_package_guard", path)
    wrapper = importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)
    wrapper.BASE = tmp_path/"old"
    wrapper.OVERRIDE = tmp_path/"monitor.conf"
    spec = {"service": "goalvision-admin-alerts.service", "override": wrapper.OVERRIDE}
    units = ("goalvision-lab-v2-discover.service", wrapper.WORKER, *wrapper.RESEARCH)
    state = {(unit.replace(".service", ".timer"), key): value
             for unit in units for key,value in (("ActiveState","active"),("UnitFileState","enabled"))}
    state.update({(wrapper.TIMER,"ActiveState"):"inactive", (wrapper.TIMER,"UnitFileState"):"disabled",
                  (wrapper.WORKER,"ActiveState"):"inactive", (wrapper.WORKER,"MainPID"):"0"})
    routes = {unit: {"ExecStart": "original-"+unit} for unit in units}
    loaded = {"monitor": str(wrapper.BASE)}
    def verify_route(_spec, target):
        if loaded["monitor"] != str(target):
            raise ValueError("ADMIN_ROUTE_MISMATCH")
    module = SimpleNamespace(PROTECTED=units, SPECS={"monitor": spec},
        prop=lambda unit,key:state[(unit,key)], protected_routes=lambda:routes,
        dropin=lambda spec,target:b"reviewed-dropin", verify_route=verify_route)
    meta = {"protected_routes_at_preparation": {k:dict(v) for k,v in routes.items()},
            "protected_timers_at_preparation":wrapper.protected_timers(module),
            "runtime_import_smoke":{"status":"ISOLATED_MONITOR_IMPORT_PASS"}}
    return wrapper,module,meta,{"monitor":tmp_path/"new"},state,routes,loaded


def test_old_and_reviewed_new_routes_accept_without_mutation(prepared):
    w,m,meta,targets,state,routes,loaded = prepared
    w.verify_preparation(m,meta,targets)
    w.OVERRIDE.write_bytes(b"reviewed-dropin")
    loaded["monitor"] = str(targets["monitor"])
    w.verify_preparation(m,meta,targets)
    assert w.OVERRIDE.read_bytes() == b"reviewed-dropin"
    assert state[(w.TIMER,"ActiveState")] == "inactive"


@pytest.mark.parametrize("drift",["prematch","original_research","forward_research",
                                  "protected_timer","codex","smoke","override","loaded_route"])
def test_unreviewed_state_blocks_operator_step(prepared, drift):
    w,m,meta,targets,state,routes,loaded = prepared
    if drift in ("prematch","original_research","forward_research"):
        unit = {"prematch":m.PROTECTED[0], "original_research":w.RESEARCH[0],
                "forward_research":w.RESEARCH[1]}[drift]
        routes[unit]["ExecStart"] = "changed"
    elif drift == "protected_timer":
        state[(w.RESEARCH[0].replace(".service",".timer"),"ActiveState")] = "inactive"
    elif drift == "codex":
        state[(w.TIMER,"UnitFileState")] = "enabled"
    elif drift == "smoke":
        meta["runtime_import_smoke"] = {}
    elif drift == "override":
        w.OVERRIDE.write_bytes(b"unreviewed")
    else:
        loaded["monitor"] = "foreign"
    with pytest.raises(ValueError):
        w.verify_preparation(m,meta,targets)


def test_reviewed_combo_repair_route_is_allowed_only_with_exact_hashes(prepared, tmp_path):
    import copy, hashlib, json
    w,m,meta,targets,state,routes,loaded = prepared
    target=tmp_path/"combo-aggregate"
    w.PREMATCH_TARGET=target
    (target/"application/app").mkdir(parents=True)
    app=target/"application/app/reviewed.py";app.write_text("REVIEWED=True\n")
    (target/"release.env").write_text("GOALVISION_PRIVATE_SINGLE_170=1\n")
    units=("goalvision-lab-v2-discover.service","goalvision-adaptive-learning-observer.service",
           "goalvision-lab-combo-settle.service","goalvision-adaptive-learning.service")
    for unit in units:
        meta["protected_routes_at_preparation"][unit]={
            "EnvironmentFiles":"old (ignore_errors=no)", "DropInPaths":"/etc/base.conf", "ExecStart":"unchanged"}
    routes.clear();routes.update(copy.deepcopy(meta["protected_routes_at_preparation"]))
    meta["reviewed_prematch"]={"target":str(target),
        "manifest":{"app/reviewed.py":hashlib.sha256(app.read_bytes()).hexdigest()},
        "environment_sha256":hashlib.sha256((target/"release.env").read_bytes()).hexdigest()}
    for unit in units:
        routes[unit]["EnvironmentFiles"]=str(target/"release.env")+" (ignore_errors=no)"
        routes[unit]["DropInPaths"]+=" /etc/systemd/system/"+unit+".d/zzzzzzzzzzzzzzzzz-combo-aggregate-20261004.conf"
    w.verify_preparation(m,meta,targets)
    app.write_text("TAMPERED=True\n")
    with pytest.raises(ValueError,match="REVIEWED_PREMATCH_HASH_DRIFT"):
        w.verify_preparation(m,meta,targets)
