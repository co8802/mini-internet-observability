#!/bin/bash
SUZIEQ_BASE=".venv/lib/python3.9/site-packages/suzieq/config/"
cd $SUZIEQ_BASE
find . -type f -name "*.yml" -exec sed -i 's/sudo //g' {} +
