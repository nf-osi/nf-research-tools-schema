# GitHub Workflows

## Update Observation Schema

### Overview
This workflow automatically updates `SubmitObservationSchema.json` with the latest data from Synapse materialized view `syn51730943`.

**Workflow File:** `update-observation-schema.yml`

### Schedule
- **Runs:** Every Monday at 9:00 AM UTC
- **Can be triggered manually** via the GitHub Actions UI

### Required Secret

This workflow requires `NF_SERVICE_GIT_TOKEN` to be configured in repository secrets for creating pull requests. This should be a GitHub Personal Access Token with `repo` permissions.

### What It Does
1. Fetches unique `resourceType` and `resourceName` values from Synapse table `syn51730943`
2. Compares with current schema values
3. If changes are detected:
   - Updates the schema with new values
   - Creates conditional enums (resourceName depends on resourceType)
   - Creates a Pull Request with the changes
4. If no changes: Workflow completes successfully without creating a PR

### Setup Instructions

#### Required: GitHub Token for Pull Requests

The workflow requires `NF_SERVICE_GIT_TOKEN` to create pull requests:

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Verify that `NF_SERVICE_GIT_TOKEN` secret exists
4. If not, you'll need to:
   - Create a GitHub Personal Access Token with `repo` scope
   - Add it as a repository secret named `NF_SERVICE_GIT_TOKEN`

#### Optional: Synapse Authentication

**Note:** Since `syn51730943` is a public table, Synapse authentication is **optional**. You only need `SYNAPSE_AUTH_TOKEN` if:
- The table becomes private in the future
- You need higher rate limits
- You're adapting this workflow for a private table

To set up Synapse authentication:

1. Log in to [Synapse](https://www.synapse.org/)
2. Go to Account Settings → Personal Access Tokens
3. Click "Create New Token"
4. Give it a descriptive name (e.g., "GitHub Actions Schema Updates")
5. Select scopes: `view`, `download`
6. Copy the token (you won't be able to see it again!)
7. Go to your repository on GitHub
8. Click **Settings** → **Secrets and variables** → **Actions**
9. Click **New repository secret**
10. Name: `SYNAPSE_AUTH_TOKEN`
11. Value: Paste the Synapse token you copied
12. Click **Add secret**

#### Enable Workflow

Once `NF_SERVICE_GIT_TOKEN` is configured, the workflow is ready! It will run automatically every Monday at 9 AM UTC.

### Manual Trigger

To manually trigger the workflow:

1. Go to **Actions** tab in your repository
2. Select **Update Observation Schema from Synapse** workflow
3. Click **Run workflow** button
4. Select the branch and click **Run workflow**

### What Happens After a Run

#### If Changes Are Detected:
- A new Pull Request is created with branch name `update-observation-schema-{run-number}`
- PR includes details about what changed
- PR is labeled with `automated` and `schema-update`
- Review the PR and merge if changes look correct

#### If No Changes:
- Workflow completes successfully
- No PR is created
- Check workflow logs to confirm everything ran correctly

### Troubleshooting

#### Authentication Errors
If you see errors about Synapse authentication:
- **Note:** Authentication is not required for public table `syn51730943`
- If using a private table:
  - Verify `SYNAPSE_AUTH_TOKEN` secret is set correctly
  - Check token hasn't expired (regenerate if needed)
  - Ensure token has `view` and `download` permissions

#### Schema Update Errors
If the script fails to update the schema:
- Check workflow logs for detailed error messages
- Verify `syn51730943` table is still accessible
- Ensure schema file structure hasn't changed

#### No PR Created
If changes should exist but no PR is created:
- Verify `NF_SERVICE_GIT_TOKEN` secret is set correctly in repository settings
- Check that the token has `repo` scope permissions
- Verify workflow has `contents: write` and `pull-requests: write` permissions
- Check that the repository has PR permissions enabled
- Look at workflow logs for any git or PR creation errors

### Testing Locally

You can test the update script locally before pushing:

```bash
# Install dependencies
pip install synapseclient pandas

# Run the script (no authentication needed for public table)
python scripts/update_observation_schema.py
```

**Optional Authentication:** If you're testing with a private table or need higher rate limits:
```bash
# Set Synapse token via environment variable
export SYNAPSE_AUTH_TOKEN="your-token-here"

# Run the script
python scripts/update_observation_schema.py
```

### Customization

#### Change Schedule
Edit the `cron` expression in the workflow file:
```yaml
schedule:
  - cron: '0 9 * * 1'  # Minute Hour Day-of-Month Month Day-of-Week
```

Common schedules:
- Every Monday at 9 AM: `0 9 * * 1`
- Every day at midnight: `0 0 * * *`
- First day of month: `0 0 1 * *`
- Every 6 hours: `0 */6 * * *`

Use [crontab.guru](https://crontab.guru/) to test cron expressions.

#### Change Synapse Table
To sync from a different Synapse table, update the `syn_id` variable in `scripts/update_observation_schema.py`:
```python
syn_id = 'syn51730943'  # Change this to your table ID
```

### Related Files

- **Workflow:** `.github/workflows/update-observation-schema.yml`
- **Update Script:** `scripts/update_observation_schema.py`
- **Schema File:** `NF-Tools-Schemas/observations/SubmitObservationSchema.json`
