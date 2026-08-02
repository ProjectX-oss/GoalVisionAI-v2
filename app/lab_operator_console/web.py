"""Standard-library localhost HTTP application with server-rendered pages."""

from __future__ import annotations

import html
import json
import mimetypes
from datetime import datetime, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, urlparse

from app.database import Database

from .actions import ConsoleActionService
from .config import ConsoleConfig
from .models import ActionRequest, PageModel
from .reads import ConsoleReadService
from .security import Session, SessionSecurity


NAV = ("overview", "readiness", "discovery", "candidates", "fixtures", "odds", "analyses", "reasoning", "observations", "previews", "reviews", "send_readiness", "results", "settlements", "monitoring", "reports", "unresolved", "incidents", "health", "actions")
PACKAGE = Path(__file__).parent


class ConsoleApplication:
    def __init__(self, config: ConsoleConfig) -> None:
        self.config = config
        self.security = SessionSecurity(config.session_secret, config.session_ttl_seconds, config.csrf_ttl_seconds)

    def render_get(self, path: str, cookie_value: str | None = None) -> tuple[int, dict[str, str], bytes]:
        parsed = urlparse(path)
        if parsed.path.startswith("/static/"):
            return self._static(parsed.path)
        page_name = (parsed.path.strip("/") or "overview").replace("-", "_")
        identifier = (parse_qs(parsed.query).get("id") or [None])[0]
        session = self.security.load(cookie_value)
        new_cookie = None
        if session is None:
            session, new_cookie = self.security.create(self.config.operator_identifier)
        database = Database(str(self.config.database))
        try:
            model = ConsoleReadService(database, self.config.database, controlled_demo=self.config.controlled_demo, page_size=self.config.maximum_page_size).page(page_name, identifier)
        finally:
            database.close()
        body = self._render(model, session, page_name).encode("utf-8")
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; connect-src 'none'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }
        if new_cookie:
            headers["Set-Cookie"] = self.security.cookie_header(new_cookie)
        return (404 if model.status == "NOT_FOUND" else 200), headers, body

    def handle_post(self, path: str, body: bytes, cookie_value: str | None) -> tuple[int, dict[str, str], bytes]:
        if len(body) > 64_000:
            return self._json_response(413, {"status": "REQUEST_TOO_LARGE"})
        session = self.security.load(cookie_value)
        if session is None:
            return self._json_response(403, {"status": "SESSION_REQUIRED"})
        values = {key: items[-1] for key, items in parse_qs(body.decode("utf-8"), keep_blank_values=True).items()}
        action = values.get("action_type", "")
        if not self.security.verify_csrf(session, action, values.get("csrf_token")):
            return self._json_response(403, {"status": "CSRF_REJECTED"})
        if path == "/logout":
            return 303, {"Location": "/", "Set-Cookie": "gv_console_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"}, b""
        normalized = {key: value for key, value in values.items() if key not in {"csrf_token", "confirmation", "operator_identifier", "action_type", "request_id"}}
        if "result_json" in normalized:
            try:
                normalized["result"] = json.loads(normalized.pop("result_json"))
            except json.JSONDecodeError:
                return self._json_response(400, {"status": "INVALID_RESULT_JSON"})
        request = ActionRequest(
            values.get("request_id") or "console-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
            action, values.get("operator_identifier") or session.operator_identifier, path,
            values.get("target_identifier"), values.get("confirmation", ""), normalized,
            datetime.now(timezone.utc).isoformat(),
        )
        database = Database(str(self.config.database))
        try:
            result = ConsoleActionService(database, actions_enabled=not self.config.read_only, allowed_output_roots=self.config.allowed_database_roots, maximum_export_bytes=self.config.maximum_export_bytes).execute(request)
        except (ValueError, RuntimeError) as exc:
            result = {"status": "ACTION_REJECTED", "reason": str(exc), "provider_calls": 0, "telegram_calls": 0}
        finally:
            database.close()
        return self._json_response(200 if result.get("status") == "COMPLETED" else 409, result)

    def serve(self) -> None:
        application = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status, headers, body = application.render_get(self.path, _cookie(self.headers.get("Cookie")))
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                status, headers, body = application.handle_post(self.path, self.rfile.read(length), _cookie(self.headers.get("Cookie")))
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer((self.config.host, self.config.port), Handler)
        try:
            server.serve_forever()
        finally:
            server.server_close()

    def _render(self, model: PageModel, session: Session, page_name: str) -> str:
        navigation = "".join(f'<a href="/{name.replace("_", "-")}">{html.escape(name.replace("_", " ").title())}</a>' for name in NAV)
        summary = "".join(f'<div class="fact"><b>{html.escape(str(key).replace("_", " ").title())}</b>{_value(value)}</div>' for key, value in model.summary)
        warnings = "".join(f'<div class="warning-box">{html.escape(item)}</div>' for item in model.warnings)
        tables = ""
        for table in model.tables:
            heads = "".join(f"<th>{html.escape(str(item))}</th>" for item in table.columns)
            rows = "".join("<tr>" + "".join(f"<td>{_value(cell)}</td>" for cell in row) + "</tr>" for row in table.rows)
            if not rows:
                rows = f'<tr><td colspan="{max(1, len(table.columns))}">No persisted evidence.</td></tr>'
            tables += f'<section class="panel"><h2>{html.escape(table.title)}</h2><div class="table-wrap"><table><thead><tr>{heads}</tr></thead><tbody>{rows}</tbody></table></div></section>'
        actions = self._forms(page_name, session) if not self.config.read_only else '<section class="panel"><b>READ-ONLY MODE</b><p>Restart with --enable-actions for confirmed manual operations.</p></section>'
        template = Template((PACKAGE / "templates/base.html").read_text(encoding="utf-8"))
        status_class = model.status.lower().replace("forward_test_", "").replace("data_quality_", "").replace("lifecycle_audit_", "")
        demo = '<span class="demo">CONTROLLED FICTIONAL DEMO DATA</span>' if model.controlled_demo else ""
        return template.safe_substitute(title=html.escape(model.title), status=html.escape(model.status), status_class=html.escape(status_class), navigation=navigation, summary=summary, warnings=warnings, tables=tables, actions=actions, demo=demo)

    def _forms(self, page: str, session: Session) -> str:
        definitions = {
            "readiness": (("READINESS_NETWORK_VERIFY", "VERIFY_API_FOOTBALL_ONCE"),),
            "discovery": (("BOUNDED_DISCOVERY", "RUN_BOUNDED_DISCOVERY"),),
            "reviews": (("CREATE_PUBLICATION_REVIEW", "CREATE_PUBLICATION_REVIEW"),),
            "reasoning": (("CREATE_REASONING", "CREATE_PREDICTION_REASONING"),),
            "results": (("IMPORT_RESULT", "IMPORT_FORWARD_TEST_RESULT"),),
            "settlements": (("SETTLE", "SETTLE_FORWARD_TEST_OBSERVATION"),),
            "reports": (("GENERATE_WEEKLY_REPORT", "GENERATE_WEEKLY_REPORT"),("GENERATE_CUMULATIVE_REPORT", "GENERATE_CUMULATIVE_REPORT"),("REPRODUCE_REPORT", "REPRODUCE_REPORT"),("COMPARE_REPORTS", "COMPARE_REPORTS"),("CREATE_EXPORT", "CREATE_REPORT_EXPORT")),
            "incidents": (("ACKNOWLEDGE_INCIDENT", "ACKNOWLEDGE_INCIDENT"),("RESOLVE_INCIDENT", "RESOLVE_INCIDENT")),
        }
        if page not in definitions:
            return ""
        forms=[]
        for action, confirmation in definitions[page]:
            csrf = self.security.csrf_token(session, action)
            if action == "IMPORT_RESULT":extra='<textarea name="result_json" aria-label="Versioned result JSON"></textarea>'
            elif action == "CREATE_EXPORT":extra='<input name="output_name" aria-label="Safe export directory name" placeholder="report-export" required>'
            elif action == "COMPARE_REPORTS":extra='<input name="comparison_report_id" aria-label="Comparison report identifier" required>'
            else:extra='<input name="reason" aria-label="Reason" placeholder="Reason or operator note">'
            maximum_calls = 1 if action == "READINESS_NETWORK_VERIFY" else 40 if action == "BOUNDED_DISCOVERY" else 0
            forms.append(f'<section class="panel"><h2>Explicit manual action: {html.escape(action.replace("_"," ").title())}</h2><form method="post" action="/action"><input type="hidden" name="csrf_token" value="{csrf}"><input type="hidden" name="action_type" value="{action}"><label>Operator identifier<input name="operator_identifier" required value="{html.escape(session.operator_identifier)}"></label><label>Target identifier<input name="target_identifier"></label>{extra}<label>Exact confirmation<input name="confirmation" required placeholder="{confirmation}"></label><label><input type="checkbox" required> I understand this is an explicit LAB operator action.</label><button>Execute bounded action</button></form><p>Maximum provider calls: {maximum_calls}. Telegram calls: 0.</p></section>')
        return "".join(forms)

    def _static(self, path: str):
        target = (PACKAGE / path.lstrip("/")).resolve()
        root = (PACKAGE / "static").resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return 404, {}, b""
        if not target.is_file():
            return 404, {}, b""
        return 200, {"Content-Type": mimetypes.guess_type(target.name)[0] or "application/octet-stream", "Cache-Control": "no-cache"}, target.read_bytes()

    @staticmethod
    def _json_response(status, value):
        return status, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _cookie(header: str | None) -> str | None:
    if not header:
        return None
    value = cookies.SimpleCookie()
    value.load(header)
    return value["gv_console_session"].value if "gv_console_session" in value else None


def _value(value) -> str:
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return html.escape(str(value if value is not None else "N/A"))
