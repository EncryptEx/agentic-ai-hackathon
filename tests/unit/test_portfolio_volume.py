"""The dashboard's "Gross Turnover" card used to be a hard-coded $0.00. The API now returns the real total."""

import os
import shutil
import sqlite3
import tempfile
import unittest

from storage.database import DatabaseManager

SEED_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "kyc_aml.db"))


@unittest.skipUnless(os.path.exists(SEED_DB), "data/kyc_aml.db is not available")
class PortfolioVolume(unittest.TestCase):
    def setUp(self):
        # Work on a copy: opening a DatabaseManager can run migrations, which must not touch the committed file.
        self.path = os.path.join(tempfile.mkdtemp(), "copy.db")
        shutil.copy(SEED_DB, self.path)

    def test_summary_reports_the_real_gross_turnover(self):
        summary = DatabaseManager(self.path).get_portfolio_summary()
        conn = sqlite3.connect(self.path)
        try:
            expected = round(conn.execute("SELECT SUM(amount_usd) FROM transactions").fetchone()[0], 2)
        finally:
            conn.close()
        self.assertGreater(expected, 0)
        self.assertEqual(summary["total_volume_usd"], expected)
        conn = sqlite3.connect(self.path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(summary["total_transactions"], count)  # existing fields are untouched (the dataset itself may change)

    def test_an_empty_ledger_reports_zero_not_none(self):
        conn = sqlite3.connect(self.path)
        conn.execute("DELETE FROM transactions")
        conn.commit()
        conn.close()
        self.assertEqual(DatabaseManager(self.path).get_portfolio_summary()["total_volume_usd"], 0)


if __name__ == "__main__":
    unittest.main()
