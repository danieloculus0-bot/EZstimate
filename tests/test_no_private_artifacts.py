"""No private/customer drawing or material costing artifacts in the public repo."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {".pdf", ".dwg", ".dxf", ".step", ".stp", ".iges", ".igs", ".sldprt", ".sldasm", ".ipt", ".iam", ".stl", ".xlsx", ".xls", ".csv", ".sqlite", ".sqlite3", ".db"}
FORBIDDEN_DIRS = {"private_inputs", "private_data", "customer_documents", "pricebooks"}

class PrivateArtifactsNeverPublished(unittest.TestCase):
    def test_no_customer_artifact_files_are_tracked(self):
        # Inspect tracked files, not local ignored/private diagnostic fixtures.
        proc = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
        paths = [p.decode("utf-8", errors="replace") for p in proc.stdout.split(b"\\0") if p]
        flagged = [p for p in paths if Path(p).suffix.lower() in FORBIDDEN
                   or any(part.lower() in FORBIDDEN_DIRS for part in Path(p).parts)]
        self.assertEqual(flagged, [], "Private/drawing file tracked by Git: " + ", ".join(flagged))

if __name__ == "__main__":
    unittest.main()
