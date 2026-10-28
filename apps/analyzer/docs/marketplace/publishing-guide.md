# Publishing to GitHub Marketplace

Six steps from "nothing registered" to a listing that accepts installs. Review
usually takes **1–2 weeks**, and it is the only step you cannot rush.

## 1. Register the GitHub App

**Settings → Developer settings → GitHub Apps → New GitHub App.**

Fill in name, homepage URL, webhook URL and the four permissions listed in
[`github-app-manifest.md`](github-app-manifest.md). You can also register
directly from the manifest JSON via GitHub's "create from manifest" flow, which
pre-fills every field.

Prerequisites:

- an organisation account (Marketplace listings are published by an org, not a
  personal account);
- a verified domain for the homepage;
- a public HTTPS webhook endpoint that answers within 10 seconds.

## 2. Fill in the manifest

Use the JSON block from [`github-app-manifest.md`](github-app-manifest.md) and
replace the three placeholder URLs with your deployment. Keep the JSON in the
repository — when you later change permissions, the diff is your audit trail.

## 3. Publish to Marketplace

**App settings → Marketplace → Publish this App.**

GitHub asks for:

- the listing name and the short description (≤140 characters);
- the logo (PNG, at least 200×200, transparent background);
- the primary category;
- the plan: Vishap is a free, open-source app, so list it as **Free**.

You can draft the listing publicly as "unlisted" first and check the rendering
before submitting.

## 4. Complete the listing

Everything below lives in [`description.md`](description.md) — paste it in:

| Listing field | Source |
| --- | --- |
| Short description | `description.md` → Short description |
| Long description | `description.md` → Long description |
| Categories | Security, Code review, CI/CD |
| Pricing plan | Free |
| Screenshots | `screenshots/` — replace the three placeholders with real PNGs |
| Support URL / email | `support@vishap.dev` |
| Privacy policy URL | `https://dvddv9.github.io/vishap/docs/legal/privacy` |
| Terms of service URL | `https://dvddv9.github.io/vishap/docs/legal/terms` |

Every URL in the listing is checked by the reviewer and must return HTTP 200
**without a login redirect**. Deploy the docs site first, then fill the form.

## 5. Submit for review

**Marketplace → Submit for review.**

Expect 1–2 weeks. The most common reasons a listing bounces:

- a URL that 404s or redirects to a sign-in page;
- permissions broader than the description justifies;
- screenshots that show another product, or contain real customer data;

Respond to reviewer questions in the same thread; re-submission after a fix is
usually faster than the first pass.

## 6. After publish

- [ ] Install the app on a fresh test repository and confirm the PR comment.
- [ ] Verify webhook deliveries under **App settings → Advanced → Recent
      Deliveries** — a 401 there means signature verification is broken.
- [ ] Add the Marketplace badge to the project README.
- [ ] Watch the first week of reviews and install errors; a listing with no
      support response looks abandoned.

## Checklist before hitting submit

- [ ] Manifest URLs point at production, all HTTPS
- [ ] Webhook verifies `X-Hub-Signature-256`
- [ ] Permissions are exactly the four listed
- [ ] Listing text pasted, no lorem ipsum
- [ ] Three real screenshots, no customer data
- [ ] Privacy policy and ToS return 200
- [ ] Publish-to-Marketplace toggle enabled
- [ ] Plan set to Free
