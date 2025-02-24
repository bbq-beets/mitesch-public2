#!/bin/bash

# Get failed workflow runs and store them in a temporary JSON file
gh run list --workflow "npm seg fault" --status failure --limit 50 --json databaseId > failed_runs.json

# Parse the JSON and process each databaseId
jq -r '.[] | .databaseId' failed_runs.json | while read -r id; do
    echo "Processing run ID: $id"
    
    # Create directory and cd into it
    mkdir -p "$id"
    cd "$id" || exit
    
    # Save log output to log.txt
    gh run view --log "$id" > log.txt
    
    # Download artifacts
    gh run download "$id"
    
    # Return to parent directory
    cd ..
done

# Cleanup temporary JSON file
rm failed_runs.json
