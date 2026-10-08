"""Per-state support margins of the Forum tables (task "wave-0 de-saturation", forum.md §23): the family margin of R0
(support_margins.json by_family: the largest held-out residual over every contact of the family) is set by a few
contacts of one state (EN_CHARGE 2.96 u: its Charge; RE_DEFEND 2.62 u: its Multihit Clashed; RE_STAB 1.37 u: Stab 3 /
Stab End), and dilates every state's template by it. Here the same rule per (type, family, state): the largest held-out
residual of the contacts in that state (ssbot.knowledge.forum_support.margins_from_contacts' residuals, q = 1.0, a
residual beyond the search radius counted at it). A state with fewer than MIN_N contacts keeps its family margin; the
family-wide, tail and world-frame templates keep the family margin too (EnemyTables.production(state_margins_path=
...)). The thrown hazards' self templates keep theirs.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_state_margins [--contacts .../build_all/extra/contacts.jsonl.gz]
        [--out ../knowledge/1.0.30000/enemies/forum/support_margins_state.json]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

CONTACTS = Path("C:/ssbot/data/m2_forum_r0/build_all/extra/contacts.jsonl.gz")
MIN_N = 100                       # a state with fewer contacts keeps its family margin (too few to bound it alone)


def state_residuals(rows: list[dict], skip_families=frozenset()) -> dict[tuple[str, str, str], list[float]]:
    """{(type, family, state): held-out residuals} of the enemies' own contacts (margins_from_contacts' "state:" set)."""
    from ssbot.knowledge.behaviour_tables import R_MARGIN_SEARCH_U
    per: dict = defaultdict(list)
    for r in rows:
        if r.get("follow") or r.get("tk") != r.get("type"):
            continue
        st, fam = r.get("state"), r.get("family")
        k = f"state:{st}"
        ho = r.get("ho") or {}
        if fam is None or st is None or k not in ho or fam in skip_families:
            continue
        v = ho[k]
        per[(r["type"], fam, st)].append(R_MARGIN_SEARCH_U if v is None else float(v))
    return per


def main(argv=None) -> int:
    from ssbot.combat.enemy_tables import FORUM_DIR
    from ssbot.core.forum import FORUM_TYPES
    from ssbot.knowledge.forum_support import read_contacts
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contacts", type=Path, default=CONTACTS)
    ap.add_argument("--out", type=Path, default=FORUM_DIR / "support_margins_state.json")
    a = ap.parse_args(argv)
    fam_doc = json.loads((FORUM_DIR / "support_margins.json").read_text("utf-8"))
    by_family = fam_doc.get("by_family") or {}
    idle = frozenset(sp.idle_family for sp in FORUM_TYPES.values() if sp.idle_family)
    per = state_residuals(read_contacts(a.contacts), skip_families=idle)
    by_state, n = {}, {}
    for (tk, fam, st), v in sorted(per.items()):
        fm = float(by_family.get(f"{tk}/{fam}", 0.0))
        m = float(np.max(v)) if len(v) >= MIN_N else fm
        # never above the family's (the family margin is the max over these contacts; equal up to the rounding)
        by_state[f"{tk}/{fam}/{st}"] = round(min(m, fm), 4)
        n[f"{tk}/{fam}/{st}"] = len(v)
    out = {"what": "per-state support margins (u): the largest held-out residual of the build's contacts in each Control "
                   "state (forum.md 23); states with fewer than min_n contacts (or none), the family-wide / tail / "
                   "world-frame templates and the hazards' self templates keep support_margins.json's family margin",
           "min_n": MIN_N,
           "contacts": str(a.contacts), "quantile": 1.0, "by_state": by_state, "n": n,
           "family_source": "support_margins.json by_family"}
    a.out.write_text(json.dumps(out, indent=1), "utf-8")
    shrunk = {k: (by_family.get(k.rsplit("/", 1)[0]), v) for k, v in by_state.items()
              if v + 0.05 < float(by_family.get(k.rsplit("/", 1)[0], 0.0))}
    print(f"{len(by_state)} states; {len(shrunk)} below their family margin -> {a.out}")
    for k, (f, s) in sorted(shrunk.items(), key=lambda z: -(z[1][0] - z[1][1]))[:40]:
        print(f"  {k}: family {f} -> state {s} (n {n[k]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
