#!/bin/bash

# Azure Web App startup script for Disgram
echo "Starting Disgram application setup..."

# Check if Git is available, try to install if not
if ! command -v git &> /dev/null; then
    echo "Git not found, attempting to install..."
    
    # Try to install git using available package managers
    if command -v apt-get &> /dev/null; then
        echo "Installing Git with apt-get..."
        apt-get update -qq && apt-get install -y git
    elif command -v apk &> /dev/null; then
        echo "Installing Git with apk..."
        apk update && apk add git
    elif command -v yum &> /dev/null; then
        echo "Installing Git with yum..."
        yum install -y git
    else
        echo "Warning: Could not install Git - package manager not found"
        echo "Application will continue without Git functionality"
    fi
fi

# Install GitPython if needed
echo "Installing GitPython..."
pip install GitPython>=3.1.40

# Verify and configure Git if available
if command -v git &> /dev/null; then
    echo "Git available: $(git --version)"
    
    # Configure Git globally first
    DEFAULT_BRANCH=${GITHUB_DEPLOY_BRANCH:-azure-prod}
    git config --global user.name "Disgram Bot" 2>/dev/null || true
    git config --global user.email "disgram@bot.local" 2>/dev/null || true
    git config --global init.defaultBranch "$DEFAULT_BRANCH" 2>/dev/null || true
    
    # Check if we're in a Git repository
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "No Git repository found - initializing repository..."
        
        # Initialize Git repository
        git init .
        
        # Add GitHub remote if repository URL is available
        if [ ! -z "$GITHUB_REPO_URL" ]; then
            if [ ! -z "$GITHUB_TOKEN" ]; then
                echo "Adding GitHub remote with authentication..."
                # Extract repo path from URL and add token authentication
                REPO_PATH=$(echo "$GITHUB_REPO_URL" | sed 's|https://github.com/||')
                git remote add origin "https://${GITHUB_TOKEN}@github.com/${REPO_PATH}"
            else
                echo "Adding GitHub remote without authentication..."
                git remote add origin "$GITHUB_REPO_URL"
            fi
            
            # Try to fetch and checkout the deployment branch
            DEPLOY_BRANCH=${GITHUB_DEPLOY_BRANCH:-azure-prod}
            echo "Fetching ${DEPLOY_BRANCH} branch..."
            
            # Configure git pull strategy to avoid warnings
            git config pull.rebase false 2>/dev/null || true
            
            # Fetch all branches
            git fetch origin 2>/dev/null || echo "Could not fetch remote branches"
            
            # Checkout or create the deployment branch
            if git show-ref --verify --quiet "refs/remotes/origin/$DEPLOY_BRANCH"; then
                echo "Remote branch $DEPLOY_BRANCH exists, checking out..."
                git checkout -b "$DEPLOY_BRANCH" "origin/$DEPLOY_BRANCH" 2>/dev/null || git checkout "$DEPLOY_BRANCH" 2>/dev/null || true
                # Set upstream tracking
                git branch --set-upstream-to="origin/$DEPLOY_BRANCH" "$DEPLOY_BRANCH" 2>/dev/null || true
            else
                echo "Remote branch $DEPLOY_BRANCH not found, creating local branch..."
                git checkout -b "$DEPLOY_BRANCH" 2>/dev/null || git checkout "$DEPLOY_BRANCH" 2>/dev/null || true
            fi
        else
            echo "No GITHUB_REPO_URL found - Git operations will be local only"
        fi
        
        # Add current files to git
        git add . 2>/dev/null || true
        git commit -m "Initial commit from Azure deployment" 2>/dev/null || true
        
        echo "Git repository initialized successfully"
    else
        echo "Git repository already exists"
    fi
else
    echo "Warning: Git not available - Git commit functionality will be disabled"
fi

# Start the Python application
echo "Starting Disgram Python application..."
exec python main.py