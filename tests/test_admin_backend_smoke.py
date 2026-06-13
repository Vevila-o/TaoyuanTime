from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class AdminBackendSmokeCommandTests(TestCase):
    def test_smoke_admin_backend_runs_safe_checks(self):
        out = StringIO()

        call_command("smoke_admin_backend", stdout=out)

        output = out.getvalue()
        self.assertIn("PASS | dashboard", output)
        self.assertIn("PASS | line simulator", output)
        self.assertIn("PASS | activity filters", output)
        self.assertIn("PASS | link error filter", output)
        self.assertIn("PASS | expired active", output)
        self.assertIn("PASS | missing ai summaries", output)
