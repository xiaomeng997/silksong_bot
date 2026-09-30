@echo off
rem Play the training copy yourself while the oracle records state + a 1080p video (DESIGN D12).
rem Quit the game normally (main menu -> Quit) to finish the recording. Recordings: C:\ssbot\data\human\
cd /d C:\modeling\silksong_bot\brain
.venv\Scripts\python.exe -m ssbot.tools.human_session
pause
