# Azure Web App Configuration for Disgram

## Git Installation Setup

To enable Git functionality for the Disgram application on Azure Web App, you need to configure the startup command.

### Steps:

1. **Go to Azure Portal** → Your Web App (`disgram`)

2. **Configure Environment Variables** in Configuration → Application Settings:
   
   **Required for Git functionality:**
   - **Name**: `GITHUB_TOKEN`
   - **Value**: `ghp_your_personal_access_token_here`
   
   - **Name**: `GITHUB_REPO_URL`
   - **Value**: `https://github.com/SimpNick6703/Disgram.git`
   
   - **Name**: `GITHUB_DEPLOY_BRANCH`
   - **Value**: `azure-prod`
   
   **Optional:**
   - **Name**: `LOG_COMMIT_INTERVAL`
   - **Value**: `2700` (45 minutes in seconds)

3. **Navigate to Configuration** → **General settings**

4. **Set Startup Command** to:
   ```bash
   bash start.sh
   ```

5. **Save** the configuration

6. **Restart** the Web App

### What the startup script does:

- ✅ Installs Git if not available
- ✅ Initializes Git repository if missing
- ✅ Configures GitHub remote using environment variables
- ✅ Sets up the correct deployment branch
- ✅ Configures Git with bot credentials
- ✅ Starts the Python application
- ✅ Gracefully handles Git unavailability

### Environment Variables Configuration

The application now uses environment variables for Git configuration, making it more flexible and secure:

- **`GITHUB_REPO_URL`**: Your repository URL (supports any GitHub repository)
- **`GITHUB_DEPLOY_BRANCH`**: The branch to deploy from (e.g., `main`, `azure-prod`, `production`)
- **`GITHUB_TOKEN`**: Personal access token for authentication
- **`LOG_COMMIT_INTERVAL`**: How often to commit log changes (in seconds)

### Alternative: Manual Git Installation

If the automatic installation doesn't work, you can try these approaches:

#### Option 1: Use SCM_DO_BUILD_DURING_DEPLOYMENT
Add this application setting:
- **Name**: `SCM_DO_BUILD_DURING_DEPLOYMENT`
- **Value**: `true`

#### Option 2: Use a Docker container
Consider switching to a container-based deployment with a custom Dockerfile that includes Git.

### Verification

After deployment, check the application logs to see:
- ✅ `Git available: git version 2.x.x` (success)
- ⚠️ `Warning: Git not available` (fallback mode)

The application will work in both cases, but Git commit functionality will only work when Git is available.