#!/bin/bash
# ---------------------------------------------------------------
#  build-mac.command
#  Builds the CBM Article Converter into a single .app.
#
#  Put this beside app.py and core.py and double-click it. It works
#  from any folder or drive and leaves the finished app in a "dist"
#  folder right here.
#
#  The first time, macOS may refuse to run it. Right-click the file,
#  choose Open, and confirm.
# ---------------------------------------------------------------

cd "$(dirname "$0")" || exit 1

show_log() {
    echo
    echo "  ---------------------------------------------------------------"
    echo "   The last 25 lines of the log:"
    echo "  ---------------------------------------------------------------"
    tail -n 25 "$LOG" 2>/dev/null
    echo "  ---------------------------------------------------------------"
    echo
    echo "   The whole log is saved here, ready to copy or send on:"
    echo "      $LOG"
    echo
    read -r -p "  Press Return to open it and close this window. "
    open -a TextEdit "$LOG" 2>/dev/null
}

echo
echo "  Building the CBM Article Converter"
echo "  Folder: $(pwd)"
echo

if [ ! -f app.py ] || [ ! -f core.py ]; then
    echo "  app.py and core.py must sit beside this file."
    echo "  Found here:"; ls -1 *.py 2>/dev/null
    echo; read -r -p "  Press Return to close. "; exit 1
fi

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
    echo "  Python 3 was not found."
    echo "  Install it from python.org, then run this again."
    echo; read -r -p "  Press Return to close. "; exit 1
fi

BUILD=$(grep '^VERSION = ' core.py | head -1 | cut -d'"' -f2)
[ -z "$BUILD" ] && BUILD="unknown"
APPNAME="CBM Article Converter $BUILD"

echo "  Version found: $BUILD"
echo "  Will produce: $APPNAME.app"
echo
LOG="$(pwd)/build-log.txt"
{ echo "Build log, $(date)"; echo "Folder: $(pwd)"; echo; } > "$LOG"

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "  This Python has no tkinter, so the window cannot open."
    echo "  Install Python from python.org and run this again."
    echo; read -r -p "  Press Return to close. "; exit 1
fi

echo "  Checking packages. This may take a minute the first time."
echo "  Everything is written to build-log.txt as it goes."
if ! "$PY" -m pip install --upgrade pyinstaller mammoth beautifulsoup4 >> "$LOG" 2>&1; then
    echo "  Could not install the packages needed to build."
    show_log; exit 1
fi

echo
echo "  Building. This takes a minute or two."
echo
if ! "$PY" -m PyInstaller --onefile --windowed --clean --noconfirm \
    --name "$APPNAME" --distpath "./dist" --workpath "./build" \
    --specpath "." --collect-all mammoth --argv-emulation \
    --add-data "USER-GUIDE.txt:." --add-data "HTML-REFERENCE.txt:." \
    --add-data "BUILD-NOTES.txt:." ./app.py >> "$LOG" 2>&1; then
    echo
    echo "  The build did not finish."
    show_log; exit 1
fi

rm -rf ./build "./$APPNAME.spec"

echo
echo "  ---------------------------------------------------------------"
echo "   Done."
echo
echo "   Your app:  dist/$APPNAME.app"
echo
echo "   A full log of the build is in build-log.txt."
echo
echo "   Copy it anywhere; it needs nothing installed. The first time"
echo "   it runs on a machine, macOS will refuse: right-click the app,"
echo "   choose Open, and confirm."
echo "  ---------------------------------------------------------------"
echo
open ./dist 2>/dev/null
read -r -p "  Press Return to close. "
