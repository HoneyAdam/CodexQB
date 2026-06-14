.PHONY: check export-sanitized

check:
	bash scripts/validate.sh

export-sanitized:
	git archive --format=zip --output CodexQB-sanitized.zip HEAD
