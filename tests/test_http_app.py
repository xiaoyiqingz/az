import unittest
from tempfile import TemporaryDirectory

from starlette.testclient import TestClient
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from config.settings import load_settings
from core.context.models import SessionMeta, utc_now
from core.context.session_store import SessionStore
from interfaces.http.app import _render_markdown, create_app


class TestHttpApp(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.settings = load_settings({"AZ_HOME": self.temp_dir.name})
        self.client = TestClient(create_app(self.settings))

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def test_serves_web_ui_and_health_check(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("项目助手", response.text)
        self.assertEqual(
            self.client.get("/api/v1/health").json(), {"status": "ok"}
        )
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)

    def test_creates_uuid_session(self):
        response = self.client.post("/api/v1/sessions")

        self.assertEqual(response.status_code, 201)
        self.assertRegex(
            response.json()["session_id"],
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        )

    def test_rejects_invalid_session_id_and_blank_prompt(self):
        invalid_id = self.client.post("/api/v1/sessions/not-a-uuid/messages", json={"prompt": "hi"})
        self.assertEqual(invalid_id.status_code, 422)

        valid_id = "019e688c-77a0-7d4a-8f50-0a8a0cddd48b"
        blank_prompt = self.client.post(
            f"/api/v1/sessions/{valid_id}/messages", json={"prompt": " "}
        )
        self.assertEqual(blank_prompt.status_code, 422)

    def test_lists_sessions_and_loads_visible_history(self):
        session_id = "019e688c-77a0-7d4a-8f50-0a8a0cddd48b"
        store = SessionStore(self.settings.az_home, session_id)
        now = utc_now()
        store.save_meta(
            SessionMeta(
                session_id=session_id,
                conversation_id=session_id,
                project_path="/project",
                created_at=now,
                updated_at=now,
            )
        )
        store.save_message_history(
            [
                ModelRequest(parts=[UserPromptPart(content="历史问题")]),
                ModelResponse(parts=[TextPart(content="历史回答")]),
            ]
        )

        sessions = self.client.get("/api/v1/sessions").json()["sessions"]
        history = self.client.get(f"/api/v1/sessions/{session_id}/history").json()

        self.assertEqual(sessions[0]["session_id"], session_id)
        self.assertEqual(sessions[0]["message_count"], 2)
        self.assertEqual(sessions[0]["first_prompt"], "历史问题")
        self.assertEqual(
            history["messages"],
            [
                {"role": "user", "content": "历史问题"},
                {
                    "role": "assistant",
                    "content": "历史回答",
                    "html": "<p>历史回答</p>\n",
                },
            ],
        )

    def test_renders_markdown_without_allowing_raw_html(self):
        html = _render_markdown("**重点**\n\n<script>alert('xss')</script>")

        self.assertIn("<strong>重点</strong>", html)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
