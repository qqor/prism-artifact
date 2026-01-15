#!/bin/bash

# Build Docker image from repository root to include all necessary files
cd "$(dirname "$0")/../.." || exit 1

docker build -f scripts/eval/Dockerfile -t afc_benchmark .
