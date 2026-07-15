.PHONY: check check-fast check-schema check-behavior check-public-privacy check-release test export-sanitized export-sanitized-worktree export-sanitized-source-package

check:
	bash scripts/validate.sh

check-fast:
	CODEXQB_VALIDATE_SKIP_BEHAVIOR_SMOKE=1 bash scripts/validate.sh

check-schema:
	python3 scripts/validate_apply_schema.py
	python3 -m unittest -v tests.test_apply_schema

check-behavior:
	python3 evals/run_apply_behavior_smoke.py
	python3 evals/run_downstream_goal_apply_dry_run.py
	python3 evals/run_goal_apply_metric_checks.py

check-public-privacy:
	python3 scripts/check_public_privacy.py --root .

check-release: check check-public-privacy check-schema
	tmpdir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmpdir"' EXIT; \
	python3 scripts/export_sanitized.py --root . --output "$$tmpdir/CodexQB-sanitized.zip"; \
	python3 scripts/verify_package_manifest.py --zip "$$tmpdir/CodexQB-sanitized.zip"; \
	unzip -q "$$tmpdir/CodexQB-sanitized.zip" -d "$$tmpdir/extracted"; \
	cd "$$tmpdir/extracted/CodexQB" && CODEXQB_VALIDATE_SKIP_UNITTESTS=1 CODEXQB_VALIDATE_SKIP_BEHAVIOR_SMOKE=1 bash scripts/validate.sh

test:
	python3 -m unittest discover -s tests -v

export-sanitized:
	python3 scripts/export_sanitized.py --root . --output CodexQB-sanitized.zip

export-sanitized-worktree:
	python3 scripts/export_sanitized.py --root . --output CodexQB-sanitized.zip --include-untracked --allow-dirty --allow-head-mismatch

export-sanitized-source-package:
	python3 scripts/export_sanitized.py --root . --output CodexQB-source-package.zip --source-package
