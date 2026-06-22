.PHONY: check check-fast check-behavior check-public-privacy check-release test export-sanitized export-sanitized-worktree

check:
	bash scripts/validate.sh

check-fast:
	CODEXQB_VALIDATE_SKIP_BEHAVIOR_SMOKE=1 bash scripts/validate.sh

check-behavior:
	python3 evals/run_apply_behavior_smoke.py
	python3 evals/run_downstream_goal_apply_dry_run.py
	python3 evals/run_goal_apply_metric_checks.py

check-public-privacy:
	python3 scripts/check_public_privacy.py --root .

check-release: check check-public-privacy export-sanitized
	tmpdir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmpdir"' EXIT; \
	unzip -q CodexQB-sanitized.zip -d "$$tmpdir"; \
	cd "$$tmpdir/CodexQB" && bash scripts/validate.sh

test:
	python3 -m unittest discover -s tests -v

export-sanitized:
	python3 scripts/export_sanitized.py --root . --output CodexQB-sanitized.zip

export-sanitized-worktree:
	python3 scripts/export_sanitized.py --root . --output CodexQB-sanitized.zip --include-untracked --allow-dirty --allow-head-mismatch
