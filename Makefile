.PHONY: check test export-sanitized

check:
	bash scripts/validate.sh

test:
	python3 -m unittest discover -s tests -v

export-sanitized:
	python3 scripts/export_sanitized.py --root . --output CodexQB-sanitized.zip
