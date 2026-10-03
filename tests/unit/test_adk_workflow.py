"""Unit tests for the integrated Google ADK Multi-Agent Workflow Studio and Endpoints."""

import unittest
from fastapi.testclient import TestClient
from app.fast_api_app import app


class TestADKWorkflowStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_adk_workflow_page_served(self):
        """Verify that the /adk-workflow HTML interface is served successfully."""
        resp = self.client.get("/adk-workflow")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Google ADK Multi-Agent Studio", resp.text)
        self.assertIn("Customer Agent", resp.text)
        self.assertIn("Transaction Agent", resp.text)
        self.assertIn("Fraud & Cyber Agent", resp.text)

    def test_adk_workflow_tab_in_dashboard(self):
        """Verify that the unified dashboard includes the ADK Agent Workflow tab."""
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ADK Agent Workflow", resp.text)
        self.assertIn("/adk-workflow", resp.text)

    def test_api_adk_agents_list(self):
        """Verify that the /api/adk/agents metadata endpoint lists all specialists."""
        resp = self.client.get("/api/adk/agents")
        self.assertEqual(resp.status_code, 200)
        agents = resp.json()
        self.assertEqual(len(agents), 7)
        agent_names = [a["name"] for a in agents]
        self.assertIn("all", agent_names)
        self.assertIn("customer_agent", agent_names)
        self.assertIn("transaction_agent", agent_names)
        self.assertIn("fraud_agent", agent_names)
        self.assertIn("ownership_agent", agent_names)
        self.assertIn("risk_agent", agent_names)
        self.assertIn("consolidator_agent", agent_names)

    def test_dev_ui_assets_mounted(self):
        """Verify that native Google ADK Dev UI is accessible at /dev-ui/."""
        resp = self.client.get("/dev-ui/")
        self.assertEqual(resp.status_code, 200)
        config_resp = self.client.get("/dev-ui/assets/config/runtime-config.json")
        self.assertEqual(config_resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
