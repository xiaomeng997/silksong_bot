@echo off
rem The re-score check of forum_planner_plan.md sec. 5 (forum.md 25.11): the person's 8 winning games and 24 1x wave-0
rem clears scored by the planner of the checkout this script sits in. Run it from a frozen checkout (git archive + the
rem git-ignored knowledge/1.0.30000/enemies/forum/*_hitboxes.npz), detached, below normal priority (the tool's workers
rem lower their own priority). About 30 min for one configuration with 3 workers x 4 threads.
rem usage: forum_human_rescore.cmd best|default <out name> [<variants>]   (output C:\ssbot\data\m2_forum_hs\<out name>\
rem        and <out name>_summary.json, log <out name>.log; variants default m0,g0, e.g. rb,rbr: the reactive support
rem        with +b / +br, task forum push 2 track B). SSBOT_RESCORE_REACT set: it replaces the arm's SSBOT_FORUM_REACT.
rem best = seen_cf + escape+n+g + state margins + --clash main (the recommended configuration); default = no switch.
setlocal
cd /d %~dp0..\brain
set PYTHONIOENCODING=utf-8
set NUMBA_NUM_THREADS=4
set SSBOT_FORUM_FR=
set SSBOT_FORUM_REACT=
set SSBOT_FORUM_MARGIN=
set CLASH=off
if "%1"=="best" (
  set SSBOT_FORUM_FR=seen_cf
  set SSBOT_FORUM_REACT=escape+n+g
  set SSBOT_FORUM_MARGIN=state
  set CLASH=main
)
if not "%SSBOT_RESCORE_REACT%"=="" set SSBOT_FORUM_REACT=%SSBOT_RESCORE_REACT%
set VARIANTS=m0,g0
if not "%3"=="" set VARIANTS=%3
set OUT=C:\ssbot\data\m2_forum_hs\%2
set SEGS=--seg C:/ssbot/data/human/20261004_133855:win:1,3,5,6 --seg C:/ssbot/data/human/20261005_160435:win:0,1,2,4 --seg C:/ssbot/data/human/20261004_002749:w0 --seg C:/ssbot/data/human/20261004_012300:w0
call ..\scripts\uv.cmd run python -m ssbot.tools.forum_human_score run %SEGS% --out %OUT% --clash %CLASH% --workers 3 --threads 4 --variants %VARIANTS% --demo-cache C:/ssbot/data/m2_forum_w0f/demo_cache > %OUT%.log 2>&1
call ..\scripts\uv.cmd run python -m ssbot.tools.forum_human_score summary %OUT% --json %OUT%_summary.json > NUL 2>> %OUT%.log
echo DONE >> %OUT%.log
endlocal
