"""Compare two PyInstaller onefile builds: list what the gi build adds.

python bundle_breakdown.py <work-nogi/Kiln/PKG-00.toc> <work-gi/Kiln/PKG-00.toc>
Reads the PKG TOCs (name, source path, typecode) and sums on-disk source sizes.
"""

import ast
import os
import sys
from collections import defaultdict


def load(path):
    toc = ast.literal_eval(open(path).read())
    # PKG-00.toc: ('...pkg', [ (name, src, typecode), ... ], ...)
    entries = next(x for x in toc if isinstance(x, list))
    out = {}
    for name, src, _typ in entries:
        try:
            out[name] = os.path.getsize(src)
        except (OSError, TypeError):
            out[name] = 0
    return out


a, b = load(sys.argv[1]), load(sys.argv[2])
added = {k: v for k, v in b.items() if k not in a}
groups = defaultdict(int)
for k, v in added.items():
    if k.startswith("gi_typelibs"):
        g = "gi_typelibs/"
    elif k.startswith(("share/", "lib/")):
        g = "/".join(k.split("/")[:2]) + "/"
    elif k.startswith("gi/") or k.startswith("gi."):
        g = "gi python pkg"
    elif ".so" in k:
        g = "shared libs (*.so)"
    else:
        g = "other"
    groups[g] += v
print(f"entries: nogi={len(a)} gi={len(b)} added={len(added)}")
print(
    f"uncompressed bytes: nogi={sum(a.values()) / 1e6:.1f}MB gi={sum(b.values()) / 1e6:.1f}MB added={sum(added.values()) / 1e6:.1f}MB"
)
for g, v in sorted(groups.items(), key=lambda x: -x[1]):
    print(f"  {g:28s} {v / 1e6:7.1f} MB")
big = sorted(added.items(), key=lambda x: -x[1])[:15]
print("largest added:")
for k, v in big:
    print(f"  {v / 1e6:6.2f} MB  {k}")
