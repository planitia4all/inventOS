"""Playwright E2E 테스트용 공용 fixture.

실제 Streamlit 서버를 서브프로세스로 띄우고(격리된 임시 데이터 폴더,
INVENTOS_AI_PROVIDER=mock), Playwright로 브라우저를 열어 화면을 조작한다.
`pytest tests/` 기본 실행에는 포함되지 않는다 — 브라우저/서버 기동이
필요해 무겁고 느리기 때문에, e2e만 따로 돌릴 때 `pytest tests/e2e` 로 쓴다.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 프리인스톨된 Chromium 위치. 시스템에 없으면(예: CI가 아닌 환경) None으로
# 두어 Playwright가 기본 탐색 경로를 쓰도록 한다.
_CHROMIUM_PATH = Path("/opt/pw-browsers/chromium")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(base_url: str, proc: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Streamlit 서버가 시작 중에 종료되었습니다 (exit code={proc.returncode})."
            )
        try:
            urllib.request.urlopen(base_url, timeout=1)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Streamlit 서버가 제한 시간 안에 준비되지 않았습니다.")


@pytest.fixture(scope="session")
def streamlit_server(tmp_path_factory):
    """격리된 데이터 폴더로 InventOS를 띄운다. 세션당 한 번만 시작한다."""
    data_dir = tmp_path_factory.mktemp("inventos_e2e_data")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["INVENTOS_DATA_DIR"] = str(data_dir)
    env["INVENTOS_AI_PROVIDER"] = "mock"
    env.pop("ANTHROPIC_API_KEY", None)

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless", "true",
            "--server.port", str(port),
            "--server.address", "127.0.0.1",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=_REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_until_ready(base_url, proc)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def browser():
    launch_kwargs = {"headless": True}
    if _CHROMIUM_PATH.exists():
        launch_kwargs["executable_path"] = str(_CHROMIUM_PATH)
    with sync_playwright() as p:
        instance = p.chromium.launch(**launch_kwargs)
        yield instance
        instance.close()


@pytest.fixture()
def page(browser, streamlit_server):
    """매 테스트마다 새 브라우저 컨텍스트/페이지로 앱 첫 화면을 연다."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    pg.goto(streamlit_server, timeout=20000)
    pg.wait_for_selector("text=발명 노트", timeout=20000)
    yield pg
    context.close()


@pytest.fixture()
def mobile_page(browser, streamlit_server):
    """390px 모바일 뷰포트 검증용 페이지."""
    context = browser.new_context(viewport={"width": 390, "height": 844})
    pg = context.new_page()
    pg.goto(streamlit_server, timeout=20000)
    pg.wait_for_selector("text=발명 노트", timeout=20000)
    yield pg
    context.close()
