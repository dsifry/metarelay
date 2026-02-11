# Metarelay Cloud Setup

Step-by-step instructions for setting up the Supabase backend and GitHub App.

> **Why run these commands from the metarelay repo?** The `cloud/supabase/` directory contains the Edge Function source code and database migration files. You deploy them to Supabase from here — this is a one-time infrastructure setup, not something that lives in your monitored repos. See [INSTALL.md](../INSTALL.md) for the full picture of how metarelay is structured.

## Prerequisites

- **[Supabase CLI](https://supabase.com/docs/guides/cli)** — see [install instructions](https://supabase.com/docs/guides/cli/getting-started#installing-the-supabase-cli) for your platform
- A Supabase account (free tier works)
- A GitHub account with admin access to target repos

## 1. Create Supabase Project

1. Go to https://supabase.com/dashboard and create a new project
2. Note your **Project URL** and **anon key** from Settings > API
3. Note your **service role key** (needed for Edge Function secrets)
4. Update `cloud/supabase/config.toml` with your project ID

## 2. Run Database Migration

Option A — Using Supabase CLI:
```bash
cd cloud/supabase
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

Option B — Using SQL Editor in Dashboard:
1. Go to SQL Editor in your Supabase dashboard
2. Copy and paste the contents of `migrations/20260210000000_create_events.sql`
3. Click "Run"

## 3. Verify Realtime

1. Go to Database > Replication in your Supabase dashboard
2. Confirm the `events` table is listed under "Realtime"
3. If not, run: `ALTER PUBLICATION supabase_realtime ADD TABLE events;`

## 4. Deploy Edge Function

```bash
cd cloud/supabase
supabase functions deploy github-webhook --no-verify-jwt
```

## 5. Set Edge Function Secrets

```bash
supabase secrets set GITHUB_WEBHOOK_SECRET=your-webhook-secret-here
```

The `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are automatically available to Edge Functions.

## 6. Create GitHub App

Option A — From manifest:
1. Go to https://github.com/settings/apps/new
2. Use the settings from `github-app/app.yml`

Option B — Manual creation:
1. Go to https://github.com/settings/apps/new
2. Set:
   - **App name**: Metarelay
   - **Homepage URL**: Your repo URL
   - **Webhook URL**: `https://YOUR-PROJECT.supabase.co/functions/v1/github-webhook`
   - **Webhook secret**: A random secret string (save this!)
3. Permissions (read-only):
   - Checks: Read
   - Pull requests: Read
   - Actions: Read
   - Metadata: Read
4. Subscribe to events:
   - Check runs
   - Check suites
   - Workflow runs
   - Pull request reviews
   - Pull request review comments
5. Click "Create GitHub App"

## 7. Install GitHub App

1. Go to your GitHub App's settings page
2. Click "Install App"
3. Select the repos you want to monitor
4. Click "Install"

## 8. Configure Webhook Secret

Make sure the same webhook secret is set in:
- GitHub App settings (Webhook secret field)
- Supabase secrets (`GITHUB_WEBHOOK_SECRET`)

## 9. Configure Local Daemon

Create `~/.metarelay/config.yaml`:
```yaml
cloud:
  supabase_url: "https://YOUR-PROJECT.supabase.co"
  supabase_key: "YOUR-ANON-KEY"

repos:
  - name: "your-org/your-repo"
    path: "/home/user/projects/your-repo"

handlers:
  - name: "pr-shepherd-ci-failure"
    event_type: "check_run"
    action: "completed"
    command: "claude -p 'Run /project:pr-shepherd for PR on {{ref}} in {{repo}}. Check {{summary}} concluded {{payload.conclusion}}.'"
    filters:
      - "payload.conclusion == 'failure'"
```

## 10. Test

1. Go to your GitHub App settings > Advanced > Recent Deliveries
2. Click "Redeliver" on any event, or push a commit to trigger a webhook
3. Check the Supabase dashboard > Table Editor > events to verify the event appeared
4. Run `metarelay sync -c ~/.metarelay/config.yaml -v` to test catch-up locally

### Test with curl

```bash
# Generate a test signature
SECRET="your-webhook-secret"
BODY='{"action":"completed","check_run":{"name":"build","conclusion":"failure","check_suite":{"head_branch":"feat/test"}},"repository":{"full_name":"owner/repo"},"sender":{"login":"testuser"}}'
SIG="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

curl -X POST \
  https://YOUR-PROJECT.supabase.co/functions/v1/github-webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: check_run" \
  -H "X-GitHub-Delivery: test-$(date +%s)" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
```
