# Deploying AnotherNote Admin

How the admin console reaches `https://admin.anothernote.app`: the one-time setup, then
what every release takes (one command), how to check it, and how to roll back. Section 7
of the build specification is the plan; this is the procedure.

## The shape

```
 Staff browser ── https://admin.anothernote.app
      │   Cloudflare Access: single sign-on + multi-factor, 8-hour session
      ▼
 Cloudflare ── Tunnel (the box dials out; no port is open on it) ──┐
                                                                   ▼
 ┌─ the AnotherNote EC2 box ─ compose project "anothernote-admin", /opt/anothernote-admin ─┐
 │  cloudflared ──(edge)──▶ admin-web :8080   the SPA and the BFF: checks the Access       │
 │                              │            token and the member list, signs each call   │
 │                              │ (admin: internal, no way out)                             │
 │                              ▼                                                           │
 │                         admin-api :8001   the backend image running app.admin_main: no  │
 │                              │            encryption key, listens on "admin" only      │
 └──────────────────────────────│───────────────────────────────────────────────────────────┘
                                │ (playstudy_default: the public stack's network)
                                ▼
            postgres, as the role an_admin_api (views only) · redis
```

Around it: secrets in SSM Parameter Store (`/anothernote/prod/admin/`), images in ECR
(`anothernote-admin`, one immutable tag per commit), logs in CloudWatch
(`/anothernote/admin`).

**Why a compose project of its own**, rather than services added to the backend's
`deploy/aws/docker-compose.yml` as 7.1 sketches: the backend's `deploy-aws.sh` runs
`docker compose up --remove-orphans` in `/opt/playstudy`, which deletes every container of
that project its own file does not define, so an override there would be removed by the
next backend deploy; and changing the networks of postgres and redis there would recreate
them on every deploy of either repository. The separate project changes nothing in the
public stack, can be deployed and rolled back on its own, and moves to its own host
(7.4) as it is.

## Before you start

- **The backend's phases 1 and 2 are deployed**: `/opt/playstudy/backend/app/admin_main.py`
  exists, and the Appendix A migration has run (the role `an_admin_api`, the `admin_*`
  views and functions). `deploy.sh` refuses to start without the first.
- **On your machine**: the AWS CLI v2, signed in as yourself (with multi-factor), allowed
  to write SSM parameters under `/anothernote/prod/admin/` and, for the one-time steps,
  to manage IAM, ECR and CloudWatch Logs; git; the box's SSH key, as for the backend's
  `deploy-aws.sh` (`PS_DEPLOY_KEY`, `PS_DEPLOY_HOST` or `PS_INSTANCE_ID`).
- **On the box**: Docker Compose 2.17 or later (`docker compose version`) and the AWS
  CLI v2 (Amazon Linux 2023 has it).
- **Cloudflare**: the `anothernote.app` zone and a Zero Trust organisation (the free plan
  covers 50 users).

Commands below use these; set them once in your shell:

```bash
REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
P=/anothernote/prod/admin
```

## One-time setup

### 1. The database role

The Appendix A migration creates `an_admin_api` without a password. Give it one, and set
the pepper the email-lookup view uses. The values travel over SSH on standard input, so
they are in no command line on the box, and Postgres does not log them (unless
`log_statement` was changed from its default, `none`):

```bash
DB_PASSWORD=$(openssl rand -hex 24)
PEPPER=$(openssl rand -hex 32)
printf "ALTER ROLE an_admin_api LOGIN PASSWORD '%s';\nALTER DATABASE playstudy_db SET app.admin_lookup_pepper = '%s';\n" \
  "$DB_PASSWORD" "$PEPPER" |
  ssh -i ~/.ssh/playstudy-turnstile.pem ec2-user@<box address> \
    'cd /opt/playstudy && docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U playstudy_user -d playstudy_db'
```

Keep `DB_PASSWORD` and `PEPPER` for step 2, then unset them.

### 2. Secrets and settings in SSM

Every setting of the admin services lives under `/anothernote/prod/admin/`; the box reads
them at each deploy (`deploy/render-env.sh`) and nobody copies them by hand. SSM keeps
every version of every parameter, and CloudTrail records who changed it.

```bash
put() { aws ssm put-parameter --region "$REGION" --name "$P/$1" --type "$2" --value "$3" --overwrite > /dev/null && echo "set $P/$1"; }

put ADMIN_DATABASE_URL  SecureString "postgresql://an_admin_api:${DB_PASSWORD}@postgres:5432/playstudy_db"
put ADMIN_LOOKUP_PEPPER SecureString "$PEPPER"
put ADMIN_SERVICE_TOKEN SecureString "$(openssl rand -hex 32)"
put ADMIN_SIGNING_KEY   SecureString "$(openssl rand -hex 32)"
put ADMIN_MEMBERS       SecureString "you@anothernote.app:owner,colleague@anothernote.app:support"
put ADMIN_WEB_IMAGE     String       "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/anothernote-admin"
unset DB_PASSWORD PEPPER
# after steps 6 and 7:
put CLOUDFLARE_TUNNEL_TOKEN SecureString "<the tunnel's token>"
put CF_ACCESS_TEAM_DOMAIN   String       "<team>.cloudflareaccess.com"
put CF_ACCESS_AUD           String       "<the Access application's AUD tag>"
```

Values may not contain a quote or a backslash (the deploy refuses them rather than
mangle them); the generated ones never do. `ADMIN_MEMBERS` is `email:role` pairs, roles
`owner`, `support`, `analyst` or `viewer` (build specification 5.8.3).

Optional, with their defaults: `ADMIN_REDIS_URL` (`redis://redis:6379/0`),
`ADMIN_PUBLIC_ORIGIN` (`https://admin.anothernote.app`), `ADMIN_IDLE_LOCK_MINUTES` (15),
`ADMIN_IDLE_SIGNOUT_MINUTES` (60), `ADMIN_LOG_GROUP` (`/anothernote/admin`),
`BACKEND_DIR` (`/opt/playstudy/backend`), `PLAYSTUDY_NETWORK` (`playstudy_default`),
`AWS_REGION` (the box's own).

### 3. The image registry, and the role GitHub releases with

ECR keeps every release, and its tags cannot be overwritten, so a SHA always means the
same image:

```bash
aws ecr create-repository --region "$REGION" --repository-name anothernote-admin \
  --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true
aws ecr put-lifecycle-policy --region "$REGION" --repository-name anothernote-admin --lifecycle-policy-text \
  '{"rules":[{"rulePriority":1,"description":"keep the last 100 releases","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":100},"action":{"type":"expire"}}]}'
```

GitHub pushes to it through OIDC, with no AWS key stored anywhere:

1. If the account has no GitHub provider yet: IAM > Identity providers > Add provider >
   OpenID Connect, URL `https://token.actions.githubusercontent.com`, audience
   `sts.amazonaws.com`.
2. A role, `anothernote-admin-release`, that only this repository's `main` can assume:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": { "Federated": "arn:aws:iam::<ACCOUNT>:oidc-provider/token.actions.githubusercontent.com" },
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": { "StringEquals": {
         "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
         "token.actions.githubusercontent.com:sub": "repo:Ifthikar20/Another-note-admin:ref:refs/heads/main"
       } }
     }]
   }
   ```

   and may only push to that one repository:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
       { "Effect": "Allow",
         "Action": ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"],
         "Resource": "arn:aws:ecr:<REGION>:<ACCOUNT>:repository/anothernote-admin" }
     ]
   }
   ```

3. In the GitHub repository: Settings > Secrets and variables > Actions > Variables:
   `AWS_ROLE_TO_ASSUME` (the role's ARN), `AWS_REGION`, `ECR_REPOSITORY`
   (`anothernote-admin`). From then on, every push to `main` that passes CI is released.

### 4. What the box may do

The box reads its settings, pulls the image and writes logs with its instance role, so no
credential is stored on it. Add this policy to the role (IAM > Roles > the box's role >
Add permissions > Create inline policy). If the instance has no role yet, create one for
EC2 and attach it (EC2 > the instance > Actions > Security > Modify IAM role).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "AdminSettings", "Effect": "Allow", "Action": "ssm:GetParametersByPath",
      "Resource": ["arn:aws:ssm:<REGION>:<ACCOUNT>:parameter/anothernote/prod/admin",
                   "arn:aws:ssm:<REGION>:<ACCOUNT>:parameter/anothernote/prod/admin/*"] },
    { "Sid": "EcrSignIn", "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
    { "Sid": "AdminImage", "Effect": "Allow", "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
      "Resource": "arn:aws:ecr:<REGION>:<ACCOUNT>:repository/anothernote-admin" },
    { "Sid": "AdminLogs", "Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:<REGION>:<ACCOUNT>:log-group:/anothernote/admin:*" }
  ]
}
```

It cannot write parameters, push images or read anything else. With a customer-managed
KMS key on the parameters, also allow `kms:Decrypt` on that key (the default `aws/ssm`
key needs nothing more).

Then require IMDSv2 and keep the metadata service one hop away, so containers cannot
borrow the instance role (first check that no container on the box needs it):

```bash
aws ec2 modify-instance-metadata-options --region "$REGION" --instance-id <the box> \
  --http-tokens required --http-put-response-hop-limit 1
```

### 5. Logs that outlive the box

```bash
aws logs create-log-group --region "$REGION" --log-group-name /anothernote/admin
aws logs put-retention-policy --region "$REGION" --log-group-name /anothernote/admin --retention-in-days 400
```

Four hundred days keeps a full year of evidence with room to spare. Every container of
the project writes there (the `awslogs` driver in `deploy/docker-compose.yml`), one stream
per container. The BFF writes one JSON line per request (method, path without its query,
status, time taken, member, role, request id) and a warning for every refusal. The audit
log of record is the admin API's `admin_audit_log` table (one row per request, kept a
year); these logs are the second record, and the one that says how requests went.

### 6. Cloudflare Tunnel

Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared, named
`anothernote-admin`. On the install page, copy the token (the long value after
`--token`) into SSM as `CLOUDFLARE_TUNNEL_TOKEN`; do not run the install command, the
`cloudflared` container is the connector. Then add a public hostname: subdomain `admin`,
domain `anothernote.app`, service `HTTP`, URL `admin-web:8080`. Cloudflare adds the DNS
record (a CNAME to the tunnel). There must be no other record for `admin.anothernote.app`,
and none that points at the box's address.

### 7. Cloudflare Access

Zero Trust > Access > Applications > Add an application > Self-hosted:

- Name `AnotherNote Admin`, domain `admin.anothernote.app`, session duration 8 hours.
- Identity provider: Google Workspace (add it first under Settings > Authentication) or,
  failing that, one-time PIN.
- One policy, `Staff`: Allow; Include: Emails, exactly the people in `ADMIN_MEMBERS`;
  Require multi-factor: an "Authentication method: MFA" rule where the identity provider
  reports it, and in any case 2-Step Verification enforced in Google Workspace for these
  accounts.
- Copy the application's AUD tag into SSM as `CF_ACCESS_AUD`, and the team domain
  (`<team>.cloudflareaccess.com`, under Settings) as `CF_ACCESS_TEAM_DOMAIN`.

The BFF checks both again on every request, and answers 403 to anyone Access lets in who
is not in `ADMIN_MEMBERS`: the two lists must agree, and both change together
([RUNBOOKS.md](RUNBOOKS.md), "Add a member").

### 8. GitHub

In the repository settings, a branch protection rule (or ruleset) for `main`:

- require a pull request with one approval, from a code owner, and dismiss approvals
  when new commits arrive;
- require these checks to pass, on an up-to-date branch: `BFF (Python 3.11)`,
  `BFF (Python 3.13)`, `Web app`, `End to end (Playwright)`,
  `Image (build, scan, SBOM)`, `Secret scan (gitleaks)`;
- no bypass, administrators included; no force pushes, no deletion.

And under Code security: Dependabot alerts and security updates on; secret scanning with
push protection where the plan offers it. Everyone with write access uses two-factor
sign-in on GitHub.

## Release and deploy

1. Merge the pull request. CI runs on `main`; its Release job builds the image, scans it,
   pushes `…/anothernote-admin:<sha>`, and prints the deploy command in the run's summary.
2. From a clone of this repository:

   ```bash
   ./deploy/deploy-aws.sh <sha>
   ```

   It refuses a commit that is not on `origin/main`, installs that commit's
   `deploy/docker-compose.yml`, `render-env.sh` and `deploy.sh` in `/opt/anothernote-admin`
   (root's, mode 0700), and runs `sudo deploy.sh <sha>` on the box, which:
   - writes the settings from SSM (a new file, which replaces `.env` only if the deploy
     works, so `.env` always describes what runs);
   - pulls the image and `cloudflared` (pinned), and rebuilds the admin API from
     `/opt/playstudy/backend`;
   - starts what changed and waits up to three minutes for the health checks;
   - fails if any container publishes a port;
   - appends a line to `/opt/anothernote-admin/deploys.log` (time, who, SHA, image
     digest, `ok` or `failed`) and writes the same record, as JSON, to the `deploys`
     stream of the log group, where it outlives the box. On a failure it prints the
     rollback command.

The first deploy is the same command, once steps 1 to 8 are done.

## Check it

After the first deploy, and after any change to Cloudflare or the networks (this is the
phase 4 acceptance of the specification):

- In a private window, `https://admin.anothernote.app` asks for the Cloudflare sign-in and
  the second factor, then shows the console with its amber ADMIN strip.
- Someone Access lets in who is not in `ADMIN_MEMBERS` gets "Not an admin member" (403):
  add a colleague to the Access policy only, try, then take them out again.
- From outside, nothing answers: `curl -m 5 http://<box address>:8080/` and `:8001` fail.
- `ssh … sudo /opt/anothernote-admin/deploy.sh --status`: three containers, admin-web and
  admin-api healthy, no published ports.
- A student ticket appears in the Tickets inbox within seconds.
- CloudWatch Logs has the streams `anothernote-admin-web`, `anothernote-admin-api` and
  `anothernote-cloudflared`, and Zero Trust > Logs > Access shows your sign-in.

## After every backend deploy

The admin API is the backend's code. After the backend deploys, rebuild it so the two
never run different versions against the same database:

```bash
./deploy/deploy-aws.sh --status          # the admin SHA running now
./deploy/deploy-aws.sh <that SHA>        # same admin-web, admin API rebuilt from the new backend
```

A change to a view's columns or to the admin API belongs in the same backend release as
the matching change here. (Worth doing later in playstudy-backend: have its
`deploy-aws.sh` run this step itself.)

## Roll back

```bash
./deploy/deploy-aws.sh <an earlier SHA>
```

`deploys.log` on the box (and `--status`) lists what ran; ECR keeps the last hundred
releases. This rolls back admin-web; the admin API follows the backend, so rolling it back
means rolling back the backend.

## Operate

- **Find what happened to a request**: staff see "Reference 1f0c2d9e" on errors. In
  CloudWatch Logs Insights, on `/anothernote/admin`:

  ```
  fields @timestamp, level, message, actor, status, request_id
  | filter request_id like /^1f0c2d9e/
  ```

  The same id is the `request_id` of the audit row, on the Audit page.
- **Refusals** (no Access token, not a member, cross-site attempts):

  ```
  filter logger = "bff.request" and level = "WARNING"
  | stats count() by reason, actor
  ```

- **Alarms**: turn the log lines into metrics and alarm on them, for example:

  ```bash
  aws logs put-metric-filter --region "$REGION" --log-group-name /anothernote/admin --filter-name admin-refused \
    --filter-pattern '{ $.logger = "bff.request" && $.level = "WARNING" }' \
    --metric-transformations metricName=Refused,metricNamespace=AnotherNote/Admin,metricValue=1,defaultValue=0
  aws logs put-metric-filter --region "$REGION" --log-group-name /anothernote/admin --filter-name admin-5xx \
    --filter-pattern '{ $.status >= 500 }' \
    --metric-transformations metricName=ServerErrors,metricNamespace=AnotherNote/Admin,metricValue=1,defaultValue=0
  TOPIC=$(aws sns create-topic --region "$REGION" --name anothernote-admin-alerts --query TopicArn --output text)
  aws sns subscribe --region "$REGION" --topic-arn "$TOPIC" --protocol email --notification-endpoint <the owner's address>
  aws cloudwatch put-metric-alarm --region "$REGION" --alarm-name anothernote-admin-refusals \
    --namespace AnotherNote/Admin --metric-name Refused --statistic Sum --period 300 --evaluation-periods 1 \
    --threshold 20 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching \
    --alarm-actions "$TOPIC"
  ```

  and the same for `ServerErrors` (threshold 5, say).
- **Members, secrets, incidents**: [RUNBOOKS.md](RUNBOOKS.md).

## Later

Build specification 7.4: move admin-web and the admin API to their own small host (or
ECS), reading a Postgres read replica once the product is on RDS. The compose project
moves nearly as it is: the database address in `ADMIN_DATABASE_URL` changes, and the
external `playstudy` network gives way to the host's route to the replica.
