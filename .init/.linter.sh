#!/bin/bash
cd /home/kavia/workspace/code-generation/device-inventory-management-portal-179092-179101/inventario_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

