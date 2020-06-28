#!/bin/bash
# Export all variables from `.env` file Run all tests with coverage
export "$(xargs < .env)"
py.test --cov esmigrate --cov-report term-missing
