from __future__ import annotations

import importlib.util
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "plugins/codexqb/skills/codexqb/scripts/safety_contracts.py"
SPEC = importlib.util.spec_from_file_location("codexqb_safety_contracts", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
SAFETY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SAFETY)

OUTPUT_SHA256 = "a" * 64


def command(argv: list[str], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "VAL-01",
        "argv": argv,
        "cwd": ".",
        "expected_exit_code": 0,
        "timeout_seconds": 120,
        "network": "deny",
        "probe_tier": 1,
    }
    payload.update(overrides)
    return payload


class SafetyContractsTests(unittest.TestCase):
    def synthetic_secret_fixtures(self) -> list[tuple[str, str, str]]:
        return [
            ("openrouter", "openrouter_api_key", "sk-" + "or-v1-" + "A" * 32),
            ("openai", "openai_api_key", "sk-" + "B" * 40),
            ("github_fine_grained", "github_pat", "github_" + "pat_" + "C" * 32),
            ("github_classic", "github_legacy_pat", "gh" + "p_" + "D" * 32),
            ("anthropic", "anthropic_api_key", "sk-" + "ant-api03-" + "E" * 40),
            ("huggingface", "huggingface_token", "hf" + "_" + "F" * 32),
            ("gitlab", "gitlab_token", "gl" + "pat-" + "G" * 32),
            ("stripe", "stripe_secret_key", "sk" + "_live_" + "H" * 32),
            ("stripe_webhook", "stripe_webhook_secret", "wh" + "sec_" + "I" * 32),
            ("google_api", "google_api_key", "AI" + "za" + "J" * 35),
            ("google_client", "google_oauth_client_secret", "GOC" + "SPX-" + "K" * 32),
            ("google_access", "google_oauth_access_token", "ya" + "29." + "L" * 32),
            ("aws_access", "aws_access_key", "AK" + "IA" + "M" * 16),
            (
                "aws_secret",
                "aws_secret_access_key",
                "AWS_" + "SECRET_ACCESS_KEY=" + "N" * 40,
            ),
            ("aws_session", "aws_session_token", "AWS_" + "SESSION_TOKEN=" + "O" * 48),
            ("slack", "slack_token", "xox" + "b-" + "P" * 32),
            ("slack_app", "slack_app_token", "xapp" + "-" + "Q" * 32),
            (
                "slack_webhook",
                "slack_webhook",
                "https://hooks." + "slack.com/services/" + "R" * 10 + "/" + "S" * 10 + "/" + "T" * 32,
            ),
            ("jwt", "jwt", "eyJ" + "U" * 12 + "." + "V" * 16 + "." + "W" * 20),
            ("private_key", "private_key", "-----BEGIN " + "PRIVATE KEY-----"),
            ("provider_assignment", "provider_credential_assignment", "HF_" + "TOKEN=" + "X" * 32),
            ("generic_assignment", "generic_credential_assignment", "password=" + "Y" * 32),
            (
                "punctuated_password",
                "generic_credential_assignment",
                'password="P@ssw0rd!' + "Z" * 16 + '"',
            ),
            ("bearer", "authorization_bearer", "Authorization: Bearer " + "a" * 32),
            ("basic", "authorization_basic", "Authorization: Basic " + "dXNlcjpwYXNz"),
            ("uri", "uri_userinfo_credential", "postgres://user:" + "p" * 16 + "@example.invalid/db"),
        ]

    def test_secret_families_are_detected_redacted_and_never_echoed(self) -> None:
        for provider, expected, fixture in self.synthetic_secret_fixtures():
            with self.subTest(provider=provider):
                findings = SAFETY.secret_findings(fixture)
                self.assertIn(expected, findings)
                locations = SAFETY.secret_match_locations(fixture)
                self.assertTrue(any(name == expected for name, _ in locations))
                if fixture in repr(locations):
                    self.fail(f"finding metadata leaked fixture for {provider}")

                try:
                    SAFETY.assert_safe_persistent_text(fixture)
                except ValueError as exc:
                    message = str(exc)
                    if fixture in message:
                        self.fail(f"persistent rejection leaked fixture for {provider}")
                    self.assertIn(expected, message)
                else:
                    self.fail(f"persistent write accepted fixture for {provider}")

                redacted = SAFETY.redact_secret_like(fixture)
                if fixture in redacted:
                    self.fail(f"redaction leaked fixture for {provider}")
                self.assertIn("<redacted:", redacted)

                diagnostic = SAFETY.safe_log_text("failure=" + fixture + "\nnext")
                if fixture in diagnostic:
                    self.fail(f"safe log leaked fixture for {provider}")
                self.assertNotIn("\n", diagnostic)

    def test_secret_scanner_limits_input_and_never_truncates_to_pass(self) -> None:
        with mock.patch.object(SAFETY, "MAX_SECRET_SCAN_CHARACTERS", 64):
            oversized = "Z" * 65
            self.assertEqual(SAFETY.secret_findings(oversized), ["secret_scan_input_too_large"])
            with self.assertRaisesRegex(ValueError, "persistent_artifact_secret_rejected=secret_scan_input_too_large"):
                SAFETY.assert_safe_persistent_text(oversized)
            self.assertEqual(SAFETY.safe_log_text(oversized), "<redacted:unsafe-diagnostic>")

    def test_secret_scanner_preserves_documentation_placeholders_and_common_safe_shapes(self) -> None:
        safe_values = [
            "task-spec.yaml",
            "skill-specific",
            "sk-abc",
            "github_" + "pat_<redacted>",
            "sk-" + "ant-api03-<redacted>",
            "hf_token",
            "HF_TOKEN=${HF_TOKEN}",
            "gl" + "pat-<redacted>",
            "pk" + "_live_" + "A" * 48,
            "sk" + "_live_<redacted>",
            "AI" + "za<redacted>",
            "AIDA" + "B" * 16,
            "AWS_" + "SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}",
            "xox" + "b-<redacted>",
            "1.2.3",
            "header.payload.signature",
            "BEGIN PRIVATE KEY",
            "a" * 64,
            "password=<redacted>",
            "OPENROUTER_" + "API_KEY=your_openrouter_api_key",
        ]
        for index, value in enumerate(safe_values):
            with self.subTest(case=index):
                self.assertEqual(SAFETY.secret_findings(value), [])

    def test_safe_json_serialization_rejects_nested_secret_without_echoing_it(self) -> None:
        fixture = "sk-" + "Z" * 40
        try:
            SAFETY.serialize_safe_persistent_json(
                {"actor": "worker", "summary": {"evidence": [fixture]}},
            )
        except ValueError as exc:
            message = str(exc)
            if fixture in message:
                self.fail("safe JSON rejection leaked fixture")
            self.assertIn("openai_api_key", message)
        else:
            self.fail("safe JSON serialization accepted nested secret")

    def test_semantic_json_escape_and_duplicate_keys_fail_closed(self) -> None:
        fixture = "sk-" + "A" * 40
        escaped = "sk-" + "\\u0041" * 40
        payloads = [
            '{"summary":"' + escaped + '"}',
            '{"summary":"' + escaped + '","summary":"safe"}',
        ]
        for index, payload in enumerate(payloads):
            with self.subTest(case=index):
                try:
                    SAFETY.parse_safe_persistent_json(payload)
                except ValueError as exc:
                    if fixture in str(exc):
                        self.fail(f"semantic JSON rejection leaked fixture for case {index}")
                else:
                    self.fail(f"semantic JSON accepted escaped or duplicate fixture for case {index}")

    def test_utf16_embedded_secret_is_rejected_before_base64(self) -> None:
        fixture = "gl" + "pat-" + "U" * 32
        encoded = fixture.encode("utf-16-le")
        try:
            SAFETY.assert_safe_embedded_content_bytes(encoded)
        except ValueError as exc:
            if fixture in str(exc):
                self.fail("UTF-16 rejection leaked fixture")
            self.assertIn("gitlab_token", str(exc))
        else:
            self.fail("UTF-16 embedded secret was accepted")

    def test_assignment_placeholders_must_match_exactly(self) -> None:
        safe_values = [
            'OPENAI_API_KEY=""',
            'HF_TOKEN="${HF_TOKEN}"',
            'GITHUB_TOKEN="<redacted>"',
            'OPENAI_API_KEY="your_openai_api_key"',
            "password=YOUR_PASSWORD",
            "OPENAI_API_KEY=<redacted:openai_api_key>",
            "password=<redacted:generic_credential_assignment>",
            "postgres://user:<redacted>@example.invalid/db",
            "https://user:placeholder@example.invalid/",
        ]
        for index, value in enumerate(safe_values):
            with self.subTest(safe=index):
                self.assertEqual(SAFETY.secret_findings(value), [])

        suffix = "S" * 24
        unsafe_values = [
            ("provider_credential_assignment", "OPENAI_API_KEY=${OPENAI_API_KEY}" + suffix),
            ("provider_credential_assignment", "OPENAI_API_KEY=YOUR_OPENAI_API_KEY" + suffix),
            ("provider_credential_assignment", "OPENAI_API_KEY=<redacted>" + suffix),
            ("aws_secret_access_key", "AWS_SECRET_ACCESS_KEY=<redacted>" + suffix),
            ("aws_session_token", "AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}" + suffix),
            ("generic_credential_assignment", "password=<redacted>" + suffix),
            ("generic_credential_assignment", "password=<redacted>," + suffix),
            ("generic_credential_assignment", "password=${PASSWORD}," + suffix),
            ("generic_credential_assignment", "password=YOUR_PASSWORD," + suffix),
            ("generic_credential_assignment", "password=placeholder," + suffix),
            ("generic_credential_assignment", 'password="<redacted>"' + suffix),
            ("generic_credential_assignment", "password='${PASSWORD}'" + suffix),
            (
                "uri_userinfo_credential",
                "postgres://user:<redacted>@" + suffix + "@example.invalid/db",
            ),
        ]
        for expected, value in unsafe_values:
            with self.subTest(finding=expected):
                self.assertIn(expected, SAFETY.secret_findings(value))

    def test_contextual_common_credential_names_are_covered_without_policy_false_positives(self) -> None:
        fixtures = [
            ("generic_credential_assignment", "MY_API_KEY=" + "A" * 32),
            ("generic_credential_assignment", "DATABASE_PASSWORD=" + "B" * 32),
            ("generic_credential_assignment", "GITHUB_CLIENT_SECRET=" + "C" * 40),
            ("aws_secret_access_key", '{"SecretAccessKey":"' + "D" * 40 + '"}'),
            ("aws_session_token", '{"SessionToken":"' + "E" * 48 + '"}'),
            ("provider_credential_assignment", "SLACK_SIGNING_SECRET=" + "F" * 32),
            ("generic_credential_assignment", "SERVICE_API_KEY_PROD=" + "G" * 32),
            ("generic_credential_assignment", '"databasePassword":"' + "H" * 32 + '"'),
            ("generic_credential_assignment", '"myApiKey":"' + "I" * 32 + '"'),
            ("generic_credential_assignment", '"githubClientSecret":"' + "J" * 40 + '"'),
            ("provider_credential_assignment", '"slackSigningSecret":"' + "K" * 32 + '"'),
            ("provider_credential_assignment", '"openaiApiKey":"' + "L" * 32 + '"'),
            ("generic_credential_assignment", "SECRET_KEY=" + "M" * 40),
            ("generic_credential_assignment", "DJANGO_SECRET_KEY=" + "N" * 40),
            ("generic_credential_assignment", "SECRET_KEY_BASE=" + "O" * 40),
            ("generic_credential_assignment", "APP_SECRET=" + "P" * 40),
            ("generic_credential_assignment", "PRIVATE_TOKEN=" + "Q" * 40),
        ]
        for expected, fixture in fixtures:
            with self.subTest(expected=expected):
                self.assertIn(expected, SAFETY.secret_findings(fixture))
                diagnostic = SAFETY.safe_log_text(fixture)
                self.assertNotIn(fixture, diagnostic)

        safe_controls = [
            "MY_API_KEY=${MY_API_KEY}",
            "DATABASE_PASSWORD=<redacted>",
            "PASSWORD_POLICY=strict",
            "CLIENT_SECRET_ROTATION_DAYS=30",
            "API_KEY_FORMAT=uuid",
            '"databasePassword":"${databasePassword}"',
            '"openaiApiKey":"$openaiApiKey"',
            "{password: <redacted>, next: value}",
            "password: <redacted>,",
            "PASSWORD=${PASSWORD}; export PASSWORD",
            'password = "<redacted>".',
        ]
        for fixture in safe_controls:
            with self.subTest(safe=fixture):
                self.assertEqual(SAFETY.secret_findings(fixture), [])

    def test_human_readable_and_provider_credential_labels_are_covered(self) -> None:
        fixtures = [
            ("generic_credential_assignment", "API Key: " + "A" * 32),
            ("generic_credential_assignment", "Client Secret: " + "B" * 32),
            ("generic_credential_assignment", "Access Token: " + "C" * 32),
            ("generic_credential_assignment", '{"api key":"' + "D" * 32 + '"}'),
            ("aws_secret_access_key", "AWS Secret Access Key: " + "E" * 40),
            ("aws_session_token", "AWS Session Token: " + "F" * 48),
            ("provider_credential_assignment", "OpenAI API Key: " + "G" * 32),
            ("provider_credential_assignment", "GitHub Token: " + "H" * 32),
            ("provider_credential_assignment", "Slack Signing Secret: " + "I" * 32),
            ("provider_credential_assignment", "Google Client Secret: " + "J" * 32),
            ("aws_secret_access_key", "Secret Access Key: " + "K" * 40),
            ("aws_secret_access_key", "secret_access_key=" + "L" * 40),
            ("aws_session_token", "Session Token: " + "M" * 48),
            ("aws_session_token", "session_token=" + "N" * 48),
        ]
        for expected, fixture in fixtures:
            with self.subTest(expected=expected, fixture=fixture[:24]):
                self.assertIn(expected, SAFETY.secret_findings(fixture))

        safe_placeholders = [
            "API Key: ${API_KEY}",
            "Client Secret: YOUR_CLIENT_SECRET",
            "AWS Secret Access Key: ${AWS_SECRET_ACCESS_KEY}",
            "Session Token: <redacted>",
            '"Google Client Secret":"${GOOGLE_CLIENT_SECRET}"',
        ]
        for fixture in safe_placeholders:
            with self.subTest(safe=fixture):
                self.assertEqual(SAFETY.secret_findings(fixture), [])

    def test_structured_and_adjacent_credential_contexts_fail_closed(self) -> None:
        secret = "S" * 40
        fixtures = [
            "| AWS Secret Access Key | " + secret + " |",
            "AWS Secret Access Key -> " + secret,
            "AWS Secret Access Key => " + secret,
            "AWS Secret Access Key — " + secret,
            '["AWS Secret Access Key","' + secret + '"]',
            '{"headers":[["AWS Secret Access Key","' + secret + '"]]}',
            '{"name":"AWS_SECRET_ACCESS_KEY","value":"' + secret + '"}',
            '{"key":"AWS Secret Access Key","value":"' + secret + '"}',
            '{"credential_name":"AWS Secret Access Key","credential_value":"' + secret + '"}',
            '{"env":[{"secretName":"AWS Secret Access Key","secretValue":"' + secret + '"}]}',
            "- name: AWS_SECRET_ACCESS_KEY\n  value: " + secret,
            "credential_name: AWS Secret Access Key\ncredential_value: " + secret,
            "Credential: AWS Secret Access Key\nValue: " + secret,
            '{"name":"Authorization","value":"Bearer ' + secret + '"}',
        ]
        for index, fixture in enumerate(fixtures):
            with self.subTest(case=index):
                self.assertTrue(SAFETY.secret_findings(fixture))
                with self.assertRaises(ValueError):
                    SAFETY.assert_safe_persistent_text(fixture)
                self.assertNotIn(secret, SAFETY.safe_log_text(fixture))

        safe_placeholders = [
            "| AWS Secret Access Key | ${AWS_SECRET_ACCESS_KEY} |",
            '["AWS Secret Access Key","${AWS_SECRET_ACCESS_KEY}"]',
            '{"name":"AWS_SECRET_ACCESS_KEY","value":"<redacted>"}',
            "- name: AWS_SECRET_ACCESS_KEY\n  value: YOUR_AWS_SECRET_ACCESS_KEY",
        ]
        for fixture in safe_placeholders:
            with self.subTest(safe=fixture):
                self.assertEqual(SAFETY.secret_findings(fixture), [])

    def test_prefixed_non_json_and_duplicate_structured_contexts_never_leak(self) -> None:
        secret = "V" * 40
        fixtures = [
            'failure={"name":"AWS_SECRET_ACCESS_KEY","value":"' + secret + '"}',
            "failure={'name':'AWS_SECRET_ACCESS_KEY','value':'" + secret + "'}",
            "name=AWS_SECRET_ACCESS_KEY,value=" + secret,
            "credential_name: AWS Secret Access Key, credential_value: " + secret,
            'failure=["AWS Secret Access Key","' + secret + '"]',
            '{"name":"AWS_SECRET_ACCESS_KEY","value":"'
            + secret
            + '","name":"safe","value":"safe"}',
            '{"name":"AWS_SECRET_ACCESS_KEY","value":"'
            + "\\u0056" * 40
            + '","name":"safe","value":"safe"}',
            'failure={broken ["AWS Secret Access Key","' + secret + '"]',
            'failure={"outer":["AWS Secret Access Key","' + secret + '"]',
            "failure=['AWS Secret Access Key','" + secret + "']",
            "headers=[('AWS Secret Access Key','" + secret + "')]",
            "failure=('AWS Secret Access Key','" + secret + "')",
            "failure=('password', b'hunter2')",
            "failure=('API_KEY', u'abcd1234')",
            "failure=('password', r'letmein123')",
            "headers=[(b'Authorization', b'Basic dXNlcjpwYXNz')]",
            "failure=('password', bytearray(b'hunter2'))",
            "failure=('password', bytes(b'hunter2'))",
            "password='''hunter2'''",
            'API_KEY="""abcd1234"""',
            "failure=('password', '''hunter2''')",
            "failure=('password', `hunter2`)",
        ]
        for index, fixture in enumerate(fixtures):
            with self.subTest(case=index):
                self.assertTrue(SAFETY.secret_findings(fixture))
                diagnostic = SAFETY.safe_log_text(fixture)
                self.assertNotIn(secret, diagnostic)
                self.assertNotIn("\\u0056" * 8, diagnostic)

        safe_pairs = [
            "['AWS Secret Access Key','${AWS_SECRET_ACCESS_KEY}']",
            "AWS Secret Access Key documentation",
            "| AWS Secret Access Key | <redacted> |",
            "PASSWORD is required.",
            "OPENAI_API_KEY must be supplied via the environment.",
            "failure=('password', `<redacted>`)",
        ]
        for fixture in safe_pairs:
            with self.subTest(safe=fixture):
                self.assertEqual(SAFETY.secret_findings(fixture), [])

    def test_oversized_structured_context_fails_before_large_node_traversal(self) -> None:
        with mock.patch.object(SAFETY, "MAX_STRUCTURED_CONTEXT_INPUT_CHARACTERS", 128):
            payload = "[" + ",".join("0" for _ in range(100)) + "]"
            for fixture in (payload, "prefix=" + payload, "failure={\"payload\":" + payload + "}"):
                with self.subTest(prefix=fixture[:8]):
                    self.assertIn("secret_scan_structured_context_input_limit", SAFETY.secret_findings(fixture))
                    with self.assertRaises(ValueError):
                        SAFETY.assert_safe_persistent_text(fixture)

    def test_high_cardinality_lines_and_fields_fail_closed_without_materializing_lists(self) -> None:
        with mock.patch.object(SAFETY, "MAX_MARKUP_TOKENS", 32):
            self.assertIn("secret_scan_structured_context_limit", SAFETY.secret_findings("|" * 1000))
            self.assertIn(
                "secret_scan_structured_context_limit",
                SAFETY.secret_findings("name:x," * 1000),
            )
        self.assertIn(
            "secret_scan_structured_context_limit",
            SAFETY.secret_findings("\n" * 10_000),
        )

    def test_detector_labels_are_safe_diagnostics_not_credential_assignments(self) -> None:
        for label in ("openai_api_key", "openrouter_api_key", "provider_credential_assignment"):
            diagnostic = f"secret_pattern={label}::Planner-docs/leak.md:1"
            with self.subTest(label=label):
                self.assertEqual(SAFETY.secret_findings(diagnostic), [])
                self.assertEqual(SAFETY.safe_log_text(diagnostic), diagnostic)

    def test_malformed_markup_scans_scale_linearly(self) -> None:
        def elapsed(value: str) -> float:
            started = time.perf_counter()
            self.assertIn(
                SAFETY.secret_findings(value),
                ([], ["secret_scan_semantic_expansion_limit"]),
            )
            return time.perf_counter() - started

        for prefix in ("<a", "[", "[x]("):
            with self.subTest(prefix=prefix):
                small = elapsed(prefix * 2_000)
                large = elapsed(prefix * 8_000)
                self.assertLess(large, small * 8 + 0.25)

    def test_renderer_visible_entities_and_terminal_controls_fail_closed(self) -> None:
        fixture = "sk-" + "R" * 40
        entity_encoded = "".join(f"&#{ord(character)};" for character in fixture)
        ansi_split = fixture[:7] + "\x1b[31m" + fixture[7:]
        zero_width_split = fixture[:7] + "\u200b" + fixture[7:]
        for label, disguised in (
            ("html_entity", entity_encoded),
            ("ansi", ansi_split),
            ("zero_width", zero_width_split),
        ):
            with self.subTest(label=label):
                self.assertIn("openai_api_key", SAFETY.secret_findings(disguised))
                with self.assertRaises(ValueError):
                    SAFETY.assert_safe_persistent_text(disguised)

        with self.assertRaises(ValueError):
            SAFETY.serialize_safe_persistent_json({"actor": ansi_split})
        diagnostic = SAFETY.safe_log_text("failure=" + ansi_split)
        self.assertNotIn(fixture, diagnostic)
        self.assertNotIn("\x1b", diagnostic)

    def test_renderer_controls_bidi_and_markdown_markup_cannot_reassemble_a_secret(self) -> None:
        fixture = "sk-" + "T" * 40
        prefix, suffix = fixture[:8], fixture[8:]
        disguised_values = [
            prefix + "\u009d0;hidden\u009c" + suffix,
            prefix + "\x1b%@" + suffix,
            "sk-@\b" + "T" * 40,
            "\u202e" + fixture[::-1] + "\u202c",
            prefix + "<!--hidden-->" + suffix,
            prefix + "<span></span>" + suffix,
            "sk-**" + "T" * 40 + "**",
            "sk-[" + "T" * 40 + "](https://example.invalid)",
            "sk-*" + "T" * 40 + "*",
            "sk\\-" + "T" * 40,
            "github\\_pat_" + "T" * 40,
            "hf\\_" + "T" * 40,
            prefix + '<span title="x>y"></span>' + suffix,
            prefix + "<span hidden>;</span>" + suffix,
            prefix + '<span style="display:none">;</span>' + suffix,
            prefix + "<script>;</script>" + suffix,
            prefix + "<template>;</template>" + suffix,
            prefix + "\ufe0f" + suffix,
            prefix + "\u034f" + suffix,
            prefix + "\U000e0100" + suffix,
            prefix + "\u3164" + suffix,
            prefix + "\u2065" + suffix,
        ]
        for index, disguised in enumerate(disguised_values):
            with self.subTest(case=index):
                self.assertTrue(SAFETY.secret_findings(disguised))
                with self.assertRaises(ValueError):
                    SAFETY.assert_safe_persistent_text(disguised)
                diagnostic = SAFETY.safe_log_text(disguised)
                self.assertNotIn(fixture, diagnostic)
                self.assertFalse(any(ord(character) == 0x1B for character in diagnostic))

    def test_structured_authorization_headers_are_scanned_with_key_value_context(self) -> None:
        fixtures = [
            {"Authorization": "Bearer " + "U" * 40},
            {"headers": {"authorization": "Basic " + "V" * 24}},
            {"Proxy-Authorization": "Bearer " + "W" * 40},
        ]
        for index, payload in enumerate(fixtures):
            with self.subTest(case=index):
                with self.assertRaises(ValueError):
                    SAFETY.serialize_safe_persistent_json(payload)

        safe_headers = [
            {"Authorization": "Bearer <redacted>"},
            {"authorization": "none"},
        ]
        for payload in safe_headers:
            SAFETY.serialize_safe_persistent_json(payload)

        diagnostic_fixture = "Bearer " + "X" * 40
        diagnostic = SAFETY.safe_log_text(
            'failure={"Authorization":"' + diagnostic_fixture + '"}'
        )
        self.assertNotIn(diagnostic_fixture, diagnostic)

    def test_nested_reversible_escapes_are_rejected_in_diagnostics(self) -> None:
        fixture = "sk-" + "A" * 40
        nested = "sk-" + ("\\u005c\\u00750041" * 40)
        escaped = "sk-" + ("\\u0041" * 40)
        for value in (escaped, nested):
            with self.subTest(depth=value.count("\\u005c")):
                self.assertIn("openai_api_key", SAFETY.secret_findings(value))
                diagnostic = SAFETY.safe_log_text("failure=" + value)
                self.assertNotIn(value, diagnostic)
                self.assertNotIn(fixture, diagnostic)

    def test_oversized_credential_contexts_fail_closed_and_logs_never_leak_the_tail(self) -> None:
        long_assignment_value = "Q" * 5000
        long_uri_value = "R" * 600
        fixtures = [
            ("generic_credential_assignment", 'password="' + long_assignment_value + '"', long_assignment_value[-128:]),
            (
                "uri_userinfo_credential",
                "postgres://user:" + long_uri_value + "@example.invalid/db",
                long_uri_value[-128:],
            ),
        ]
        for expected, fixture, tail in fixtures:
            with self.subTest(expected=expected):
                self.assertIn(expected, SAFETY.secret_findings(fixture))
                diagnostic = SAFETY.safe_log_text(fixture)
                self.assertNotIn(tail, diagnostic)
                self.assertLessEqual(len(diagnostic), SAFETY.MAX_SAFE_LOG_CHARACTERS)

    def test_semantic_normalization_expansion_is_bounded_and_fails_closed(self) -> None:
        with mock.patch.object(SAFETY, "MAX_SECRET_SCAN_CHARACTERS", 1024):
            expanding = "\ufdfa" * 100
            self.assertEqual(
                SAFETY.secret_findings(expanding),
                ["secret_scan_semantic_expansion_limit"],
            )
            with self.assertRaisesRegex(ValueError, "secret_scan_semantic_expansion_limit"):
                SAFETY.assert_safe_persistent_text(expanding)

    def test_full_private_key_block_is_fully_redacted(self) -> None:
        body = "M" * 96
        fixture = "-----BEGIN " + "PRIVATE KEY-----\n" + body + "\n-----END " + "PRIVATE KEY-----"
        diagnostic = SAFETY.safe_log_text("failure=" + fixture)
        if body in diagnostic or "-----END " in diagnostic:
            self.fail("private-key body or footer leaked from safe log")
        self.assertIn("<redacted:private_key>", diagnostic)

    def test_structured_validation_accepts_only_narrow_read_only_profiles(self) -> None:
        positive = [
            ["python3", "-B", "-m", "pytest", "-p", "no:cacheprovider", "tests/test_example.py", "-q"],
            [
                "python3",
                "-B",
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "tests/test_example.py",
                "--collect-only",
                "-q",
            ],
            ["python3", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            ["ruff", "check", "--no-fix", "--no-cache", "."],
            ["ruff", "check", "--no-fix", "--no-cache", "src", "tests"],
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for argv in positive:
                with self.subTest(argv=argv):
                    self.assertTrue(SAFETY.safe_validation_command_item(command(argv), root=root))

            evidence = command(positive[0], exit_code=0, output_sha256=OUTPUT_SHA256)
            self.assertFalse(SAFETY.safe_validation_command_item(evidence, root=root))
            self.assertTrue(SAFETY.safe_validation_command_item(evidence, root=root, evidence=True))

    def test_structured_validation_rejects_mutation_output_and_opaque_command_profiles(self) -> None:
        unsafe_argv = [
            ["ruff", "check", "--fix", "."],
            ["ruff", "check", "--fix-only", "."],
            ["ruff", "check", "--unsafe-fixes", "."],
            ["ruff", "check", "--add-noqa", "."],
            ["ruff", "check", "--output-file", ".env", "."],
            ["ruff", "check", "--output-file=.env", "."],
            ["pytest", "--basetemp=.git"],
            ["pytest", "--basetemp", ".git"],
            ["pytest", "--junitxml=.env"],
            ["pytest", "--junit-xml", ".env"],
            ["pytest", "--cache-clear"],
            ["pytest", "-o", "cache_dir=.git"],
            ["pytest", "--override-ini=cache_dir=.git"],
            ["pytest", "--unknown-output=.env"],
            ["python3", "-B", "-m", "pytest", "-p", "no:cacheprovider", "--unknown-option"],
            ["python3", "-B", "-m", "unittest", "--unknown-option"],
            ["ruff", "check", "--no-fix", "--no-cache", "--unknown-option", "."],
            ["python3", "-m", "pytest", "tests/test_example.py", "-q"],
            ["python3", "-m", "pytest", "--basetemp=.git"],
            ["python", "-B", "-m", "unittest", "tests.test_example"],
            ["python3.14", "-B", "-m", "unittest", "tests.test_example"],
            ["python3.999", "-B", "-m", "unittest", "tests.test_example"],
            ["python3.１２", "-B", "-m", "unittest", "tests.test_example"],
            ["python3", "-m", "compileall", "."],
            ["mypy", "--cache-dir=.git", "src"],
            ["mypy", "--junit-xml=.env", "src"],
            ["npm", "run", "lint", "--", "--fix"],
            ["npm", "run", "test", "--", "--updateSnapshot"],
            ["npm", "run", "build"],
            ["make", "check"],
            ["uv", "run", "pytest", "tests"],
            ["cargo", "test", "--target-dir=.git"],
            ["go", "test", "-o", ".env", "./..."],
            ["tools/pytest", "tests"],
            ["./ruff", "check", "."],
            ["pytest", "@args.txt"],
            ["pytest", "tests", ">", ".env"],
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for argv in unsafe_argv:
                with self.subTest(argv=argv):
                    self.assertFalse(SAFETY.safe_validation_command_item(command(argv), root=root))

    def test_structured_validation_rejects_unsafe_or_ambiguous_envelopes(self) -> None:
        base = command(
            ["python3", "-B", "-m", "pytest", "-p", "no:cacheprovider", "tests/test_example.py", "-q"]
        )
        cases = [
            {key: value}
            for key, value in [
                ("cwd", "../outside"),
                ("cwd", "..\\outside"),
                ("cwd", "/tmp"),
                ("cwd", ".git"),
                ("cwd", ".env"),
                ("network", "local"),
                ("network", "live"),
                ("network", "allow"),
                ("network", None),
                ("probe_tier", True),
                ("probe_tier", 0),
                ("probe_tier", 2),
                ("probe_tier", 3),
                ("probe_tier", 999),
                ("expected_exit_code", True),
                ("expected_exit_code", 1),
                ("timeout_seconds", True),
                ("timeout_seconds", 0),
                ("timeout_seconds", 3601),
                ("shell", True),
                ("command", "rm -rf ."),
                ("env", {"PYTEST_ADDOPTS": "--basetemp=.git"}),
                ("stdout_path", ".env"),
            ]
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outside = Path(temp_dir).parent / f"{Path(temp_dir).name}-outside"
            outside.mkdir()
            try:
                (root / "outside-link").symlink_to(outside, target_is_directory=True)
                cases.append({"cwd": "outside-link"})
                for overrides in cases:
                    with self.subTest(overrides=overrides):
                        payload = dict(base)
                        payload.update(overrides)
                        self.assertFalse(SAFETY.safe_validation_command_item(payload, root=root))
            finally:
                outside.rmdir()

    def test_structured_validation_requires_the_complete_envelope(self) -> None:
        base = command(
            ["python3", "-B", "-m", "pytest", "-p", "no:cacheprovider", "tests/test_example.py", "-q"]
        )
        required = {
            "id",
            "argv",
            "cwd",
            "expected_exit_code",
            "timeout_seconds",
            "network",
            "probe_tier",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for field in sorted(required):
                with self.subTest(missing=field):
                    payload = dict(base)
                    del payload[field]
                    self.assertFalse(SAFETY.safe_validation_command_item(payload, root=root))

            self.assertFalse(
                SAFETY.safe_validation_command_item({**base, "exit_code": 0}, root=root),
                "evidence without an output hash must fail closed",
            )
            self.assertFalse(
                SAFETY.safe_validation_command_item(
                    {**base, "exit_code": 0, "output_sha256": OUTPUT_SHA256},
                    root=root,
                ),
                "planned commands must reject evidence-only fields",
            )

    def test_structured_validation_rejects_repo_local_module_and_executable_shadows(self) -> None:
        pytest_command = command(
            ["python3", "-B", "-m", "pytest", "-p", "no:cacheprovider", "tests/test_example.py", "-q"]
        )
        unittest_command = command(["python3", "-B", "-m", "unittest", "tests.test_example"])
        ruff_command = command(["ruff", "check", "--no-fix", "--no-cache", "."])
        for shadow, payload in [
            ("pytest.py", pytest_command),
            ("unittest.py", unittest_command),
            ("python3", unittest_command),
            ("ruff", ruff_command),
        ]:
            with self.subTest(shadow=shadow), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / shadow).write_text("raise SystemExit('shadow')\n", encoding="utf-8")
                self.assertFalse(SAFETY.safe_validation_command_item(payload, root=root))

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tools = root / "tools"
            tools.mkdir()
            (tools / "ruff").write_text("raise SystemExit('shadow')\n", encoding="utf-8")
            payload = command(["ruff", "check", "--no-fix", "--no-cache", "."], cwd="tools")
            self.assertFalse(SAFETY.safe_validation_command_item(payload, root=root))

        for startup_hook in ("sitecustomize.py", "usercustomize.py"):
            with self.subTest(startup_hook=startup_hook), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / startup_hook).write_text("raise SystemExit('shadow')\n", encoding="utf-8")
                self.assertFalse(SAFETY.safe_validation_command_item(unittest_command, root=root))

    def test_structured_validation_rejects_symlinked_targets_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(temp_dir)
            outside = Path(outside_dir)
            (outside / "test_external.py").write_text("raise SystemExit('external')\n", encoding="utf-8")
            (root / "external-tests").symlink_to(outside, target_is_directory=True)
            payloads = [
                command(
                    [
                        "python3",
                        "-B",
                        "-m",
                        "pytest",
                        "-p",
                        "no:cacheprovider",
                        "external-tests/test_external.py",
                    ]
                ),
                command(["ruff", "check", "--no-fix", "--no-cache", "external-tests"]),
            ]
            for payload in payloads:
                with self.subTest(argv=payload["argv"]):
                    self.assertFalse(SAFETY.safe_validation_command_item(payload, root=root))

    def test_legacy_command_is_compatibility_only(self) -> None:
        legacy = {
            "id": "VAL-01",
            "command": "python3 -B -m pytest -p no:cacheprovider tests/test_example.py -q",
            "expected_result": "exit_code_0",
        }
        self.assertFalse(SAFETY.safe_validation_command_item(legacy))
        self.assertTrue(SAFETY.safe_validation_command_item(legacy, allow_legacy=True))


if __name__ == "__main__":
    unittest.main()
