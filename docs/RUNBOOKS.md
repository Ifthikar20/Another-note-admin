# Runbooks

What to do, step by step, for the things that happen to an admin console. Each one says
what to keep as evidence. Commands use the settings of [DEPLOY.md](DEPLOY.md) (`REGION`,
`P=/anothernote/prod/admin`) and a clone of this repository.

"Redeploy what runs" below means:

```bash
./deploy/deploy-aws.sh --status        # the SHA running now
./deploy/deploy-aws.sh <that SHA>      # the same version, with the settings read again from SSM
```

## Add a member, or change a role

1. Get the request approved by the owner, in writing (a ticket or an email). Choose the
   smallest role that does the job:

   | Role | Can |
   |---|---|
   | viewer | the overview, usage and cost, the Activity overview and errors, users (masked), plans, organisations, and tickets, read only |
   | analyst | the same as viewer, without tickets |
   | support | the same as viewer, plus answering tickets, revealing an email (with a reason), signing someone out everywhere, a person's sign-in events and tickets, security, and a person's activity log |
   | owner | everything: also changing plans, deactivating and reactivating accounts, the audit log, and settings |

2. Add their email to the Access policy `Staff` (Zero Trust > Access > Applications >
   AnotherNote Admin > Policies).
3. Update the member list in SSM, whole: every `email:role` pair, comma separated. The
   old list stays in the parameter's history.

   ```bash
   aws ssm get-parameter --region "$REGION" --name "$P/ADMIN_MEMBERS" --with-decryption --query Parameter.Value --output text
   aws ssm put-parameter --region "$REGION" --name "$P/ADMIN_MEMBERS" --type SecureString --overwrite \
     --value "owner@anothernote.app:owner,sam@anothernote.app:support,new@anothernote.app:viewer"
   ```

4. Redeploy what runs.
5. Check: they can sign in, and Settings > Members shows them with the right role.

Keep: the approval, and the date it took effect.

## Remove a member

The same day they leave, or no longer need it.

1. Remove their email from the Access policy, then end their session: Zero Trust > Users
   (or My Team > Users) > the person > Revoke session.
2. Remove their pair from `ADMIN_MEMBERS` in SSM, and redeploy what runs. From then on the
   BFF answers 403 to them even if Access let them through.
3. Suspend their Google Workspace account (the offboarding checklist does this).
4. If they could read secrets (SSM, the box, a laptop copy of anything), rotate those
   secrets (below).

Keep: the date and time of each step.

## The quarterly access review

1. The owner opens Settings > Access review and downloads the CSV: every member, their
   role, and their last action and its time.
2. Compare it with the Access policy's emails, Google Workspace, the GitHub
   collaborators, the AWS people who can read `/anothernote/prod/admin/` or reach the box,
   and the SSH keys on the box.
3. Remove whoever no longer needs access; lower a role nobody used in the quarter.
4. Save the CSV in the evidence folder with the date, what changed, and the owner's
   sign-off.

## Rotate a secret

Every secret is in SSM, and the containers read them at deploy time.

- **`ADMIN_SERVICE_TOKEN`, `ADMIN_SIGNING_KEY`**: shared by admin-web and the admin API,
  which a deploy restarts together.

  ```bash
  aws ssm put-parameter --region "$REGION" --name "$P/ADMIN_SERVICE_TOKEN" --type SecureString --overwrite --value "$(openssl rand -hex 32)"
  aws ssm put-parameter --region "$REGION" --name "$P/ADMIN_SIGNING_KEY" --type SecureString --overwrite --value "$(openssl rand -hex 32)"
  ```

  Then redeploy what runs. A request made while the containers restart may fail once.
- **The database password**: as in DEPLOY.md step 1 (the `ALTER ROLE` line only), then
  `ADMIN_DATABASE_URL` in SSM with the new password, then redeploy what runs.
- **The tunnel token**: in Zero Trust > Networks > Tunnels, create a new tunnel with the
  same public hostname, put its token in SSM, redeploy what runs, check, and delete the old
  tunnel.
- **`ADMIN_LOOKUP_PEPPER`**: only if it leaked. Change it in the database
  (`ALTER DATABASE … SET app.admin_lookup_pepper`, DEPLOY.md step 1) and in SSM together,
  then redeploy what runs.

Rotate the first two once a year even if nothing happened, and at once if anyone who
could read them leaves or a copy may have leaked. Keep: the date, and which secret.

## A staff account is compromised, or a laptop is lost

1. Remove the member (above), at once: revoke the Access session first.
2. In Google Workspace: suspend the account, sign it out everywhere, reset the password
   and the second factor, revoke its app tokens.
3. See what the account did: the Audit page filtered by that actor (and its CSV export),
   the CloudWatch logs by `actor` (DEPLOY.md, "Operate"), and the Cloudflare Access logs
   (when and from where it signed in).
4. If it revealed emails or changed accounts, treat it as a security incident (below).
5. Rotate every secret the person could read.

## A security incident

1. **Declare it.** Whoever notices tells the security owner, who opens an incident
   record: when, who reported it, what was seen.
2. **Contain it.** Remove access (above). If the console itself is the problem, take it
   offline: on the box, `sudo docker compose -p anothernote-admin stop`, or remove
   everyone from the Access policy. Rotate what may have leaked.
3. **Investigate.** The audit log, the CloudWatch logs (every request has an id that is
   also on its audit row), the Cloudflare Access logs, CloudTrail. Save the queries and
   their results in the incident record before anything expires.
4. **Fix and recover** through the normal change process: pull request, review, CI,
   release, deploy. When it cannot wait, deploy first and complete the review
   afterwards, and write down why.
5. **Notify.** If student data may have been exposed, the security owner and counsel
   decide who must be told and by when: schools under their contracts and FERPA,
   parents for children's data (COPPA), and state breach-notification laws.
6. **Review.** Within two weeks: what happened, why, and what changes; track each change
   to done.

## "Something went wrong" on a staff member's screen

1. Ask for the reference on the message ("Reference 1f0c2d9e").
2. In CloudWatch Logs Insights, on `/anothernote/admin`:

   ```
   fields @timestamp, level, message, actor, status, request_id
   | filter request_id like /^1f0c2d9e/
   ```

3. The line says which route failed and how. The admin API's own log line and the audit
   row carry the same id (the Audit page's "Request" column shows the same eight
   characters).

## The console is down

1. `./deploy/deploy-aws.sh --status`: are all three containers up, and healthy?
2. Zero Trust > Networks > Tunnels: is the `anothernote-admin` connector healthy?
3. On the box: `sudo docker logs --since 30m anothernote-admin-web` (and
   `anothernote-admin-api`, `anothernote-cloudflared`).
4. By message:
   - "Sign-in cannot be checked right now" (503): the BFF cannot fetch Cloudflare
     Access's keys; check the box's outbound HTTPS.
   - "The admin API refused this app's credentials": the token or signing key differ
     between the two containers (redeploy what runs), or the clocks differ by more than a
     minute (`chronyc tracking` on the box).
   - "The admin API is not reachable right now": the admin API is down or restarting;
     see its log.
5. Redeploy what runs; if a release caused it, roll back:
   `./deploy/deploy-aws.sh <the previous SHA>`.
