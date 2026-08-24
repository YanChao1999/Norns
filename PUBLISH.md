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
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ norns-ide
norns --version
```

`--extra-index-url` is required so dependencies still come from real PyPI.

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
   - Create a GitHub Release (tag `v0.0.1`). A published release uploads to PyPI automatically.

Do not upload the same version twice. Bump `version` in `pyproject.toml` and `norns/__init__.py` for the next release.

No API token is stored in the repo. Trusted publishing uses GitHub OIDC (`id-token: write`).
