# Upgrade Guide

```bash
cd /opt/netwatchdog
sudo netwatchdogctl backup
git fetch --all --prune
git checkout feature/oled-v1
git pull --ff-only
sudo ./install.sh
sudo netwatchdogctl selftest
```

Rollback:

```bash
cd /opt/netwatchdog
sudo netwatchdogctl rollback <previous_commit_sha>
sudo ./install.sh
```

Risk: rollback runs `git reset --hard`, so local uncommitted changes inside `/opt/netwatchdog` are removed.
