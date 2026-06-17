from __future__ import annotations

import base64
import csv
import json
import re
import shutil
import socket
import subprocess
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
    generate_srt,
    get_video_duration_seconds,
    overlay_logo_with_ffmpeg,
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
            image_path = self.download_image(product.product_image, index)
            self.upload_image(frame, image_path)
        self.sleep_ms(self.config.extra_wait_after_fill_ms)

        # ── Step 1 → Step 2 ──────────────────────────────────
        if self.config.auto_next:
            self.emit_log(f"{tag} Step 1 → Step 2 — Nhấn Next Step...")
            self.click_next_step(frame)

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
        if self.config.auto_generate:
            self.emit_log(f"{tag} Step 3 — Nhấn Generate Video...")
            self.click_generate(frame)
            self.emit_log(f"{tag} Step 3 — Đang chờ video render xong...")
            result = self.wait_for_video_completed_and_capture(product, index)
            self.persist_scene_video_result(result)
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

    def handle_scene_settings_mode(self, frame: Frame, product: ProductRow) -> None:
        mode = self.config.scene_mode
        if mode == "skip":
            self.emit_log("Scene mode: skip.", "INFO")
            return
        if mode == "manual_pause":
            self.wait_for_manual_scene_continue()
            return
        if mode == "auto_excel":
            if not self.config.scene_field_keys:
                self.emit_log("No scene columns found. Skipping scene settings.", "WARNING")
                return
            self.emit_log(
                "Scene mode: auto_excel. Filling scene settings from Excel columns.",
                "INFO",
            )
            self.fill_scene_metadata_if_available(frame, product)
            return
        self.emit_log(f"Unknown scene mode '{mode}'. Skipping scene settings.", "WARNING")

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

    def click_brainstorm_idea(self, frame: Frame) -> None:
        """Click the 'Brainstorm Ý Tưởng' button on Step 2."""
        self.emit_log("Looking for brainstorm idea button...")

        # Poll — the button may appear a moment after step transition
        deadline = time.time() + 30
        btn: Optional[Locator] = None
        while time.time() < deadline:
            btn = self.find_button_by_selectors_or_text(
                frame,
                selectors=[
                    '[data-flow-action="brainstorm-idea"]',
                    '[data-flow-field="brainstorm-idea"]',
                ],
                patterns=[
                    r"brainstorm",
                    r"ý tưởng",
                    r"y tuong",
                    r"tạo ý tưởng",
                    r"tao y tuong",
                ],
            )
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
            btn = self.find_generate_button(frame)
            if btn is not None:
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

    # ════════════════════════════════════════════════════════
    # GENERATE VIDEO
    # ════════════════════════════════════════════════════════

    def find_generate_button(self, frame: Frame) -> Optional[Locator]:
        """Return the generate-video button if visible and enabled, else None."""
        return self.find_button_by_selectors_or_text(
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
                r"create video",
                r"\bgenerate\b",
            ],
        )

    def click_generate(self, frame: Frame) -> None:
        self.emit_log("Looking for generate video button...")
        btn = self.find_generate_button(frame)
        if btn is None:
            self.capture_debug("generate-video-not-found")
            raise RuntimeError("Generate video button not found.")
        btn.click()
        self.emit_log("Clicked generate video.", "SUCCESS")

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
        self, product: ProductRow, index: int
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
            "status": "pending",
            "created_at": "",
            "error": "",
        }

        self.emit_log("Polling video result status...")
        while time.time() < deadline:
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
                video_url = video_url_from_data or video_url_fallback
                video_filename = self.read_flow_output_text("video-filename")
                video_download_data = self.read_flow_output_text("video-download-data")
                voiceover_text = self.read_flow_output_text("voiceover")
                caption_text = self.read_flow_output_text("caption")
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
                        "voiceover_text": voiceover_text,
                        "caption_text": caption_text,
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
                        "status": "failed",
                        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "error": f"Video generation failed. Status: {status_text or 'failed'}",
                    }
                )
                self.emit_log(result["error"], "ERROR")
                return result

            self.sleep_ms(3_000)

        result.update(
            {
                "scene_group_id": scene["scene_group_id"],
                "scene_number": int(scene["scene_number"]),
                "scene_total": int(scene["scene_total"]),
                "scene_role": scene["scene_role"],
                "scene_title": scene["scene_title"],
                "status": "failed",
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "error": "Timed out waiting for video generation to complete.",
            }
        )
        self.emit_log(result["error"], "ERROR")
        return result

    def append_video_result_csv(self, row: dict) -> None:
        target = self.config.output_dir / "video_results.csv"
        fieldnames = [
            "run_id",
            "batch_id",
            "index",
            "product_name",
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
            "logo_overlay_status",
            "logo_position",
            "subtitle_enabled",
            "subtitle_file",
            "subtitle_status",
            "subtitle_source",
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

    def persist_scene_video_result(self, row: dict) -> None:
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
                raise RuntimeError(
                    f"Could not download scene video for group {scene_group_id} "
                    f"scene {scene_number} before continuing."
                )
            target.write_bytes(video_bytes)
            batch_raw_target.write_bytes(video_bytes)
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

        if not subtitle_text.strip():
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
            duration = get_video_duration_seconds(current_video)
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
            return self.fetch_url_bytes_in_browser(video_url)

        with suppress(Exception):
            return self.fetch_url_bytes_in_browser(video_url)
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
        selectors = [f'[data-flow-output="{output_name}"]']
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
                    '[data-flow-action="create-next-product"]',
                    '[data-flow-field="create-next-product"]',
                ],
                patterns=[
                    r"tạo tiếp sản phẩm mới",
                    r"tao tiep san pham moi",
                    r"tiếp tục tạo video",
                    r"tiep tuc tao video",
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

        self.ensure_preset_manager_open(frame)
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
            raise RuntimeError("Preset import textarea not found.")

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
            raise RuntimeError("Import preset button not found.")

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

        self.ensure_preset_manager_open(frame)
        self.emit_log("Looking for website logo upload input...")
        for selector in (
            'input[data-flow-field="website-logo-upload-input"]',
            '[data-flow-field="website-logo-upload-input"] input',
            '[data-flow-field="website-logo-upload-input"]',
        ):
            with suppress(Exception):
                input_locator = frame.locator(selector).first
                if input_locator.count():
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
            raise RuntimeError("Website logo upload field not found.")

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
                with suppress(Exception):
                    input_locator = frame.locator(selector).first
                    if input_locator.count():
                        input_locator.set_input_files(logo_path.as_posix())
                        break
            else:
                raise RuntimeError("Website logo file input did not appear.")

        self.emit_log("Uploaded website logo.", "SUCCESS")
        self.sleep_ms(self.config.extra_wait_after_upload_ms)

    def ensure_preset_manager_open(self, frame: Frame) -> None:
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
            return

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
            raise RuntimeError("Preset manager toggle not found.")

        toggle.scroll_into_view_if_needed()
        toggle.click()
        self.emit_log("Opened preset manager toggle.", "SUCCESS")
        self.sleep_ms(500)

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
        self.emit_log(f"Downloaded image to {target}")
        return target

    def upload_image(self, frame: Frame, image_path: Path) -> None:
        assert self.page is not None
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

    def wait_for_dialog(self, optional: bool = False, timeout_ms: int = 15_000):
        assert self.page is not None
        dialog = self.page.locator('[role="dialog"]').last
        try:
            dialog.wait_for(state="visible", timeout=timeout_ms)
            return dialog
        except PlaywrightTimeoutError:
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
