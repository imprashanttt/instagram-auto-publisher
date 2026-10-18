# Instagram Auto Publisher (Instagram Login API)

Starter for an Instagram **Creator/Business** account using Instagram Login (`graph.instagram.com`), without requiring a Facebook Page.

## Important
- This project does not generate AI content; it publishes media URLs you provide.
- Instagram must be able to fetch each image/video from a public HTTPS URL.
- First run is manual. Do not enable a schedule until a test publish succeeds.
- Keep `IG_ACCESS_TOKEN` and any other credentials in GitHub Actions Secrets only.
- The API access token may expire. Check its expiration and refresh/replace it before unattended runs.
- The API and permissions available to your app depend on Meta app mode, tester access, and granted permissions.

## 1. Add the files
Upload this ZIP's contents into the root of your GitHub repository, preserving the `.github/workflows/` folder.

## 2. Required GitHub repository secrets
- `IG_ACCESS_TOKEN`: the Instagram Login access token
- `IG_USER_ID`: Instagram professional account ID (`17841460852194064` if still the ID shown in your Meta dashboard)

## 3. Queue a post
Edit `queue/posts.json`. Example image and Reel entries are included but disabled. Replace `REPLACE_WITH_PUBLIC_HTTPS_URL` with a real public HTTPS URL, update the caption, then set `"enabled": true`.

Example:
```json
{
  "id": "unique-post-id",
  "type": "image",
  "media_url": "https://your-host.example/image.jpg",
  "caption": "Your caption",
  "enabled": true
}
```
Supported `type` values: `image`, `reel`. Only one enabled item is processed per run. The workflow marks it published in the queue and commits that state back to the repository after success. Do not manually rerun a workflow after an ambiguous network failure until you check Instagram; no remote API can guarantee exactly-once publishing across every timeout.

## 4. Test
In GitHub: **Actions → Instagram automation → Run workflow**. The workflow runs the queue publisher. It will fail safely if there is no enabled item.

## 5. Insights and comments
Run **Actions → Instagram automation → Run workflow** with the workflow's `task` input set to:
- `publish` (default)
- `insights`
- `comments`

Insights fetches available account/media metrics. Comments logs recent comments from your own media; it does not reply automatically.

## Permissions
Publishing requires `instagram_business_basic` and `instagram_business_content_publish`. Insights requires `instagram_business_manage_insights` (plus basic access). Comment reading requires `instagram_business_manage_comments` (plus basic access). Your app must have the appropriate access granted to the account.

## Media requirements
- Image posts: public JPEG URL.
- Reels: public HTTPS MP4 URL, accessible to Meta without login/cookies; use a compatible H.264/AAC MP4 where possible.
- URLs that expire quickly, require cookies, or block Meta's fetcher may fail.

## Security
Never print access tokens in logs. Do not add tokens to JSON files, source code, issues, or commits.
