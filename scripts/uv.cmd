@echo off
rem uv with its managed Pythons under C:\ssbot\tools\uv-python (outside AppData; see brain/uv.toml for why).
set UV_PYTHON_INSTALL_DIR=C:\ssbot\tools\uv-python
"C:\ssbot\tools\uv\uv.exe" %*
