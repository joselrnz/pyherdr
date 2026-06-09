@echo off
rem PyHerdr launcher: always uses the project venv's Python (so you never hit
rem "No module named pyherdr / pyte" from the global interpreter) and always runs
rem from the repo root (so the server + .pyherdr state are consistent no matter
rem where you call it from).
rem Usage (from anywhere):  pyherdr tui  |  pyherdr server start  |  pyherdr pane list
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pyherdr %*
