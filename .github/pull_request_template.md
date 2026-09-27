## What changes

<!-- What this pull request does and why. Link the ticket or issue. -->

## Privacy (build specification, section 3)

- [ ] No content reaches the admin app: no study material, notes, answers, pictures,
      document text, or message bodies other than support tickets.
- [ ] Any new field the admin API sends is added to `bff/app/contract.py` on purpose, and
      is on the list of what the admin app may show.
- [ ] Emails stay masked unless revealed with a reason; nothing new is logged that holds a
      query string, a request body, an email or a token.

## Security

- [ ] New `/bff` routes are in the role table (`bff/app/members.py`) and in
      `bff/tests/test_routes.py`.
- [ ] Every new admin action writes an audit row (in the admin API) with a reason where
      it changes something.
- [ ] No new third-party script, font, stylesheet or network call in the SPA.
- [ ] No secret, token or real person's data in the code, tests, fixtures or screenshots.

## Tests and rollout

- [ ] Tests cover the change (`pytest`, `npm test`, and `npm run e2e` for a new page).
- [ ] Deploy notes: new settings in SSM, backend changes it needs first, or "none".
- [ ] Rollback: redeploying the previous SHA undoes it, or the steps are written here.
