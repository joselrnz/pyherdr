# Release Checklist

Use this checklist before pushing a version tag. The release workflow publishes
to PyPI from tags matching `v*` through PyPI Trusted Publishing.

## Dry Run

1. Confirm the version.

   ```powershell
   .\.venv\Scripts\python.exe -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
   ```

   The `pyproject.toml` version, README badge, changelog heading, and tag must
   all describe the same release.

2. Confirm the changelog.

   Move relevant entries from `Unreleased` into the target version section and
   keep the notes user-facing. Do not copy internal porting logs into the public
   changelog.

3. Run mandatory validation.

   ```powershell
   .\.venv\Scripts\python.exe -m ruff check pyherdr tools tests
   .\.venv\Scripts\python.exe -m mypy
   .\.venv\Scripts\python.exe -m unittest discover -s tests
   .\.venv\Scripts\python.exe -m tools.docs_site --check
   ```

4. Build and inspect artifacts locally.

   ```powershell
   Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
   .\.venv\Scripts\python.exe -m build
   .\.venv\Scripts\python.exe -m twine check dist/*
   ```

5. Run the install/launch smoke.

   This creates a temporary virtual environment, installs the local package,
   verifies package metadata matches `pyherdr.__version__`, and launches the
   installed console script.

   ```powershell
   .\.venv\Scripts\python.exe tools\release_smoke.py
   ```

6. Commit the release prep.

   ```powershell
   git status --short
   git commit -m "Prepare vX.Y.Z release"
   ```

7. Create and push the tag only after validation is green.

   ```powershell
   git tag -a vX.Y.Z -m "PyHerdr vX.Y.Z"
   git push github main vX.Y.Z
   ```

8. Watch the publish workflow.

   The `.github/workflows/release.yml` workflow should build, run `twine check`,
   and publish to PyPI through Trusted Publishing.

9. Verify the published package.

   Check the PyPI project page, install in a clean environment, and run:

   ```powershell
   pyherdr --version
   pyherdr --help
   ```

## Abort Conditions

- Version, tag, README badge, or changelog disagree.
- Any validation command fails.
- `twine check` fails.
- The working tree includes `.venv/`, `.pyherdr/`, `.artifacts/`, caches, or
  generated build output.
