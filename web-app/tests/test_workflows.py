from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.extract import FIELDS
from src.pipeline import process_inbox
from src.reporting import results_csv_bytes, results_json_bytes, results_pdf_bytes
from src.service import (
    ProcessingArtifacts,
    apply_human_review,
    retry_failed_email,
)


EMAIL = {
    "email_id": "email_001",
    "from": "ops@example.com",
    "subject": "Draft BL - please compare against SI",
    "body": "Please verify the attached shipping instruction and bill of lading.",
    "attachments": [
        "attachments/email_001_SI.txt",
        "attachments/email_001_BL.txt",
    ],
}

SI_DOCUMENT = """SHIPPING INSTRUCTION
========================================
Shipper: ACME EXPORTS
Consignee: GLOBAL IMPORTS
Notify Party: PORT AGENT
Port of Loading: SINGAPORE
Port of Discharge: ROTTERDAM
Container Count: 1
Gross Weight: 1000 KG
"""

BL_DOCUMENT = """BILL OF LADING (DRAFT)
========================================
Shipper: ACME EXPORTS
Consignee: GLOBAL IMPORTS
Notify Party: PORT AGENT
Port of Loading: SINGAPORE
Port of Discharge: ROTTERDAM
Container Count: 1
Gross Weight: 1000 KG
"""


class BrokenInbox:
    def __iter__(self):
        return iter([EMAIL])

    def read_bytes(self, path: str) -> bytes:
        raise RuntimeError(f"temporary read failure: {path}")


class WorkflowTests(unittest.TestCase):
    def failed_artifacts(self) -> ProcessingArtifacts:
        submission, results, summary = process_inbox(BrokenInbox())
        return ProcessingArtifacts([EMAIL], submission, results, summary)

    def test_processing_error_is_recorded_without_stopping_inbox(self) -> None:
        artifacts = self.failed_artifacts()
        result = artifacts.submission["email_001"]
        detail = artifacts.internal_results["email_001"]
        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(detail["processing_status"], "Failed")
        self.assertTrue(detail["retryable"])
        self.assertEqual(detail["error_history"][0]["type"], "RuntimeError")
        self.assertIn("temporary read failure", detail["error_history"][0]["message"])

    def test_failed_case_can_be_retried_and_preserves_error_history(self) -> None:
        artifacts = self.failed_artifacts()
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "inbox").mkdir()
            (bundle / "attachments").mkdir()
            (bundle / "inbox" / "email_001.json").write_text(json.dumps(EMAIL))
            (bundle / "attachments" / "email_001_SI.txt").write_text(SI_DOCUMENT)
            (bundle / "attachments" / "email_001_BL.txt").write_text(BL_DOCUMENT)
            (bundle / "sample_submission.json").write_text(
                json.dumps({"email_001": artifacts.submission["email_001"]})
            )
            (bundle / "loader.py").write_text(
                """import json
from pathlib import Path
class Inbox:
    def __init__(self, source): self.root = Path(source)
    def emails(self): return [self.get('email_001')]
    def __iter__(self): return iter(self.emails())
    def get(self, email_id): return json.loads((self.root/'inbox'/f'{email_id}.json').read_text())
    def read_bytes(self, path): return (self.root/path).read_bytes()
    def sample_submission(self): return json.loads((self.root/'sample_submission.json').read_text())
"""
            )
            retried = retry_failed_email(bundle, artifacts, "email_001")
        detail = retried.internal_results["email_001"]
        self.assertEqual(retried.submission["email_001"]["status"], "OK")
        self.assertEqual(detail["processing_status"], "Completed")
        self.assertEqual(detail["processing_attempts"], 2)
        self.assertEqual(detail["retry_count"], 1)
        self.assertEqual(len(detail["error_history"]), 1)

    def test_human_review_correction_recalculates_result(self) -> None:
        artifacts = self.failed_artifacts()
        si_values = {
            "shipper": "ACME EXPORTS",
            "consignee": "GLOBAL IMPORTS",
            "notify_party": "PORT AGENT",
            "port_of_loading": "SINGAPORE",
            "port_of_discharge": "ROTTERDAM",
            "container_count": "1",
            "gross_weight_kg": "1000 KG",
        }
        bl_values = dict(si_values)
        bl_values["port_of_discharge"] = "HAMBURG"
        reviewed = apply_human_review(
            artifacts, "email_001", si_values, bl_values, "Checked against originals"
        )
        result = reviewed.submission["email_001"]
        detail = reviewed.internal_results["email_001"]
        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["defect_fields"], ["port_of_discharge"])
        self.assertEqual(detail["review_state"], "corrected")
        self.assertEqual(detail["human_review"]["note"], "Checked against originals")
        self.assertTrue(all(field in detail["extracted"]["si"] for field in FIELDS))

        json_export = results_json_bytes(reviewed)
        csv_export = results_csv_bytes(reviewed)
        pdf_export = results_pdf_bytes(reviewed)
        self.assertIn(b'"human_review"', json_export)
        self.assertIn(b"port_of_discharge", json_export)
        self.assertIn(b"Port of Discharge", csv_export)
        self.assertTrue(pdf_export.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_export), 2000)


if __name__ == "__main__":
    unittest.main()
