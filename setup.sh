#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}[INFO] Checking Python installation...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}[WARN] python3 not found.${NC}"
    # Try to install python3 if possible? 
    # Usually strictly required. 
    echo -e "${RED}[ERROR] python3 is required to run this script. Please install it first.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED_VERSION="3.12"

# Minimal check (3.12 is just a soft target from Windows script, strict check might be annoying on older LTS)
# But let's at least check for 3.6+
echo -e "${GREEN}[OK] Found Python $PYTHON_VERSION${NC}"

echo -e "${CYAN}[INFO] Setting up Virtual Environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

echo -e "${CYAN}[INFO] Updating dependencies...${NC}"
pip install --upgrade pip --quiet
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt --quiet
fi
echo -e "${GREEN}[OK] Python environment ready.${NC}"

echo -e "${CYAN}[INFO] Handing over to installation script...${NC}"
echo -e "${CYAN}========================================================${NC}"
echo

python3 lib/main.py "$@"

EXIT_CODE=$?

echo
echo -e "${CYAN}========================================================${NC}"
echo

if [ $EXIT_CODE -ne 0 ]; then
    echo -e "${RED}[ERROR] Python script exited with error.${NC}"
    exit 1
fi

echo -e "${GREEN}[OK] Script finished successfully.${NC}"
