# Azure Web App Configuration for Disgram

## Git Installation Setup

To enable Git functionality for the Disgram application on Azure Web App, you need to configure the startup command.

### Steps:

1. **Go to Azure Portal** → Your Web App (`disgram`)

2. **Navigate to Configuration** → **General settings**

3. **Set Startup Command** to:
   ```bash
   bash startup.sh
   ```

4. **Save** the configuration

5. **Restart** the Web App

### What the startup script does:

- ✅ Attempts to install Git if not available
- ✅ Configures Git with bot credentials
- ✅ Starts the Python application
- ✅ Gracefully handles Git unavailability

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