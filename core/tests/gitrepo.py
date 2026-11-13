"""A scratch git repository for the gates' tests: commit files, get shas."""

import os
import subprocess
import tempfile

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@t.invalid", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"):
    ENV.pop(k, None)


class Repo:
    def __init__(self, test):
        self.dir = tempfile.mkdtemp()
        test.addCleanup(subprocess.run, ["rm", "-rf", self.dir], check=False)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, check=True):
        return subprocess.run(["git", "-C", self.dir, *args], env=ENV, capture_output=True, text=True,
                              check=check).stdout.strip()

    def commit(self, files, message="c"):
        """Write FILES ({path: text, or None to delete}) and commit; the sha."""
        for rel, text in files.items():
            path = os.path.join(self.dir, rel)
            if text is None:
                os.remove(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")
