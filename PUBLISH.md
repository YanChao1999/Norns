# Publish to PyPI

`pip install norns` is **already taken** (a YAML config library). This project publishes as **`norns-ide`**. The CLI is still `norns`.

```bash
pip install norns-ide
# or
uv tool install norns-ide
norns init
norns run
```

## Test first (TestPyPI)

1. Create an account on [test.pypi.org](https://test.pypi.org/account/register/).
2. Enable 2FA.
3. Add a **pending trusted publisher** at [TestPyPI publishing](https://test.pypi.org/manage/account/publishing/):
   - PyPI project name: `norns-ide`
   - Owner: `YanChao1999`
   - Repository: `Norns`
   - Workflow name: `publish.yml`
   - Environment name: `testpypi`
4. In GitHub: **Settings → Environments → New environment** named `testpypi`.
5. On the `feat/pip-uv-install` branch (or `main` after merge), run **Actions → Publish → Run workflow**, target `testpypi`.
6. Install from TestPyPI:

```bash
# Prefer: download the project wheel only from TestPyPI, then install deps from real PyPI
# (TestPyPI often has stub packages like a broken fastapi that break `-i test.pypi.org` installs.)
pip download --no-deps -i https://test.pypi.org/simple/ -d /tmp/norns-wheels 'norns-ide==0.0.3'
pip install /tmp/norns-wheels/norns_ide-*.whl
norns --version
```

Shorthand that sometimes works (deps may still resolve from TestPyPI first — prefer the download recipe above):

```bash
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ norns-ide
```

7. **Acceptance (lean real-user path)** — from a git checkout, after TestPyPI has the version you want:

```bash
# Install from TestPyPI into a throwaway venv, then:
# init → run → login → create board → sample card → preferences → logout
bash scripts/acceptance_testpypi.sh --version 0.0.3
```

Or in GitHub: **Actions → TestPyPI acceptance → Run workflow** (optional version pin, or build a wheel from the branch instead).

## Then production PyPI

1. Account on [pypi.org](https://pypi.org/account/register/) with 2FA.
2. Pending trusted publisher at [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/):
   - Project name: `norns-ide`
   - Owner: `YanChao1999`
   - Repository: `Norns`
   - Workflow: `publish.yml`
   - Environment: `pypi`
3. GitHub environment named `pypi` (optional: require reviewers).
4. Either:
   - **Actions → Publish → Run workflow**, target `pypi`, or
   - Create a GitHub Release (tag `v0.0.3`). A published release uploads to PyPI automatically.

Do not upload the same version twice. Bump `version` in `pyproject.toml` and `norns/__init__.py` for the next release.

No API token is stored in the repo. Trusted publishing uses GitHub OIDC (`id-token: write`).
