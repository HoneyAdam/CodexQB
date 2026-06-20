.PHONY: check test export-sanitized

check:
	bash scripts/validate.sh

test:
	python3 -m unittest discover -s tests -v

export-sanitized:
	git diff --quiet
	git diff --cached --quiet
	git archive --format=zip --prefix=CodexQB/ --output CodexQB-sanitized.zip HEAD
