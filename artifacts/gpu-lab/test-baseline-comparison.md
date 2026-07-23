# GPU Lab baseline comparison

- `origin/main`: `24e1230bbfbcf5543492395b91ae46f2e6459f6d`
- Feature branch HEAD after rebase: `24e1230bbfbcf5543492395b91ae46f2e6459f6d`
- Environment: repository `.venv`; command: `python -m pytest -q`

The exact repository-wide pytest command was run from an isolated detached
`origin/main` worktree. It exceeded the 60-second execution window before
pytest emitted a final collection/pass/fail summary. It was therefore not
possible to determine exact repository-wide counts or attribute introduced
failures honestly. No statement that existing failures are pre-existing is
made in this comparison.

Focused verification completed in the feature worktree:

- `python scripts/validate_nvidia_eval_pack.py`: passed.
- `python -m pytest tests/test_gpu_lab.py -q`: 27 passed.

No authenticated API or GPU request was issued.
