from __future__ import annotations

import base64
import csv
import asyncio
import json
import importlib
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional
import unicodedata

import requests
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Frame,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .models import ProductRow, RunConfig
from .video_postprocess import (
    burn_subtitles_with_ffmpeg,
    find_ffmpeg_path,
    find_ffprobe_path,
    generate_srt,
    get_video_duration_seconds,
    overlay_logo_with_ffmpeg,
    seconds_to_srt_time,
)


def log(message: str, level: str = "INFO") -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] [{level}] {message}")


class FlowBot:
    # ════════════════════════════════════════════════════════
    # INIT / LIFECYCLE
    # ════════════════════════════════════════════════════════

    def __init__(
        self,
        config: RunConfig,
        log_hook: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.config = config
        self.log_hook = log_hook
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.chrome_process: subprocess.Popen | None = None
        self.cdp_port: int | None = None
        self.cdp_user_data_dir: Path | None = None
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.current_image_cleanup_result: dict[str, str] = {}
        self.last_browser_health_check = 0.0

    def __enter__(self) -> "FlowBot":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def emit_log(self, message: str, level: str = "INFO") -> None:
        self.show_browser_toast(message, level)
        if self.log_hook:
            self.log_hook(message, level)
            return
        log(message, level)

    def show_browser_toast(
        self,
        message: str,
        level: str = "INFO",
        kind: str | None = None,
    ) -> None:
        if self.page is None:
            return
        payload = {
            "message": self.browser_toast_message(message),
            "level": level.upper(),
            "kind": kind or self.browser_toast_kind(message, level),
        }
        with suppress(Exception):
            self.page.evaluate(
                """
                (payload) => {
                  if (!document.body) return;

                  const rootId = "flow-bot-visual-log-root-v2";
                  let root = document.getElementById(rootId);
                  if (!root) {
                    const style = document.createElement("style");
                    style.id = "flow-bot-visual-log-style-v2";
                    style.textContent = `
                      #${rootId} {
                        position: fixed;
                        top: 18px;
                        right: 18px;
                        z-index: 2147483647;
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                        width: min(360px, calc(100vw - 36px));
                        pointer-events: none;
                        font-family: Arial, Helvetica, sans-serif;
                      }
                      .flow-bot-toast {
                        position: relative;
                        display: grid;
                        grid-template-columns: 28px 1fr;
                        gap: 10px;
                        align-items: start;
                        overflow: hidden;
                        padding: 12px 13px 14px;
                        border-radius: 12px;
                        border: 1px solid #e5e7eb;
                        background: #fff;
                        color: #111827;
                        box-shadow: 0 14px 30px rgba(17, 24, 39, 0.16);
                        transform: translateX(12px);
                        opacity: 0;
                        animation: flowBotToastIn 180ms ease-out forwards;
                      }
                      .flow-bot-toast-title {
                        margin: 0 0 3px;
                        font-size: 12px;
                        font-weight: 700;
                        line-height: 1.2;
                      }
                      .flow-bot-toast-msg {
                        margin: 0;
                        color: #374151;
                        font-size: 12px;
                        line-height: 1.35;
                        word-break: break-word;
                      }
                      .flow-bot-toast-icon {
                        width: 28px;
                        height: 28px;
                        border-radius: 999px;
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 14px;
                        font-weight: 800;
                      }
                      .flow-bot-toast.loading .flow-bot-toast-icon {
                        background: #fff;
                        color: #4f46e5;
                        border: 1px solid #e5e7eb;
                      }
                      .flow-bot-spinner {
                        width: 16px;
                        height: 16px;
                        border-radius: 999px;
                        border: 2px solid #e5e7eb;
                        border-top-color: #4f46e5;
                        animation: flowBotSpin 780ms linear infinite;
                      }
                      .flow-bot-toast.info .flow-bot-toast-icon {
                        background: #eff6ff;
                        color: #1d4ed8;
                        border: 1px solid rgba(37, 99, 235, 0.25);
                      }
                      .flow-bot-toast.success .flow-bot-toast-icon {
                        background: #f0fdf4;
                        color: #15803d;
                        border: 1px solid rgba(22, 163, 74, 0.3);
                      }
                      .flow-bot-toast.warning .flow-bot-toast-icon {
                        background: #fffbeb;
                        color: #b45309;
                        border: 1px solid rgba(217, 119, 6, 0.28);
                      }
                      .flow-bot-toast.error .flow-bot-toast-icon {
                        background: #fef2f2;
                        color: #dc2626;
                        border: 1px solid rgba(220, 38, 38, 0.28);
                      }
                      .flow-bot-toast-progress {
                        position: absolute;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        height: 3px;
                        background: #4f46e5;
                        transform-origin: left center;
                        animation: flowBotTimeline var(--flow-bot-ttl, 8000ms) linear forwards;
                      }
                      .flow-bot-toast.success .flow-bot-toast-progress {
                        background: #16a34a;
                      }
                      .flow-bot-toast.warning .flow-bot-toast-progress {
                        background: #d97706;
                      }
                      .flow-bot-toast.error .flow-bot-toast-progress {
                        background: #dc2626;
                      }
                      .flow-bot-toast.info .flow-bot-toast-progress {
                        background: #2563eb;
                      }
                      @keyframes flowBotSpin {
                        to { transform: rotate(360deg); }
                      }
                      @keyframes flowBotTimeline {
                        from { transform: scaleX(1); }
                        to { transform: scaleX(0); }
                      }
                      @keyframes flowBotToastIn {
                        to { transform: translateX(0); opacity: 1; }
                      }
                      @keyframes flowBotToastOut {
                        to { transform: translateX(12px); opacity: 0; }
                      }
                    `;
                    document.head.appendChild(style);
                    root = document.createElement("div");
                    root.id = rootId;
                    document.body.appendChild(root);
                  }

                  const kind = payload.kind || "info";
                  const titleMap = {
                    loading: "Đang xử lý",
                    info: "Thông tin",
                    success: "Thành công",
                    warning: "Cảnh báo",
                    error: "Lỗi"
                  };
                  const iconMap = {
                    loading: "",
                    info: "i",
                    success: "✓",
                    warning: "!",
                    error: "×"
                  };
                  const toast = document.createElement("div");
                  toast.className = `flow-bot-toast ${kind}`;
                  const icon = document.createElement("div");
                  icon.className = "flow-bot-toast-icon";
                  if (kind === "loading") {
                    const spinner = document.createElement("span");
                    spinner.className = "flow-bot-spinner";
                    icon.appendChild(spinner);
                  } else {
                    icon.textContent = Object.prototype.hasOwnProperty.call(iconMap, kind) ? iconMap[kind] : "i";
                  }
                  const content = document.createElement("div");
                  const title = document.createElement("p");
                  title.className = "flow-bot-toast-title";
                  title.textContent = titleMap[kind] || payload.level || "INFO";
                  const msg = document.createElement("p");
                  msg.className = "flow-bot-toast-msg";
                  msg.textContent = payload.message;
                  const progress = document.createElement("div");
                  progress.className = "flow-bot-toast-progress";
                  content.append(title, msg);
                  toast.append(icon, content, progress);
                  root.prepend(toast);

                  while (root.children.length > 5) {
                    root.lastElementChild?.remove();
                  }
                  const ttlMap = {
                    loading: 9000,
                    info: 7500,
                    success: 7500,
                    warning: 9000,
                    error: 12000
                  };
                  const ttl = ttlMap[kind] || 8000;
                  toast.style.setProperty("--flow-bot-ttl", `${ttl}ms`);
                  window.setTimeout(() => {
                    toast.style.animation = "flowBotToastOut 160ms ease-in forwards";
                    window.setTimeout(() => toast.remove(), 180);
                  }, ttl);
                }
                """,
                payload,
            )

    def set_manual_continue_overlay(self, visible: bool, message: str = "") -> None:
        if self.page is None:
            return
        payload = {
            "visible": visible,
            "message": message or "Bot dang tam dung de ban tu cau hinh Scene Settings trong Flow.",
            "runId": self.config.run_id,
            "apiBaseUrl": (self.config.ui_base_url or "http://127.0.0.1:8000").rstrip("/"),
        }
        with suppress(Exception):
            self.page.evaluate(
                """
                (payload) => {
                  if (!document.body) return;
                  const rootId = "flow-bot-manual-continue-root";
                  let root = document.getElementById(rootId);

                  if (!payload.visible) {
                    root?.remove();
                    return;
                  }

                  if (!root) {
                    const style = document.createElement("style");
                    style.id = "flow-bot-manual-continue-style";
                    style.textContent = `
                      #${rootId} {
                        position: fixed;
                        right: 18px;
                        bottom: 18px;
                        z-index: 2147483647;
                        width: min(360px, calc(100vw - 36px));
                        border-radius: 16px;
                        border: 1px solid rgba(79, 70, 229, 0.22);
                        background: rgba(17, 24, 39, 0.96);
                        color: #fff;
                        box-shadow: 0 20px 45px rgba(0, 0, 0, 0.35);
                        overflow: hidden;
                        font-family: Arial, Helvetica, sans-serif;
                      }
                      .flow-bot-manual-panel {
                        padding: 16px;
                        display: flex;
                        flex-direction: column;
                        gap: 12px;
                      }
                      .flow-bot-manual-kicker {
                        display: inline-flex;
                        align-items: center;
                        gap: 8px;
                        font-size: 11px;
                        font-weight: 800;
                        letter-spacing: 0.08em;
                        text-transform: uppercase;
                        color: #c7d2fe;
                      }
                      .flow-bot-manual-dot {
                        width: 8px;
                        height: 8px;
                        border-radius: 999px;
                        background: #818cf8;
                        box-shadow: 0 0 0 6px rgba(129, 140, 248, 0.14);
                      }
                      .flow-bot-manual-title {
                        margin: 0;
                        font-size: 15px;
                        font-weight: 800;
                        line-height: 1.3;
                      }
                      .flow-bot-manual-text {
                        margin: 0;
                        color: rgba(255,255,255,0.78);
                        font-size: 12px;
                        line-height: 1.5;
                      }
                      .flow-bot-manual-actions {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                      }
                      .flow-bot-manual-btn {
                        border: 0;
                        border-radius: 12px;
                        padding: 11px 16px;
                        background: linear-gradient(135deg, #4f46e5, #7c3aed);
                        color: #fff;
                        font-size: 13px;
                        font-weight: 800;
                        cursor: pointer;
                      }
                      .flow-bot-manual-btn[disabled] {
                        opacity: 0.65;
                        cursor: wait;
                      }
                      .flow-bot-manual-status {
                        font-size: 11px;
                        color: #cbd5e1;
                      }
                    `;
                    document.head.appendChild(style);
                    root = document.createElement("div");
                    root.id = rootId;
                    root.innerHTML = `
                      <div class="flow-bot-manual-panel">
                        <div class="flow-bot-manual-kicker"><span class="flow-bot-manual-dot"></span> Scene Settings Pause</div>
                        <p class="flow-bot-manual-title">Bot dang cho ban xac nhan.</p>
                        <p class="flow-bot-manual-text"></p>
                        <div class="flow-bot-manual-actions">
                          <button type="button" class="flow-bot-manual-btn">Continue / Done</button>
                          <span class="flow-bot-manual-status">Sau khi xong scene settings, bam nut nay de bot tiep tuc.</span>
                        </div>
                      </div>
                    `;
                    document.body.appendChild(root);
                  }

                  const text = root.querySelector(".flow-bot-manual-text");
                  const btn = root.querySelector(".flow-bot-manual-btn");
                  const status = root.querySelector(".flow-bot-manual-status");
                  if (text) text.textContent = payload.message;
                  if (btn) {
                    btn.disabled = false;
                    btn.textContent = "Continue / Done";
                    btn.onclick = async () => {
                      if (btn.disabled) return;
                      btn.disabled = true;
                      btn.textContent = "Dang gui...";
                      if (status) status.textContent = "Dang gui tin hieu tiep tuc cho bot...";
                      try {
                        const resp = await fetch(`${payload.apiBaseUrl}/api/runs/${payload.runId}/continue`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ action: "continue_after_scene_manual" }),
                        });
                        const data = await resp.json().catch(() => ({}));
                        if (!resp.ok) {
                          throw new Error(data.detail || "Khong the tiep tuc bot.");
                        }
                        root.remove();
                      } catch (error) {
                        btn.disabled = false;
                        btn.textContent = "Continue / Done";
                        if (status) status.textContent = error?.message || "Khong the tiep tuc bot.";
                      }
                    };
                  }
                }
                """,
                payload,
            )

    @staticmethod
    def browser_toast_kind(message: str, level: str) -> str:
        level = level.upper()
        text = message.lower()
        if level == "ERROR":
            return "error"
        if level == "WARNING":
            return "warning"
        if level == "SUCCESS" or text.startswith("filled ") or "attached image" in text:
            return "success"
        loading_terms = (
            "waiting",
            "looking",
            "connecting",
            "navigating",
            "opening",
            "uploading",
            "downloading",
            "running product",
            "filling",
            "searching",
            "polling",
            "retry",
        )
        if any(term in text for term in loading_terms):
            return "loading"
        return "info"

    @staticmethod
    def browser_toast_message(message: str) -> str:
        text = message.lower()
        if text.startswith("filling product_name"):
            return "Đang nhập tên sản phẩm vào input."
        if text.startswith("filling short_description"):
            return "Đang nhập mô tả ngắn vào input."
        if text.startswith("filling long_description"):
            return "Đang nhập mô tả dài vào input."
        if "waiting for step 1 product inputs" in text:
            return "Đang đợi các input Step 1 sẵn sàng."
        if text == "filled product_name":
            return "Nhập thành công tên sản phẩm."
        if text == "filled short_description":
            return "Nhập thành công mô tả ngắn."
        if text == "filled long_description":
            return "Nhập thành công mô tả dài."
        if "looking for next step button" in text:
            return "Đang tìm nút để qua bước tiếp theo."
        if "clicked next step" in text:
            return "Qua bước tiếp theo thành công."
        if "looking for image upload trigger" in text:
            return "Đang tìm nút nhập ảnh sản phẩm."
        if "uploading image" in text:
            return "Đang nhập ảnh sản phẩm."
        if "looking for preset import textarea" in text:
            return "Đang tìm ô import preset."
        if "looking for preset manager toggle" in text:
            return "Đang tìm toggle preset manager."
        if "opened preset manager toggle" in text:
            return "Đã mở preset manager."
        if "filled preset json textarea" in text:
            return "Đã nhập preset JSON."
        if "looking for import preset button" in text:
            return "Đang tìm nút import preset."
        if "imported preset from paste" in text:
            return "Import preset thành công."
        if "looking for website logo upload input" in text:
            return "Đang tìm vùng upload logo website."
        if "uploading website logo" in text:
            return "Đang upload logo website."
        if "uploaded website logo" in text:
            return "Upload logo website thành công."
        if "downloading product image" in text:
            return "Đang tải ảnh sản phẩm."
        if "attached image" in text or "confirmed selected image" in text:
            return "Nhập thành công ảnh sản phẩm."
        if "downloaded image" in text:
            return "Đã tải ảnh sản phẩm về máy tạm."
        if "looking for brainstorm" in text:
            return "Đang tìm nút Brainstorm."
        if "clicked brainstorm idea" in text:
            return "Brainstorm thành công."
        if "waiting for brainstorm" in text:
            return "Đang đợi Brainstorm hoàn tất."
        if "generate video step is ready" in text:
            return "Bước tạo video đã sẵn sàng."
        if "looking for generate video button" in text:
            return "Đang tìm nút tạo video."
        if "clicked generate video" in text:
            return "Đã bấm tạo video."
        if "polling video result status" in text:
            return "Đang kiểm tra trạng thái video."
        if "video generation completed" in text:
            return "Video đã tạo xong."
        if "captured video url" in text:
            return "Đã lấy URL video."
        if "waiting for video generation" in text:
            return "Đang đợi video tạo xong."
        if "clicked create next product" in text:
            return "Đã bấm tạo sản phẩm tiếp theo."
        if "step 1 is ready for next product" in text:
            return "Step 1 đã sẵn sàng cho sản phẩm tiếp theo."
        if "connected to existing chrome" in text:
            return "Kết nối Chrome thành công."
        if "connecting to chrome" in text:
            return "Đang kết nối Chrome CDP."
        if "scene mode: skip" in text:
            return "Bo qua Scene Settings va tiep tuc."
        if "scene mode: manual pause" in text:
            return "Bot dang cho ban cau hinh Scene Settings thu cong."
        if "manual scene setup confirmed" in text:
            return "Da nhan xac nhan, bot tiep tuc chay."
        if "no scene columns found" in text:
            return "Excel khong co cot scene, bot se bo qua Scene Settings."
        return message

    # ════════════════════════════════════════════════════════
    # START / CLOSE
    # ════════════════════════════════════════════════════════

    def start(self) -> None:
        self.playwright = sync_playwright().start()

        # ── Chrome profile mode: launch/connect through CDP ───
        if self.config.chrome_user_data_dir:
            cdp_port = self.config.cdp_port
            self.cdp_port = cdp_port
            if not self.is_cdp_ready(cdp_port):
                self.launch_chrome_for_cdp(cdp_port)
            self.emit_log(f"Connecting to Chrome CDP on port {cdp_port}...", "INFO")
            self.wait_for_cdp_ready(cdp_port, timeout_ms=30_000)
            self.browser = self.connect_over_cdp_retry(cdp_port, attempts=6)
            self.context = (
                self.browser.contexts[0]
                if self.browser.contexts
                else self.browser.new_context()
            )
            self.page = self.context.new_page()
            with suppress(Exception):
                self.page.bring_to_front()
            self.emit_log("Connected to existing Chrome successfully.", "SUCCESS")
            return

        # ── Auth-state mode: Playwright launches Chromium ────
        self.browser = self.playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo_ms,
            channel=self.config.channel,
        )
        context_kwargs: dict = {
            "viewport": {"width": 1500, "height": 1000},
            "ignore_https_errors": True,
        }
        if self.config.auth_state_path.exists():
            context_kwargs["storage_state"] = self.config.auth_state_path.as_posix()
            self.emit_log(f"Using saved auth state: {self.config.auth_state_path}")
        self.context = self.browser.new_context(**context_kwargs)
        self.page = self.context.new_page()

    def close(self) -> None:
        if self.context is not None and not self.config.chrome_user_data_dir:
            with suppress(Exception):
                self.context.storage_state(
                    path=self.config.auth_state_path.as_posix(), indexed_db=True
                )
        if self.context is not None:
            with suppress(Exception):
                self.context.close()
        if self.browser is not None:
            with suppress(Exception):
                self.browser.close()
        if self.chrome_process is not None and self.chrome_process.poll() is None:
            with suppress(Exception):
                self.chrome_process.terminate()
            with suppress(Exception):
                self.chrome_process.wait(timeout=5)
        if self.playwright is not None:
            with suppress(Exception):
                self.playwright.stop()

    # ════════════════════════════════════════════════════════
    # AUTH / NAVIGATION
    # ════════════════════════════════════════════════════════

    def save_auth_interactive(self) -> None:
        assert self.context is not None
        self.page = self.context.new_page()
        self.emit_log(f"Opening Flow URL: {self.config.flow_url}", "INFO")
        self.page.goto(self.config.flow_url, wait_until="load", timeout=60_000)
        self.page.bring_to_front()
        self.emit_log(f"Opened page: {self.page.url}", "SUCCESS")
        if self.config.chrome_user_data_dir:
            self.emit_log("Login to Flow in the opened Chrome profile then press Enter.", "INFO")
            input()
            return
        self.emit_log("Login to Flow in the opened browser then press Enter.", "INFO")
        input()
        self.context.storage_state(
            path=self.config.auth_state_path.as_posix(), indexed_db=True
        )
        self.emit_log(f"Saved auth state to {self.config.auth_state_path}", "SUCCESS")

    def open_flow(self) -> None:
        assert self.context is not None
        self.page = self.context.new_page()
        self.page.bring_to_front()
        self.emit_log(f"Navigating to {self.config.flow_url}", "INFO")
        self.page.goto(self.config.flow_url, wait_until="load", timeout=60_000)
        self.emit_log(f"Current URL: {self.page.url}", "SUCCESS")
        try:
            self.page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception as exc:
            self.emit_log(f"Network idle timeout: {exc}", "WARNING")
        self.page.bring_to_front()

    def ensure_browser_alive(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.last_browser_health_check < 10:
            return
        self.last_browser_health_check = now
        page_closed = True
        with suppress(Exception):
            page_closed = self.page is None or self.page.is_closed()
        if not page_closed:
            return
        self.emit_log("Browser/page appears closed. Attempting recovery...", "WARNING")
        self.recover_browser_session()

    def recover_browser_session(self) -> None:
        last_error: Exception | None = None
        attempts = max(0, self.config.max_browser_reconnect_retries)
        for attempt in range(1, attempts + 1):
            try:
                self.emit_log(f"Browser reconnect attempt {attempt}/{attempts}...", "WARNING")
                if self.config.chrome_user_data_dir:
                    port = self.cdp_port or self.config.cdp_port
                    if not self.is_cdp_ready(port):
                        self.launch_chrome_for_cdp(port)
                    self.wait_for_cdp_ready(port, timeout_ms=30_000)
                    assert self.playwright is not None
                    self.browser = self.connect_over_cdp_retry(port, attempts=2)
                    self.context = (
                        self.browser.contexts[0]
                        if self.browser.contexts
                        else self.browser.new_context()
                    )
                    self.page = self.first_open_page_or_new()
                else:
                    if self.browser is None:
                        assert self.playwright is not None
                        self.browser = self.playwright.chromium.launch(
                            headless=self.config.headless,
                            slow_mo=self.config.slow_mo_ms,
                            channel=self.config.channel,
                        )
                    if self.context is None:
                        context_kwargs: dict = {
                            "viewport": {"width": 1500, "height": 1000},
                            "ignore_https_errors": True,
                        }
                        if self.config.auth_state_path.exists():
                            context_kwargs["storage_state"] = self.config.auth_state_path.as_posix()
                        self.context = self.browser.new_context(**context_kwargs)
                    self.page = self.context.new_page()

                assert self.page is not None
                self.page.goto(self.config.flow_url, wait_until="load", timeout=60_000)
                with suppress(Exception):
                    self.page.wait_for_load_state("networkidle", timeout=15_000)
                self.page.bring_to_front()
                self.emit_log("Browser recovery succeeded.", "SUCCESS")
                return
            except Exception as exc:
                last_error = exc
                self.emit_log(f"Browser reconnect attempt failed: {exc}", "WARNING")
                self.sleep_ms(2_000)
        raise RuntimeError(f"Browser recovery failed after {attempts} attempts: {last_error}")

    def first_open_page_or_new(self) -> Page:
        assert self.context is not None
        for page in self.context.pages:
            with suppress(Exception):
                if not page.is_closed():
                    return page
        return self.context.new_page()

    # ════════════════════════════════════════════════════════
    # BATCH / SINGLE PRODUCT ORCHESTRATION
    # ════════════════════════════════════════════════════════

    def run_batch(self, products: list[ProductRow]) -> None:
        if not products:
            raise ValueError("No products to run")
        start = max(0, self.config.start_index)
        end = (
            len(products)
            if self.config.limit is None
            else min(len(products), start + self.config.limit)
        )
        total = end - start
        self.emit_log(
            f"═══════════════════════════════════════",
            "INFO",
        )
        self.emit_log(
            f"  BATCH START: {total} sản phẩm  (#{start + 1} → #{end})",
            "INFO",
        )
        self.emit_log(
            f"═══════════════════════════════════════",
            "INFO",
        )
        self.open_flow()
        for index in range(start, end):
            product = products[index]
            current = index - start + 1
            self.emit_log(
                f"───────────────────────────────────────",
                "INFO",
            )
            self.emit_log(
                f"  [SP {current}/{total}] Bắt đầu: {product.product_name}",
                "INFO",
            )
            self.emit_log(
                f"───────────────────────────────────────",
                "INFO",
            )
            try:
                self.run_single(product, index, current, total)
                self.emit_log(
                    f"  [SP {current}/{total}] ✓ Hoàn thành: {product.product_name}",
                    "SUCCESS",
                )
            except Exception as exc:
                self.capture_debug(f"error-product-{index + 1}")
                self.emit_log(
                    f"  [SP {current}/{total}] ✗ Thất bại: {exc}",
                    "ERROR",
                )
                if self.config.continue_on_video_failure:
                    self.emit_log(
                        f"  [SP {current}/{total}] Continuing with next product after failure.",
                        "WARNING",
                    )
                    with suppress(Exception):
                        if self.config.auto_restart:
                            self.wait_for_create_next_product(45_000)
                    continue
                raise
        self.emit_log(
            f"═══════════════════════════════════════",
            "SUCCESS",
        )
        self.emit_log(f"  BATCH DONE: Tất cả {total} sản phẩm đã xong!", "SUCCESS")
        self.emit_log(
            f"═══════════════════════════════════════",
            "SUCCESS",
        )
        if self.config.enable_logo_overlay and self.config.auto_logo_overlay_after_batch:
            self.emit_log("Batch post-processing: applying missing logo overlays...", "INFO")
            self.process_batch_logo_overlays()
        if self.config.keep_browser_open:
            self.emit_log("Browser kept open. Press Enter to close.", "INFO")
            input()

    def run_single(
        self,
        product: ProductRow,
        index: int,
        current: int = 1,
        total: int = 1,
    ) -> None:
        """
        Full automation flow for one product:
          Step 1  → fill fields + upload image + click next-step
          Step 2  → click brainstorm idea  (auto-advances to Step 3)
          Step 3  → wait for generate-video button, click it
          Post    → wait for create-next-product, click it, wait for Step 1
        """
        tag = f"[SP {current}/{total}]"
        self.current_image_cleanup_result = {}

        # ── Step 1: product form ─────────────────────────────
        self.emit_log(f"{tag} Step 1 — Đang chờ giao diện sẵn sàng...")
        frame = self.wait_for_tool_frame()
        self.wait_for_product_step_ready(frame)
        self.import_preset_if_needed(frame)
        self.upload_website_logo_if_needed(frame)
        self.emit_log(f"{tag} Step 1 — Điền thông tin sản phẩm: {product.product_name}")
        self.fill_text_fields(frame, product)
        if product.product_image:
            self.emit_log(f"{tag} Step 1 — Upload ảnh sản phẩm...")
            original_image_path = self.download_image(product.product_image, index)
            upload_image_path = self.clean_product_image(original_image_path, product, index)
            frame = self.upload_image(frame, upload_image_path, product=product)
            self.clean_uploaded_product_image_in_flow(frame, product=product)
        self.configure_multi_clip_flow_settings(frame)
        self.sleep_ms(self.config.extra_wait_after_fill_ms)

        # ── Step 1 → Step 2 ──────────────────────────────────
        if self.config.auto_next:
            self.emit_log(f"{tag} Step 1 -> Step 2 - Checking whether Next Step is needed...")
            self.click_next_step_if_needed(frame)

        self.handle_scene_settings_mode(frame, product)

        # ── Step 2: brainstorm ───────────────────────────────
        self.emit_log(f"{tag} Step 2 — Bắt đầu Brainstorm ý tưởng...")
        self.emit_log(f"{tag} Step 2 - Selecting video model: {self.config.video_model}...")
        self.select_video_model_if_available(frame, self.config.video_model)
        self.click_brainstorm_idea(frame)

        # ── Wait for Step 3: generate-video ready ────────────
        self.emit_log(f"{tag} Step 3 — Đang chờ Brainstorm hoàn tất để tạo video...")
        self.wait_for_generate_video_step(frame, timeout_ms=120_000)

        # ── Step 3: generate video ───────────────────────────
        if self.config.auto_generate and self.config.multi_clip_mode != "off":
            self.run_multi_clip_product(frame, product, index, current, total)
            if self.config.auto_restart:
                self.emit_log(f"{tag} Post â€” Äang chá» nÃºt Táº¡o sáº£n pháº©m tiáº¿p theo...")
                self.wait_for_create_next_product(self.config.wait_timeout_ms)
            return

        if self.config.auto_generate:
            self.emit_log(f"{tag} Step 3 — Nhấn Generate Video...")
            self.click_generate(frame)
            self.emit_log(f"{tag} Step 3 — Đang chờ video render xong...")
            result = self.wait_for_video_completed_and_capture(product, index)
            self.persist_scene_video_result(result, frame=frame)
            self.append_video_result_csv(result)
            if result.get("status") == "failed" and not self.config.continue_on_video_failure:
                raise RuntimeError(result.get("error") or "Video generation failed.")

        # ── Post: wait for create-next-product, then restart ─
        if self.config.auto_restart:
            self.emit_log(f"{tag} Post — Đang chờ nút Tạo sản phẩm tiếp theo...")
            self.wait_for_create_next_product(self.config.wait_timeout_ms)

    # ════════════════════════════════════════════════════════
    # STEP NAVIGATION
    # ════════════════════════════════════════════════════════

    def click_next_step(self, frame: Frame) -> None:
        """Click the next-step button at the end of Step 1."""
        self.emit_log("Looking for next step button...")
        btn = self.find_button_by_selectors_or_text(
            frame,
            selectors=[
                '[data-flow-action="next-step"]',
                '[data-flow-field="next-step"]',
            ],
            patterns=[
                r"^tiếp$",
                r"tiếp tục",
                r"tiep tuc",
                r"\bnext\b",
                r"\bcontinue\b",
            ],
        )
        if btn is None:
            self.capture_debug("next-step-not-found")
            raise RuntimeError("next-step button not found.")
        btn.click()
        self.emit_log("Clicked next step.")
        self.sleep_ms(800)

    def click_next_step_if_needed(self, frame: Frame) -> None:
        if self.find_brainstorm_button(frame) is not None:
            self.emit_log("Brainstorm button is already visible; skipping next-step.", "INFO")
            return
        try:
            self.click_next_step(frame)
        except RuntimeError:
            if self.find_brainstorm_button(frame) is not None:
                self.emit_log("No next-step found, but brainstorm is ready; continuing.", "INFO")
                return
            raise

    def handle_scene_settings_mode(self, frame: Frame, product: ProductRow) -> None:
        mode = self.config.scene_mode
        if mode == "skip":
            self.emit_log("Scene mode: skip.", "INFO")
            return
        if mode == "manual_pause":
            if not self.has_scene_settings_fields(frame):
                self.emit_log(
                    "Scene mode: manual pause requested, but this tool has no Scene Settings fields. Skipping pause.",
                    "INFO",
                )
                return
            self.wait_for_manual_scene_continue()
            return
        if mode == "auto_excel":
            if not self.config.scene_field_keys:
                self.emit_log("No scene columns found. Skipping scene settings.", "WARNING")
                return
            if not self.has_scene_settings_fields(frame):
                self.emit_log(
                    "Excel has scene columns, but this tool has no Scene Settings fields. Skipping scene fill.",
                    "INFO",
                )
                return
            self.emit_log(
                "Scene mode: auto_excel. Filling scene settings from Excel columns.",
                "INFO",
            )
            self.fill_scene_metadata_if_available(frame, product)
            return
        self.emit_log(f"Unknown scene mode '{mode}'. Skipping scene settings.", "WARNING")

    def has_scene_settings_fields(self, frame: Frame) -> bool:
        selectors = [
            '[data-flow-field="scene-group-id"]',
            '[data-flow-field="scene-number"]',
            '[data-flow-field="scene-total"]',
            '[data-flow-field="scene-role"]',
            '[data-flow-field="scene-continuity-notes"]',
        ]
        for selector in selectors:
            if self.find_in_all_frames(selector, require_visible=False) is not None:
                return True
            with suppress(Exception):
                locator = frame.locator(selector).first
                if locator.count():
                    return True
        return False

    def wait_for_manual_scene_continue(self) -> None:
        timeout_ms = max(self.config.manual_scene_pause_timeout_ms, 1)
        message = "Paused for manual scene setup."
        self.emit_log("Scene mode: manual pause. Waiting for user.", "WARNING")
        self.emit_log("Bot đang tạm dừng để bạn tự cấu hình Scene Settings trong Flow.", "INFO")
        if self.config.notify_manual_scene_pause:
            self.config.notify_manual_scene_pause(True, message)
        self.set_manual_continue_overlay(
            True,
            "Bot dang tam dung de ban tu cau hinh Scene Settings trong Flow. Xong roi bam Continue / Done ngay tren tool nay.",
        )
        self.show_browser_toast(message, "WARNING", kind="warning")
        wait_fn = self.config.wait_for_manual_scene_continue
        if wait_fn is None:
            raise RuntimeError("Manual scene continue handler is not configured.")
        try:
            continued = wait_fn(timeout_ms)
        finally:
            self.set_manual_continue_overlay(False)
            if self.config.notify_manual_scene_pause:
                self.config.notify_manual_scene_pause(False, "")
        if not continued:
            raise RuntimeError("Manual scene setup timed out after waiting 30 minutes.")
        self.emit_log("Manual scene setup confirmed. Continuing automation.", "SUCCESS")
        self.sleep_ms(400)

    # ════════════════════════════════════════════════════════
    # STEP 2: BRAINSTORM
    # ════════════════════════════════════════════════════════

    def select_video_model_if_available(self, frame: Frame, model_name: str) -> None:
        self.emit_log("Looking for video model selector...")
        selectors = [
            'select[data-flow-field="video-model"]',
            '[data-flow-field="video-model"] select',
            '[data-flow-field="video-model"]',
        ]
        deadline = time.time() + 20
        locator: Optional[Locator] = None
        while time.time() < deadline:
            locator = self.find_visible_by_selector(frame, selectors)
            if locator is not None:
                break
            self.sleep_ms(500)

        if locator is None:
            self.emit_log(
                "Video model selector not found. Continuing with current model.",
                "WARNING",
            )
            return

        locator.scroll_into_view_if_needed()
        tag_name = ""
        with suppress(Exception):
            tag_name = (locator.evaluate("(el) => el.tagName") or "").lower()
        if tag_name != "select":
            nested = self.find_visible_by_selector(locator, ["select"])
            if nested is not None:
                locator = nested

        errors: list[str] = []
        for option in ({"value": model_name}, {"label": model_name}):
            try:
                locator.select_option(**option)
                locator.dispatch_event("input")
                locator.dispatch_event("change")
                selected = locator.input_value()
                if selected == model_name:
                    self.emit_log(f"Selected video model: {model_name}", "SUCCESS")
                    return
            except Exception as exc:
                errors.append(str(exc))

        with suppress(Exception):
            selected_text = locator.evaluate(
                """(select, modelName) => {
                    const option = Array.from(select.options || []).find((item) =>
                        item.value === modelName || item.textContent.trim() === modelName
                    );
                    if (!option) return "";
                    select.value = option.value;
                    select.dispatchEvent(new Event("input", { bubbles: true }));
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                    return option.textContent.trim();
                }""",
                model_name,
            )
            if selected_text == model_name:
                self.emit_log(f"Selected video model: {model_name}", "SUCCESS")
                return

        self.emit_log(
            f"Could not select video model '{model_name}'. Continuing with current model.",
            "WARNING",
        )
        if errors:
            self.emit_log(f"Video model select errors: {' | '.join(errors[:2])}", "WARNING")

    def find_brainstorm_button(self, frame: Frame) -> Optional[Locator]:
        selectors = [
            '[data-flow-action="brainstorm-idea"]',
            '[data-flow-field="brainstorm-idea"]',
        ]
        patterns = [
            r"brainstorm",
            r"ý tưởng",
            r"y tuong",
            r"tạo ý tưởng",
            r"tao y tuong",
            r"lập kịch bản",
            r"lap kich ban",
        ]
        button = self.find_button_by_selectors_or_text(frame, selectors=selectors, patterns=patterns)
        if button is not None:
            return button
        for scope in self.iter_page_and_frame_scopes():
            if scope == frame:
                continue
            button = self.find_button_by_selectors_or_text(scope, selectors=selectors, patterns=patterns)
            if button is not None:
                return button
        return None

    def click_brainstorm_idea(self, frame: Frame) -> None:
        """Click the 'Brainstorm Ý Tưởng' button on Step 2."""
        self.emit_log("Looking for brainstorm idea button...")

        # Poll — the button may appear a moment after step transition
        deadline = time.time() + 30
        btn: Optional[Locator] = None
        while time.time() < deadline:
            self.ensure_browser_alive()
            frame = self.refresh_frame_reference(frame)
            btn = self.find_brainstorm_button(frame)
            if btn is not None:
                break
            self.sleep_ms(800)

        if btn is None:
            self.capture_debug("brainstorm-not-found")
            raise RuntimeError(
                "Brainstorm idea button not found on Step 2. "
                "Screenshot saved to brainstorm-not-found.png"
            )
        btn.click()
        self.emit_log("Clicked brainstorm idea.", "SUCCESS")

    # ════════════════════════════════════════════════════════
    # STEP 3: WAIT FOR GENERATE VIDEO
    # ════════════════════════════════════════════════════════

    def wait_for_generate_video_step(
        self, frame: Frame, timeout_ms: int = 120_000
    ) -> None:
        """
        Poll until the generate-video button is visible and enabled.
        Brainstorm runs in the background — this waits for it to finish.
        """
        deadline = time.time() + timeout_ms / 1000
        log_interval = 10          # seconds between progress logs
        last_log_time = time.time()

        self.emit_log("Waiting for brainstorm to finish and generate-video to appear...")
        while time.time() < deadline:
            self.ensure_browser_alive()
            frame = self.refresh_frame_reference(frame)
            brainstorm_status = self.read_flow_output_text("brainstorm-status").strip().lower()
            brainstorm_ready = self.read_flow_output_text("brainstorm-ready").strip().lower()
            generate_ready = self.read_flow_output_text("generate-video-ready").strip().lower()
            if brainstorm_status in {"failed", "error"} or "failed" in brainstorm_status:
                raise RuntimeError("Brainstorm failed before video generation became ready.")
            flow_error = self.read_visible_flow_error(frame)
            if flow_error:
                raise RuntimeError(f"Flow Builder reported an error before generate-video became ready: {flow_error}")
            btn = self.find_generate_button(frame)
            output_ready = generate_ready in {"true", "1", "yes", "ready", "completed"}
            brainstorm_done = (
                brainstorm_status in {"completed", "done", "success"}
                or brainstorm_ready in {"true", "1", "yes", "ready"}
            )
            if output_ready or (btn is not None and (brainstorm_done or not brainstorm_status)):
                self.emit_log("Generate video step is ready.", "SUCCESS")
                return

            now = time.time()
            if now - last_log_time >= log_interval:
                elapsed = int(now - (deadline - timeout_ms / 1000))
                self.emit_log(
                    f"Waiting for brainstorm to finish... ({elapsed}s elapsed)"
                )
                last_log_time = now

            self.sleep_ms(1_000)

        self.capture_debug("generate-video-not-found")
        raise TimeoutError(
            f"generate-video button did not appear after {timeout_ms // 1000}s. "
            "Screenshot saved to generate-video-not-found.png"
        )

    def read_visible_flow_error(self, frame: Frame) -> str:
        selectors = [
            '[data-flow-error]',
            '[data-flow-status="error"]',
            '[data-flow-alert="error"]',
            '[data-flow-message="error"]',
            '[role="alert"]',
            '[aria-live="assertive"]',
        ]
        script = """
            (selectors) => {
              for (const selector of selectors) {
                for (const el of Array.from(document.querySelectorAll(selector)).slice(0, 8)) {
                  const style = window.getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  const visible = style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
                  if (!visible) continue;
                  const text = (el.getAttribute("data-flow-error") || el.textContent || "").trim().replace(/\\s+/g, " ");
                  if (text) return text.slice(0, 500);
                }
              }
              return "";
            }
        """
        scopes: list[Page | Frame] = []
        if frame is not None:
            scopes.append(frame)
        scopes.extend(self.iter_page_and_frame_scopes())
        for scope in scopes:
            with suppress(Exception):
                message = str(scope.evaluate(script, selectors) or "").strip()
                if message:
                    return message
        return ""

    # ════════════════════════════════════════════════════════
    # GENERATE VIDEO
    # ════════════════════════════════════════════════════════

    def find_generate_button(self, frame: Frame) -> Optional[Locator]:
        """Return the generate-video button if visible and enabled, else None."""
        button = self.find_button_by_selectors_or_text(
            frame,
            selectors=[
                '[data-flow-action="generate-video"]',
                '[data-flow-field="generate-video"]',
            ],
            patterns=[
                r"generate video",
                r"dựng video",
                r"dung video",
                r"tạo video",
                r"tao video",
                r"sản xuất video",
                r"san xuat video",
                r"create video",
                r"\bgenerate\b",
            ],
        )
        if button is not None:
            return button
        for scope in self.iter_page_and_frame_scopes():
            if scope == frame:
                continue
            button = self.find_button_by_selectors_or_text(
                scope,
                selectors=[
                    '[data-flow-action="generate-video"]',
                    '[data-flow-field="generate-video"]',
                ],
                patterns=[
                r"generate video",
                r"render clip",
                r"render video",
                r"dá»±ng video",
                    r"dung video",
                    r"táº¡o video",
                    r"tao video",
                    r"sản xuất video",
                    r"san xuat video",
                    r"create video",
                    r"\bgenerate\b",
                ],
            )
            if button is not None:
                return button
        return None

    def click_generate(self, frame: Frame) -> None:
        self.emit_log("Looking for generate video button...")
        btn = self.find_generate_button(frame)
        if btn is None:
            self.capture_debug("generate-video-not-found")
            raise RuntimeError("Generate video button not found.")
        btn.click()
        self.emit_log("Clicked generate video.", "SUCCESS")

    def configure_multi_clip_flow_settings(self, frame: Frame) -> None:
        core_settings = [
            ("video-model", self.config.video_model),
            ("aspect-ratio", self.config.aspect_ratio),
        ]
        optional_settings = [
            ("multi-clip-mode", self.config.multi_clip_mode),
            ("scene-builder-mode", self.config.scene_builder_mode),
            ("target-final-duration", self.normalize_target_final_duration(self.config.target_final_duration)),
        ]
        for field_name, value in core_settings:
            if self.select_flow_field_value(frame, field_name, value):
                self.emit_log(f"Selected Flow {field_name}: {value}", "INFO")
            else:
                self.emit_log(f"Flow selector not found for {field_name}; continuing.", "WARNING")

        if self.find_brainstorm_button(frame) is not None:
            self.emit_log("Brainstorm button is ready after core settings; skipping optional setting selectors.", "INFO")
            return

        for field_name, value in optional_settings:
            if self.find_brainstorm_button(frame) is not None:
                self.emit_log("Brainstorm button became ready; continuing to script generation.", "INFO")
                return
            if self.select_flow_field_value(frame, field_name, value):
                self.emit_log(f"Selected Flow {field_name}: {value}", "INFO")
            else:
                self.emit_log(f"Flow selector not found for {field_name}; continuing.", "WARNING")

    def select_flow_field_value(self, frame: Frame, field_name: str, value: str) -> bool:
        selectors = [
            f'select[data-flow-field="{field_name}"]',
            f'[data-flow-field="{field_name}"] select',
            f'[data-flow-field="{field_name}"]',
        ]
        locator = self.find_visible_by_selector(frame, selectors)
        if locator is None:
            for selector in selectors:
                locator = self.find_in_all_frames(selector)
                if locator is not None:
                    break
        if locator is None:
            return False
        with suppress(Exception):
            locator.scroll_into_view_if_needed()
        with suppress(Exception):
            tag_name = (locator.evaluate("(el) => el.tagName") or "").lower()
            if tag_name != "select":
                nested = self.find_visible_by_selector(locator, ["select"])
                if nested is not None:
                    locator = nested
        option_tokens = self.flow_option_tokens(field_name, value)
        for option in ({"value": value}, {"label": value}):
            with suppress(Exception):
                locator.select_option(**option, timeout=1_500)
                locator.dispatch_event("input")
                locator.dispatch_event("change")
                return True
        with suppress(Exception):
            selected = locator.evaluate(
                """(select, payload) => {
                    const { targetValue, optionTokens } = payload;
                    const option = Array.from(select.options || []).find((item) =>
                        item.value === targetValue
                        || item.textContent.trim() === targetValue
                        || optionTokens.includes(item.value || "")
                        || optionTokens.includes(item.getAttribute("data-flow-option") || "")
                    );
                    if (!option) return false;
                    select.value = option.value;
                    select.dispatchEvent(new Event("input", { bubbles: true }));
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                    return true;
                }""",
                {"targetValue": value, "optionTokens": option_tokens},
            )
            return bool(selected)
        for token in option_tokens:
            option_locator = self.find_in_all_frames(f'[data-flow-option="{token}"]')
            if option_locator is not None:
                with suppress(Exception):
                    locator.click()
                with suppress(Exception):
                    option_locator.click()
                    return True
        return False

    def normalize_target_final_duration(self, value: int | str) -> str:
        text = str(value or "").strip()
        return text if text.endswith("s") else f"{text}s"

    def flow_option_tokens(self, field_name: str, value: str) -> list[str]:
        normalized = str(value or "").strip().lower()
        tokens_by_field = {
            "video-model": {
                "veo 3.1 - lite": "video-model-veo31-lite",
                "veo 3.1 - fast": "video-model-veo31-fast",
                "veo 3.1 - quality": "video-model-veo31-quality",
                "omni flash": "video-model-gemini-omni-flash",
                "gemini omni flash": "video-model-gemini-omni-flash",
            },
            "aspect-ratio": {
                "9:16": "aspect-ratio-9-16",
                "9-16": "aspect-ratio-9-16",
                "16:9": "aspect-ratio-16-9",
                "16-9": "aspect-ratio-16-9",
                "1:1": "aspect-ratio-1-1",
                "1-1": "aspect-ratio-1-1",
            },
            "multi-clip-mode": {
                "2": "multi-clip-2",
                "3": "multi-clip-3",
                "auto": "multi-clip-auto",
                "off": "multi-clip-off",
            },
            "scene-builder-mode": {
                "native_flow": "scene-builder-native-flow",
                "native-flow": "scene-builder-native-flow",
                "bot_merge": "scene-builder-bot-merge",
                "bot-merge": "scene-builder-bot-merge",
                "off": "scene-builder-off",
            },
        }
        token = tokens_by_field.get(field_name, {}).get(normalized)
        return [token] if token else []

    def run_multi_clip_product(
        self,
        frame: Frame,
        product: ProductRow,
        index: int,
        current: int,
        total: int,
    ) -> None:
        self.emit_log("Multi-clip mode enabled.", "INFO")
        plan = self.read_clip_plan(frame)
        if not plan:
            plan = self.build_fallback_clip_plan(product, self.config.video_model, self.config.target_final_duration)
        plan = self.normalize_clip_plan_for_mode(plan, product)
        self.emit_log(f"Clip plan loaded: {len(plan)} clips.", "SUCCESS")
        native_scene_controls_seen = False
        if self.config.scene_builder_mode == "native_flow" and not self.has_native_scene_builder_controls():
            self.emit_log(
                "Native Scene Builder controls are not present yet; bot will use local merge unless they appear after render.",
                "INFO",
            )

        scene_group_id = self.multi_clip_scene_group_id(product, index)
        batch_dir = self.batch_storage_dir()
        clips_dir = batch_dir / "clips" / scene_group_id
        voice_dir = batch_dir / "voice" / scene_group_id
        subtitle_dir = batch_dir / "subtitles" / scene_group_id
        final_dir = batch_dir / "final"
        clips_dir.mkdir(parents=True, exist_ok=True)
        voice_dir.mkdir(parents=True, exist_ok=True)
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        clip_results: list[dict] = []
        clip_paths: list[Path] = []
        clip_subtitle_segments: list[tuple[int, float, list[dict]]] = []
        last_frame_path: Path | None = None
        scene_id = ""
        scene_clip_list = ""
        previous_video_url = ""
        previous_video_download_data = ""
        status = "completed"
        error = ""

        for clip_index, clip in enumerate(plan, start=1):
            clip_role = self.slugify(str(clip.get("clip_role") or clip.get("role") or f"clip_{clip_index}")) or f"clip_{clip_index}"
            self.emit_log(f"Generating clip {clip_index}/{len(plan)}: {clip_role}", "INFO")
            if clip_index > 1 and last_frame_path is not None:
                if self.has_start_frame_upload_input() and self.upload_start_frame(frame, last_frame_path):
                    self.emit_log(f"Uploaded start frame for clip {clip_index}.", "SUCCESS")
                elif self.has_start_frame_upload_input():
                    self.emit_log(
                        f"Could not upload start frame for clip {clip_index}; continuing with product image reference.",
                        "WARNING",
                    )
                else:
                    self.emit_log("Start-frame input not present; using tool-native next-clip continuity.", "INFO")

            max_attempts = max(1, int(self.config.max_generate_retries) + 1)
            for attempt in range(1, max_attempts + 1):
                try:
                    if attempt > 1:
                        self.emit_log(f"Retrying clip {clip_index} ({attempt}/{max_attempts})...", "WARNING")
                    self.click_generate_for_clip(frame, clip_index)
                    clip_metadata = {
                        "multi_clip": True,
                        "clip_total": len(plan),
                        "clip_index": clip_index,
                        "clip_role": clip_role,
                        "clip_duration": clip.get("duration", ""),
                        "scene_group_id": scene_group_id,
                        "scene_number": clip_index,
                        "scene_total": len(plan),
                        "scene_role": clip_role,
                        "scene_title": f"{product.product_name} - {clip_role}",
                    }
                    result = self.wait_for_video_completed_and_capture(
                        product,
                        index,
                        clip_metadata=clip_metadata,
                        previous_video_url=previous_video_url,
                        previous_video_download_data=previous_video_download_data,
                    )
                    if str(result.get("status") or "").lower() != "completed":
                        raise RuntimeError(result.get("error") or f"Clip {clip_index} failed.")

                    clip_path = clips_dir / f"clip_{clip_index:02d}_raw.mp4"
                    video_bytes = self.resolve_video_bytes(result)
                    if video_bytes is not None:
                        clip_path.write_bytes(video_bytes)
                    elif not self.try_download_video_button(frame, clip_path):
                        raise RuntimeError(f"Could not download clip {clip_index} video bytes.")
                    result["batch_id"] = self.batch_id()
                    result["clip_video_file"] = clip_path.relative_to(batch_dir).as_posix()
                    result["video_file"] = result["clip_video_file"]
                    result["raw_video_file"] = result["clip_video_file"]
                    result["storage_path"] = clip_path.relative_to(self.config.output_dir).as_posix()
                    self.emit_log(f"Saved clip {clip_index}.", "SUCCESS")

                    audio_result = self.process_clip_external_tts(
                        frame=frame,
                        result=result,
                        clip_index=clip_index,
                        clip_path=clip_path,
                        voiced_path=clips_dir / f"clip_{clip_index:02d}_voiced.mp4",
                        voice_path=voice_dir / f"clip_{clip_index:02d}_voice.mp3",
                        voice_json_path=voice_dir / f"clip_{clip_index:02d}_voice.json",
                        subtitle_path=subtitle_dir / f"clip_{clip_index:02d}.srt",
                        batch_dir=batch_dir,
                    )
                    result.update(audio_result)
                    effective_clip_path = (
                        clips_dir / Path(str(audio_result.get("voiced_clip_file") or "")).name
                        if audio_result.get("tts_status") == "success" and audio_result.get("voiced_clip_file")
                        else clip_path
                    )
                    if audio_result.get("voiceover_json"):
                        clip_duration = self.safe_media_duration_seconds(clip_path)
                        clip_subtitle_segments.append(
                            (
                                clip_index,
                                clip_duration,
                                audio_result.get("voiceover_json") or [],
                            )
                        )

                    last_frame_path = clips_dir / f"last_frame_{clip_index:02d}.png"
                    if not self.has_start_frame_upload_input():
                        if not self.extract_last_frame_ffmpeg(clip_path, last_frame_path):
                            self.emit_log(f"Could not extract last frame for clip {clip_index}.", "WARNING")
                            last_frame_path = None
                    elif not self.capture_last_frame_from_flow(frame, clip_index, last_frame_path):
                        if not self.extract_last_frame_ffmpeg(clip_path, last_frame_path):
                            self.emit_log(f"Could not capture last frame for clip {clip_index}.", "WARNING")
                            last_frame_path = None
                    if last_frame_path is not None and last_frame_path.exists():
                        result["last_frame_file"] = last_frame_path.relative_to(batch_dir).as_posix()
                        self.emit_log(f"Captured last frame for clip {clip_index}.", "SUCCESS")

                    if (
                        self.config.scene_builder_mode == "native_flow"
                        and self.has_native_scene_builder_controls()
                    ):
                        native_scene_controls_seen = True
                        if self.add_clip_to_native_scene(frame):
                            self.emit_log("Added clip to native Flow scene.", "SUCCESS")
                        scene_id = self.read_flow_output_text("scene-id") or scene_id
                        scene_clip_list = self.read_flow_output_text("scene-clip-list") or scene_clip_list

                    previous_video_url = str(result.get("video_url") or "")
                    previous_video_download_data = str(result.get("video_download_data") or "")
                    clip_results.append(result)
                    clip_paths.append(effective_clip_path)
                    break
                except Exception as exc:
                    if attempt < max_attempts:
                        self.emit_log(f"Clip {clip_index} attempt {attempt} failed: {exc}", "WARNING")
                        self.sleep_ms(1_500)
                        continue
                    status = "failed"
                    error = str(exc)
                    self.emit_log(f"Clip {clip_index} failed: {exc}", "ERROR")
            if status == "failed":
                break

        final_video_file = ""
        native_scene_file = ""
        merge_method = ""
        postprocess_result: dict = {}
        raw_final_path = final_dir / f"{scene_group_id}_raw.mp4"
        final_path = final_dir / f"{scene_group_id}_final.mp4"

        if status == "completed":
            if (
                self.config.scene_builder_mode == "native_flow"
                and (native_scene_controls_seen or self.has_native_scene_builder_controls())
            ):
                native_target = final_dir / f"{scene_group_id}_native.mp4"
                self.wait_for_scene_finished(timeout_ms=60_000)
                if self.try_download_native_scene(frame, native_target):
                    raw_final_path = native_target
                    native_scene_file = native_target.relative_to(batch_dir).as_posix()
                    merge_method = "native_flow/download_scene"
                else:
                    self.emit_log("Native scene download failed; using FFmpeg merge.", "WARNING")

            if not raw_final_path.exists():
                if self.merge_clips_ffmpeg(clip_paths, raw_final_path):
                    merge_method = merge_method or "ffmpeg_concat"
                    self.emit_log("Final merged video saved.", "SUCCESS")
                else:
                    status = "failed"
                    error = "FFmpeg merge failed."

            if status == "completed":
                final_subtitle_path = batch_dir / "subtitles" / scene_group_id / "final.srt"
                if clip_subtitle_segments and self.combine_clip_subtitles(clip_subtitle_segments, final_subtitle_path):
                    self.emit_log(f"Combined final subtitles: {final_subtitle_path.name}", "SUCCESS")
                base_row = self.multi_clip_base_row(
                    product,
                    index,
                    scene_group_id,
                    clip_results,
                    raw_final_path,
                    final_path,
                    native_scene_file,
                    scene_id,
                    merge_method,
                )
                if final_subtitle_path.exists():
                    base_row["subtitles_srt"] = final_subtitle_path.read_text(encoding="utf-8")
                    base_row["final_subtitle_file"] = final_subtitle_path.relative_to(batch_dir).as_posix()
                base_row["audio_pipeline"] = "external-tts" if self.config.enable_external_tts else "raw"
                base_row["tts_provider"] = self.config.tts_provider
                postprocess_result = self.create_final_video_with_postprocessing(raw_final_path, final_path, base_row)
                postprocess_result.setdefault("final_subtitle_file", base_row.get("final_subtitle_file", ""))
                postprocess_result.setdefault("audio_pipeline", base_row.get("audio_pipeline", ""))
                postprocess_result.setdefault("tts_provider", base_row.get("tts_provider", ""))
                base_row.update(postprocess_result)
                final_video_file = final_path.relative_to(batch_dir).as_posix() if final_path.exists() else raw_final_path.relative_to(batch_dir).as_posix()
                for result in clip_results:
                    result["final_video_file"] = final_video_file
                    result["scene_id"] = scene_id
                    result["merge_method"] = merge_method
                    self.append_video_result_csv(result)
                self.persist_multi_clip_product_manifest(
                    batch_dir=batch_dir,
                    product=product,
                    index=index,
                    scene_group_id=scene_group_id,
                    clip_results=clip_results,
                    scene_id=scene_id,
                    scene_clip_list=scene_clip_list,
                    native_scene_file=native_scene_file,
                    final_video_file=final_video_file,
                    merge_method=merge_method,
                    status=status,
                    error=error,
                    postprocess_result=postprocess_result,
                )
                return

        self.persist_multi_clip_product_manifest(
            batch_dir=batch_dir,
            product=product,
            index=index,
            scene_group_id=scene_group_id,
            clip_results=clip_results,
            scene_id=scene_id,
            scene_clip_list=scene_clip_list,
            native_scene_file=native_scene_file,
            final_video_file=final_video_file,
            merge_method=merge_method,
            status=status,
            error=error,
            postprocess_result=postprocess_result,
        )
        for result in clip_results:
            result["final_video_file"] = final_video_file
            result["scene_id"] = scene_id
            result["merge_method"] = merge_method
            result["status"] = result.get("status") or status
            result["error"] = result.get("error") or error
            self.append_video_result_csv(result)
        raise RuntimeError(error or "Multi-clip product failed.")

    def click_generate_for_clip(self, frame: Frame, clip_index: int) -> None:
        if clip_index > 1:
            self.advance_to_next_clip_if_needed(frame, clip_index)

        selectors = [
            '[data-flow-action="generate-video"]',
            '[data-flow-field="generate-video"]',
        ]
        btn = self.find_button_in_all_scopes(
            frame,
            selectors=selectors,
            patterns=[r"generate video", r"tao video", r"sản xuất video", r"san xuat video", r"\bgenerate\b"],
        )
        if btn is None:
            self.capture_debug(f"generate-clip-{clip_index:02d}-not-found")
            raise RuntimeError(f"Generate button not found for clip {clip_index}.")
        btn.click()
        self.emit_log(f"Generating clip {clip_index}...", "INFO")

    def advance_to_next_clip_if_needed(self, frame: Frame, clip_index: int) -> None:
        current = self.parse_scene_int(self.read_flow_output_text("current-clip-index"), 1)
        if current >= clip_index and self.find_generate_button(frame) is not None:
            return

        btn = self.find_button_in_all_scopes(
            frame,
            selectors=[
                '[data-flow-action="next-clip"]',
                '[data-flow-field="next-clip"]',
                '[data-flow-action="generate-next-clip"]',
                '[data-flow-field="generate-next-clip"]',
                '[data-flow-action="generate-next-scene-clip"]',
            ],
            patterns=[r"generate next", r"next clip", r"tiếp sang", r"tiep sang", r"cảnh"],
        )
        if btn is None:
            btn = self.find_next_clip_button_fallback(frame, clip_index)
        if btn is None:
            self.capture_debug(f"next-clip-{clip_index:02d}-not-found")
            raise RuntimeError(f"Next clip button not found before clip {clip_index}.")

        btn.click()
        self.emit_log(f"Advanced tool to clip {clip_index}.", "INFO")
        deadline = time.time() + 45
        while time.time() < deadline:
            self.ensure_browser_alive()
            current = self.parse_scene_int(self.read_flow_output_text("current-clip-index"), current)
            ready = self.read_flow_output_text("generate-video-ready").strip().lower()
            if current >= clip_index and (ready in {"true", "1", "yes", "ready"} or self.find_generate_button(frame) is not None):
                return
            self.sleep_ms(500)
        self.capture_debug(f"next-clip-{clip_index:02d}-not-ready")
        raise TimeoutError(f"Clip {clip_index} did not become ready after clicking next clip.")

    def find_next_clip_button_fallback(self, frame: Frame, clip_index: int) -> Optional[Locator]:
        selectors = [
            '[data-flow-action="next-clip"]',
            '[data-flow-field="next-clip"]',
            '[data-flow-action="generate-next-clip"]',
            '[data-flow-field="generate-next-clip"]',
            '[data-flow-action="next-day"]',
            '[data-flow-field="next-day"]',
            'button[data-flow-action*="next"]',
            'button[data-flow-field*="next"]',
        ]
        patterns = [
            r"ti.p\s+sang",
            r"tiep\s+sang",
            r"c.nh\s*" + str(clip_index),
            r"canh\s*" + str(clip_index),
            r"arrow_forward",
        ]
        for scope in self.iter_page_and_frame_scopes():
            for selector in selectors:
                with suppress(Exception):
                    locator = scope.locator(selector).first
                    if locator.count() and locator.is_visible() and not locator.is_disabled():
                        return locator
            button = self.find_button(scope, patterns)
            if button is not None:
                return button
        button = self.find_button(frame, patterns)
        if button is not None:
            return button
        return None

    def find_button_in_all_scopes(
        self,
        frame: Frame,
        selectors: list[str],
        patterns: list[str],
    ) -> Optional[Locator]:
        button = self.find_button_by_selectors_or_text(frame, selectors=selectors, patterns=patterns)
        if button is not None:
            return button
        for scope in self.iter_page_and_frame_scopes():
            if scope == frame:
                continue
            button = self.find_button_by_selectors_or_text(scope, selectors=selectors, patterns=patterns)
            if button is not None:
                return button
        return None

    def read_clip_plan(self, frame: Frame) -> list[dict]:
        raw = self.read_flow_output_text_from_scope(frame, "clip-plan-json") or self.read_flow_output_text("clip-plan-json")
        if not raw:
            return []
        candidates = [raw]
        match = re.search(r"(\{.*\}|\[.*\])", raw, flags=re.DOTALL)
        if match:
            candidates.append(match.group(1))
        for candidate in candidates:
            with suppress(Exception):
                parsed = json.loads(candidate)
                clips = parsed.get("clips") if isinstance(parsed, dict) else parsed
                if not isinstance(clips, list):
                    continue
                normalized = []
                for item in clips:
                    if not isinstance(item, dict):
                        continue
                    role = str(item.get("clip_role") or item.get("role") or item.get("name") or "").strip()
                    if not role:
                        role = f"clip_{len(normalized) + 1}"
                    duration = item.get("duration") or item.get("duration_seconds") or item.get("seconds") or ""
                    normalized.append({"clip_role": role, "duration": duration, **item})
                if normalized:
                    return normalized
        return []

    def build_fallback_clip_plan(self, product: ProductRow, selected_model: str, target_final_duration: int) -> list[dict]:
        count = 3 if self.config.multi_clip_mode == "3" else 2
        if self.config.multi_clip_mode == "auto":
            count = 3 if int(target_final_duration or 20) >= 24 else 2
        roles = ["hook", "product_proof", "offer_cta"] if count == 3 else ["hook_problem", "solution_cta"]
        duration = max(1, int(target_final_duration or 20) // count)
        return [
            {
                "clip_role": role,
                "duration": duration,
                "continuity_prompt": f"{product.product_name} {role} using {selected_model}",
            }
            for role in roles
        ]

    def normalize_clip_plan_for_mode(self, plan: list[dict], product: ProductRow) -> list[dict]:
        if self.config.multi_clip_mode in {"2", "3"}:
            target = int(self.config.multi_clip_mode)
            plan = plan[:target]
            if len(plan) < target:
                plan = self.build_fallback_clip_plan(product, self.config.video_model, self.config.target_final_duration)
        if len(plan) < 2 or len(plan) > 3:
            plan = plan[:3] if len(plan) > 3 else self.build_fallback_clip_plan(product, self.config.video_model, self.config.target_final_duration)
        return plan

    def upload_start_frame(self, frame: Frame, frame_path: Path) -> bool:
        if not frame_path.exists():
            return False
        selectors = [
            'input[data-flow-field="start-frame-upload-input"]',
            '[data-flow-field="start-frame-upload-input"] input[type="file"]',
        ]
        for selector in selectors:
            locator = self.find_in_all_frames(selector, require_visible=False)
            if locator is None:
                continue
            with suppress(Exception):
                locator.set_input_files(frame_path.as_posix())
                self.sleep_ms(800)
                action = self.find_button_by_selectors_or_text(
                    frame,
                    selectors=['[data-flow-action="use-last-frame-as-start-frame"]'],
                    patterns=[r"use last frame", r"start frame", r"reference"],
                )
                if action is not None:
                    action.click()
                    self.sleep_ms(800)
                return True
        return False

    def has_start_frame_upload_input(self) -> bool:
        selectors = [
            'input[data-flow-field="start-frame-upload-input"]',
            '[data-flow-field="start-frame-upload-input"] input[type="file"]',
        ]
        return any(self.find_in_all_frames(selector, require_visible=False) is not None for selector in selectors)

    def capture_last_frame_from_flow(self, frame: Frame, clip_index: int, output_path: Path) -> bool:
        if self.write_data_url_to_file(self.read_flow_output_text("last-frame-image-data"), output_path):
            return True
        button = self.find_button_by_selectors_or_text(
            frame,
            selectors=['[data-flow-action="save-last-frame"]'],
            patterns=[r"save last frame", r"last frame"],
        )
        if button is None:
            return False
        try:
            assert self.page is not None
            with self.page.expect_download(timeout=5_000) as download_info:
                button.click()
            download = download_info.value
            download.save_as(output_path.as_posix())
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception:
            with suppress(Exception):
                button.click()
            deadline = time.time() + 8
            while time.time() < deadline:
                if self.write_data_url_to_file(self.read_flow_output_text("last-frame-image-data"), output_path):
                    return True
                self.sleep_ms(500)
        return False

    def write_data_url_to_file(self, value: str, output_path: Path) -> bool:
        value = str(value or "").strip()
        if not value.startswith("data:"):
            return False
        with suppress(Exception):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(self.decode_data_url(value))
            return output_path.exists() and output_path.stat().st_size > 0
        return False

    def extract_last_frame_ffmpeg(self, clip_path: Path, output_path: Path) -> bool:
        ffmpeg_path = find_ffmpeg_path()
        if not ffmpeg_path or not clip_path.exists():
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg_path,
            "-y",
            "-sseof",
            "-0.1",
            "-i",
            str(clip_path),
            "-frames:v",
            "1",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0

    def merge_clips_ffmpeg(self, clip_paths: list[Path], output_path: Path) -> bool:
        ffmpeg_path = find_ffmpeg_path()
        if not ffmpeg_path or not clip_paths:
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        list_path = output_path.with_name("clips.txt")
        list_path.write_text(
            "\n".join(f"file '{path.resolve().as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for path in clip_paths),
            encoding="utf-8",
        )
        copy_command = [ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output_path)]
        result = subprocess.run(copy_command, capture_output=True, text=True)
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return True
        with suppress(Exception):
            output_path.unlink()
        encode_command = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]
        result = subprocess.run(encode_command, capture_output=True, text=True)
        return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0

    def try_download_native_scene(self, frame: Frame, output_path: Path) -> bool:
        button = self.find_button_by_selectors_or_text(
            frame,
            selectors=['[data-flow-action="download-scene"]', '[data-flow-field="download-scene"]'],
            patterns=[r"download scene", r"download final", r"tai"],
        )
        if button is None:
            for scope in self.iter_page_and_frame_scopes():
                button = self.find_button_by_selectors_or_text(
                    scope,
                    selectors=['[data-flow-action="download-scene"]', '[data-flow-field="download-scene"]'],
                    patterns=[r"download scene", r"download final", r"tai"],
                )
                if button is not None:
                    break
        if button is None:
            return False
        try:
            assert self.page is not None
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.page.expect_download(timeout=60_000) as download_info:
                button.click()
            download_info.value.save_as(output_path.as_posix())
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            self.emit_log(f"Native scene download failed: {exc}", "WARNING")
            return False

    def wait_for_scene_finished(self, timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            scene_ready = self.read_flow_output_text("scene-ready").strip().lower()
            multi_clip_status = self.read_flow_output_text("multi-clip-status").strip().lower()
            if scene_ready in {"true", "1", "yes", "ready"}:
                return True
            if multi_clip_status in {"completed", "done", "success"}:
                return True
            if multi_clip_status in {"failed", "error"}:
                self.emit_log("Native scene builder reported failure.", "WARNING")
                return False
            self.sleep_ms(1_000)
        self.emit_log("Scene-ready output did not complete before timeout; trying fallback download/merge.", "WARNING")
        return False

    def try_download_video_button(self, frame: Frame, output_path: Path) -> bool:
        button = self.find_button_by_selectors_or_text(
            frame,
            selectors=['[data-flow-action="download-video"]', '[data-flow-field="download-video"]'],
            patterns=[r"download video", r"download", r"tai video", r"tai"],
        )
        if button is None:
            for scope in self.iter_page_and_frame_scopes():
                button = self.find_button_by_selectors_or_text(
                    scope,
                    selectors=['[data-flow-action="download-video"]', '[data-flow-field="download-video"]'],
                    patterns=[r"download video", r"download", r"tai video", r"tai"],
                )
                if button is not None:
                    break
        if button is None:
            return False
        try:
            assert self.page is not None
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.page.expect_download(timeout=60_000) as download_info:
                button.click()
            download_info.value.save_as(output_path.as_posix())
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            self.emit_log(f"Video download button fallback failed: {exc}", "WARNING")
            return False

    def process_clip_external_tts(
        self,
        frame: Frame,
        result: dict,
        clip_index: int,
        clip_path: Path,
        voiced_path: Path,
        voice_path: Path,
        voice_json_path: Path,
        subtitle_path: Path,
        batch_dir: Path,
    ) -> dict:
        audio_result = {
            "audio_pipeline": "external-tts" if self.config.enable_external_tts else "disabled",
            "tts_provider": self.config.tts_provider,
            "tts_enabled": bool(self.config.enable_external_tts),
            "tts_status": "disabled" if not self.config.enable_external_tts else "pending",
            "tts_error": "",
            "tts_audio_file": "",
            "voiced_clip_file": "",
            "voiced_video_file": "",
            "voiceover_text": str(result.get("voiceover_text") or result.get("voiceover") or "").strip(),
            "voiceover": str(result.get("voiceover_text") or result.get("voiceover") or "").strip(),
            "voiceover_json": [],
            "voiceover_json_file": "",
            "voiceover_language": self.read_flow_output_text("voiceover-language"),
            "voiceover_mode": self.read_flow_output_text("voiceover-mode"),
            "voiceover_status": self.read_flow_output_text("voiceover-status"),
            "tts_required": self.read_flow_output_text("tts-required"),
            "subtitle_file": "",
        }

        self.emit_log(f"Reading voiceover for clip {clip_index}...", "INFO")
        segments, source = self.wait_for_voiceover_segments_for_clip(clip_index, clip_path, result)
        if not segments:
            self.emit_log(f"No voiceover found for clip {clip_index}.", "WARNING")
            audio_result["tts_status"] = "missing" if self.config.enable_external_tts else "disabled"
            audio_result["tts_error"] = "voiceover output missing after polling and fallback"
            return audio_result

        self.emit_log(f"Voiceover source: {source}", "INFO")
        voiceover_text = " ".join(
            str(item.get("text") or "").strip() for item in segments if str(item.get("text") or "").strip()
        ).strip()
        audio_result["voiceover_text"] = voiceover_text
        audio_result["voiceover"] = voiceover_text
        audio_result["voiceover_json"] = segments

        voice_json_path.parent.mkdir(parents=True, exist_ok=True)
        voice_json_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        audio_result["voiceover_json_file"] = voice_json_path.relative_to(batch_dir).as_posix()

        if self.write_segments_as_srt(segments, subtitle_path):
            audio_result["subtitle_file"] = subtitle_path.relative_to(batch_dir).as_posix()

        if not self.config.enable_external_tts or self.config.tts_provider == "none":
            audio_result["tts_status"] = "disabled"
            return audio_result

        if not voiceover_text:
            audio_result["tts_status"] = "missing"
            return audio_result

        try:
            self.emit_log("Generating Vietnamese TTS...", "INFO")
            if not self.run_generate_tts_audio(voiceover_text, voice_path):
                self.emit_log("TTS failed; using raw clip.", "WARNING")
                audio_result["tts_status"] = "failed"
                audio_result["tts_error"] = f"TTS audio was not created: {voice_path}"
                return audio_result

            audio_result["tts_audio_file"] = voice_path.relative_to(batch_dir).as_posix()

            video_duration = self.safe_media_duration_seconds(clip_path)
            audio_duration = self.safe_media_duration_seconds(voice_path)
            mix_voice_path = voice_path
            if video_duration and audio_duration and audio_duration > max(0.2, video_duration - 0.2):
                trimmed = voice_path.with_name(f"{voice_path.stem}_trimmed{voice_path.suffix}")
                if self.trim_audio_to_duration(voice_path, trimmed, max(0.2, video_duration - 0.2)):
                    mix_voice_path = trimmed
                    self.emit_log("Voiceover longer than clip duration; trimmed.", "WARNING")

            self.emit_log("Mixing voiceover into clip...", "INFO")
            if self.mix_voiceover_with_video(
                clip_path,
                mix_voice_path,
                voiced_path,
                background_volume=self.config.background_audio_volume,
                voice_volume=self.config.voice_audio_volume * self.config.tts_volume,
            ):
                if not self.validate_audio_stream_ffprobe(voiced_path):
                    audio_result["tts_status"] = "failed"
                    audio_result["tts_error"] = f"Voiced clip has no audio stream: {voiced_path}"
                    self.emit_log(audio_result["tts_error"], "WARNING")
                    return audio_result
                audio_result["tts_status"] = "success"
                audio_result["voiced_clip_file"] = voiced_path.relative_to(batch_dir).as_posix()
                audio_result["voiced_video_file"] = audio_result["voiced_clip_file"]
                audio_result["clip_video_file"] = audio_result["voiced_clip_file"]
                audio_result["video_file"] = audio_result["voiced_clip_file"]
                self.emit_log(f"Voiced clip saved: {voiced_path}", "SUCCESS")
                return audio_result

            self.emit_log("Voiceover mix failed; using raw clip.", "WARNING")
            audio_result["tts_status"] = "failed"
            audio_result["tts_error"] = f"FFmpeg voiceover mix failed: {voiced_path}"
        except Exception as exc:
            audio_result["tts_status"] = "failed"
            audio_result["tts_error"] = str(exc)
            self.emit_log(f"TTS pipeline failed; using raw clip: {exc}", "WARNING")
        return audio_result

    def wait_for_voiceover_segments_for_clip(
        self,
        clip_index: int,
        clip_path: Path,
        result: dict,
        timeout_ms: int = 20_000,
        interval_ms: int = 500,
    ) -> tuple[list[dict], str]:
        deadline = time.time() + timeout_ms / 1000
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            segments, source = self.read_voiceover_segments_for_clip(clip_index, clip_path, log_lengths=True)
            if segments:
                return segments, source
            self.sleep_ms(interval_ms)

        segments, source = self.read_voiceover_segments_for_clip(clip_index, clip_path, log_lengths=True)
        if segments:
            return segments, source

        fallback_text = str(result.get("voiceover_text") or result.get("voiceover") or "").strip()
        if fallback_text:
            clip_duration = self.safe_media_duration_seconds(clip_path)
            end = max(0.5, (clip_duration or 3.0) - 0.3)
            self.emit_log(f"Using captured result voiceover fallback for clip {clip_index}.", "WARNING")
            return [{"start": 0.0, "end": end, "text": fallback_text}], "result.voiceover_text"

        return [], ""

    def read_voiceover_segments_for_clip(
        self,
        clip_index: int,
        clip_path: Path,
        log_lengths: bool = False,
    ) -> tuple[list[dict], str]:
        duration = self.safe_media_duration_seconds(clip_path)
        selectors = self.voiceover_output_selectors()
        for output_name, expects_json in selectors:
            raw = self.read_voiceover_output_text(output_name).strip()
            if log_lengths:
                self.emit_log(f"voiceover selector {output_name} length={len(raw)}", "INFO")
            if not raw:
                continue
            selector_clip = self.voiceover_selector_clip_index(output_name)
            if selector_clip and selector_clip != clip_index:
                continue
            segments = self.parse_voiceover_segments(
                raw,
                duration,
                expects_json=expects_json,
                clip_index=clip_index,
                source_name=output_name,
            )
            if segments:
                return segments, output_name
        return [], ""

    def voiceover_selector_clip_index(self, output_name: str) -> int:
        match = re.match(r"clip-(\d+)-voiceover", str(output_name or ""))
        if not match:
            return 0
        with suppress(ValueError):
            return int(match.group(1))
        return 0

    def voiceover_output_selectors(self) -> list[tuple[str, bool]]:
        return [
            ("clip-1-voiceover-json", True),
            ("clip-2-voiceover-json", True),
            ("clip-3-voiceover-json", True),
            ("current-clip-voiceover-json", True),
            ("voiceover-json", True),
            ("clip-1-voiceover", False),
            ("clip-2-voiceover", False),
            ("clip-3-voiceover", False),
            ("current-clip-voiceover", False),
            ("voiceover-script", False),
            ("voiceover", False),
        ]

    def read_voiceover_output_text(self, output_name: str) -> str:
        values = self.read_flow_output_values(output_name)
        for value in values:
            if value.strip():
                return value.strip()
        return ""

    def read_flow_output_values(self, output_name: str) -> list[str]:
        selectors = [
            f'[data-flow-output="{output_name}"]',
            f'[data-flow-field="{output_name}"]',
            f'input[data-flow-output="{output_name}"]',
            f'textarea[data-flow-output="{output_name}"]',
            f'input[data-flow-field="{output_name}"]',
            f'textarea[data-flow-field="{output_name}"]',
            f'#{output_name}',
        ]
        values: list[str] = []
        seen: set[str] = set()
        for scope in self.iter_page_and_frame_scopes():
            for selector in selectors:
                with suppress(Exception):
                    locator_group = scope.locator(selector)
                    count = min(locator_group.count(), 10)
                    for index in range(count):
                        locator = locator_group.nth(index)
                        for reader in (
                            lambda item: item.input_value(),
                            lambda item: item.get_attribute("value") or "",
                            lambda item: item.text_content() or "",
                            lambda item: item.inner_text(),
                        ):
                            with suppress(Exception):
                                value = str(reader(locator) or "").strip()
                                if value and value not in seen:
                                    seen.add(value)
                                    values.append(value)
        return values

    def parse_voiceover_segments(
        self,
        raw: str,
        clip_duration: float,
        expects_json: bool = False,
        clip_index: int = 1,
        source_name: str = "",
    ) -> list[dict]:
        candidates = [raw]
        match = re.search(r"(\{.*\}|\[.*\])", raw, flags=re.DOTALL)
        if match:
            candidates.insert(0, match.group(1))
        if expects_json or match:
            for candidate in candidates:
                with suppress(Exception):
                    parsed = json.loads(candidate)
                    items = self.voiceover_items_from_parsed(parsed, clip_index, source_name)
                    if isinstance(items, dict):
                        items = [items]
                    if not isinstance(items, list):
                        continue
                    segments = self.normalize_voiceover_segments(items, clip_duration)
                    if segments:
                        return segments
        text = re.sub(r"\s+", " ", raw).strip()
        if not text or text.startswith("[") or text.startswith("{"):
            return []
        end = max(0.5, (clip_duration or 3.0) - 0.3)
        return [{"start": 0.0, "end": end, "text": text}]

    def voiceover_items_from_parsed(self, parsed: object, clip_index: int, source_name: str = "") -> object:
        if isinstance(parsed, dict):
            if any(key in parsed for key in ("start", "end", "text", "voiceover", "caption")):
                return [parsed]
            for collection_key in ("clips", "items", "scenes"):
                collection = parsed.get(collection_key)
                selected = self.voiceover_items_for_clip_from_collection(collection, clip_index)
                if selected:
                    return selected
            for direct_key in (
                f"clip-{clip_index}",
                f"clip_{clip_index}",
                f"clip{clip_index}",
                str(clip_index),
            ):
                selected = self.voiceover_items_from_parsed(parsed.get(direct_key), clip_index, source_name)
                if selected:
                    return selected
            for direct_collection_key in ("segments", "voiceover", "subtitles"):
                direct_collection = parsed.get(direct_collection_key)
                selected = self.voiceover_items_for_clip_from_collection(direct_collection, clip_index)
                if selected:
                    return selected
            return parsed.get("segments") or parsed.get("voiceover") or parsed.get("subtitles")
        if isinstance(parsed, list):
            if source_name == "voiceover-json":
                selected = self.voiceover_items_for_clip_from_collection(parsed, clip_index)
                if selected:
                    return selected
            return parsed
        return parsed

    def voiceover_items_for_clip_from_collection(self, collection: object, clip_index: int) -> object:
        if not isinstance(collection, list):
            return []
        matches: list[object] = []
        for item in collection:
            if not isinstance(item, dict):
                continue
            item_clip_index = self.parse_scene_int(
                item.get("clip_index")
                or item.get("clipIndex")
                or item.get("scene_number")
                or item.get("sceneNumber")
                or item.get("index"),
                0,
            )
            if item_clip_index != clip_index:
                continue
            value = (
                item.get("segments")
                or item.get("voiceover")
                or item.get("voiceover_json")
                or item.get("subtitles")
                or item.get("text")
            )
            if isinstance(value, list):
                matches.extend(value)
            elif value:
                matches.append(value)
        return matches

    def normalize_voiceover_segments(self, items: list, clip_duration: float) -> list[dict]:
        segments: list[dict] = []
        fallback_end = max(0.5, (clip_duration or 3.0) - 0.3)
        for item in items:
            if isinstance(item, str):
                text = re.sub(r"\s+", " ", item).strip()
                if text:
                    segments.append({"start": 0.0, "end": fallback_end, "text": text})
                continue
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("voiceover") or item.get("caption") or "").strip()
            if not text:
                continue
            start = self.parse_float(item.get("start") or item.get("start_seconds"), 0.0)
            end = self.parse_float(item.get("end") or item.get("end_seconds"), 0.0)
            if end <= start:
                end = min(fallback_end, start + 2.5)
            segments.append({"start": start, "end": end, "text": text})
        return segments

    def run_generate_tts_audio(self, text: str, output_audio_path: Path) -> bool:
        self.emit_log(f"Generating TTS: {output_audio_path}", "INFO")

        def coroutine_factory():
            return self.generate_tts_audio(
                text,
                output_audio_path,
                voice=self.config.tts_voice,
                rate=self.config.tts_rate,
                pitch=self.config.tts_pitch,
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                ok = asyncio.run(coroutine_factory())
            except Exception as exc:
                self.emit_log(f"TTS failed: {exc}", "WARNING")
                return False
        else:
            ok, error = self.run_coroutine_factory_in_thread(coroutine_factory, "TTS")
            if error is not None:
                self.emit_log(f"TTS failed: {error}", "WARNING")
                return False

        if not ok:
            self.emit_log("TTS failed: provider returned no audio.", "WARNING")
            return False
        if not output_audio_path.exists() or output_audio_path.stat().st_size <= 0:
            self.emit_log(f"TTS failed: output file is missing or empty: {output_audio_path}", "WARNING")
            return False
        self.emit_log(f"TTS generated: {output_audio_path}", "SUCCESS")
        return True

    def run_coroutine_factory_in_thread(self, coroutine_factory, label: str = "async task") -> tuple[bool, Exception | None]:
        result: dict[str, object] = {"ok": False, "error": None}

        def runner() -> None:
            try:
                result["ok"] = bool(asyncio.run(coroutine_factory()))
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=runner, name=f"flow-bot-{label.lower().replace(' ', '-')}", daemon=True)
        thread.start()
        thread.join()
        return bool(result["ok"]), result["error"] if isinstance(result["error"], Exception) else None

    async def generate_tts_audio(
        self,
        text: str,
        output_audio_path: Path,
        voice: str = "vi-VN-HoaiMyNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bool:
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        provider = str(self.config.tts_provider or "edge_tts").strip().lower()
        if provider in {"none", ""}:
            return False
        if provider == "edge_tts":
            edge_tts = self.ensure_edge_tts_module()

            communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
            await communicate.save(output_audio_path.as_posix())
            if not output_audio_path.exists() or output_audio_path.stat().st_size <= 0:
                raise RuntimeError(f"edge-tts output is missing or empty: {output_audio_path}")
            return True
        if provider == "gtts":
            from gtts import gTTS

            await asyncio.to_thread(gTTS(text=text, lang="vi").save, output_audio_path.as_posix())
            if not output_audio_path.exists() or output_audio_path.stat().st_size <= 0:
                raise RuntimeError(f"gTTS output is missing or empty: {output_audio_path}")
            return True
        raise RuntimeError(f"TTS provider '{provider}' is not available/configured.")

    def ensure_edge_tts_module(self):
        try:
            return importlib.import_module("edge_tts")
        except ModuleNotFoundError:
            pass

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "edge-tts>=7.0.0",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "pip install edge-tts failed").strip()
            raise RuntimeError(error[-1200:])
        importlib.invalidate_caches()
        return importlib.import_module("edge_tts")

    def mix_voiceover_with_video(
        self,
        input_video: Path,
        voice_audio: Path,
        output_video: Path,
        background_volume: float = 0.35,
        voice_volume: float = 1.0,
    ) -> bool:
        ffmpeg_path = find_ffmpeg_path()
        if not ffmpeg_path:
            self.emit_log("FFmpeg is not available; skipping audio mix.", "WARNING")
            return False
        if not input_video.exists() or not voice_audio.exists():
            return False
        output_video.parent.mkdir(parents=True, exist_ok=True)
        if self.video_has_audio(input_video):
            command = [
                ffmpeg_path,
                "-y",
                "-i",
                str(input_video),
                "-i",
                str(voice_audio),
                "-filter_complex",
                f"[0:a]volume={float(background_volume):.3f}[a0];[1:a]volume={float(voice_volume):.3f}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_video),
            ]
        else:
            command = [
                ffmpeg_path,
                "-y",
                "-i",
                str(input_video),
                "-i",
                str(voice_audio),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_video),
            ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0 and output_video.exists() and output_video.stat().st_size > 0:
            return True
        with suppress(Exception):
            output_video.unlink()
        error = (result.stderr or result.stdout or "FFmpeg audio mix failed.").strip()
        self.emit_log(error[-800:], "WARNING")
        return False

    def validate_audio_stream_ffprobe(self, media_path: Path, emit_missing: bool = True) -> bool:
        ffprobe_path = find_ffprobe_path()
        if not media_path.exists():
            if emit_missing:
                self.emit_log(f"Media missing for audio validation: {media_path}", "WARNING")
            return False
        if not ffprobe_path:
            if emit_missing:
                self.emit_log("ffprobe is unavailable; validating audio stream with FFmpeg fallback.", "WARNING")
            return self.validate_audio_stream_ffmpeg(media_path, emit_missing=emit_missing)
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(media_path),
            ],
            capture_output=True,
            text=True,
        )
        has_audio = result.returncode == 0 and "audio" in (result.stdout or "").lower()
        if has_audio:
            self.emit_log(f"ffprobe audio stream OK: {media_path}", "INFO")
            return True
        if emit_missing:
            detail = (result.stderr or result.stdout or "no audio stream").strip()
            self.emit_log(f"ffprobe found no audio stream in {media_path}: {detail}", "WARNING")
        return False

    def validate_audio_stream_ffmpeg(self, media_path: Path, emit_missing: bool = True) -> bool:
        ffmpeg_path = find_ffmpeg_path()
        if not ffmpeg_path or not media_path.exists():
            if emit_missing:
                self.emit_log(f"FFmpeg unavailable or media missing for audio validation: {media_path}", "WARNING")
            return False
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-i", str(media_path)],
            capture_output=True,
            text=True,
        )
        has_audio = bool(re.search(r"Audio:", result.stderr or result.stdout, re.I))
        if has_audio and emit_missing:
            self.emit_log(f"FFmpeg audio stream OK: {media_path}", "INFO")
        elif emit_missing:
            detail = (result.stderr or result.stdout or "no audio stream").strip()
            self.emit_log(f"FFmpeg found no audio stream in {media_path}: {detail[-800:]}", "WARNING")
        return has_audio

    def video_has_audio(self, video_path: Path) -> bool:
        return self.validate_audio_stream_ffprobe(video_path, emit_missing=False)

    def safe_media_duration_seconds(self, media_path: Path) -> float:
        with suppress(Exception):
            return float(get_video_duration_seconds(media_path))
        return 0.0

    def trim_audio_to_duration(self, input_audio: Path, output_audio: Path, duration: float) -> bool:
        ffmpeg_path = find_ffmpeg_path()
        if not ffmpeg_path or duration <= 0:
            return False
        output_audio.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(input_audio),
                "-t",
                f"{duration:.3f}",
                "-c:a",
                "libmp3lame",
                str(output_audio),
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and output_audio.exists() and output_audio.stat().st_size > 0

    def write_segments_as_srt(self, segments: list[dict], output_srt: Path) -> bool:
        if not segments:
            return False
        lines: list[str] = []
        for segment in segments:
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            start = self.parse_float(segment.get("start"), 0.0)
            end = self.parse_float(segment.get("end"), start + 2.0)
            if end <= start:
                end = start + 2.0
            lines.extend(
                [
                    str(len(lines) // 4 + 1),
                    f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}",
                    text,
                    "",
                ]
            )
        if not lines:
            return False
        output_srt.parent.mkdir(parents=True, exist_ok=True)
        output_srt.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return True

    def combine_clip_subtitles(
        self,
        clip_subtitle_segments: list[tuple[int, float, list[dict]]],
        output_srt: Path,
    ) -> bool:
        lines: list[str] = []
        offset = 0.0
        for _clip_index, clip_duration, segments in sorted(clip_subtitle_segments, key=lambda item: item[0]):
            for segment in segments:
                text = str(segment.get("text") or "").strip()
                if not text:
                    continue
                start = offset + self.parse_float(segment.get("start"), 0.0)
                end = offset + self.parse_float(segment.get("end"), start - offset + 2.0)
                if end <= start:
                    end = start + 2.0
                lines.extend(
                    [
                        str(len(lines) // 4 + 1),
                        f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}",
                        text,
                        "",
                    ]
                )
            offset += max(0.0, float(clip_duration or 0.0))
        if not lines:
            return False
        output_srt.parent.mkdir(parents=True, exist_ok=True)
        output_srt.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return True

    def has_native_scene_builder_controls(self) -> bool:
        selectors = [
            '[data-flow-action="add-clip-to-scene"]',
            '[data-flow-action="download-scene"]',
            '[data-flow-field="download-scene"]',
            '[data-flow-output="scene-id"]',
            '[data-flow-output="scene-clip-list"]',
        ]
        return any(
            self.find_in_all_frames(selector, require_visible=False) is not None
            for selector in selectors
        )

    def add_clip_to_native_scene(self, frame: Frame) -> bool:
        button = self.find_button_by_selectors_or_text(
            frame,
            selectors=['[data-flow-action="add-clip-to-scene"]'],
            patterns=[r"add clip", r"add to scene", r"scene"],
        )
        if button is None:
            return False
        with suppress(Exception):
            button.click()
            self.sleep_ms(800)
            return True
        return False

    def multi_clip_scene_group_id(self, product: ProductRow, index: int) -> str:
        product_slug = self.slugify(product.product_name) or "product"
        return f"{product_slug}-{index + 1:04d}"

    def multi_clip_base_row(
        self,
        product: ProductRow,
        index: int,
        scene_group_id: str,
        clip_results: list[dict],
        raw_final_path: Path,
        final_path: Path,
        native_scene_file: str,
        scene_id: str,
        merge_method: str,
    ) -> dict:
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        voiceover = " ".join(str(item.get("voiceover_text") or "").strip() for item in clip_results).strip()
        caption = " ".join(str(item.get("caption_text") or "").strip() for item in clip_results).strip()
        final_prompt = "\n\n".join(str(item.get("final_prompt_text") or "").strip() for item in clip_results if item.get("final_prompt_text"))
        return {
            "run_id": self.config.run_id,
            "batch_id": self.batch_id(),
            "index": index + 1,
            "product_name": product.product_name,
            "product_short_description": product.short_description,
            "scene_group_id": scene_group_id,
            "scene_number": 1,
            "scene_total": len(clip_results),
            "scene_role": "multi_clip_final",
            "scene_title": product.product_name,
            "multi_clip": True,
            "scene_builder_mode": self.config.scene_builder_mode,
            "scene_id": scene_id,
            "native_scene_file": native_scene_file,
            "merge_method": merge_method,
            "raw_video_file": raw_final_path.relative_to(raw_final_path.parent.parent).as_posix(),
            "final_video_file": final_path.relative_to(final_path.parent.parent).as_posix(),
            "voiceover_text": voiceover,
            "caption_text": caption,
            "final_prompt_text": final_prompt,
            "status": "completed",
            "created_at": created_at,
            "error": "",
        }

    def persist_multi_clip_product_manifest(
        self,
        batch_dir: Path,
        product: ProductRow,
        index: int,
        scene_group_id: str,
        clip_results: list[dict],
        scene_id: str,
        scene_clip_list: str,
        native_scene_file: str,
        final_video_file: str,
        merge_method: str,
        status: str,
        error: str,
        postprocess_result: dict,
    ) -> None:
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        clips = []
        for result in clip_results:
            clips.append(
                {
                    "clip_index": self.parse_scene_int(result.get("clip_index"), len(clips) + 1),
                    "clip_role": result.get("clip_role", ""),
                    "duration": result.get("clip_duration", ""),
                    "video_file": result.get("clip_video_file", ""),
                    "raw_video_file": result.get("raw_video_file", ""),
                    "voiced_video_file": result.get("voiced_video_file") or result.get("voiced_clip_file", ""),
                    "last_frame": result.get("last_frame_file", ""),
                    "voiceover_text": result.get("voiceover_text", ""),
                    "voiceover_json": result.get("voiceover_json", []),
                    "voiceover_json_file": result.get("voiceover_json_file", ""),
                    "voiceover_language": result.get("voiceover_language", ""),
                    "voiceover_mode": result.get("voiceover_mode", ""),
                    "voiceover_status": result.get("voiceover_status", ""),
                    "tts_required": result.get("tts_required", ""),
                    "tts_enabled": result.get("tts_enabled", ""),
                    "tts_provider": result.get("tts_provider", ""),
                    "tts_status": result.get("tts_status", ""),
                    "tts_error": result.get("tts_error", ""),
                    "tts_audio_file": result.get("tts_audio_file", ""),
                    "subtitle_file": result.get("subtitle_file", ""),
                    "audio_pipeline": result.get("audio_pipeline", ""),
                    "status": result.get("status", ""),
                }
            )
        entry = {
            "run_id": self.config.run_id,
            "batch_id": self.batch_id(),
            "index": index + 1,
            "scene_group_id": scene_group_id,
            "product_name": product.product_name,
            "multi_clip": True,
            "scene_builder_mode": self.config.scene_builder_mode,
            "scene_id": scene_id,
            "scene_clip_list": scene_clip_list,
            "clip_total": len(clip_results),
            "clips": clips,
            "native_scene_file": native_scene_file,
            "final_video_file": final_video_file,
            "video_file": final_video_file,
            "storage_path": f"storage/{self.batch_id()}/{final_video_file}" if final_video_file else "",
            "merge_method": merge_method,
            "audio_pipeline": postprocess_result.get("audio_pipeline") or ("external-tts" if self.config.enable_external_tts else "raw"),
            "tts_provider": postprocess_result.get("tts_provider") or self.config.tts_provider,
            "final_subtitle_file": postprocess_result.get("final_subtitle_file", ""),
            "status": status,
            "created_at": created_at,
            "updated_at": created_at,
            "error": error,
            **postprocess_result,
        }
        if final_video_file:
            final_path = batch_dir / final_video_file
            if final_path.exists():
                entry["file_size"] = final_path.stat().st_size

        manifest_path = batch_dir / "manifest.json"
        with suppress(Exception):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        if "manifest" not in locals():
            manifest = {}
        manifest.setdefault("batch_id", self.batch_id())
        manifest.setdefault("run_id", self.config.run_id or self.batch_id())
        manifest.setdefault("created_at", created_at)
        manifest["updated_at"] = created_at
        items = manifest.setdefault("items", [])
        identity = (index + 1, scene_group_id, "multi_clip")
        for item_index, existing in enumerate(items):
            existing_identity = (
                self.parse_row_index(existing.get("index")),
                str(existing.get("scene_group_id") or ""),
                "multi_clip" if existing.get("multi_clip") else existing.get("scene_number"),
            )
            if existing_identity == identity:
                items[item_index] = entry
                break
        else:
            items.append(entry)
        manifest["item_count"] = len(items)
        manifest["completed_count"] = sum(1 for item in items if str(item.get("status") or "").lower() == "completed")
        manifest["failed_count"] = sum(1 for item in items if str(item.get("status") or "").lower() == "failed")
        manifest["status"] = "failed" if manifest["failed_count"] else "completed"
        manifest["products"] = [
            {
                "scene_group_id": item.get("scene_group_id", ""),
                "product_name": item.get("product_name", ""),
                "multi_clip": bool(item.get("multi_clip")),
                "scene_builder_mode": item.get("scene_builder_mode", ""),
                "clip_total": item.get("clip_total", 0),
                "clips": item.get("clips", []),
                "final_video_file": item.get("final_video_file", ""),
                "merge_method": item.get("merge_method", ""),
                "status": item.get("status", ""),
            }
            for item in items
            if item.get("multi_clip")
        ]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        group_manifest_path = batch_dir / "clips" / scene_group_id / "manifest.json"
        group_manifest_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    def fill_scene_metadata_if_available(self, frame: Frame, product: ProductRow) -> None:
        scene = self.scene_metadata_for_product(product)
        field_map = {
            "scene_group_id": '[data-flow-field="scene-group-id"]',
            "scene_number": '[data-flow-field="scene-number"]',
            "scene_total": '[data-flow-field="scene-total"]',
            "scene_role": '[data-flow-field="scene-role"]',
            "scene_continuity_notes": '[data-flow-field="scene-continuity-notes"]',
        }
        for key, selector in field_map.items():
            if key not in self.config.scene_field_keys:
                continue
            locator = self.find_scene_field(frame, selector)
            if locator is None:
                self.emit_log(f"Scene field not found in Flow: {key}. Skipping.", "WARNING")
                continue
            self.emit_log(f"Filling {key}...")
            try:
                self.enter_field_value(locator, str(scene[key]), key)
                self.emit_log(f"Filled {key}")
            except Exception as exc:
                self.emit_log(
                    f"Scene field '{key}' could not be filled ({exc}). Skipping.",
                    "WARNING",
                )

    def scene_metadata_for_product(self, product: ProductRow) -> dict[str, str | int]:
        scene_group_id = (product.scene_group_id or "").strip() or self.slugify(product.product_name)
        scene_title = (product.scene_title or "").strip() or product.product_name
        scene_role = (product.scene_role or "").strip() or "single"
        scene_number = max(1, int(product.scene_number or 1))
        scene_total = max(1, int(product.scene_total or 1))
        return {
            "scene_group_id": scene_group_id,
            "scene_number": scene_number,
            "scene_total": scene_total,
            "scene_role": scene_role,
            "scene_title": scene_title,
            "scene_continuity_notes": (product.scene_continuity_notes or "").strip(),
        }

    def find_scene_field(self, frame: Frame, selector: str) -> Optional[Locator]:
        selectors = [
            f"{selector} input",
            f"{selector} textarea",
            f"{selector} [contenteditable='true']",
            f"{selector} [role='textbox']",
            selector,
        ]
        return self.find_visible_by_selector(frame, selectors)

    def wait_for_video_completed_and_capture(
        self,
        product: ProductRow,
        index: int,
        clip_metadata: dict | None = None,
        previous_video_url: str = "",
        previous_video_download_data: str = "",
    ) -> dict:
        assert self.page is not None
        deadline = time.time() + self.config.wait_timeout_ms / 1000
        scene = self.scene_metadata_for_product(product)
        result = {
            "run_id": self.config.run_id,
            "index": index + 1,
            "product_name": product.product_name,
            "product_short_description": product.short_description,
            "scene_group_id": scene["scene_group_id"],
            "scene_number": scene["scene_number"],
            "scene_total": scene["scene_total"],
            "scene_role": scene["scene_role"],
            "scene_title": scene["scene_title"],
            "video_file": "",
            "video_url": "",
            "video_filename": "",
            "video_download_data": "",
            "original_image_file": "",
            "clean_image_file": "",
            "image_cleanup_status": "",
            "status": "pending",
            "created_at": "",
            "error": "",
        }

        self.emit_log("Polling video result status...")
        while time.time() < deadline:
            self.ensure_browser_alive()
            status_text = self.read_flow_output_text("video-status")
            normalized_status = status_text.strip().lower()
            if normalized_status:
                self.emit_log(f"Video status: {status_text}")

            video_url_from_data = self.read_flow_output_text("video-url")
            video_url_fallback = ""
            if not video_url_from_data:
                video_url_fallback = self.find_video_url_fallback()

            is_completed = (
                "completed" in normalized_status
                or "thành công" in normalized_status
                or "hoàn thành" in normalized_status
                or "success" in normalized_status
                or "done" in normalized_status
                or bool(video_url_from_data)
                or bool(video_url_fallback)
            )

            if is_completed:
                scene_group_id = self.read_flow_output_text("scene-group-id") or str(scene["scene_group_id"])
                scene_number_raw = self.read_flow_output_text("scene-number")
                scene_total_raw = self.read_flow_output_text("scene-total")
                scene_role = self.read_flow_output_text("scene-role") or str(scene["scene_role"])
                scene_title = self.read_flow_output_text("scene-title") or str(scene["scene_title"])
                current_clip_raw = self.read_flow_output_text("current-clip-index")
                expected_clip_index = self.parse_scene_int(
                    clip_metadata.get("clip_index") if clip_metadata else None,
                    0,
                )
                if expected_clip_index:
                    current_clip_index = self.parse_scene_int(current_clip_raw, 0)
                    if current_clip_index and current_clip_index != expected_clip_index:
                        self.emit_log(
                            f"Video output is for clip {current_clip_index}; waiting for clip {expected_clip_index}...",
                            "INFO",
                        )
                        self.sleep_ms(1_000)
                        continue
                video_url = video_url_from_data or video_url_fallback
                video_filename = self.read_flow_output_text("video-filename")
                video_download_data = self.read_flow_output_text("video-download-data")
                if (
                    previous_video_url
                    and video_url
                    and video_url == previous_video_url
                    and (not video_download_data or video_download_data == previous_video_download_data)
                ):
                    self.emit_log("Video output still matches previous clip; waiting for next clip output...", "INFO")
                    self.sleep_ms(2_000)
                    continue
                if (
                    previous_video_download_data
                    and video_download_data
                    and video_download_data == previous_video_download_data
                    and (not video_url or video_url == previous_video_url)
                ):
                    self.emit_log("Video download data still matches previous clip; waiting for next clip output...", "INFO")
                    self.sleep_ms(2_000)
                    continue
                voiceover_text = self.read_flow_output_text("voiceover")
                caption_text = self.read_flow_output_text("caption")
                subtitles_srt = self.read_flow_output_text("subtitles-srt")
                subtitles_json = self.read_flow_output_text("subtitles-json")
                video_duration = self.read_flow_output_text("video-duration")
                final_prompt_text = (
                    self.read_flow_output_text("final-prompt")
                    or self.read_flow_output_text("final_prompt")
                    or self.read_flow_output_text("prompt")
                )
                result.update(
                    {
                        "scene_group_id": scene_group_id,
                        "scene_number": self.parse_scene_int(scene_number_raw, int(scene["scene_number"])),
                        "scene_total": self.parse_scene_int(scene_total_raw, int(scene["scene_total"])),
                        "scene_role": scene_role,
                        "scene_title": scene_title,
                        "video_url": video_url,
                        "video_filename": video_filename,
                        "video_download_data": video_download_data,
                        "original_image_file": self.current_image_cleanup_result.get("original_image_file", ""),
                        "clean_image_file": self.current_image_cleanup_result.get("clean_image_file", ""),
                        "image_cleanup_status": self.current_image_cleanup_result.get("image_cleanup_status", ""),
                        "voiceover_text": voiceover_text,
                        "voiceover": voiceover_text,
                        "caption_text": caption_text,
                        "subtitles_srt": subtitles_srt,
                        "subtitles_json": subtitles_json,
                        "video_duration": video_duration,
                        "final_prompt_text": final_prompt_text,
                        "status": "completed",
                        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "error": "",
                    }
                )
                self.emit_log("Video generation completed.", "SUCCESS")
                if video_url:
                    self.emit_log(f"Captured video URL: {video_url}", "SUCCESS")
                else:
                    self.emit_log("Video completed but URL is empty.", "WARNING")
                if clip_metadata:
                    result.update(clip_metadata)
                return result

            is_failed = (
                "failed" in normalized_status
                or "thất bại" in normalized_status
                or "lỗi" in normalized_status
                or "error" in normalized_status
            )
            if is_failed:
                result.update(
                    {
                        "scene_group_id": scene["scene_group_id"],
                        "scene_number": int(scene["scene_number"]),
                        "scene_total": int(scene["scene_total"]),
                        "scene_role": scene["scene_role"],
                        "scene_title": scene["scene_title"],
                        "original_image_file": self.current_image_cleanup_result.get("original_image_file", ""),
                        "clean_image_file": self.current_image_cleanup_result.get("clean_image_file", ""),
                        "image_cleanup_status": self.current_image_cleanup_result.get("image_cleanup_status", ""),
                        "status": "failed",
                        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "error": f"Video generation failed. Status: {status_text or 'failed'}",
                    }
                )
                self.emit_log(result["error"], "ERROR")
                if clip_metadata:
                    result.update(clip_metadata)
                return result

            self.sleep_ms(3_000)

        result.update(
            {
                "scene_group_id": scene["scene_group_id"],
                "scene_number": int(scene["scene_number"]),
                "scene_total": int(scene["scene_total"]),
                "scene_role": scene["scene_role"],
                "scene_title": scene["scene_title"],
                "original_image_file": self.current_image_cleanup_result.get("original_image_file", ""),
                "clean_image_file": self.current_image_cleanup_result.get("clean_image_file", ""),
                "image_cleanup_status": self.current_image_cleanup_result.get("image_cleanup_status", ""),
                "status": "failed",
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "error": "Timed out waiting for video generation to complete.",
            }
        )
        self.emit_log(result["error"], "ERROR")
        if clip_metadata:
            result.update(clip_metadata)
        return result

    def append_video_result_csv(self, row: dict) -> None:
        target = self.config.output_dir / "video_results.csv"
        fieldnames = [
            "run_id",
            "batch_id",
            "index",
            "product_name",
            "multi_clip",
            "clip_total",
            "clip_index",
            "clip_role",
            "clip_video_file",
            "last_frame_file",
            "scene_id",
            "merge_method",
            "scene_group_id",
            "scene_number",
            "scene_total",
            "scene_role",
            "scene_title",
            "raw_video_file",
            "final_video_file",
            "video_file",
            "storage_path",
            "video_url",
            "voiceover_text",
            "voiceover",
            "voiceover_json_file",
            "voiceover_language",
            "voiceover_mode",
            "voiceover_status",
            "tts_required",
            "tts_enabled",
            "tts_provider",
            "tts_status",
            "tts_error",
            "tts_audio_file",
            "voiced_clip_file",
            "voiced_video_file",
            "audio_pipeline",
            "video_duration",
            "subtitles_srt",
            "subtitles_json",
            "logo_overlay_status",
            "logo_position",
            "subtitle_enabled",
            "subtitle_file",
            "subtitle_status",
            "subtitle_source",
            "original_image_file",
            "clean_image_file",
            "image_cleanup_status",
            "status",
            "created_at",
            "error",
        ]
        file_exists = target.exists()
        with target.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    def persist_scene_video_result(self, row: dict, frame: Frame | None = None) -> None:
        scene_group_id = str(row.get("scene_group_id") or "").strip() or "ungrouped"
        group_dir = self.video_group_dir(scene_group_id)
        group_dir.mkdir(parents=True, exist_ok=True)
        batch_dir = self.batch_storage_dir()
        batch_raw_dir = batch_dir / "raw"
        batch_final_dir = batch_dir / "videos"
        batch_raw_dir.mkdir(parents=True, exist_ok=True)
        batch_final_dir.mkdir(parents=True, exist_ok=True)

        video_file = ""
        video_bytes: bytes | None = None
        if str(row.get("status") or "").lower() == "completed":
            scene_number = self.parse_scene_int(row.get("scene_number"), 1)
            video_file = self.scene_video_filename(row)
            target = group_dir / video_file
            batch_raw_target = batch_raw_dir / video_file
            batch_final_target = batch_final_dir / video_file
            video_bytes = self.resolve_video_bytes(row)
            if video_bytes is None:
                if frame is not None and self.try_download_video_button(frame, batch_raw_target):
                    self.emit_log("Saved scene video through download button fallback.", "SUCCESS")
                    with suppress(Exception):
                        video_bytes = batch_raw_target.read_bytes()
                else:
                    raise RuntimeError(
                        f"Could not download scene video for group {scene_group_id} "
                        f"scene {scene_number} before continuing."
                    )
            if video_bytes is not None:
                batch_raw_target.write_bytes(video_bytes)
            shutil.copyfile(batch_raw_target, target)
            self.emit_log(f"Saved raw scene video: {batch_raw_target.name}", "SUCCESS")
            postprocess_result = self.create_final_video_with_postprocessing(batch_raw_target, batch_final_target, row)
            final_target_for_group = batch_final_target if batch_final_target.exists() else batch_raw_target
            shutil.copyfile(final_target_for_group, target)
            row["group_video_file"] = video_file
            row["raw_video_file"] = batch_raw_target.relative_to(batch_dir).as_posix()
            row["final_video_file"] = batch_final_target.relative_to(batch_dir).as_posix() if batch_final_target.exists() else ""
            row["video_file"] = row["final_video_file"] or row["raw_video_file"]
            row["batch_id"] = self.batch_id()
            row["raw_storage_path"] = batch_raw_target.relative_to(self.config.output_dir).as_posix()
            row["storage_path"] = (
                batch_final_target if batch_final_target.exists() else batch_raw_target
            ).relative_to(self.config.output_dir).as_posix()
            row.update(postprocess_result)

        manifest_path = group_dir / "manifest.json"
        manifest = self.load_scene_manifest(manifest_path, row)
        self.upsert_manifest_scene(manifest, row)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.persist_batch_manifest(batch_dir, row, video_bytes)

    def scene_video_filename(self, row: dict) -> str:
        index = self.parse_row_index(row.get("index"))
        scene_number = self.parse_scene_int(row.get("scene_number"), 1)
        scene_role = str(row.get("scene_role") or "single")
        role_slug = self.slugify(scene_role)
        if index > 0:
            return f"item_{index:04d}_scene_{scene_number:02d}_{role_slug}.mp4"
        return f"scene_{scene_number:02d}_{role_slug}.mp4"

    def video_group_dir(self, scene_group_id: str) -> Path:
        return self.config.output_dir / "videos" / self.slugify(scene_group_id)

    def batch_id(self) -> str:
        raw = str(self.config.run_id or "batch").strip() or "batch"
        return raw.replace("\\", "-").replace("/", "-")

    def batch_storage_dir(self) -> Path:
        return self.config.output_dir / "storage" / self.batch_id()

    def create_final_video_with_postprocessing(self, raw_video: Path, final_video: Path, row: dict) -> dict:
        result = {}
        subtitle_enabled = bool(self.config.enable_subtitles)
        logo_output = final_video.with_name(f"{final_video.stem}.logo-tmp{final_video.suffix}") if subtitle_enabled else final_video

        logo_result = self.create_final_video_with_logo(raw_video, logo_output)
        result.update(logo_result)
        current_video = logo_output if logo_output.exists() else raw_video

        if not subtitle_enabled:
            return result

        subtitle_result = self.subtitle_result("skipped", "")
        subtitle_result["subtitle_source"] = self.resolve_subtitle_source_name(row)
        subtitle_dir = final_video.parent.parent / "subtitles"
        subtitle_path = subtitle_dir / f"{final_video.stem}.srt"
        subtitle_text = self.resolve_subtitle_text(row)
        provided_srt = str(row.get("subtitles_srt") or "").strip()
        provided_json = str(row.get("subtitles_json") or "").strip()

        if provided_srt:
            subtitle_path.parent.mkdir(parents=True, exist_ok=True)
            subtitle_path.write_text(provided_srt, encoding="utf-8")
            subtitle_result["subtitle_source"] = "subtitles_srt"
        elif provided_json and self.write_subtitles_json_as_srt(provided_json, subtitle_path):
            subtitle_result["subtitle_source"] = "subtitles_json"
        elif not subtitle_text.strip():
            subtitle_result.update(
                {
                    "subtitle_status": "skipped",
                    "subtitle_error": "Subtitle text is empty.",
                }
            )
            if current_video != final_video:
                shutil.copyfile(current_video, final_video)
            result.update(subtitle_result)
            self.cleanup_temp_video(logo_output, final_video)
            self.emit_log(f"Subtitle skipped: empty text for {final_video.name}", "INFO")
            return result

        try:
            if not subtitle_path.exists():
                duration = self.parse_float(row.get("video_duration"), 0.0) or get_video_duration_seconds(current_video)
                self.emit_log(f"Subtitle generation: video duration {duration:.1f}s", "INFO")
                generate_srt(subtitle_text, duration, subtitle_path)
            subtitle_result["subtitle_file"] = subtitle_path.relative_to(final_video.parent.parent).as_posix()
            if not subtitle_path.read_text(encoding="utf-8").strip():
                subtitle_result.update(
                    {
                        "subtitle_status": "skipped",
                        "subtitle_error": "Generated subtitle is empty.",
                    }
                )
                if current_video != final_video:
                    shutil.copyfile(current_video, final_video)
                result.update(subtitle_result)
                self.cleanup_temp_video(logo_output, final_video)
                return result

            self.emit_log(f"Adding subtitles to {final_video.name}...", "INFO")
            burn_subtitles_with_ffmpeg(
                current_video,
                subtitle_path,
                final_video,
                font_size=self.config.subtitle_font_size,
            )
            subtitle_result.update(
                {
                    "subtitle_status": "success",
                    "subtitle_error": "",
                }
            )
            self.emit_log(f"Added subtitles: {final_video.name}", "SUCCESS")
        except Exception as exc:
            subtitle_result.update(
                {
                    "subtitle_status": "failed",
                    "subtitle_error": str(exc),
                }
            )
            if current_video != final_video and current_video.exists():
                shutil.copyfile(current_video, final_video)
            self.emit_log(f"Subtitle burn failed: {exc}", "WARNING")
        finally:
            self.cleanup_temp_video(logo_output, final_video)

        result.update(subtitle_result)
        return result

    def write_subtitles_json_as_srt(self, value: str, output_srt: Path) -> bool:
        try:
            parsed = json.loads(value)
            items = parsed.get("subtitles") if isinstance(parsed, dict) else parsed
            if not isinstance(items, list):
                return False
            lines: list[str] = []
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or item.get("caption") or item.get("voiceover") or "").strip()
                if not text:
                    continue
                start = self.parse_float(item.get("start") or item.get("start_seconds"), 0.0)
                end = self.parse_float(item.get("end") or item.get("end_seconds"), start + 2.0)
                if end <= start:
                    end = start + 2.0
                lines.extend(
                    [
                        str(len(lines) // 4 + 1),
                        f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}",
                        text,
                        "",
                    ]
                )
            if not lines:
                return False
            output_srt.parent.mkdir(parents=True, exist_ok=True)
            output_srt.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
            return True
        except Exception as exc:
            self.emit_log(f"Could not convert subtitles JSON to SRT: {exc}", "WARNING")
            return False

    def create_final_video_with_logo(self, raw_video: Path, final_video: Path) -> dict:
        result = self.logo_overlay_result("skipped", "")
        if not self.config.enable_logo_overlay:
            shutil.copyfile(raw_video, final_video)
            result["logo_overlay_status"] = "disabled"
            self.emit_log(f"Logo overlay disabled. Saved final video: {final_video.name}", "INFO")
            return result

        logo_path = self.resolve_logo_overlay_path()
        if logo_path is None:
            result.update(
                {
                    "logo_overlay_status": "failed",
                    "logo_overlay_error": "Logo overlay is enabled but no logo file path was provided.",
                }
            )
            self.emit_log(result["logo_overlay_error"], "WARNING")
            if self.config.strict_logo_overlay:
                raise RuntimeError(result["logo_overlay_error"])
            return result

        try:
            overlay_logo_with_ffmpeg(
                raw_video,
                logo_path,
                final_video,
                position=self.config.logo_position,
                logo_width_percent=self.config.logo_width_percent,
                margin=self.config.logo_margin,
            )
            result["logo_overlay_status"] = "success"
            self.emit_log(f"Applied logo overlay: {final_video.name}", "SUCCESS")
            return result
        except Exception as exc:
            result.update(
                {
                    "logo_overlay_status": "failed",
                    "logo_overlay_error": str(exc),
                }
            )
            self.emit_log(f"Logo overlay failed: {exc}", "WARNING")
            if self.config.strict_logo_overlay:
                raise RuntimeError(f"Logo overlay failed: {exc}") from exc
            return result

    def cleanup_temp_video(self, temp_video: Path, final_video: Path) -> None:
        if temp_video != final_video:
            with suppress(Exception):
                temp_video.unlink()

    def logo_overlay_result(self, status: str, error: str = "") -> dict:
        return {
            "logo_overlay_enabled": bool(self.config.enable_logo_overlay),
            "logo_overlay_status": status,
            "logo_overlay_error": error,
            "logo_position": self.config.logo_position,
            "logo_width_percent": self.config.logo_width_percent,
            "logo_margin": self.config.logo_margin,
        }

    def subtitle_result(self, status: str, error: str = "") -> dict:
        return {
            "subtitle_enabled": bool(self.config.enable_subtitles),
            "subtitle_file": "",
            "subtitle_status": status,
            "subtitle_error": error,
            "subtitle_source": self.config.subtitle_source,
            "subtitle_position": self.config.subtitle_position,
            "subtitle_font_size": self.config.subtitle_font_size,
            "subtitle_style": self.config.subtitle_style,
        }

    def resolve_subtitle_source_name(self, row: dict) -> str:
        source_text = self.subtitle_source_candidates(row)
        requested = str(self.config.subtitle_source or "voiceover")
        if requested != "auto" and source_text.get(requested, "").strip():
            return requested
        for source in ("voiceover", "caption", "final_prompt", "short_description"):
            if source_text.get(source, "").strip():
                return source
        return requested

    def resolve_subtitle_text(self, row: dict) -> str:
        source_text = self.subtitle_source_candidates(row)
        requested = str(self.config.subtitle_source or "voiceover")
        if requested != "auto" and source_text.get(requested, "").strip():
            return source_text[requested]
        for source in ("voiceover", "caption", "final_prompt", "short_description"):
            value = source_text.get(source, "").strip()
            if value:
                return value
        return ""

    def subtitle_source_candidates(self, row: dict) -> dict[str, str]:
        final_prompt = self.compress_voiceover_from_prompt(str(row.get("final_prompt_text") or ""))
        return {
            "voiceover": str(row.get("voiceover_text") or ""),
            "caption": str(row.get("caption_text") or ""),
            "final_prompt": final_prompt,
            "short_description": str(row.get("product_short_description") or ""),
        }

    def compress_voiceover_from_prompt(self, text: str) -> str:
        value = str(text or "").strip()
        if not value:
            return ""
        match = re.search(
            r"(?:voiceover|lời thoại|loi thoai|thuyết minh|thuyet minh)\s*[:：-]\s*(.+)",
            value,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            value = match.group(1)
        value = re.split(r"(?:\n\s*\n|visual|scene|shot|camera)\s*[:：-]", value, maxsplit=1, flags=re.IGNORECASE)[0]
        value = re.sub(r"\[[^\]]+\]|\([^)]*\)", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def resolve_logo_overlay_path(self) -> Path | None:
        raw_path = self.config.logo_file_path or (
            self.config.website_logo_path.as_posix() if self.config.website_logo_path else ""
        )
        if not raw_path:
            return None
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path

    def process_batch_logo_overlays(self) -> None:
        batch_dir = self.batch_storage_dir()
        manifest_path = batch_dir / "manifest.json"
        if not manifest_path.exists():
            self.emit_log("Batch manifest not found for logo overlay post-processing.", "WARNING")
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.emit_log(f"Cannot read batch manifest for logo overlay: {exc}", "WARNING")
            return

        changed = False
        for item in manifest.get("items", []):
            if str(item.get("status") or "").lower() != "completed":
                continue
            raw_rel = str(item.get("raw_video_file") or "")
            raw_path = batch_dir / raw_rel if raw_rel else None
            if raw_path is None or not raw_path.exists():
                continue
            final_rel = str(item.get("final_video_file") or f"videos/{raw_path.name}")
            final_path = batch_dir / final_rel
            if final_path.exists() and item.get("logo_overlay_status") == "success":
                continue
            overlay_result = self.create_final_video_with_logo(raw_path, final_path)
            item.update(overlay_result)
            if final_path.exists():
                item["final_video_file"] = final_rel
                item["video_file"] = final_rel
                item["storage_path"] = (final_path.relative_to(self.config.output_dir)).as_posix()
            changed = True

        if changed:
            manifest["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.emit_log("Batch logo overlay manifest updated.", "SUCCESS")

    def load_scene_manifest(self, manifest_path: Path, row: dict) -> dict:
        if manifest_path.exists():
            with suppress(Exception):
                return json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "scene_group_id": row.get("scene_group_id", ""),
            "product_name": row.get("product_name", ""),
            "scene_total": self.parse_scene_int(row.get("scene_total"), 1),
            "created_at": row.get("created_at", ""),
            "scenes": [],
        }

    def upsert_manifest_scene(self, manifest: dict, row: dict) -> None:
        row_index = self.parse_row_index(row.get("index"))
        scene_number = self.parse_scene_int(row.get("scene_number"), 1)
        scene_entry = {
            "index": row_index,
            "scene_number": scene_number,
            "scene_role": row.get("scene_role", ""),
            "scene_title": row.get("scene_title", ""),
            "raw_video_file": row.get("raw_video_file", ""),
            "final_video_file": row.get("final_video_file", ""),
            "video_file": row.get("group_video_file") or row.get("video_file", ""),
            "video_url": row.get("video_url", ""),
            "status": row.get("status", ""),
            "created_at": row.get("created_at", ""),
            "logo_overlay_enabled": row.get("logo_overlay_enabled", False),
            "logo_overlay_status": row.get("logo_overlay_status", ""),
            "logo_overlay_error": row.get("logo_overlay_error", ""),
            "logo_position": row.get("logo_position", ""),
            "logo_width_percent": row.get("logo_width_percent", ""),
            "subtitle_enabled": row.get("subtitle_enabled", False),
            "subtitle_file": row.get("subtitle_file", ""),
            "subtitle_status": row.get("subtitle_status", ""),
            "subtitle_error": row.get("subtitle_error", ""),
            "subtitle_source": row.get("subtitle_source", ""),
            "subtitle_font_size": row.get("subtitle_font_size", ""),
            "original_image_file": row.get("original_image_file", ""),
            "clean_image_file": row.get("clean_image_file", ""),
            "image_cleanup_status": row.get("image_cleanup_status", ""),
        }
        scenes = manifest.setdefault("scenes", [])
        for index, existing in enumerate(scenes):
            existing_index = self.parse_row_index(existing.get("index"))
            same_index = row_index > 0 and existing_index == row_index
            same_legacy_scene = (
                row_index <= 0
                and self.parse_scene_int(existing.get("scene_number"), -1) == scene_number
            )
            if same_index or same_legacy_scene:
                scenes[index] = scene_entry
                break
        else:
            scenes.append(scene_entry)
        scenes.sort(
            key=lambda item: (
                self.parse_scene_int(item.get("scene_number"), 0),
                self.parse_row_index(item.get("index")),
            )
        )
        manifest["scene_group_id"] = row.get("scene_group_id", manifest.get("scene_group_id", ""))
        manifest["product_name"] = row.get("product_name", manifest.get("product_name", ""))
        manifest["scene_total"] = self.parse_scene_int(row.get("scene_total"), manifest.get("scene_total", 1))
        manifest["created_at"] = manifest.get("created_at") or row.get("created_at", "")

    def persist_batch_manifest(self, batch_dir: Path, row: dict, video_bytes: bytes | None) -> None:
        manifest_path = batch_dir / "manifest.json"
        if manifest_path.exists():
            manifest = {}
            with suppress(Exception):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {}

        manifest.setdefault("batch_id", self.batch_id())
        manifest.setdefault("run_id", self.config.run_id or self.batch_id())
        manifest.setdefault("created_at", row.get("created_at", ""))
        manifest["updated_at"] = row.get("created_at", "")
        items = manifest.setdefault("items", [])

        identity = (
            self.parse_row_index(row.get("index")),
            str(row.get("scene_group_id") or ""),
            self.parse_scene_int(row.get("scene_number"), 0),
        )
        entry = {
            "run_id": row.get("run_id", ""),
            "batch_id": row.get("batch_id", self.batch_id()),
            "index": self.parse_row_index(row.get("index")),
            "product_name": row.get("product_name", ""),
            "scene_group_id": row.get("scene_group_id", ""),
            "scene_number": self.parse_scene_int(row.get("scene_number"), 1),
            "scene_total": self.parse_scene_int(row.get("scene_total"), 1),
            "scene_role": row.get("scene_role", ""),
            "scene_title": row.get("scene_title", ""),
            "raw_video_file": row.get("raw_video_file", ""),
            "final_video_file": row.get("final_video_file", ""),
            "video_file": row.get("video_file", ""),
            "raw_storage_path": row.get("raw_storage_path", ""),
            "storage_path": row.get("storage_path", ""),
            "video_url": row.get("video_url", ""),
            "status": row.get("status", ""),
            "created_at": row.get("created_at", ""),
            "error": row.get("error", ""),
            "logo_overlay_enabled": row.get("logo_overlay_enabled", False),
            "logo_overlay_status": row.get("logo_overlay_status", ""),
            "logo_overlay_error": row.get("logo_overlay_error", ""),
            "logo_position": row.get("logo_position", ""),
            "logo_width_percent": row.get("logo_width_percent", ""),
            "logo_margin": row.get("logo_margin", ""),
            "subtitle_enabled": row.get("subtitle_enabled", False),
            "subtitle_file": row.get("subtitle_file", ""),
            "subtitle_status": row.get("subtitle_status", ""),
            "subtitle_error": row.get("subtitle_error", ""),
            "subtitle_source": row.get("subtitle_source", ""),
            "subtitle_position": row.get("subtitle_position", ""),
            "subtitle_font_size": row.get("subtitle_font_size", ""),
            "subtitle_style": row.get("subtitle_style", ""),
            "original_image_file": row.get("original_image_file", ""),
            "clean_image_file": row.get("clean_image_file", ""),
            "image_cleanup_status": row.get("image_cleanup_status", ""),
            "file_size": len(video_bytes) if video_bytes is not None else 0,
        }
        for idx, existing in enumerate(items):
            existing_identity = (
                self.parse_row_index(existing.get("index")),
                str(existing.get("scene_group_id") or ""),
                self.parse_scene_int(existing.get("scene_number"), 0),
            )
            if existing_identity == identity:
                items[idx] = entry
                break
        else:
            items.append(entry)

        items.sort(
            key=lambda item: (
                self.parse_row_index(item.get("index")),
                str(item.get("scene_group_id") or ""),
                self.parse_scene_int(item.get("scene_number"), 0),
            )
        )
        manifest["item_count"] = len(items)
        manifest["completed_count"] = sum(
            1 for item in items if str(item.get("status") or "").lower() == "completed"
        )
        manifest["failed_count"] = sum(
            1 for item in items if str(item.get("status") or "").lower() == "failed"
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def resolve_video_bytes(self, row: dict) -> bytes | None:
        video_download_data = str(row.get("video_download_data") or "").strip()
        if video_download_data.startswith("data:"):
            return self.decode_data_url(video_download_data)

        video_url = str(row.get("video_url") or "").strip()
        if not video_url:
            return None

        if video_url.startswith("data:"):
            return self.decode_data_url(video_url)

        with suppress(Exception):
            with requests.get(video_url, stream=True, timeout=120) as response:
                response.raise_for_status()
                return response.content

        if video_url.startswith("blob:"):
            try:
                return self.fetch_url_bytes_in_browser(video_url)
            except Exception as exc:
                self.emit_log(f"Browser fetch for blob video failed; trying download button fallback. {exc}", "WARNING")
                return None

        try:
            return self.fetch_url_bytes_in_browser(video_url)
        except Exception as exc:
            self.emit_log(f"Browser fetch for video URL failed; trying download button fallback. {exc}", "WARNING")
        return None

    def decode_data_url(self, value: str) -> bytes:
        _, encoded = value.split(",", 1)
        return base64.b64decode(encoded)

    def fetch_url_bytes_in_browser(self, url: str) -> bytes:
        script = """
            async (targetUrl) => {
              const response = await fetch(targetUrl);
              if (!response.ok) {
                throw new Error(`Fetch failed: ${response.status}`);
              }
              const buffer = await response.arrayBuffer();
              const bytes = new Uint8Array(buffer);
              let binary = "";
              const chunkSize = 0x8000;
              for (let index = 0; index < bytes.length; index += chunkSize) {
                const chunk = bytes.subarray(index, index + chunkSize);
                binary += String.fromCharCode(...chunk);
              }
              return btoa(binary);
            }
        """
        last_error = None
        for scope in self.iter_page_and_frame_scopes():
            try:
                encoded = scope.evaluate(script, url)
                return base64.b64decode(encoded)
            except Exception as e:
                last_error = e

        # Fallback: trigger a download via <a download> click in all frames.
        # This bypasses Chrome's strict CORS block for fetch() on blob:null URLs.
        try:
            assert self.page is not None
            with self.page.expect_download(timeout=45000) as download_info:
                for scope in self.iter_page_and_frame_scopes():
                    with suppress(Exception):
                        scope.evaluate("""(blobUrl) => {
                            const a = document.createElement('a');
                            a.style.display = 'none';
                            a.href = blobUrl;
                            a.download = "fallback_download.mp4";
                            document.body.appendChild(a);
                            a.click();
                            setTimeout(() => a.remove(), 1000);
                        }""", url)
            
            download = download_info.value
            path = download.path()
            if path:
                with open(path, "rb") as f:
                    return f.read()
        except Exception as fallback_err:
            raise RuntimeError(
                f"Failed to fetch {url} via fetch ({last_error}) "
                f"and fallback download failed ({fallback_err})"
            )
        
        raise RuntimeError(f"Failed to fetch {url} in all frame scopes: {last_error}")

    def read_flow_output_text(self, output_name: str) -> str:
        return self.read_output(f'[data-flow-output="{output_name}"]')

    def find_in_all_frames(
        self,
        selector: str,
        require_visible: bool = True,
        require_enabled: bool = False,
    ) -> Optional[Locator]:
        for scope in self.iter_page_and_frame_scopes():
            with suppress(Exception):
                locator = scope.locator(selector).first
                if not locator.count():
                    continue
                if require_visible and not locator.is_visible():
                    continue
                if require_enabled and locator.is_disabled():
                    continue
                return locator
        return None

    def click_first_available(self, selectors: Iterable[str]) -> bool:
        for selector in selectors:
            locator = self.find_in_all_frames(
                selector,
                require_visible=True,
                require_enabled=True,
            )
            if locator is None:
                continue
            with suppress(Exception):
                locator.scroll_into_view_if_needed()
            locator.click()
            return True
        return False

    def read_output(self, selector: str) -> str:
        selector = str(selector or "").strip()
        if selector and not selector.startswith(("[", ".", "#")):
            selector = f'[data-flow-output="{selector}"]'
        selectors = [selector]
        for scope in self.iter_page_and_frame_scopes():
            for selector in selectors:
                with suppress(Exception):
                    locator = scope.locator(selector).first
                    if not locator.count():
                        continue
                    for reader in (
                        lambda item: item.input_value(),
                        lambda item: item.get_attribute("value") or "",
                        lambda item: item.get_attribute("href") or "",
                        lambda item: item.get_attribute("src") or "",
                        lambda item: item.inner_text(),
                        lambda item: item.text_content() or "",
                    ):
                        with suppress(Exception):
                            value = (reader(locator) or "").strip()
                            if value:
                                return value
        return ""

    def wait_output_value(
        self,
        selector: str,
        expected_values: Iterable[str],
        timeout_ms: int,
    ) -> str:
        expected = {str(value).strip().lower() for value in expected_values}
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            self.ensure_browser_alive()
            value = self.read_output(selector).strip()
            if value.lower() in expected:
                return value
            self.sleep_ms(500)
        return ""

    def find_video_url_fallback(self) -> str:
        selectors = [
            "video[src]",
            "source[src]",
            'a[href*=".mp4"]',
            "a[download]",
        ]
        attr_by_selector = {
            "video[src]": "src",
            "source[src]": "src",
            'a[href*=".mp4"]': "href",
            "a[download]": "href",
        }
        for scope in self.iter_page_and_frame_scopes():
            for selector in selectors:
                with suppress(Exception):
                    locator = scope.locator(selector).first
                    if not locator.count():
                        continue
                    attr = attr_by_selector[selector]
                    value = (locator.get_attribute(attr) or "").strip()
                    if value:
                        return value
        return ""

    def iter_page_and_frame_scopes(self) -> list[Page | Frame]:
        assert self.page is not None
        return [self.page] + list(self.page.frames)

    # ════════════════════════════════════════════════════════
    # POST-GENERATION: CREATE NEXT PRODUCT
    # ════════════════════════════════════════════════════════

    def wait_for_create_next_product(self, timeout_ms: int) -> None:
        """
        Wait for the create-next-product button after video completion, then click it.
        """
        assert self.page is not None
        deadline = time.time() + timeout_ms / 1000
        log_interval = 10
        last_log_time = time.time()

        self.emit_log("Waiting for create next product button...")

        while time.time() < deadline:
            self.ensure_browser_alive()
            # Search page + all frames
            btn = self._find_create_next_in_all_frames()
            if btn is not None:
                btn.click()
                self.emit_log("Clicked create next product.", "SUCCESS")
                # Wait for Step 1 product fields to reappear
                self._wait_for_step1_after_restart(timeout_ms=30_000)
                return

            now = time.time()
            if now - last_log_time >= log_interval:
                elapsed = int(now - (deadline - timeout_ms / 1000))
                self.emit_log(
                    f"Waiting for create next product button... ({elapsed}s elapsed)"
                )
                last_log_time = now

            self.sleep_ms(1_000)

        self.capture_debug("create-next-product-not-found")
        raise TimeoutError(
            f"create-next-product button did not appear after {timeout_ms // 1000}s. "
            "Screenshot saved to create-next-product-not-found.png"
        )

    def _find_create_next_in_all_frames(self) -> Optional[Locator]:
        """Search page and all iframes for the create-next-product button."""
        assert self.page is not None
        scopes: list[Page | Frame] = [self.page] + list(self.page.frames)
        for scope in scopes:
            btn = self.find_button_by_selectors_or_text(
                scope,
                selectors=[
                    '[data-flow-action="next-day"]',
                    '[data-flow-field="next-day"]',
                    '[data-flow-action="create-next-product"]',
                    '[data-flow-field="create-next-product"]',
                ],
                patterns=[
                    r"tạo tiếp sản phẩm mới",
                    r"tao tiep san pham moi",
                    r"tiếp tục tạo video",
                    r"tiep tuc tao video",
                    r"next day",
                    r"create next product",
                    r"next product",
                ],
            )
            if btn is not None:
                return btn
        return None

    def _wait_for_step1_after_restart(self, timeout_ms: int = 30_000) -> None:
        """Wait until Step 1 product fields are visible again after restart."""
        deadline = time.time() + timeout_ms / 1000
        self.emit_log("Waiting for Step 1 to reload...")
        while time.time() < deadline:
            self.ensure_browser_alive()
            frame = self._get_tool_frame_or_none()
            if frame is not None and self.frame_has_product_fields(frame):
                self.emit_log("Step 1 is ready for next product.", "SUCCESS")
                return
            self.sleep_ms(800)
        self.emit_log(
            "Step 1 did not reappear in time after restart — continuing anyway.",
            "WARNING",
        )

    def _get_tool_frame_or_none(self) -> Optional[Frame]:
        """Return the tool frame if product fields are present, else None."""
        assert self.page is not None
        if self.frame_has_product_fields(self.page.main_frame):
            return self.page.main_frame
        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            if self.frame_has_product_fields(frame):
                return frame
        return None

    # ════════════════════════════════════════════════════════
    # UNIVERSAL BUTTON FINDER
    # ════════════════════════════════════════════════════════

    def find_button_by_selectors_or_text(
        self,
        scope: Page | Frame | Locator,
        selectors: list[str],
        patterns: list[str],
    ) -> Optional[Locator]:
        """
        Try each CSS selector first (data-flow-action / data-flow-field).
        Fall back to text-pattern search.
        Ignores hidden or disabled buttons.
        Returns the first visible + enabled match, or None.
        """
        # 1. Try explicit selectors
        for selector in selectors:
            with suppress(Exception):
                locator = scope.locator(selector).first
                if (
                    locator.count()
                    and locator.is_visible()
                    and not locator.is_disabled()
                ):
                    return locator

        # 2. Fallback: text pattern search
        return self.find_button(scope, patterns)

    # ════════════════════════════════════════════════════════
    # FRAME / FIELD DETECTION   (Step 1 — DO NOT CHANGE)
    # ════════════════════════════════════════════════════════

    def wait_for_tool_frame(self, timeout_ms: int = 60_000) -> Frame:
        assert self.page is not None
        end_time = time.time() + timeout_ms / 1000
        self.sleep_ms(1_500)
        while time.time() < end_time:
            self.ensure_browser_alive()
            if self.frame_has_product_fields(self.page.main_frame):
                self.emit_log(f"Tool fields found in main frame: {self.page.url}")
                return self.page.main_frame
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                if self.frame_has_product_fields(frame):
                    self.emit_log(f"Tool frame ready: {frame.url or '<srcdoc>'}")
                    return frame
            self.sleep_ms(500)
        raise TimeoutError(
            f"Could not find Flow tool frame with product fields after "
            f"{timeout_ms // 1000}s. Last URL: {self.page.url}"
        )

    def frame_has_product_fields(self, frame: Frame) -> bool:
        selectors = [
            '[data-flow-field="product-name"]',
            '[data-flow-field="product-description"]',
            '[data-flow-field="product-short-description"]',
            'input[placeholder*="Ví dụ"]',
            'textarea[placeholder*="Ví dụ"]',
        ]
        for selector in selectors:
            with suppress(Exception):
                if frame.locator(selector).count():
                    return True
        return False

    def wait_for_product_step_ready(
        self, frame: Frame, timeout_ms: int = 45_000
    ) -> None:
        end_time = time.time() + timeout_ms / 1000
        self.emit_log("Waiting for Step 1 product inputs...")
        while time.time() < end_time:
            self.ensure_browser_alive()
            frame = self.refresh_frame_reference(frame)
            name_input  = self.find_text_field(frame, "product_name")
            short_input = self.find_text_field(frame, "short_description")
            long_input  = self.find_text_field(frame, "long_description")
            if name_input and short_input and long_input:
                name_input.wait_for(state="visible", timeout=3_000)
                return
            self.sleep_ms(600)
        raise TimeoutError("Step 1 product inputs did not become ready in time.")

    # ════════════════════════════════════════════════════════
    # TEXT FIELD FILL   (Step 1 — DO NOT CHANGE)
    # ════════════════════════════════════════════════════════

    def fill_text_fields(self, frame: Frame, product: ProductRow) -> None:
        field_values = {
            "product_name":      product.product_name,
            "short_description": product.short_description,
            "long_description":  product.long_description,
        }
        for field_key, value in field_values.items():
            self.emit_log(f"Filling {field_key}...")
            locator = self.find_text_field(frame, field_key)
            if locator is None:
                raise RuntimeError(f"Could not locate field: {field_key}")
            self.enter_field_value(locator, value, field_key)
            self.sleep_ms(250)
            self.emit_log(f"Filled {field_key}")

    def find_text_field(self, frame: Frame, field_key: str) -> Optional[Locator]:
        selectors_by_key = {
            "product_name": [
                '[data-flow-field="product-name"] [contenteditable="true"]',
                '[data-flow-field="product-name"] [role="textbox"]',
                '[data-flow-field="product-name"] input',
                '[data-flow-field="product-name"] textarea',
                'input[data-flow-field="product-name"]',
                'textarea[data-flow-field="product-name"]',
                '[data-flow-field="product-name"]',
                '[data-flow-field="product name"]',
                '[data-flow-field="product name"] input',
                '[data-flow-field="product_name"] [contenteditable="true"]',
                '[data-flow-field="product_name"] input',
                'input[data-flow-field="product_name"]',
                'input[placeholder*="Tên sản phẩm"]',
                'input[placeholder*="Ví dụ:"]',
            ],
            "short_description": [
                '[data-flow-field="product-short-description"] textarea',
                'textarea[data-flow-field="product-short-description"]',
                '[data-flow-field="product-short-description"] input',
                '[data-flow-field="product-short-description"]',
                '[data-flow-field="product short description"]',
                '[data-flow-field="product-short-decription"] textarea',
                'textarea[data-flow-field="product-short-decription"]',
                '[data-flow-field="product-short-decription"] input',
                '[data-flow-field="product-short-decription"]',
                '[data-flow-field="product short decription"]',
                '[data-flow-field="product-description"] textarea',
                'textarea[data-flow-field="product-description"]',
                '[data-flow-field="product-description"]',
                '[data-flow-field="short_description"] textarea',
                'textarea[placeholder*="Mô tả ngắn"]',
                'textarea[placeholder*="Thức ăn"]',
            ],
            "long_description": [
                '[data-flow-field="product-long-description"] textarea',
                'textarea[data-flow-field="product-long-description"]',
                '[data-flow-field="product-long-description"] input',
                '[data-flow-field="product-long-description"]',
                '[data-flow-field="product long description"]',
                '[data-flow-field="product-long-decription"] textarea',
                'textarea[data-flow-field="product-long-decription"]',
                '[data-flow-field="product-long-decription"] input',
                '[data-flow-field="product-long-decription"]',
                '[data-flow-field="product long decription"]',
                '[data-flow-field="selling-points"] textarea',
                '[data-flow-field="long_description"] textarea',
                'textarea[placeholder*="Mô tả dài"]',
                'textarea[placeholder*="Thành phần"]',
            ],
        }
        for selector in selectors_by_key[field_key]:
            with suppress(Exception):
                locator = frame.locator(selector).first
                if locator.count():
                    return locator

        regex_by_key = {
            "product_name":      re.compile(r"ten san pham|product name", re.I),
            "short_description": re.compile(
                r"mo ta ngan|mo ta so luoc|short description|product description", re.I
            ),
            "long_description":  re.compile(
                r"mo ta dai|diem noi bat|long description|selling points", re.I
            ),
        }
        pattern = regex_by_key[field_key]
        for locator in self.iter_candidate_inputs(frame):
            text = self.locator_context_text(locator)
            if pattern.search(text):
                return locator
        return None

    def enter_field_value(self, locator: Locator, value: str, field_key: str) -> None:
        tag_name = ""
        locator.scroll_into_view_if_needed()
        with suppress(Exception):
            tag_name = (locator.evaluate("(el) => el.tagName") or "").lower()

        if tag_name in {"input", "textarea"}:
            with suppress(Exception):
                locator.focus()
            with suppress(Exception):
                locator.fill("")
                locator.fill(value)
                locator.dispatch_event("input")
                locator.dispatch_event("change")
                locator.dispatch_event("blur")
            if self.field_contains_value(locator, value):
                return

            with suppress(Exception):
                locator.evaluate(
                    """(el, nextValue) => {
                        if ('value' in el) {
                            el.value = nextValue;
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    }""",
                    value,
                )
            if self.field_contains_value(locator, value):
                return

            with suppress(Exception):
                locator.click()
                locator.press("Control+A")
                locator.press("Backspace")
                locator.type(value, delay=18)
                locator.dispatch_event("input")
                locator.dispatch_event("change")
                locator.dispatch_event("blur")
            if self.field_contains_value(locator, value):
                return

        with suppress(Exception):
            locator.click()

        with suppress(Exception):
            locator.evaluate(
                """(el, nextValue) => {
                    if (el.isContentEditable) {
                        el.innerText = nextValue;
                    } else if ('value' in el) {
                        el.value = nextValue;
                    } else {
                        el.textContent = nextValue;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }""",
                value,
            )
        if self.field_contains_value(locator, value):
            return

        raise RuntimeError(f"Could not reliably fill field: {field_key}")

    def field_contains_value(self, locator: Locator, expected: str) -> bool:
        expected_normalized = " ".join(expected.split())
        actual = ""
        with suppress(Exception):
            actual = locator.input_value()
        if not actual:
            with suppress(Exception):
                actual = locator.inner_text()
        if not actual:
            with suppress(Exception):
                actual = locator.text_content() or ""
        actual_normalized = " ".join(str(actual).split())
        return bool(actual_normalized) and expected_normalized in actual_normalized

    @staticmethod
    def parse_scene_int(value: object, fallback: int) -> int:
        try:
            return max(1, int(float(str(value))))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def parse_float(value: object, fallback: float = 0.0) -> float:
        try:
            return max(0.0, float(str(value)))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def parse_row_index(value: object) -> int:
        try:
            return max(0, int(float(str(value))))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def slugify(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
        return slug or "single"

    @staticmethod
    def ascii_fold(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", normalized).strip()

    def iter_candidate_inputs(self, frame: Frame) -> Iterable[Locator]:
        for selector in ("input", "textarea", '[contenteditable="true"]'):
            group = frame.locator(selector)
            count = min(group.count(), 50)
            for idx in range(count):
                locator = group.nth(idx)
                with suppress(Exception):
                    if locator.is_visible():
                        yield locator

    def locator_context_text(self, locator: Locator) -> str:
        texts = []
        for attr in ("aria-label", "placeholder", "name", "title"):
            with suppress(Exception):
                value = locator.get_attribute(attr)
                if value:
                    texts.append(value)
        with suppress(Exception):
            parent_text = locator.locator(
                "xpath=ancestor::*[self::label or self::div or self::section][1]"
            ).inner_text(timeout=500)
            if parent_text:
                texts.append(parent_text)
        return " ".join(texts).lower()

    # Step 1 preset/logo helpers.
    def import_preset_if_needed(self, frame: Frame) -> None:
        preset_json = (self.config.preset_json or "").strip()
        if not preset_json:
            return

        if not self.has_preset_import_controls():
            self.emit_log("Preset JSON was provided, but this tool has no preset import controls. Skipping preset import.", "INFO")
            return

        if not self.ensure_preset_manager_open(frame, optional=True):
            self.emit_log("Preset manager is not available in this tool. Skipping preset import.", "INFO")
            return

        self.emit_log("Looking for preset import textarea...")
        textarea = self.find_visible_by_selector(
            frame,
            [
                '[data-flow-field="preset-json-import-textarea"]',
                'textarea[data-flow-field="preset-json-import-textarea"]',
                '[data-flow-field="preset-json-import-textarea"] textarea',
            ],
        )
        if textarea is None:
            self.emit_log("Preset import textarea not found. Skipping preset import.", "INFO")
            return

        textarea.scroll_into_view_if_needed()
        textarea.click()
        textarea.fill("")
        textarea.fill(preset_json)
        self.emit_log("Filled preset JSON textarea.", "SUCCESS")

        self.emit_log("Looking for import preset button...")
        button = self.find_visible_by_selector(
            frame,
            ['[data-flow-field="import-preset-from-paste"]'],
            require_enabled=True,
        )
        if button is None:
            self.emit_log("Import preset button not found. Skipping preset import.", "INFO")
            return

        button.click()
        self.emit_log("Imported preset from paste.", "SUCCESS")
        self.sleep_ms(1_000)

    def upload_website_logo_if_needed(self, frame: Frame) -> None:
        logo_path = self.config.website_logo_path
        if logo_path is None:
            return
        logo_path = logo_path.expanduser()
        if not logo_path.exists():
            raise FileNotFoundError(f"Website logo not found: {logo_path}")

        self.emit_log("Looking for website logo upload input...")
        for selector in (
            'input[data-flow-field="website-logo-upload-input"]',
            '[data-flow-field="website-logo-upload-input"] input',
            '[data-flow-field="website-logo-upload-input"]',
        ):
            input_locator = self.find_in_all_frames(selector, require_visible=False)
            if input_locator is not None:
                self.emit_log("Uploading website logo...")
                input_locator.set_input_files(logo_path.as_posix())
                self.emit_log("Uploaded website logo.", "SUCCESS")
                self.sleep_ms(self.config.extra_wait_after_upload_ms)
                return

        upload_area = self.find_visible_by_selector(
            frame,
            ['[data-flow-field="website-logo-upload"]'],
        )
        if upload_area is None:
            if not self.ensure_preset_manager_open(frame, optional=True):
                self.emit_log("Website logo was provided, but this tool has no website-logo upload field. Skipping tool logo upload.", "INFO")
                return
            upload_area = self.find_visible_by_selector(
                frame,
                ['[data-flow-field="website-logo-upload"]'],
            )
            if upload_area is None:
                self.emit_log("Website logo upload field not found after opening preset manager. Skipping tool logo upload.", "INFO")
                return

        assert self.page is not None
        self.emit_log("Uploading website logo...")
        try:
            with self.page.expect_file_chooser(timeout=3_000) as chooser_info:
                upload_area.click()
            chooser_info.value.set_files(logo_path.as_posix())
        except PlaywrightTimeoutError:
            for selector in (
                'input[data-flow-field="website-logo-upload-input"]',
                '[data-flow-field="website-logo-upload-input"] input',
                '[data-flow-field="website-logo-upload-input"]',
            ):
                input_locator = self.find_in_all_frames(selector, require_visible=False)
                if input_locator is not None:
                    input_locator.set_input_files(logo_path.as_posix())
                    break
            else:
                self.emit_log("Website logo file input did not appear. Skipping tool logo upload.", "INFO")
                return

        self.emit_log("Uploaded website logo.", "SUCCESS")
        self.sleep_ms(self.config.extra_wait_after_upload_ms)

    def has_preset_import_controls(self) -> bool:
        selectors = [
            '[data-flow-field="preset-json-import-textarea"]',
            'textarea[data-flow-field="preset-json-import-textarea"]',
            '[data-flow-field="preset-json-import-textarea"] textarea',
            '[data-flow-field="import-preset-from-paste"]',
            '[data-flow-field="preset-manager-toggle"]',
            '[data-flow-action="preset-manager-toggle"]',
        ]
        return any(
            self.find_in_all_frames(selector, require_visible=False) is not None
            for selector in selectors
        )

    def ensure_preset_manager_open(self, frame: Frame, optional: bool = False) -> bool:
        if self.find_visible_by_selector(
            frame,
            [
                '[data-flow-field="preset-json-import-textarea"]',
                'textarea[data-flow-field="preset-json-import-textarea"]',
                '[data-flow-field="preset-json-import-textarea"] textarea',
                '[data-flow-field="website-logo-upload-input"]',
                '[data-flow-field="website-logo-upload-input"] input',
                '[data-flow-field="website-logo-upload"]',
            ],
        ) is not None:
            return True

        self.emit_log("Looking for preset manager toggle...")
        toggle = self.find_visible_by_selector(
            frame,
            [
                '[data-flow-field="preset-manager-toggle"]',
                '[data-flow-action="preset-manager-toggle"]',
            ],
            require_enabled=True,
        )
        if toggle is None:
            if optional:
                return False
            raise RuntimeError("Preset manager toggle not found.")

        toggle.scroll_into_view_if_needed()
        toggle.click()
        self.emit_log("Opened preset manager toggle.", "SUCCESS")
        self.sleep_ms(500)
        return True

    def find_visible_by_selector(
        self,
        scope: Page | Frame | Locator,
        selectors: list[str],
        require_enabled: bool = False,
    ) -> Optional[Locator]:
        for selector in selectors:
            with suppress(Exception):
                locator = scope.locator(selector).first
                if not locator.count() or not locator.is_visible():
                    continue
                if require_enabled and locator.is_disabled():
                    continue
                return locator
        return None

    # ════════════════════════════════════════════════════════
    # IMAGE UPLOAD   (Step 1 — DO NOT CHANGE)
    # ════════════════════════════════════════════════════════

    def download_image(self, image_url: str, index: int) -> Path:
        self.emit_log("Downloading product image...")
        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/png")
        ext = ".png"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "webp" in content_type:
            ext = ".webp"
        target = self.config.temp_dir / f"product_{index + 1}{ext}"
        target.write_bytes(response.content)
        self.emit_log(f"Downloaded original image to {target}")
        return target

    def clean_product_image(self, original_path: Path, product: ProductRow, index: int) -> Path:
        slug = self.slugify(product.product_name)
        filename_base = f"{index + 1:04d}_{slug}"
        original_png = self.config.output_dir / "original-images" / f"{filename_base}.png"
        clean_png = self.config.output_dir / "clean-images" / f"{filename_base}_clean.png"
        failed_png = self.config.output_dir / "failed-cleanup-images" / f"{filename_base}.png"
        original_png.parent.mkdir(parents=True, exist_ok=True)
        clean_png.parent.mkdir(parents=True, exist_ok=True)
        failed_png.parent.mkdir(parents=True, exist_ok=True)

        stored_original = original_png
        self.current_image_cleanup_result = {
            "original_image_file": stored_original.relative_to(self.config.output_dir).as_posix(),
            "clean_image_file": "",
            "image_cleanup_status": "pending",
        }

        try:
            self.save_image_as_png(original_path, original_png)
            cleanup_input = original_png
        except Exception as exc:
            self.emit_log(f"Could not normalize original image to PNG: {exc}", "WARNING")
            suffix = original_path.suffix if original_path.suffix else ".img"
            stored_original = original_png.with_suffix(suffix)
            shutil.copyfile(original_path, stored_original)
            cleanup_input = stored_original
            self.current_image_cleanup_result["original_image_file"] = stored_original.relative_to(
                self.config.output_dir
            ).as_posix()
        self.emit_log(f"Downloaded original image saved: {stored_original}", "SUCCESS")

        mode = str(self.config.cleanup_mode or "auto").strip().lower()
        if not self.config.enable_product_image_cleanup or mode == "none":
            self.current_image_cleanup_result["image_cleanup_status"] = "disabled"
            self.emit_log("Product image cleanup disabled. Using original image.", "INFO")
            return stored_original

        if self.config.cleanup_cache_enabled and clean_png.exists() and clean_png.stat().st_size > 0:
            self.current_image_cleanup_result.update(
                {
                    "clean_image_file": clean_png.relative_to(self.config.output_dir).as_posix(),
                    "image_cleanup_status": "cached",
                }
            )
            self.emit_log(f"Using cached cleaned product image: {clean_png}", "SUCCESS")
            return clean_png

        self.emit_log("Cleaning product image...", "INFO")
        cleaned = False
        cleanup_status = ""
        try:
            if mode in {"auto", "remove_background"}:
                cleaned = self.remove_background_with_rembg(cleanup_input, clean_png)
                if cleaned:
                    cleanup_status = "rembg"
                    self.emit_log("Background removed successfully.", "SUCCESS")
                elif mode == "remove_background" and not self.config.cleanup_white_background_fallback:
                    raise RuntimeError("rembg is not installed or background removal failed.")
            if not cleaned and mode in {"auto", "remove_background", "sharpen_only"}:
                cleaned = self.fallback_pillow_cleanup(cleanup_input, clean_png)
                cleanup_status = "pillow"
        except Exception as exc:
            self.emit_log(f"Cleanup failed, using original image. {exc}", "WARNING")
            with suppress(Exception):
                shutil.copyfile(stored_original, failed_png.with_suffix(stored_original.suffix))
            self.current_image_cleanup_result["image_cleanup_status"] = "failed"
            return stored_original

        if cleaned and clean_png.exists() and clean_png.stat().st_size > 0:
            self.current_image_cleanup_result.update(
                {
                    "clean_image_file": clean_png.relative_to(self.config.output_dir).as_posix(),
                    "image_cleanup_status": cleanup_status or "success",
                }
            )
            self.emit_log(f"Using cleaned product image: {clean_png}", "SUCCESS")
            return clean_png

        self.emit_log("Cleanup failed, using original image.", "WARNING")
        with suppress(Exception):
            shutil.copyfile(stored_original, failed_png.with_suffix(stored_original.suffix))
        self.current_image_cleanup_result["image_cleanup_status"] = "failed"
        return stored_original

    def save_image_as_png(self, input_path: Path, output_path: Path) -> None:
        from PIL import Image, ImageOps

        with Image.open(input_path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA")
            image.save(output_path, "PNG")

    def remove_background_with_rembg(self, input_path: Path, output_path: Path) -> bool:
        try:
            from rembg import remove
            from PIL import Image, ImageOps
        except Exception as exc:
            self.emit_log(f"rembg unavailable, using Pillow fallback. {exc}", "INFO")
            return False

        try:
            with Image.open(input_path) as image:
                image = ImageOps.exif_transpose(image).convert("RGBA")
                cleaned = remove(image)
                if cleaned.mode != "RGBA":
                    cleaned = cleaned.convert("RGBA")
                cleaned.save(output_path, "PNG")
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            self.emit_log(f"rembg background removal failed: {exc}", "WARNING")
            return False

    def fallback_pillow_cleanup(self, input_path: Path, output_path: Path) -> bool:
        try:
            from PIL import Image, ImageChops, ImageEnhance, ImageOps
        except Exception as exc:
            self.emit_log(f"Pillow cleanup unavailable: {exc}", "WARNING")
            return False

        try:
            with Image.open(input_path) as image:
                image = ImageOps.exif_transpose(image).convert("RGBA")
                image = self.crop_image_border(image, ImageChops)
                if self.config.cleanup_sharpen:
                    image = ImageEnhance.Sharpness(image).enhance(1.2)
                image = ImageEnhance.Contrast(image).enhance(1.05)
                if self.config.cleanup_background == "white":
                    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
                    background.alpha_composite(image)
                    image = background
                image.save(output_path, "PNG")
            self.emit_log("Pillow cleanup completed.", "SUCCESS")
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            self.emit_log(f"Pillow cleanup failed: {exc}", "WARNING")
            return False

    def crop_image_border(self, image, image_chops):
        from PIL import Image

        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if bbox and bbox != (0, 0, image.width, image.height):
            return image.crop(bbox)

        background = image.getpixel((0, 0))
        bg = Image.new(image.mode, image.size, background)
        diff = image_chops.difference(image, bg)
        diff = image_chops.add(diff, diff, 2.0, -24)
        bbox = diff.getbbox()
        if bbox:
            return image.crop(bbox)
        return image

    def upload_image(self, frame: Frame, image_path: Path, product: ProductRow | None = None) -> Frame:
        assert self.page is not None
        product_label = self.slugify(product.product_name) if product else image_path.stem
        product_label = product_label or "product"
        last_error = ""

        for refresh_attempt in range(max(0, self.config.max_page_refresh_retries) + 1):
            self.ensure_browser_alive(force=True)
            frame = self.refresh_frame_reference(frame)
            self.wait_for_flow_render_idle(frame)
            if self.try_direct_product_image_upload(image_path):
                return frame
            diagnostics = self.capture_media_upload_diagnostics(frame)
            self.log_media_upload_diagnostics(diagnostics)
            self.emit_log("Attempting media upload.", "INFO")

            success, last_error = self.try_upload_image_with_dialog_candidates(frame, image_path)
            if success:
                return frame

            self.write_media_failure_artifacts(product_label, diagnostics, suffix="failed")
            if refresh_attempt >= max(0, self.config.max_page_refresh_retries):
                break

            self.emit_log(
                f"Media dialog failed after selector retries ({last_error}). Refreshing page for recovery...",
                "WARNING",
            )
            self.recover_page_after_media_dialog_failure(product_label, product)
            frame = self.wait_for_tool_frame()

        raise RuntimeError(f"Media dialog did not appear after recovery. Last error: {last_error}")

        self.emit_log("Looking for image upload trigger...")
        trigger = self.find_upload_trigger(frame)
        if trigger is None:
            raise RuntimeError("Could not find image upload trigger.")
        self.emit_log("Uploading image through Flow media dialog...")
        dialog = None
        try:
            with self.page.expect_file_chooser(timeout=3_000) as chooser_info:
                trigger.click()
            chooser_info.value.set_files(image_path.as_posix())
            self.emit_log("Attached image via file chooser.")
        except PlaywrightTimeoutError:
            trigger.click()
            self.sleep_ms(1_000)
            dialog = self.wait_for_dialog()
            dialog.locator('input[type="file"]').first.set_input_files(
                image_path.as_posix()
            )
            self.emit_log("Attached image inside media dialog.")

        self.sleep_ms(self.config.extra_wait_after_upload_ms)
        dialog = dialog or self.wait_for_dialog(optional=True)
        if dialog is not None:
            self.select_dialog_image(dialog, image_path.name)
            self.sleep_ms(self.config.extra_wait_before_confirm_ms)
            confirm = self.find_button(dialog, [r"xác nhận", r"confirm", r"done", r"chọn"])
            if confirm is not None:
                confirm.click()
                self.sleep_ms(1_500)
                self.emit_log("Confirmed selected image.")

    def try_direct_product_image_upload(self, image_path: Path) -> bool:
        selectors = [
            'input[data-flow-field="product-upload-input"]',
            '[data-flow-field="product-upload-input"] input[type="file"]',
            '[data-flow-field="product-upload"] input[type="file"]',
        ]
        for selector in selectors:
            input_locator = self.find_in_all_frames(selector, require_visible=False)
            if input_locator is None:
                continue
            try:
                self.emit_log("Uploading product image through direct file input...", "INFO")
                input_locator.set_input_files(image_path.as_posix())
                if self.wait_for_product_image_preview(timeout_ms=max(60_000, self.config.extra_wait_after_upload_ms)):
                    self.emit_log("Product image preview is ready.", "SUCCESS")
                    return True
                self.emit_log("Product image input accepted the file, but preview did not appear.", "WARNING")
                return False
            except Exception as exc:
                self.emit_log(f"Direct product image upload failed for {selector}: {exc}", "WARNING")
        return False

    def wait_for_product_image_preview(self, timeout_ms: int = 30_000) -> bool:
        deadline = time.time() + timeout_ms / 1000
        selectors = [
            '[data-flow-field="product-upload"] img',
            '[data-flow-field="product-upload"] [src^="data:image"]',
            '[data-flow-field="product-upload"] [src^="blob:"]',
        ]
        while time.time() < deadline:
            self.ensure_browser_alive()
            for selector in selectors:
                if self.find_in_all_frames(selector, require_visible=True) is not None:
                    return True
            self.sleep_ms(500)
        return False

    def try_upload_image_with_dialog_candidates(self, frame: Frame, image_path: Path) -> tuple[bool, str]:
        selectors_tried: list[str] = []
        last_error = ""
        for attempt in range(1, max(1, self.config.max_upload_dialog_retries) + 1):
            candidates = self.find_upload_candidates(frame)
            if not candidates:
                last_error = "No upload candidates found."
                self.emit_log(last_error, "WARNING")
                continue

            for selector, locator in candidates:
                selectors_tried.append(selector)
                try:
                    self.emit_log(
                        f"Upload dialog attempt {attempt}/{self.config.max_upload_dialog_retries}: {selector}",
                        "INFO",
                    )
                    if self.is_file_input_locator(locator):
                        locator.set_input_files(image_path.as_posix())
                        self.emit_log("Attached image via file input.", "SUCCESS")
                        self.finish_media_dialog_upload(frame, image_path)
                        return True, ""

                    opened = self.click_upload_candidate_and_wait(frame, locator, attempt)
                    if not opened:
                        last_error = f"No dialog or file input appeared after clicking {selector}."
                        continue
                    self.attach_image_to_open_media_dialog(frame, image_path)
                    self.finish_media_dialog_upload(frame, image_path)
                    return True, ""
                except Exception as exc:
                    last_error = f"{selector}: {exc}"
                    self.emit_log(f"Upload candidate failed: {last_error}", "WARNING")
                    self.ensure_browser_alive(force=True)

        self.emit_log(
            f"Media dialog failed. Selectors tried: {', '.join(dict.fromkeys(selectors_tried)) or 'none'}",
            "WARNING",
        )
        return False, last_error or "All upload candidates exhausted."

    def is_file_input_locator(self, locator: Locator) -> bool:
        with suppress(Exception):
            return bool(
                locator.evaluate(
                    """(el) => el instanceof HTMLInputElement && (el.type || '').toLowerCase() === 'file'"""
                )
            )
        return False

    def find_upload_candidates(self, frame: Frame) -> list[tuple[str, Locator]]:
        candidate_specs = [
            ('input[data-flow-field="product-upload-input"]', 'input[data-flow-field="product-upload-input"]'),
            ('[data-flow-field="product-upload"] input[type="file"]', '[data-flow-field="product-upload"] input[type="file"]'),
            ('[data-flow-field="product-upload"]', '[data-flow-field="product-upload"]'),
            ('[data-flow-action="upload-image"]', '[data-flow-action="upload-image"]'),
            ('button:has-text("Upload")', 'button:has-text("Upload")'),
            ('button:has-text("Add Media")', 'button:has-text("Add Media")'),
            ('button:has-text("Image")', 'button:has-text("Image")'),
        ]
        candidates: list[tuple[str, Locator]] = []
        for label, selector in candidate_specs:
            scopes: list[Page | Frame] = [frame]
            if self.page is not None and self.page != frame:
                scopes.append(self.page)
            for scope in scopes:
                with suppress(Exception):
                    locators = scope.locator(selector)
                    count = min(locators.count(), 8)
                    for index in range(count):
                        locator = locators.nth(index)
                        if label != 'input[type="file"]' and (not locator.is_visible() or locator.is_disabled()):
                            continue
                        candidates.append((label, locator))
        return candidates

    def click_upload_candidate_and_wait(self, frame: Frame, locator: Locator, attempt: int) -> bool:
        assert self.page is not None
        self._pending_file_chooser = None
        try:
            with self.page.expect_file_chooser(timeout=10_000) as chooser_info:
                if attempt == 1:
                    locator.click(timeout=5_000)
                elif attempt == 2:
                    locator.scroll_into_view_if_needed(timeout=5_000)
                    locator.click(timeout=5_000)
                else:
                    locator.evaluate("(el) => el.click()")
            self._pending_file_chooser = chooser_info.value
            return True
        except PlaywrightTimeoutError:
            self._pending_file_chooser = None
        except Exception:
            self._pending_file_chooser = None
            if attempt == 3:
                with suppress(Exception):
                    locator.evaluate("(el) => el.click()")
            else:
                raise
        return self.wait_for_media_dialog_or_input(frame, timeout_ms=10_000)

    def wait_for_media_dialog_or_input(self, frame: Frame, timeout_ms: int = 10_000) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            self.ensure_browser_alive()
            for scope in self.iter_page_and_frame_scopes():
                for selector in ('input[type="file"]', '[role="dialog"]', '[data-flow-dialog="media"]'):
                    with suppress(Exception):
                        locator = scope.locator(selector).first
                        if locator.count() and (selector == 'input[type="file"]' or locator.is_visible()):
                            return True
            self.sleep_ms(300)
        return False

    def attach_image_to_open_media_dialog(self, frame: Frame, image_path: Path) -> None:
        chooser = getattr(self, "_pending_file_chooser", None)
        if chooser is not None:
            chooser.set_files(image_path.as_posix())
            self._pending_file_chooser = None
            self.emit_log("Attached image via file chooser.", "SUCCESS")
            return

        for scope in self.iter_page_and_frame_scopes():
            with suppress(Exception):
                input_locator = scope.locator('input[type="file"]').first
                if input_locator.count():
                    input_locator.set_input_files(image_path.as_posix())
                    self.emit_log("Attached image inside media dialog.", "SUCCESS")
                    return
        raise RuntimeError("Media dialog opened but file input was not found.")

    def finish_media_dialog_upload(self, frame: Frame, image_path: Path) -> None:
        self.sleep_ms(self.config.extra_wait_after_upload_ms)
        dialog = self.wait_for_dialog(optional=True, timeout_ms=10_000)
        if dialog is not None:
            self.select_dialog_image(dialog, image_path.name)
            self.sleep_ms(self.config.extra_wait_before_confirm_ms)
            confirm = self.find_button(dialog, [r"xác nhận", r"xac nhan", r"confirm", r"done", r"chọn", r"chon"])
            if confirm is not None:
                confirm.click()
                self.sleep_ms(1_500)
                self.emit_log("Confirmed selected image.")

    def recover_page_after_media_dialog_failure(self, product_label: str, product: ProductRow | None) -> None:
        assert self.page is not None
        self.ensure_browser_alive(force=True)
        self.page.reload(wait_until="load", timeout=60_000)
        self.sleep_ms(15_000)
        self.capture_debug(f"page-refresh-recovery-{product_label}")
        self.ensure_browser_alive(force=True)
        frame = self.wait_for_tool_frame()
        self.wait_for_product_step_ready(frame)
        if product is not None:
            self.import_preset_if_needed(frame)
            self.upload_website_logo_if_needed(frame)
            self.fill_text_fields(frame, product)
            self.sleep_ms(self.config.extra_wait_after_fill_ms)

    def wait_for_flow_render_idle(self, frame: Frame, timeout_ms: int = 20_000) -> None:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            self.ensure_browser_alive()
            ready = False
            with suppress(Exception):
                ready = bool(frame.evaluate("() => document.readyState === 'complete'"))
            spinner = self.detect_spinner_state(frame)
            if ready and not spinner.get("visible"):
                return
            self.sleep_ms(500)
        self.emit_log("Flow render did not become fully idle before upload; continuing with retries.", "WARNING")

    def detect_spinner_state(self, frame: Frame | None = None) -> dict:
        script = """
            () => {
              const selectors = [
                '[role="progressbar"]',
                '[aria-busy="true"]',
                '[data-loading="true"]',
                '.loading',
                '.spinner',
                '[class*="spinner"]',
                '[class*="loading"]'
              ];
              const found = [];
              for (const selector of selectors) {
                for (const el of Array.from(document.querySelectorAll(selector)).slice(0, 10)) {
                  const style = window.getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  if (style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0) {
                    found.push(selector);
                    break;
                  }
                }
              }
              return { visible: found.length > 0, selectors: found };
            }
        """
        for scope in ([frame] if frame is not None else []) + self.iter_page_and_frame_scopes():
            if scope is None:
                continue
            with suppress(Exception):
                state = scope.evaluate(script)
                if state and state.get("visible"):
                    return state
        return {"visible": False, "selectors": []}

    def capture_media_upload_diagnostics(self, frame: Frame) -> dict:
        current_url = ""
        with suppress(Exception):
            current_url = self.page.url if self.page else ""
        return {
            "url": current_url,
            "flow_step": self.detect_current_flow_step(frame),
            "visible_buttons": self.visible_button_texts(frame),
            "visible_dialogs": self.visible_dialog_texts(frame),
            "spinner_state": self.detect_spinner_state(frame),
        }

    def log_media_upload_diagnostics(self, diagnostics: dict) -> None:
        self.emit_log(f"Media upload URL: {diagnostics.get('url') or '-'}", "INFO")
        self.emit_log(f"Media upload active step: {diagnostics.get('flow_step') or 'unknown'}", "INFO")
        self.emit_log(f"Media upload spinner state: {diagnostics.get('spinner_state')}", "INFO")
        buttons = diagnostics.get("visible_buttons") or []
        dialogs = diagnostics.get("visible_dialogs") or []
        self.emit_log(f"Visible buttons before upload: {' | '.join(buttons[:25]) or 'none'}", "INFO")
        self.emit_log(f"Visible dialogs before upload: {' | '.join(dialogs[:8]) or 'none'}", "INFO")

    def write_media_failure_artifacts(self, product_label: str, diagnostics: dict, suffix: str) -> None:
        label = f"media-dialog-{suffix}-{product_label}"
        self.emit_log(
            "Media dialog failure diagnostics: "
            f"url={diagnostics.get('url') or '-'}; "
            f"step={diagnostics.get('flow_step') or 'unknown'}; "
            f"spinner={diagnostics.get('spinner_state')}; "
            f"buttons={' | '.join((diagnostics.get('visible_buttons') or [])[:25]) or 'none'}",
            "WARNING",
        )
        self.capture_debug(label)
        dom_path = self.config.output_dir / f"{label}.html"
        buttons_path = self.config.output_dir / f"{label}-buttons.json"
        with suppress(Exception):
            assert self.page is not None
            dom_path.write_text(self.page.content(), encoding="utf-8")
        with suppress(Exception):
            buttons_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")

    def detect_current_flow_step(self, frame: Frame) -> str:
        outputs = ("current-step", "step", "flow-step", "multi-clip-status", "video-status")
        for output in outputs:
            value = self.read_flow_output_text_from_scope(frame, output) or self.read_flow_output_text(output)
            if value:
                return value
        if self.frame_has_product_fields(frame):
            return "step-1-product"
        with suppress(Exception):
            if self.find_generate_button(frame) is not None:
                return "generate-video"
        with suppress(Exception):
            if self.find_button_by_selectors_or_text(
                frame,
                selectors=['[data-flow-action="brainstorm-idea"]', '[data-flow-field="brainstorm-idea"]'],
                patterns=[r"brainstorm", r"y tuong"],
            ) is not None:
                return "brainstorm"
        return "unknown"

    def visible_button_texts(self, frame: Frame) -> list[str]:
        script = """
            () => Array.from(document.querySelectorAll('button, [role="button"], a'))
              .filter(el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
              })
              .slice(0, 80)
              .map(el => (el.getAttribute("data-flow-action") || el.getAttribute("data-flow-field") || el.textContent || "").trim())
              .filter(Boolean)
        """
        values: list[str] = []
        for scope in [frame, self.page] if self.page is not None else [frame]:
            with suppress(Exception):
                values.extend(str(item)[:120] for item in scope.evaluate(script))
        return list(dict.fromkeys(values))

    def visible_dialog_texts(self, frame: Frame) -> list[str]:
        script = """
            () => Array.from(document.querySelectorAll('[role="dialog"], [data-flow-dialog]'))
              .filter(el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
              })
              .slice(0, 20)
              .map(el => (el.getAttribute("data-flow-dialog") || el.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 180))
              .filter(Boolean)
        """
        values: list[str] = []
        for scope in [frame, self.page] if self.page is not None else [frame]:
            with suppress(Exception):
                values.extend(str(item) for item in scope.evaluate(script))
        return list(dict.fromkeys(values))

    def refresh_frame_reference(self, frame: Frame) -> Frame:
        with suppress(Exception):
            if frame.is_detached():
                fresh = self._get_tool_frame_or_none()
                if fresh is not None:
                    return fresh
        return frame

    def clean_uploaded_product_image_in_flow(self, frame: Frame, product: ProductRow | None = None) -> None:
        has_enhance_controls = self.has_flow_product_enhance_controls()
        if not self.config.enable_flow_product_cleanup and not has_enhance_controls:
            return

        if not self.has_flow_product_cleanup_controls():
            self.emit_log("Flow product enhancement controls are not present in this tool; skipping Flow enhancement.", "INFO")
            return

        self.emit_log("Waiting for uploaded product image before Flow enhancement...", "INFO")
        product_label = self.slugify(product.product_name) if product else "product"
        product_label = product_label or "product"
        if not self.wait_for_flow_product_cleanup_ready(frame):
            self.capture_debug(f"flow-product-enhance-not-ready-{product_label}")
            self.emit_log(
                "Flow product enhancement controls did not become ready; skipping Flow enhancement and continuing.",
                "WARNING",
            )
            return
        self.ensure_flow_product_cleanup_enabled(frame)

        button = self.find_visible_by_selector(
            frame,
            [
                '[data-flow-action="enhance-product-image"]',
                '[data-flow-field="enhance-product-image"]',
                '[data-flow-action="clean-product-image"]',
                '[data-flow-field="clean-product-image"]',
            ],
            require_enabled=True,
        )
        if button is None:
            self.emit_log("Flow product enhancement button not found; skipping Flow enhancement.", "WARNING")
            return

        before_fingerprint = self.product_upload_image_fingerprint()
        action = "enhance" if self.locator_matches_any_selector(
            button,
            ['[data-flow-action="enhance-product-image"]', '[data-flow-field="enhance-product-image"]'],
        ) else "cleanup"
        self.emit_log(f"Clicking Flow product {action} button...", "INFO")
        try:
            button.scroll_into_view_if_needed()
            button.click()
            if self.wait_for_flow_product_cleanup_success(frame, before_fingerprint=before_fingerprint, action=action):
                self.emit_log(f"Flow product {action} status: success.", "SUCCESS")
            else:
                self.emit_log(f"Flow product {action} did not finish; continuing with uploaded image.", "WARNING")
        except Exception as exc:
            self.emit_log(f"Flow product enhancement skipped after error: {exc}", "WARNING")

    def has_flow_product_cleanup_controls(self) -> bool:
        selectors = [
            '[data-flow-action="enhance-product-image"]',
            '[data-flow-field="enhance-product-image"]',
            '[data-flow-action="clean-product-image"]',
            '[data-flow-field="clean-product-image"]',
            '[data-flow-field="enable-product-cleanup"]',
            '[data-flow-output="product-enhance-status"]',
            '[data-flow-output="product-image-enhance-status"]',
            '[data-flow-output="product-cleanup-status"]',
        ]
        return any(
            self.find_in_all_frames(selector, require_visible=False) is not None
            for selector in selectors
        )

    def has_flow_product_enhance_controls(self) -> bool:
        selectors = [
            '[data-flow-action="enhance-product-image"]',
            '[data-flow-field="enhance-product-image"]',
        ]
        return any(
            self.find_in_all_frames(selector, require_visible=False) is not None
            for selector in selectors
        )

    def wait_for_flow_product_cleanup_ready(self, frame: Frame) -> bool:
        timeout_ms = max(1, self.config.flow_product_cleanup_timeout_ms)
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            self.ensure_browser_alive()
            frame = self.refresh_frame_reference(frame)
            button = self.find_visible_by_selector(
                frame,
                [
                    '[data-flow-action="enhance-product-image"]',
                    '[data-flow-field="enhance-product-image"]',
                    '[data-flow-action="clean-product-image"]',
                    '[data-flow-field="clean-product-image"]',
                ],
                require_enabled=True,
            )
            if button is not None:
                self.emit_log("Uploaded product image is ready for Flow enhancement.", "SUCCESS")
                return True
            self.sleep_ms(500)
        return False

    def ensure_flow_product_cleanup_enabled(self, frame: Frame) -> None:
        toggle = self.find_visible_by_selector(frame, ['[data-flow-field="enable-product-cleanup"]'])
        if toggle is None:
            return
        with suppress(Exception):
            class_name = toggle.get_attribute("class") or ""
            aria_checked = (toggle.get_attribute("aria-checked") or "").lower()
            is_enabled = aria_checked == "true" or "bg-blue" in class_name or "bg-blue-500" in class_name
            if not is_enabled:
                toggle.click()
                self.sleep_ms(400)
                self.emit_log("Enabled Flow product cleanup toggle.", "INFO")

    def wait_for_flow_product_cleanup_success(
        self,
        frame: Frame,
        before_fingerprint: str = "",
        action: str = "cleanup",
    ) -> bool:
        timeout_ms = max(1, self.config.flow_product_cleanup_timeout_ms)
        deadline = time.time() + timeout_ms / 1000
        last_status = ""
        saw_processing = False
        min_wait_until = time.time() + 2.0
        success_states = {"success", "succeeded", "done", "completed", "complete", "thanh cong"}
        processing_states = {"processing", "pending", "running", "loading", "enhancing", "cleaning", "dang xu ly"}
        failure_states = {"failed", "fail", "error", "loi", "that bai"}
        while time.time() < deadline:
            self.ensure_browser_alive()
            frame = self.refresh_frame_reference(frame)
            status = self.read_product_enhancement_status(frame)
            normalized = self.ascii_fold(status.strip().lower())
            if normalized and normalized != last_status:
                self.emit_log(f"Flow product {action} status: {status}", "INFO")
                last_status = normalized
            if normalized in success_states:
                return True
            if normalized in processing_states:
                saw_processing = True
            if normalized in failure_states:
                self.emit_log(f"Flow product {action} failed: {status}", "WARNING")
                return False
            if before_fingerprint:
                current_fingerprint = self.product_upload_image_fingerprint()
                if current_fingerprint and current_fingerprint != before_fingerprint and time.time() >= min_wait_until:
                    self.emit_log(f"Flow product {action} image updated.", "SUCCESS")
                    return True
            button_state = self.product_enhancement_button_state()
            if button_state in {"disabled", "busy"}:
                saw_processing = True
            elif saw_processing and button_state == "ready" and self.wait_for_product_image_preview(timeout_ms=2_000):
                return True
            self.sleep_ms(800)
        self.emit_log(
            f"Flow product {action} did not finish successfully. Last status: {last_status or 'unknown'}",
            "WARNING",
        )
        return False

    def read_product_enhancement_status(self, frame: Frame) -> str:
        for output_name in (
            "product-enhance-status",
            "product-image-enhance-status",
            "product-cleanup-status",
        ):
            status = self.read_flow_output_text_from_scope(frame, output_name)
            if status:
                return status
        return ""

    def product_upload_image_fingerprint(self) -> str:
        selectors = [
            '[data-flow-field="product-upload"] img',
            '[data-flow-field="product-upload"] [src^="data:image"]',
            '[data-flow-field="product-upload"] [src^="blob:"]',
        ]
        for selector in selectors:
            locator = self.find_in_all_frames(selector, require_visible=False)
            if locator is None:
                continue
            with suppress(Exception):
                src = locator.get_attribute("src") or ""
                current_src = locator.get_attribute("currentSrc") or ""
                alt = locator.get_attribute("alt") or ""
                return f"{len(src)}:{src[:80]}:{src[-80:]}:{current_src[:80]}:{current_src[-80:]}:{alt}"
        return ""

    def product_enhancement_button_state(self) -> str:
        locator = self.find_in_all_frames(
            '[data-flow-action="enhance-product-image"], [data-flow-field="enhance-product-image"], [data-flow-action="clean-product-image"], [data-flow-field="clean-product-image"]',
            require_visible=True,
        )
        if locator is None:
            return "missing"
        with suppress(Exception):
            if locator.is_disabled():
                return "disabled"
        with suppress(Exception):
            aria_busy = (locator.get_attribute("aria-busy") or "").strip().lower()
            if aria_busy == "true":
                return "busy"
        with suppress(Exception):
            text = self.ascii_fold((locator.inner_text() or "").strip().lower())
            if re.search(r"loading|processing|enhancing|cleaning|dang xu ly|toi uu", text):
                return "busy"
        return "ready"

    def locator_matches_any_selector(self, locator: Locator, selectors: list[str]) -> bool:
        for selector in selectors:
            with suppress(Exception):
                if locator.evaluate("(el, selector) => el.matches(selector)", selector):
                    return True
        return False

    def read_flow_output_text_from_scope(self, scope: Page | Frame | Locator, output_name: str) -> str:
        selector = f'[data-flow-output="{output_name}"]'
        with suppress(Exception):
            locator = scope.locator(selector).first
            if not locator.count():
                return ""
            for reader in (
                lambda item: item.input_value(),
                lambda item: item.get_attribute("value") or "",
                lambda item: item.inner_text(),
                lambda item: item.text_content() or "",
            ):
                with suppress(Exception):
                    value = (reader(locator) or "").strip()
                    if value:
                        return value
        return ""

    def find_upload_trigger(self, frame: Frame) -> Optional[Locator]:
        for selector in [
            '[data-flow-field="product-upload"]',
            '[data-flow-field="product-upload-input"]',
            '[data-flow-field="product_image"]',
            'button:has-text("Ảnh sản phẩm")',
            'button:has-text("Thêm hình ảnh")',
        ]:
            with suppress(Exception):
                locator = frame.locator(selector).first
                if locator.count() and locator.is_visible():
                    return locator
        for locator in frame.locator("button, div, label").all()[:80]:
            with suppress(Exception):
                if locator.is_visible() and re.search(
                    r"ảnh sản phẩm|thêm hình ảnh|upload image|product image",
                    locator.inner_text(),
                    re.I,
                ):
                    return locator
        return None

    def wait_for_dialog(self, optional: bool = False, timeout_ms: int = 10_000):
        deadline = time.time() + timeout_ms / 1000
        selectors = ('[data-flow-dialog="media"]', '[role="dialog"]')
        while time.time() < deadline:
            self.ensure_browser_alive()
            for scope in self.iter_page_and_frame_scopes():
                for selector in selectors:
                    with suppress(Exception):
                        dialog = scope.locator(selector).last
                        if dialog.count() and dialog.is_visible():
                            return dialog
            self.sleep_ms(300)
        if optional:
            return None
        raise RuntimeError("Media dialog did not appear.")

    def select_dialog_image(self, dialog: Locator, filename: str) -> None:
        self.sleep_ms(1_200)
        options = dialog.locator('[role="option"]')
        with suppress(Exception):
            option = options.filter(has_text=filename).first
            if option.count():
                option.click()
                self.emit_log("Selected uploaded image by filename.")
                return
        with suppress(Exception):
            if options.count():
                options.first.click()
                self.emit_log("Selected first image option in dialog.")

    # ════════════════════════════════════════════════════════
    # LEGACY HELPERS (kept for backwards compatibility)
    # ════════════════════════════════════════════════════════

    def advance_to_generate(self, frame: Frame, max_steps: int = 8) -> None:
        """Legacy: repeatedly click next until generate button appears."""
        for _ in range(max_steps):
            if self.find_generate_button(frame) is not None:
                self.emit_log("Generate button is ready.")
                return
            next_btn = self.find_button(frame, [r"^tiếp$", r"next", r"continue", r"tiếp tục"])
            if next_btn is None:
                return
            next_btn.click()
            self.sleep_ms(1_200)
            self.emit_log("Clicked next step.")

    def wait_for_completion_and_restart(self) -> None:
        """Legacy: wait for any restart-like button and click it."""
        assert self.page is not None
        deadline = time.time() + self.config.wait_timeout_ms / 1000
        while time.time() < deadline:
            btn = self.find_button(
                self.page,
                [r"tạo tiếp sản phẩm mới", r"create next product", r"start over", r"restart"],
            )
            if btn is not None:
                btn.click()
                self.emit_log("Restarted Flow for next product.", "SUCCESS")
                self.sleep_ms(2_500)
                return
            self.sleep_ms(3_000)
        raise TimeoutError("Timed out while waiting for generation completion.")

    # ════════════════════════════════════════════════════════
    # LOW-LEVEL BUTTON FINDER
    # ════════════════════════════════════════════════════════

    def find_button(
        self, scope: Page | Frame | Locator, patterns: list[str]
    ) -> Optional[Locator]:
        regexes = [re.compile(p, re.I) for p in patterns]
        locator = scope.locator("button, [role='button'], a")
        count = min(locator.count(), 120)
        for idx in range(count):
            candidate = locator.nth(idx)
            with suppress(Exception):
                if not candidate.is_visible() or candidate.is_disabled():
                    continue
                text = candidate.inner_text(timeout=500)
                if any(rx.search(text) for rx in regexes):
                    return candidate
        return None

    # ════════════════════════════════════════════════════════
    # UTILITIES
    # ════════════════════════════════════════════════════════

    def capture_debug(self, label: str) -> None:
        if not self.config.save_debug_screenshot_on_error or self.page is None:
            return
        target = self.config.output_dir / f"{label}.png"
        with suppress(Exception):
            self.page.screenshot(path=target.as_posix(), full_page=True)
            self.emit_log(f"Saved debug screenshot: {target}", "WARNING")
        snapshot = self.config.output_dir / f"{label}.dom.html"
        with suppress(Exception):
            frames_html = []
            for idx, frame in enumerate(self.page.frames):
                with suppress(Exception):
                    frames_html.append(
                        f"\n<!-- frame {idx}: {frame.url or '<srcdoc>'} -->\n{frame.content()}"
                    )
            snapshot.write_text("\n".join(frames_html), encoding="utf-8")
            self.emit_log(f"Saved DOM snapshot: {snapshot}", "WARNING")

    @staticmethod
    def sleep_ms(milliseconds: int) -> None:
        time.sleep(milliseconds / 1000)

    @staticmethod
    def find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def resolve_chrome_executable() -> str:
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.as_posix()
        raise FileNotFoundError(
            "Could not find chrome.exe. Install Chrome or update the executable path."
        )

    def launch_chrome_for_cdp(self, port: int) -> None:
        if self.config.chrome_user_data_dir is None:
            return

        source_user_data_dir = self.config.chrome_user_data_dir.expanduser()
        source_user_data_dir.mkdir(parents=True, exist_ok=True)
        user_data_dir = self.prepare_cdp_user_data_dir(source_user_data_dir)
        chrome_executable = self.resolve_chrome_executable()
        args = [
            chrome_executable,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self.config.chrome_profile_directory:
            args.append(f"--profile-directory={self.config.chrome_profile_directory}")
        args.append(self.config.flow_url)

        profile_label = self.config.chrome_profile_directory or user_data_dir.name
        self.emit_log(
            f"Opening Chrome profile {profile_label} with CDP port {port}...",
            "INFO",
        )
        self.chrome_process = subprocess.Popen(args)

    def prepare_cdp_user_data_dir(self, source_user_data_dir: Path) -> Path:
        if not self.should_clone_chrome_profile(source_user_data_dir):
            self.cdp_user_data_dir = source_user_data_dir
            return source_user_data_dir

        profile_directory = self.config.chrome_profile_directory or "Default"
        safe_profile = re.sub(r"[^A-Za-z0-9_.-]+", "-", profile_directory).strip("-")
        clone_root = (self.config.temp_dir / f"chrome-cdp-profile-{safe_profile}").resolve()
        clone_profile_dir = clone_root / profile_directory
        clone_root.mkdir(parents=True, exist_ok=True)

        if (clone_profile_dir / "Preferences").exists():
            self.cdp_user_data_dir = clone_root
            self.emit_log(
                f"Using existing Chrome CDP profile copy: {clone_root}",
                "INFO",
            )
            return clone_root

        self.emit_log(f"Preparing Chrome profile copy from {profile_directory}...", "INFO")
        with suppress(Exception):
            shutil.copy2(source_user_data_dir / "Local State", clone_root / "Local State")
        self.copy_chrome_profile_tree(
            source_user_data_dir / profile_directory,
            clone_profile_dir,
        )
        self.cdp_user_data_dir = clone_root
        self.emit_log("Chrome profile copy is ready for CDP.", "SUCCESS")
        return clone_root

    @staticmethod
    def should_clone_chrome_profile(user_data_dir: Path) -> bool:
        normalized = user_data_dir.resolve().as_posix().lower()
        return normalized.endswith("/google/chrome/user data")

    def copy_chrome_profile_tree(self, source: Path, target: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(f"Chrome profile directory not found: {source}")
        target.mkdir(parents=True, exist_ok=True)
        excluded_dirs = [
            "Cache",
            "Code Cache",
            "GPUCache",
            "DawnCache",
            "DawnGraphiteCache",
            "GrShaderCache",
            "ShaderCache",
            "Media Cache",
            "BrowserMetrics",
            "Crashpad",
            "Crash Reports",
            "OptimizationGuidePredictionModels",
            "Safe Browsing",
            "SafetyTips",
            "Safe Browsing Network",
            "Service Worker\\CacheStorage",
            "Sessions",
        ]
        excluded_files = [
            "SingletonCookie",
            "SingletonLock",
            "SingletonSocket",
            "lockfile",
            "*-journal",
            "*.tmp",
            "*.log",
        ]
        command = [
            "robocopy",
            str(source),
            str(target),
            "/E",
            "/R:1",
            "/W:1",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
            "/NP",
            "/XF",
            *excluded_files,
            "/XD",
            *excluded_dirs,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode > 7:
            error = (result.stderr or result.stdout or "Unknown robocopy error.").strip()
            self.emit_log(
                "Chrome profile copy skipped some locked files. "
                "If the bot Chrome opens logged out, sign in once there and run again.",
                "WARNING",
            )
            self.emit_log(error[-700:], "WARNING")

    @staticmethod
    def is_cdp_ready(port: int) -> bool:
        try:
            response = requests.get(
                f"http://127.0.0.1:{port}/json/version", timeout=1
            )
            return response.ok
        except Exception:
            return False

    def wait_for_cdp_ready(self, port: int, timeout_ms: int = 15_000) -> None:
        deadline = time.time() + timeout_ms / 1000
        last_error = ""
        while time.time() < deadline:
            try:
                response = requests.get(
                    f"http://127.0.0.1:{port}/json/version", timeout=2
                )
                if response.ok:
                    return
            except Exception as exc:
                last_error = str(exc)
            self.sleep_ms(300)
        hint = ""
        if self.config.chrome_user_data_dir:
            hint = (
                " If Chrome is already open with this profile, close that Chrome window "
                "and press Run Bot again."
            )
        raise RuntimeError(
            f"Chrome remote debugging endpoint did not become ready on port {port}. "
            f"{last_error}{hint}"
        )

    def connect_over_cdp_retry(self, port: int, attempts: int = 5):
        assert self.playwright is not None
        last_error = None
        endpoint = f"http://127.0.0.1:{port}"
        for attempt in range(1, attempts + 1):
            try:
                return self.playwright.chromium.connect_over_cdp(endpoint)
            except Exception as exc:
                last_error = exc
                self.emit_log(
                    f"CDP connect retry {attempt}/{attempts} failed: {exc}", "WARNING"
                )
                self.sleep_ms(1_500)
        raise RuntimeError(
            f"Failed to connect to Chrome via CDP at {endpoint}: {last_error}"
        )


# ════════════════════════════════════════════════════════════
# CLI HELPER
# ════════════════════════════════════════════════════════════

def print_products(products: list[ProductRow]) -> None:
    for idx, product in enumerate(products, start=1):
        print(f"{idx}. {product.product_name}")
        print(f"   image: {product.product_image}")
        print(f"   short: {product.short_description[:80]}")
        print(f"   long:  {product.long_description[:80]}")
