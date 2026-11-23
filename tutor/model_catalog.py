import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from queue import Empty, Queue
from threading import Thread
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener

from .contracts import ModelCatalogRequest, ModelEffortsRequest, RuntimeSettings
from .models import API_REASONING_EFFORTS, CODEX_REASONING_EFFORTS, ModelError, NoRedirects, Provider, api_base_url, codex_environment
from .storage import encode


def _model_entry(raw, *, codex=False):
    if not isinstance(raw, dict):
        return None
    identifier = (raw.get("model") or raw.get("id")) if codex else raw.get("id")
    if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 240:
        return None
    name = raw.get("displayName") or raw.get("display_name") or raw.get("name")
    if not isinstance(name, str) or not name.strip():
        name = identifier
    return {
        "id": identifier, "name": name[:240], **_effort_details(raw, codex=codex),
        "isDefault": codex and raw.get("isDefault") is True,
    }


def _effort_details(raw: dict, *, codex=False):
    capabilities = raw.get("capabilities")
    reasoning = raw.get("reasoning")
    sources = [raw, capabilities if isinstance(capabilities, dict) else {}, reasoning if isinstance(reasoning, dict) else {}]
    names = ("supportedReasoningEfforts", "supported_reasoning_efforts", "reasoning_efforts", "efforts")
    levels = next((source[name] for source in sources for name in names if isinstance(source.get(name), list)), None)
    allowed = CODEX_REASONING_EFFORTS if codex else API_REASONING_EFFORTS
    effort_ids = [
        item.get("reasoningEffort", item.get("effort")) if isinstance(item, dict) else item
        for item in levels or []
    ]
    default = next((source[name] for source in sources for name in (
        "defaultReasoningEffort", "default_reasoning_effort", "default_effort",
    ) if isinstance(source.get(name), str)), None)
    return {
        "reasoningEfforts": [effort for effort in allowed if effort in effort_ids] if levels is not None else None,
        "defaultReasoningEffort": default if default in allowed else None,
    }


class _CodexCatalogProcess:
    def __init__(self, process, deadline):
        self.process = process
        self.deadline = deadline
        self.lines = Queue()
        Thread(target=self._read_stdout, daemon=True).start()
        self.request_id = 0

    def _read_stdout(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self.lines.put(None)

    def send(self, message):
        self.process.stdin.write(encode(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.request_id += 1
        self.send({"id": self.request_id, "method": method, "params": params})
        while (remaining := self.deadline - monotonic()) > 0:
            try:
                line = self.lines.get(timeout=remaining)
            except Empty as error:
                raise ModelError("model_catalog_timeout") from error
            if line is None:
                raise ModelError("cli_catalog_unavailable")
            try:
                response = json.loads(line)
            except ValueError:
                continue
            if not isinstance(response, dict) or response.get("id") != self.request_id:
                continue
            if not isinstance(response.get("result"), dict):
                raise ModelError("cli_catalog_unavailable")
            return response["result"]
        raise ModelError("model_catalog_timeout")


def _codex_models(provider: Provider):
    executable = provider.codex_executable()
    command = [
        executable, "app-server", "--listen", "stdio://",
        "-c", 'model_provider="openai"', "-c", 'web_search="disabled"',
        "--disable", "shell_tool", "--disable", "plugins", "--disable", "apps",
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="ai-tutor-models-") as directory, subprocess.Popen(
            command, cwd=directory, env=codex_environment(), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding="utf-8", errors="replace",
        ) as process:
            try:
                connection = _CodexCatalogProcess(process, monotonic() + min(20, provider.settings.timeout))
                connection.request("initialize", {
                    "clientInfo": {"name": "ai_tutor", "title": "AI Tutor", "version": "0.1.0"},
                })
                connection.send({"method": "initialized", "params": {}})
                models = {}
                params = {"limit": 100, "includeHidden": False}
                cursors = set()
                while True:
                    result = connection.request("model/list", params)
                    if not isinstance(result.get("data"), list):
                        raise ModelError("cli_catalog_unavailable")
                    for raw in result["data"]:
                        if isinstance(raw, dict) and (raw.get("hidden") or (
                            isinstance(raw.get("inputModalities"), list) and "text" not in raw["inputModalities"]
                        )):
                            continue
                        if entry := _model_entry(raw, codex=True):
                            models[entry["id"]] = entry
                    cursor = result.get("nextCursor")
                    if not cursor:
                        return {
                            "models": list(models.values()),
                            "codexVersion": provider.codex_version,
                            "codexExecutable": executable,
                        }
                    if not isinstance(cursor, str) or cursor in cursors:
                        raise ModelError("cli_catalog_unavailable")
                    cursors.add(cursor)
                    params["cursor"] = cursor
            finally:
                with suppress(OSError):
                    process.stdin.close()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
    except OSError as error:
        raise ModelError("cli_catalog_unavailable") from error


class _ApiCatalog:
    def __init__(self, provider: Provider, query: ModelCatalogRequest):
        settings = provider.configured(RuntimeSettings(
            provider="api", apiBaseUrl=query.apiBaseUrl, apiKey=query.apiKey,
        )).settings
        if not settings.api_key:
            raise ModelError("api_key_required")
        self.url = api_base_url(settings.api_url)
        self.key = settings.api_key
        self.timeout = min(8, settings.timeout)

    def request(self, path: str, body=None):
        headers = {"Authorization": f"Bearer {self.key}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = encode(body).encode("utf-8")
        request = Request(self.url + path, headers=headers, data=data)
        try:
            with build_opener(NoRedirects()).open(request, timeout=self.timeout) as response:
                raw = json.loads(response.read(8_000_000))
        except (TimeoutError, URLError) as error:
            if isinstance(error, HTTPError):
                raise
            code = "model_catalog_timeout" if isinstance(error, TimeoutError) or isinstance(
                getattr(error, "reason", None), TimeoutError,
            ) else "api_catalog_unavailable"
            raise ModelError(code) from error
        except (OSError, ValueError) as error:
            raise ModelError("api_catalog_unavailable") from error
        if not isinstance(raw, dict):
            raise ModelError("api_catalog_unavailable")
        return raw

    @staticmethod
    def http_failure(error: HTTPError):
        status = error.code
        error.close()
        return ModelError({
            401: "api_auth", 403: "api_auth", 429: "model_limit",
        }.get(status, "api_catalog_unavailable"))

    def models(self):
        try:
            result = self.request("/models")
        except HTTPError as error:
            raise self.http_failure(error) from error
        if not isinstance(result.get("data"), list):
            raise ModelError("api_catalog_unavailable")
        models = {}
        for raw in result["data"]:
            if entry := _model_entry(raw):
                if entry["id"] not in models:
                    models[entry["id"]] = entry
        return list(models.values())

    def model_efforts(self, model):
        try:
            details = _effort_details(self.request("/models/" + quote(model, safe="")))
        except HTTPError as error:
            if error.code not in (400, 404, 405, 501):
                raise self.http_failure(error) from error
            error.close()
            details = {"reasoningEfforts": None, "defaultReasoningEffort": None}
        if details["reasoningEfforts"] is None:
            details["reasoningEfforts"] = self._probe_efforts(model)
        return details

    def _probe_efforts(self, model):
        def count(effort=None):
            data = {"model": model, "input": "Hello"}
            if effort is not None:
                data["reasoning"] = {"effort": effort}
            try:
                response = self.request("/responses/input_tokens", data)
            except HTTPError as error:
                if error.code not in (400, 404, 405, 422, 501):
                    raise self.http_failure(error) from error
                error.close()
                return False
            return response.get("object") == "response.input_tokens" and type(response.get("input_tokens")) is int

        # Check the token-count route and verify it distinguishes invalid effort values.
        if not count() or count("__invalid_effort__"):
            return None
        with ThreadPoolExecutor(max_workers=4) as executor:
            supported = list(executor.map(count, API_REASONING_EFFORTS))
        return [effort for effort, accepted in zip(API_REASONING_EFFORTS, supported, strict=True) if accepted]


def list_models(provider: Provider, query: ModelCatalogRequest):
    if query.provider == "codex_cli":
        return _codex_models(provider)
    return {"models": _ApiCatalog(provider, query).models()}


def model_efforts(provider: Provider, query: ModelEffortsRequest):
    return _ApiCatalog(provider, query).model_efforts(query.model)
