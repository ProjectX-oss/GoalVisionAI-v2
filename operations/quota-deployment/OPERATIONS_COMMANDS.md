# Exact operator commands — reviewed controller v2

The old 20260927 controller package is superseded and MUST NOT be installed.
Verify the new archive SHA256 from HANDOFF.json before extraction. No deployment has been performed.
Fresh privileged ADMIN readback is required; pending unsent diagnostics are allowed while sender=false.

Package verification:

```bash
cd /home/arvis/goalvision-operations/prematch-quota-deployment-controller-package-v2-r1-20260927 && sha256sum --check --quiet SHA256SUMS
```

Required read-only privileged preflight:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-quota-deployment-controller-package-v2-r1-20260927/controller.py check --contract-sha256 e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a
```

Read-only status:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-quota-deployment-controller-package-v2-r1-20260927/controller.py status --contract-sha256 e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a
```

Future explicit operator installation after CHECK_PASSED:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-quota-deployment-controller-package-v2-r1-20260927/controller.py install --contract-sha256 e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a --confirm INSTALL:f24738b05fef5f71f3ebcaead3c791233d94fcc38cee21e96a59f2f23493fff2:e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a
```

Future explicit operator rollback:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-quota-deployment-controller-package-v2-r1-20260927/controller.py rollback --contract-sha256 e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a --confirm ROLLBACK:f24738b05fef5f71f3ebcaead3c791233d94fcc38cee21e96a59f2f23493fff2:e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a
```

Future recovery of an interrupted transaction, including after reboot:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-quota-deployment-controller-package-v2-r1-20260927/controller.py rollback --recover --contract-sha256 e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a --confirm ROLLBACK:f24738b05fef5f71f3ebcaead3c791233d94fcc38cee21e96a59f2f23493fff2:e7eb6e1184a6662b96791fec40ce989aa534eff374bdfd563af726c4fb59970a
```
