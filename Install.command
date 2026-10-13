#!/usr/bin/env bash
# Double-click me once to install Narrated Slides Studio.
cd "$(dirname "$0")"
./setup.sh && { echo "Opening the Studio…"; exec ./studio.sh; }
echo; read -n 1 -s -r -p "Setup didn't finish — see the message above. Press any key to close."
