#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""site/demo-logbook.py: the logbook of the latest ./go demo on main (docs/adr/0089 §6).

    python3 site/demo-logbook.py <out file>

The ci workflow's engine-compat job runs ./go demo at L0 with no API key,
writes its logbook (.crew/logbook-demo.json) and uploads it in the
`console-snapshot` artifact. This walks main's last commits, newest
first, and for each takes the successful ci push runs of that commit on
any branch: main is fast-forwarded to a commit already judged on its
land branch, and ci on main does not judge it again (docs/adr/0065), so
the run with the demo is the land branch's (docs/adr/0089, amendment
2026-11-17). The first run that still has the artifact (a run that
skipped engine-compat has none) gives the logbook, written to <out file>;
it prints `<run id>\t<head sha>`.
Exit 1 with one line when there is none: the site does not link a
snapshot it could not build.

GITHUB_TOKEN (actions: read) and GITHUB_REPOSITORY from the workflow.
Standard library only; runs in the site workflow, not on the host.
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile

API = "https://api.github.com"
ARTIFACT = "console-snapshot"
MEMBER = "logbook-demo.json"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(url, token, raw=False):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "Accept": "application/vnd.github+json",
                                               "X-GitHub-Api-Version": "2022-11-28"})
    if not raw:
        with urllib.request.urlopen(req, timeout=60) as r:  # nosec B310 - the GitHub API, https
            return json.load(r)
    # The archive answers 302 to a signed URL: follow it without the token.
    try:
        urllib.request.build_opener(NoRedirect).open(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        with urllib.request.urlopen(e.headers["Location"], timeout=120) as r:  # nosec B310 - GitHub's signed https URL
            return r.read()
    raise RuntimeError(f"{url}: no redirect to the archive")


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python3 site/demo-logbook.py <out file>")
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY are not set")
        return 1
    commits = get(f"{API}/repos/{repo}/commits?sha=main&per_page=30", token)
    runs = [run for c in commits
            for run in get(f"{API}/repos/{repo}/actions/workflows/ci.yml/runs?head_sha={c['sha']}"
                           "&status=success&event=push&per_page=10", token)["workflow_runs"]]
    for run in runs:
        arts = get(f"{API}/repos/{repo}/actions/runs/{run['id']}/artifacts?name={ARTIFACT}", token)["artifacts"]
        arts = [a for a in arts if not a.get("expired")]
        if not arts:
            continue
        with zipfile.ZipFile(io.BytesIO(get(arts[0]["archive_download_url"], token, raw=True))) as z:
            names = [n for n in z.namelist() if n.endswith(MEMBER)]
            if not names:
                continue
            data = z.read(names[0])
        json.loads(data)
        with open(sys.argv[1], "wb") as f:
            f.write(data)
        print(f"{run['id']}\t{run['head_sha']}")
        return 0
    print(f"no successful ci run of main's last {len(commits)} commits has a {ARTIFACT} artifact with {MEMBER}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
