# Upgrade Guide

```bash
cd /opt/netwatchdog
sudo netwatchdogctl backup
git fetch --all --prune
git checkout feature/oled-v1
git pull --ff-only
sudo sh install.sh
sudo netwatchdogctl selftest
```

Verify ports after upgrade:

```bash
ss -lntp | grep -E '8080|8090'
```

Expected:

```text
8080 NetWatchDog Dashboard
8090 Smart Condo Dashboard
```

Rollback:

```bash
cd /opt/netwatchdog
sudo netwatchdogctl backup
sudo netwatchdogctl rollback <previous_commit_sha>
sudo sh install.sh
```

Risk: rollback resets repo files inside `/opt/netwatchdog`. The command refuses to run when the working tree is dirty.

Never stop or modify `smart-condo-dashboard.service` during NetWatchDog upgrade.
