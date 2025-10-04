#!/bin/bash

# Azure Web App startup script for Disgram
echo "Starting Disgram application setup..."

# Install Git (required for git_manager functionality)
echo "Installing Git..."
apt-get update -qq
apt-get install -y git

# Verify Git installation
if command -v git &> /dev/null; then
    echo "Git installed successfully: $(git --version)"
else
    echo "Warning: Git installation failed, but continuing..."
fi

#!/bin/bash

# Azure Web App startup script for Disgram
echo "Starting Disgram application..."

# Check if Git is available, try to install if not
if ! command -v git &> /dev/null; then
    echo "Git not found, attempting to install..."
    
    # Try to install git using available package managers
    if command -v apt-get &> /dev/null; then
        apt-get update -qq && apt-get install -y git
    elif command -v apk &> /dev/null; then
        apk update && apk add git
    elif command -v yum &> /dev/null; then
        yum install -y git
    else
        echo "Warning: Could not install Git - package manager not found"
        echo "Application will continue without Git functionality"
    fi
fi

# Verify and configure Git if available
if command -v git &> /dev/null; then
    echo "Git available: $(git --version)"
    git config --global user.name "Disgram Bot" 2>/dev/null || true
    git config --global user.email "disgram@bot.local" 2>/dev/null || true
    git config --global init.defaultBranch main 2>/dev/null || true
else
    echo "Warning: Git not available - Git commit functionality will be disabled"
fi

# Start the Python application
echo "Starting Disgram Python application..."
exec python main.py

# Start the Python application
echo "Starting Disgram Python application..."
python main.py