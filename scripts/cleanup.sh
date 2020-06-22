#!/bin/bash
# silently cleans up working directory from generated files
# uninstalls package automatically
# keeps venv

# uninstall elastic-migrate
pip uninstall -y elastic-migrate 1> /dev/null 2> /dev/null

# remove local build cache
rm -rf ./.eggs
rm -rf ./*.egg-info
rm -rf ./dist
rm -rf ./build
rm -rf ./logs

# remove test coverage cache
rm -rf ./.pytest_cache
rm -rf ./.tox
rm -f ./.coverage
