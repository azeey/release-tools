@echo on
set SCRIPT_DIR="%~dp0"

set VCS_DIRECTORY=ign-rendering
set PLATFORM_TO_BUILD=x86_amd64
set IGN_CLEAN_WORKSPACE=true
:: dlfcn
set DEPEN_PKGS="dlfcn"
:: This needs to be migrated to DSL to get multi-major versions correctly
set GAZEBODISTRO_FILE="ign-rendering0.yaml"

call "%SCRIPT_DIR%\lib\colcon-default-devel-windows.bat"
