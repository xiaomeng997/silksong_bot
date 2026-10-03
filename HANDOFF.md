# HANDOFF - Task R (Forum route research, offline)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_c0d56d51-4cb-5`, branch `worktree-wf_c0d56d51-4cb-5`.
Finished normally (no stop). Offline only: no game instance used, no job running.

## Done (committed)

- `docs/research/forum_route.md` (Chinese): Ascendant's Grip (Jubilana's shop in Songclave, 350 rosaries, after the
  "Save City Merchant" wish + Song_07 ambush), Reaper chapel (Greymoor_07 -> 20b -> 20c, 4-wave gauntlet, shrine
  needs 3 Binds, AutoEquipCrestV2 strips non-skill tools until a bench, respawn set to the chapel + autosave, ~8-9 s
  pause disabled), G&Z chain (Greymoor_05 forced first meeting, roof shortcut lever in Library_09, garmondInLibrary
  only via TimePasses, spar 460 HP, lethal = spikes AND the Stun Box, garmondWillAidInForumBattle via the FSM variable
  override, Hang_06 recruit), LoadedFromMenu call chain (Continue / new game only) and re-recruit (NPC visible in
  Hang_06 <=> not recruited), Cogfly (Hang_09, 1 Tool Metal, 0 rosaries, 8.3-9.3 s no pause), Reaper slots and
  conflicts (Grip vs Weighted Belt, lockets per crest), time estimates (gate distances + pace from the human
  recording), concrete DESIGN 3.6.4 / 3.6.5 (+3.5.7 / 3.7.5) edit proposals, open items.

## Scripts / raw outputs

`C:\ssbot\sandbox\forum_route_scripts\` (UnityPy scripts run with the scratch venv
`...\scratchpad\venv\Scripts\python.exe`; `pace.py` runs with `..\scripts\uv.cmd run python` from brain).

## Next (for the lead / a live agent)

1. Live checks listed in forum_route.md section 8 (Continue clears garmondAidForumBattle and Garmond reappears in
   Hang_06; Reaper shrine sequence; Stun Box lethality via LethalBlock; Hang_09 mite reach; caravan bench in S11).
2. Merge the DESIGN proposals (section 7) after K1 decides Reaper / Grip.
3. `docs/facts/1.0.30000/crests.json` is untracked in the main checkout; forum_route.md cites it there.
