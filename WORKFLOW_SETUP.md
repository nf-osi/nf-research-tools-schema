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

### Step 1: Create Synapse Personal Access Token

1. Log in to [Synapse.org](https://www.synapse.org/)
2. Navigate to **Account Settings** → **Personal Access Tokens**
3. Click **Create New Token**
4. Name it something descriptive (e.g., "GitHub Actions - Schema Updates")
5. Select the following scopes:
   - ✅ `view` (required to query tables)
   - ✅ `download` (required to download query results)
6. Click **Create Token**
7. **IMPORTANT:** Copy the token immediately - you won't be able to see it again!

### Step 2: Add Token to GitHub Repository Secrets

1. Go to your GitHub repository
2. Click **Settings** tab
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret** button
5. Fill in:
   - **Name:** `SYNAPSE_AUTH_TOKEN`
   - **Secret:** Paste the Synapse token you copied in Step 1
6. Click **Add secret**

### Step 3: Push Changes to GitHub

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

### Step 4: Verify Setup (Optional)

Test the workflow manually:

1. Go to **Actions** tab in your GitHub repository
2. Click on **Update Observation Schema from Synapse** workflow
3. Click **Run workflow** dropdown
4. Select your branch
5. Click **Run workflow** button
6. Watch the workflow run - it should complete successfully

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

# Set Synapse token (Option 1: Environment variable)
export SYNAPSE_AUTH_TOKEN="your-token-here"

# Or Option 2: Config file
cat > ~/.synapseConfig <<EOF
[authentication]
authtoken = your-token-here
EOF

# Run the script
python scripts/update_observation_schema.py

# Check exit codes:
# 0 = Changes made successfully
# 2 = No changes needed
# 1 = Error occurred
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

**Problem:** Synapse credentials not configured correctly

**Solution:**
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

- ✅ Synapse token is stored as an encrypted GitHub secret
- ✅ Token is only accessible during workflow runs
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
