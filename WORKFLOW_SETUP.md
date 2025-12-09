# Automated Schema Update Workflow - Setup Guide

## Overview

This repository now includes an automated GitHub Actions workflow that:
- ✅ Runs every Monday at 9:00 AM UTC
- ✅ Checks Synapse table `syn51730943` for new resourceType and resourceName values
- ✅ Automatically updates `SubmitObservationSchema.json` if changes are detected
- ✅ Creates a Pull Request with the changes for review

## Files Created

```
.github/workflows/
├── update-observation-schema.yml  # GitHub Actions workflow
└── README.md                      # Detailed workflow documentation

scripts/
└── update_observation_schema.py   # Python script to sync schema with Synapse
```

## 🚀 Setup Instructions

### Important Notes

#### GitHub Token (Required)
This workflow uses `NF_SERVICE_GIT_TOKEN` to create pull requests. Verify this secret is configured in your repository settings:
- Go to **Settings** → **Secrets and variables** → **Actions**
- Confirm `NF_SERVICE_GIT_TOKEN` exists
- If not, create a GitHub Personal Access Token with `repo` scope and add it

#### Synapse Authentication (Optional)
Since `syn51730943` is a **public table**, Synapse authentication is **optional**. The workflow will work without setting up `SYNAPSE_AUTH_TOKEN`.

You only need to set up a Synapse token if:
- The table becomes private in the future
- You hit rate limits (unlikely for weekly updates)
- You're adapting this for a private table

### Step 1: Push Changes to GitHub (Required)

```bash
# Add all new files
git add .github/workflows/update-observation-schema.yml \
        .github/workflows/README.md \
        scripts/update_observation_schema.py \
        WORKFLOW_SETUP.md

# Commit
git commit -m "Add automated schema update workflow from Synapse"

# Push to GitHub
git push origin observation-select-tool
```

### Step 2: Verify Setup (Optional)

Test the workflow manually:

1. Go to **Actions** tab in your GitHub repository
2. Click on **Update Observation Schema from Synapse** workflow
3. Click **Run workflow** dropdown
4. Select your branch
5. Click **Run workflow** button
6. Watch the workflow run - it should complete successfully

### Optional: Set Up NF_SERVICE_GIT_TOKEN (If Not Already Set)

If `NF_SERVICE_GIT_TOKEN` is not already configured in your repository:

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click **Generate new token** → **Generate new token (classic)**
3. Give it a descriptive name (e.g., "NF Service - Repository Access")
4. Select scopes:
   - ✅ `repo` (Full control of private repositories)
5. Click **Generate token** and copy it immediately
6. In your GitHub repository: **Settings** → **Secrets and variables** → **Actions**
7. Click **New repository secret**
8. Name: `NF_SERVICE_GIT_TOKEN`
9. Value: Paste the GitHub token
10. Click **Add secret**

### Optional: Set Up Synapse Authentication (Only if Needed)

If you need to set up a Synapse token later:

1. Log in to [Synapse.org](https://www.synapse.org/)
2. Navigate to **Account Settings** → **Personal Access Tokens**
3. Click **Create New Token**
4. Name it something descriptive (e.g., "GitHub Actions - Schema Updates")
5. Select scopes: `view` and `download`
6. Click **Create Token** and copy the token immediately
7. In your GitHub repository: **Settings** → **Secrets and variables** → **Actions**
8. Click **New repository secret**
9. Name: `SYNAPSE_AUTH_TOKEN`
10. Value: Paste the Synapse token
11. Click **Add secret**

## 📅 Schedule

The workflow runs:
- **Automatically:** Every Monday at 9:00 AM UTC
- **Manually:** Can be triggered anytime via GitHub Actions UI

To change the schedule, edit the cron expression in `.github/workflows/update-observation-schema.yml`:

```yaml
schedule:
  - cron: '0 9 * * 1'  # Current: Monday 9 AM UTC
```

**Common schedules:**
- Daily at midnight: `0 0 * * *`
- Every 6 hours: `0 */6 * * *`
- First of month: `0 0 1 * *`
- Fridays at 5 PM: `0 17 * * 5`

Use [crontab.guru](https://crontab.guru/) to create custom schedules.

## 🔄 How It Works

### When Changes Are Detected:

1. Script fetches latest data from `syn51730943`
2. Compares with current schema values
3. Updates schema with:
   - New resourceType enum values
   - Conditional resourceName enums (based on selected resourceType)
4. Creates a Pull Request with:
   - Branch name: `update-observation-schema-{run-number}`
   - Labels: `automated`, `schema-update`
   - Detailed description of changes
5. You review and merge the PR

### When No Changes:

1. Script runs successfully
2. Confirms schema is up-to-date
3. No PR is created
4. Workflow completes with success status

## 🧪 Testing Locally

Before the workflow runs on GitHub, you can test locally:

```bash
# Install dependencies
pip install synapseclient pandas

# Run the script (no authentication needed for public table syn51730943)
python scripts/update_observation_schema.py

# Check exit codes:
# 0 = Changes made successfully
# 2 = No changes needed
# 1 = Error occurred
```

**Optional:** If you need authentication (for private tables or rate limits):
```bash
# Set Synapse token via environment variable
export SYNAPSE_AUTH_TOKEN="your-token-here"

# Run the script
python scripts/update_observation_schema.py
```

## 🔍 What Gets Updated

The script updates these parts of `SubmitObservationSchema.json`:

1. **resourceType enum** - List of all resource types
   ```json
   "resourceType": {
     "enum": ["Animal Model", "Antibody", "Biobank", "Cell Line", "Genetic Reagent"]
   }
   ```

2. **Conditional resourceName enums** - Names filtered by type
   ```json
   "allOf": [
     {
       "if": {"properties": {"resourceType": {"const": "Antibody"}}},
       "then": {"properties": {"resourceName": {"enum": [...]}}}
     }
   ]
   ```

## 🛠️ Troubleshooting

### "Authentication failed" error

**Problem:** Synapse credentials not configured correctly (only relevant if using private tables)

**Solution:**
- For public table `syn51730943`, authentication is not required - you can safely ignore this
- If using a private table:
  - Verify `SYNAPSE_AUTH_TOKEN` secret is set in GitHub
  - Check token hasn't expired (regenerate if needed)
  - Ensure token has `view` and `download` permissions

### "Schema file not found" error

**Problem:** Script can't find the schema file

**Solution:**
- Verify file exists at: `NF-Tools-Schemas/observations/SubmitObservationSchema.json`
- Check repository structure hasn't changed
- Ensure script is run from repository root

### No PR created when changes expected

**Problem:** Workflow ran but didn't create a PR

**Solution:**
- Verify `NF_SERVICE_GIT_TOKEN` secret is set correctly in repository settings
- Check that the token has `repo` scope permissions and hasn't expired
- Check workflow logs in Actions tab for errors
- Verify workflow has correct permissions (contents: write, pull-requests: write)
- Ensure branch protection rules allow automated PRs

### Rate limiting from Synapse

**Problem:** Too many requests to Synapse

**Solution:**
- Default schedule (weekly) should be fine
- If running manually frequently, add delays between runs
- Check Synapse status page for any service issues

## 📊 Monitoring

### Check Workflow Status

1. Go to **Actions** tab
2. View **Update Observation Schema from Synapse** runs
3. Green checkmark = Success
4. Red X = Failed (click to view logs)

### Review PRs

- All automated PRs are labeled with: `automated` and `schema-update`
- Filter PRs by these labels to see all schema updates
- Review changes before merging

### Notifications

GitHub will notify you:
- When workflow fails
- When PR is created
- Configure notifications in GitHub Settings → Notifications

## 🔐 Security Notes

- ✅ No authentication required for public table `syn51730943`
- ✅ If using authentication: token is stored as an encrypted GitHub secret
- ✅ Token is only accessible during workflow runs (never exposed in logs)
- ✅ Token permissions are limited to view/download only
- ✅ All changes go through PR review before merging
- ✅ Workflow uses official GitHub actions

## 📝 Maintenance

### Update Dependencies

If Python dependencies need updating:

1. Edit workflow file: `.github/workflows/update-observation-schema.yml`
2. Update the `Install dependencies` step:
   ```yaml
   - name: Install dependencies
     run: |
       pip install synapseclient==3.2.0 pandas==2.1.0
   ```

### Change Synapse Table

To sync from a different table:

1. Edit `scripts/update_observation_schema.py`
2. Change line: `syn_id = 'syn51730943'`
3. Update to new table ID
4. Commit and push changes

### Disable Workflow

If you need to temporarily disable the workflow:

1. Go to **Actions** tab
2. Click **Update Observation Schema from Synapse**
3. Click the **⋯** menu
4. Select **Disable workflow**

To re-enable, follow same steps and select **Enable workflow**.

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Synapse Python Client Docs](https://python-docs.synapse.org/)
- [JSON Schema Specification](https://json-schema.org/)
- [Cron Expression Helper](https://crontab.guru/)

## ❓ Questions?

For questions or issues:
1. Check the [workflow README](.github/workflows/README.md) for detailed docs
2. Review workflow logs in the Actions tab
3. Open an issue in this repository
