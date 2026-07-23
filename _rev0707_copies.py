#!/usr/bin/env python3
"""Ревизия 07.07: рабочие копии доков для правки."""
import shutil
for k in ("index", "roadmap_master"):
    src = f"/tmp/revision0707/{k}.snap.md"
    dst = f"/root/turbobaby-manager-bot/_rev0707_{k}.new.md"
    shutil.copy(src, dst)
    print("copied", dst)
