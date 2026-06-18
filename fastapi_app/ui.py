from __future__ import annotations


def render_home(flow_url: str) -> str:
    html = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Google Flow Bot</title>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <style>
    :root {
      --primary: #4f46e5;
      --primary-strong: #4338ca;
      --success: #16a34a;
      --success-subtle: #f0fdf4;
      --success-text: #15803d;
      --warning: #d97706;
      --warning-subtle: #fffbeb;
      --warning-text: #b45309;
      --info-subtle: #eff6ff;
      --info-text: #1d4ed8;
      --error: #dc2626;
      --error-subtle: #fef2f2;
      --border: #e5e7eb;
      --surface: #ffffff;
      --surface-muted: #f9fafb;
      --page: #f9fafb;
      --text: #111827;
      --muted: #6b7280;
      --faint: #9ca3af;
      --radius: 0.75rem;
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; }
    body {
      min-height: 100dvh;
      background: #f9fafb;
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
      overflow: hidden;
    }
    button, input, select { font: inherit; }
    button { border: 0; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 999px; }

    .app-shell { display: flex; flex-direction: column; height: 100dvh; min-height: 0; }
    .topbar {
      height: 3.5rem;
      flex-shrink: 0;
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0 1.25rem;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }
    .brand {
      min-width: 180px;
      display: flex;
      align-items: center;
      gap: 0.625rem;
      font-size: 0.875rem;
      font-weight: 700;
    }
    .brand-mark {
      width: 2rem;
      height: 2rem;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 0.5rem;
      background: var(--primary);
      color: #fff;
    }
    .top-meta { display: flex; gap: 0.5rem; flex-shrink: 0; }
    .pipeline { display: flex; align-items: center; gap: 0.375rem; flex: 1; overflow-x: auto; }
    .pipeline-step {
      white-space: nowrap;
      border-radius: 9999px;
      padding: 0.2rem 0.625rem;
      font-size: 0.7rem;
      font-weight: 600;
      border: 1px solid;
    }
    .pipeline-done {
      background: var(--success-subtle);
      color: var(--success-text);
      border-color: rgba(22, 163, 74, 0.3);
    }
    .pipeline-active { background: var(--primary); color: #fff; border-color: var(--primary); }
    .pipeline-idle { background: #f3f4f6; color: var(--faint); border-color: var(--border); }

    .body-shell { display: flex; flex: 1; min-height: 0; }
    .sidebar {
      width: 250px;
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      background: var(--surface);
      border-right: 1px solid var(--border);
    }
    .sidebar-title {
      padding: 1rem 1.25rem 0.5rem;
      font-size: 0.625rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--faint);
    }
    .nav { display: flex; flex-direction: column; gap: 2px; padding: 0 0.75rem; }
    .nav-btn {
      width: 100%;
      display: flex;
      align-items: center;
      gap: 0.75rem;
      border-radius: 0.5rem;
      padding: 0.625rem 0.75rem;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      text-align: left;
      transition: background 0.15s, color 0.15s;
    }
    .nav-btn:hover { background: #f3f4f6; color: var(--text); }
    .nav-btn.active { background: #eef2ff; color: #3730a3; font-weight: 700; }
    .nav-btn.active svg { color: var(--primary); }
    .nav-label { flex: 1; line-height: 1.3; }
    .sidebar-status { margin-top: auto; border-top: 1px solid var(--border); padding: 1rem; }
    .status-note { background: #eef2ff; border-radius: 0.625rem; padding: 0.75rem; }
    .status-note strong { display: block; font-size: 0.7rem; color: #3730a3; }
    .status-note span { display: block; margin-top: 0.25rem; font-size: 0.65rem; color: var(--muted); }

    main { flex: 1; min-height: 0; overflow-y: auto; padding: 1.5rem; background: #f9fafb; }
    .section { display: none; }
    .section.active { display: flex; flex-direction: column; gap: 1.25rem; }
    .section.log-section.active { height: calc(100dvh - 3.5rem - 3rem); }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
    .section-head h2 { margin: 0; font-size: 1rem; font-weight: 700; }
    .section-head p { margin: 2px 0 0; font-size: 0.875rem; color: var(--muted); }
    .section-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem;
    }
    .soft-card {
      background: rgba(17, 24, 39, 0.03);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem;
    }
    .code-block {
      background: rgba(17, 24, 39, 0.04);
      border-radius: 0.5rem;
      padding: 0.75rem 1rem;
      color: rgba(17, 24, 39, 0.8);
      font-family: Consolas, Monaco, monospace;
      font-size: 0.72rem;
      line-height: 1.7;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .status-bar {
      display: none;
      align-items: center;
      gap: 0.75rem;
      border-radius: var(--radius);
      padding: 0.625rem 1rem;
      font-family: Consolas, Monaco, monospace;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .status-bar.ok {
      display: flex;
      border: 1px solid rgba(22, 163, 74, 0.3);
      background: var(--success-subtle);
      color: var(--success-text);
    }
    .status-bar.err {
      display: flex;
      border: 1px solid rgba(220, 38, 38, 0.25);
      background: var(--error-subtle);
      color: var(--error);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      border-radius: 9999px;
      padding: 0.25rem 0.75rem;
      font-size: 0.75rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .badge-mini { font-size: 0.6rem; padding: 0.15rem 0.5rem; }
    .badge-success { background: var(--success-subtle); color: var(--success-text); }
    .badge-warning { background: var(--warning-subtle); color: var(--warning-text); }
    .badge-muted { background: #f3f4f6; color: var(--muted); }
    .badge-error { background: var(--error-subtle); color: var(--error); }
    .badge-outline { background: transparent; border: 1px solid var(--border); color: #374151; }
    .badge-outline-success {
      background: var(--success-subtle);
      border: 1px solid rgba(22, 163, 74, 0.3);
      color: var(--success-text);
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.375rem;
      min-height: 34px;
      border-radius: 0.5rem;
      padding: 0.375rem 0.875rem;
      font-size: 0.875rem;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.15s, border 0.15s, transform 0.15s, opacity 0.15s;
      border: 1px solid transparent;
      white-space: nowrap;
    }
    .btn:hover { transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .btn-primary { background: var(--primary); color: #fff; border-color: var(--primary); }
    .btn-primary:hover { background: var(--primary-strong); }
    .btn-outline { background: #fff; color: #374151; border-color: var(--border); }
    .btn-outline:hover { background: var(--surface-muted); }
    .btn-danger { background: #fff; color: var(--error); border-color: rgba(220, 38, 38, 0.4); }
    .btn-danger:hover { background: rgba(220, 38, 38, 0.05); }
    .btn-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .floating-run {
      position: fixed;
      top: 5.25rem;
      right: 2rem;
      z-index: 60;
      width: 72px;
      height: 72px;
      border: 0;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, var(--primary), #6d5ef3);
      color: #fff;
      box-shadow: 0 20px 45px rgba(79, 70, 229, 0.32);
      cursor: grab;
      transition: transform 0.16s ease, box-shadow 0.16s ease, opacity 0.16s ease, filter 0.16s ease;
      touch-action: none;
      user-select: none;
    }
    .floating-run:hover:not(:disabled) {
      transform: translateY(-2px) scale(1.02);
      box-shadow: 0 24px 55px rgba(79, 70, 229, 0.38);
    }
    .floating-run:active:not(:disabled),
    .floating-run.dragging {
      cursor: grabbing;
      transform: scale(0.98);
      box-shadow: 0 18px 38px rgba(79, 70, 229, 0.28);
    }
    .floating-run:disabled {
      background: #d1d5db;
      color: #6b7280;
      box-shadow: none;
      cursor: not-allowed;
      opacity: 0.92;
      filter: saturate(0.5);
    }
    .floating-run svg {
      width: 28px;
      height: 28px;
      margin-left: 2px;
    }
    .floating-run-hint {
      position: fixed;
      z-index: 59;
      padding: 0.35rem 0.65rem;
      border-radius: 999px;
      background: rgba(17, 24, 39, 0.92);
      color: #fff;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      pointer-events: none;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 0.14s ease, transform 0.14s ease;
    }
    .floating-run:hover + .floating-run-hint,
    .floating-run:focus-visible + .floating-run-hint {
      opacity: 1;
      transform: translateY(0);
    }

    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .span-all { grid-column: 1 / -1; }
    .form-label {
      display: flex;
      align-items: center;
      gap: 0.375rem;
      margin-bottom: 0.375rem;
      color: var(--muted);
      font-size: 0.75rem;
      font-weight: 700;
    }
    .required { color: #ef4444; }
    .info {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 14px;
      height: 14px;
      border-radius: 999px;
      border: 1px solid #d1d5db;
      color: var(--muted);
      font-size: 10px;
      font-weight: 800;
      cursor: help;
      background: #fff;
    }
    .form-input, .form-select, .form-textarea {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.5rem 0.75rem;
      color: var(--text);
      background: #fff;
      outline: none;
      font-size: 0.875rem;
      transition: border 0.15s, box-shadow 0.15s;
    }
    .form-input:focus, .form-select:focus, .form-textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.12);
    }
    .form-textarea {
      min-height: 260px;
      resize: vertical;
      font-family: Consolas, Monaco, monospace;
      line-height: 1.55;
    }
    .form-select {
      appearance: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 0.75rem center;
      padding-right: 2.5rem;
    }
    .preset-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr); gap: 1rem; align-items: start; }
    .preset-side { display: flex; flex-direction: column; gap: 1rem; }
    .inline-status {
      margin-top: 0.75rem;
      color: var(--muted);
      font-size: 0.75rem;
      line-height: 1.45;
    }
    .inline-status strong { color: var(--text); }
    .preset-summary {
      display: grid;
      gap: 0.5rem;
      margin-top: 0.75rem;
      color: var(--muted);
      font-size: 0.75rem;
    }
    .preset-summary-row {
      display: flex;
      justify-content: space-between;
      gap: 0.75rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.5rem;
    }
    .preset-summary-row:last-child { border-bottom: 0; padding-bottom: 0; }
    .preset-summary-row strong { color: var(--text); font-weight: 700; text-align: right; }
    .file-row { display: flex; align-items: center; gap: 0.75rem; }
    .file-picker {
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: #f3f4f6;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.5rem 0.875rem;
      font-size: 0.875rem;
      font-weight: 700;
      color: #374151;
      white-space: nowrap;
    }
    .file-picker:hover { background: #e5e7eb; }
    .file-name {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      background: var(--surface-muted);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.5rem 0.75rem;
      font-family: Consolas, Monaco, monospace;
      font-size: 0.8rem;
      color: var(--muted);
    }
    .dataset-info {
      margin-top: 0.75rem;
      padding-top: 0.75rem;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.75rem;
      line-height: 1.5;
    }
    .dataset-info strong { color: var(--text); }
    .scene-mode-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.875rem;
    }
    .scene-mode-option {
      display: block;
      cursor: pointer;
    }
    .scene-mode-option input {
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }
    .scene-mode-card {
      height: 100%;
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      background: var(--surface-muted);
      padding: 0.95rem 1rem;
      transition: border 0.15s, background 0.15s, box-shadow 0.15s, opacity 0.15s;
    }
    .scene-mode-option:hover .scene-mode-card {
      border-color: rgba(79, 70, 229, 0.35);
      background: #fff;
    }
    .scene-mode-option input:checked + .scene-mode-card {
      border-color: var(--primary);
      background: #eef2ff;
      box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.12);
    }
    .scene-mode-option input:disabled + .scene-mode-card {
      opacity: 0.55;
      cursor: not-allowed;
      background: #f3f4f6;
    }
    .scene-mode-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      margin-bottom: 0.45rem;
      font-size: 0.82rem;
      font-weight: 800;
      color: var(--text);
    }
    .scene-mode-desc {
      color: var(--muted);
      font-size: 0.75rem;
      line-height: 1.5;
    }
    .scene-mode-status {
      margin-top: 0.875rem;
      padding: 0.875rem 1rem;
      border-radius: 0.75rem;
      border: 1px solid var(--border);
      background: var(--surface-muted);
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.5;
    }
    .scene-mode-status.is-warning {
      border-color: rgba(217, 119, 6, 0.28);
      background: var(--warning-subtle);
      color: var(--warning-text);
    }
    .scene-mode-status.is-paused {
      border-color: rgba(79, 70, 229, 0.22);
      background: #eef2ff;
      color: #3730a3;
    }

    .log-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      flex-shrink: 0;
    }
    .filter-tabs {
      width: fit-content;
      display: flex;
      gap: 2px;
      padding: 0.25rem;
      border-radius: 0.5rem;
      background: #f3f4f6;
      flex-shrink: 0;
    }
    .filter-tab {
      border-radius: 0.375rem;
      padding: 0.25rem 0.75rem;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-size: 0.75rem;
      font-weight: 700;
      transition: background 0.15s, color 0.15s, box-shadow 0.15s;
    }
    .filter-tab:hover:not(.active) { color: var(--text); }
    .filter-tab.active { background: #fff; color: var(--text); box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
    .log-box {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      background: rgba(249, 250, 251, 0.8);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.75rem;
    }
    .log-line {
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      padding: 0.25rem 0.5rem;
      border-radius: 0.375rem;
      font-family: Consolas, Monaco, monospace;
      font-size: 0.7rem;
      line-height: 1.45;
    }
    .log-line:hover { background: #fff; }
    .log-time { color: var(--faint); white-space: nowrap; }
    .log-msg { color: #374151; word-break: break-word; }
    .log-badge {
      border-radius: 0.25rem;
      padding: 0.1rem 0.375rem;
      font-size: 0.65rem;
      font-weight: 800;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .log-badge-INFO { background: var(--info-subtle); color: var(--info-text); }
    .log-badge-SUCCESS { background: var(--success-subtle); color: var(--success-text); }
    .log-badge-WARNING { background: var(--warning-subtle); color: var(--warning-text); }
    .log-badge-ERROR { background: var(--error-subtle); color: var(--error); }
    .postprocess-panel {
      display: grid;
      gap: 0.625rem;
      border: 1px solid var(--border);
      border-radius: 0.625rem;
      background: #ffffff;
      padding: 0.75rem;
    }
    .postprocess-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      font-size: 0.75rem;
      color: var(--muted);
    }
    .postprocess-title {
      color: var(--text);
      font-weight: 800;
      font-size: 0.875rem;
    }
    .postprocess-track {
      height: 0.5rem;
      overflow: hidden;
      border-radius: 999px;
      background: #eef2ff;
      border: 1px solid #e0e7ff;
    }
    .postprocess-fill {
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #2563eb, #16a34a);
      transition: width 0.35s ease;
    }
    .postprocess-steps {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 0.375rem;
    }
    .postprocess-step {
      min-width: 0;
      border-radius: 0.375rem;
      border: 1px solid var(--border);
      background: #f9fafb;
      color: var(--muted);
      padding: 0.35rem 0.45rem;
      text-align: center;
      font-size: 0.68rem;
      font-weight: 800;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .postprocess-step.active { border-color: #93c5fd; background: #eff6ff; color: #1d4ed8; }
    .postprocess-step.done { border-color: #bbf7d0; background: #f0fdf4; color: #15803d; }
    .empty {
      display: flex;
      min-height: 180px;
      align-items: center;
      justify-content: center;
      color: var(--faint);
      font-size: 0.875rem;
    }
    .mapping-preview { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }
    .mapping-preview th, .mapping-preview td { border-bottom: 1px solid var(--border); padding: 8px; vertical-align: top; }
    .mapping-preview th { color: var(--primary); white-space: nowrap; }
    .results-layout {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 1rem;
      min-height: 0;
      flex: 1;
    }
    .batch-list {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      max-height: calc(100dvh - 15rem);
      overflow-y: auto;
    }
    .batch-card {
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      background: var(--surface);
      padding: 0.9rem;
      cursor: pointer;
      transition: border 0.15s, box-shadow 0.15s, transform 0.15s;
    }
    .batch-card:hover { transform: translateY(-1px); box-shadow: 0 10px 24px rgba(17,24,39,0.06); }
    .batch-card.active {
      border-color: rgba(79, 70, 229, 0.35);
      box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.1);
      background: #eef2ff;
    }
    .batch-card-title {
      margin: 0 0 0.35rem;
      font-size: 0.84rem;
      font-weight: 800;
      color: var(--text);
      word-break: break-word;
    }
    .batch-card-meta {
      color: var(--muted);
      font-size: 0.73rem;
      line-height: 1.45;
    }
    .batch-detail {
      display: flex;
      flex-direction: column;
      gap: 1rem;
      min-width: 0;
    }
    .batch-summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .batch-summary-meta {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      align-items: center;
    }
    .video-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1rem;
    }
    .video-card {
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      overflow: hidden;
      background: var(--surface);
    }
    .video-card video {
      width: 100%;
      aspect-ratio: 9 / 16;
      background: #111827;
      display: block;
      object-fit: contain;
    }
    .video-card-body {
      padding: 0.9rem;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }
    .video-card-title {
      margin: 0;
      font-size: 0.84rem;
      font-weight: 800;
      color: var(--text);
      line-height: 1.4;
    }
    .video-card-meta {
      color: var(--muted);
      font-size: 0.73rem;
      line-height: 1.5;
      word-break: break-word;
    }
    .video-card-actions {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .pulse { animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

    .swal2-popup { border-radius: 0.75rem !important; }
    .swal2-html-container { color: var(--muted) !important; }

    @media (max-width: 900px) {
      body { overflow: auto; }
      .app-shell { min-height: 100dvh; height: auto; }
      .topbar { height: auto; align-items: flex-start; flex-wrap: wrap; padding: 0.875rem; }
      .brand { min-width: 0; }
      .top-meta { margin-left: auto; }
      .pipeline { order: 3; flex-basis: 100%; }
      .body-shell { flex-direction: column; }
      .sidebar { width: 100%; border-right: 0; border-bottom: 1px solid var(--border); }
      .nav { flex-direction: row; overflow-x: auto; padding-bottom: 0.75rem; }
      .nav-btn { min-width: 175px; }
      .sidebar-status { display: none; }
      main { padding: 1rem; }
      .section-head, .log-toolbar, .file-row { align-items: flex-start; flex-direction: column; }
      .section.log-section.active { height: auto; min-height: 520px; }
      .form-grid { grid-template-columns: 1fr; }
      .preset-grid { grid-template-columns: 1fr; }
      .scene-mode-grid { grid-template-columns: 1fr; }
      .results-layout { grid-template-columns: 1fr; }
      .batch-list { max-height: none; }
      .span-all { grid-column: auto; }
      .btn-row { align-items: stretch; }
      .btn-row .btn { width: 100%; }
    }
  </style>
</head>
<body>
<div class="app-shell">
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect><path d="M2 14h2M20 14h2M15 13v2M9 13v2"></path>
        </svg>
      </span>
      <span>Google Flow Bot</span>
    </div>
    <div id="pipeline" class="pipeline"></div>
    <div class="top-meta">
      <span class="badge badge-outline">LOCAL UI</span>
      <span class="badge badge-outline-success" id="cdp-chip">CDP 9222</span>
    </div>
  </header>

  <div class="body-shell">
    <aside class="sidebar">
      <div class="sidebar-title">Sections</div>
      <nav class="nav">
        <button class="nav-btn active" onclick="switchSection('upload', this)" id="nav-upload">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" x2="12" y1="3" y2="15"></line></svg>
          <span class="nav-label">Upload Excel / CSV</span>
          <span class="badge badge-mini badge-muted" id="dataset-chip">No file</span>
        </button>
        <button class="nav-btn" onclick="switchSection('batch', this)" id="nav-batch">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg>
          <span class="nav-label">Batch Settings</span>
          <span class="badge badge-mini badge-muted" id="nav-batch-badge">Idle</span>
        </button>
        <button class="nav-btn" onclick="switchSection('mapping', this)" id="nav-mapping">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="6" x2="6" y1="3" y2="15"></line><circle cx="18" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><path d="M18 9a9 9 0 0 1-9 9"></path></svg>
          <span class="nav-label">Field Mapping</span>
          <span class="badge badge-mini badge-muted" id="mapping-chip">Not ready</span>
        </button>
        <button class="nav-btn" onclick="switchSection('preset', this)" id="nav-preset">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6"></path><path d="M8 13h8"></path><path d="M8 17h5"></path></svg>
          <span class="nav-label">Preset Import</span>
          <span class="badge badge-mini badge-muted" id="preset-chip">Optional</span>
        </button>
        <button class="nav-btn" onclick="switchSection('log', this)" id="nav-log">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" x2="20" y1="19" y2="19"></line></svg>
          <span class="nav-label">Realtime Log</span>
        </button>
        <button class="nav-btn" onclick="switchSection('results', this); loadVideoBatches(selectedBatchId)" id="nav-results">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="15" height="14" rx="2"></rect><path d="m17 7 5 3v4l-5 3z"></path></svg>
          <span class="nav-label">Video Storage</span>
          <span class="badge badge-mini badge-muted" id="results-chip">0 batch</span>
        </button>
      </nav>
      <div class="sidebar-status">
        <div class="status-note">
          <strong id="pipeline-note-title">Waiting for Excel</strong>
          <span id="pipeline-note">Upload a file to start.</span>
        </div>
      </div>
    </aside>

    <main>
      <section id="section-upload" class="section active">
        <div class="section-head">
          <div>
            <h2>Upload Excel / CSV</h2>
            <p>Upload product data to prepare the bot run.</p>
          </div>
          <span class="badge badge-muted" id="upload-status-badge">No dataset</span>
        </div>

        <div class="soft-card">
          <div class="form-label" style="text-transform:uppercase;letter-spacing:.08em;color:var(--faint);">
            Chrome profile
          </div>
          <div class="code-block">Bot sẽ tự mở Chrome bằng Profile 12 khi bấm Run Bot.</div>
        </div>

        <div id="status-bar" class="status-bar"></div>

        <div class="section-card">
          <div class="file-row">
            <label class="file-picker">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M8 13h2M8 17h8M10 9H8"></path></svg>
              Choose file
              <input type="file" id="file" accept=".xlsx,.xls,.csv" style="display:none"/>
            </label>
            <span id="file-name" class="file-name">No file selected</span>
          </div>
          <div class="btn-row" style="margin-top:.75rem">
            <button class="btn btn-primary" onclick="uploadFile()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
              Upload File
            </button>
          </div>
          <div id="dataset-history-container" style="margin-top:1.25rem; border-top:1px solid var(--border); padding-top:1.25rem;">
            <label class="form-label" for="dataset-history">Hoặc chọn file đã upload trước đó:</label>
            <div class="file-row" style="margin-top:0.5rem">
              <select class="form-select" id="dataset-history" style="flex:1">
                <option value="">Đang tải...</option>
              </select>
              <button class="btn btn-outline" onclick="selectHistoryDataset()">Chọn file này</button>
            </div>
          </div>
          <div id="dataset-info" class="dataset-info">Dataset info will appear after upload.</div>
        </div>
      </section>

      <section id="section-batch" class="section">
        <div class="section-head">
          <div>
            <h2>Batch Settings</h2>
            <p>Configure bot execution parameters.</p>
          </div>
          <span class="badge badge-muted" id="run-status-badge">IDLE</span>
        </div>

        <div class="section-card">
          <div class="form-grid">
            <div class="span-all">
              <label class="form-label" for="dataset-id">Dataset ID <span class="info" title="ID của file Excel đã upload.">i</span></label>
              <input class="form-input" id="dataset-id" placeholder="Auto filled after upload"/>
            </div>
            <div>
              <label class="form-label" for="cdp-port">CDP Port <span class="info" title="Port Chrome remote debugging, thường là 9222.">i</span></label>
              <input class="form-input" id="cdp-port" type="number" value="9222"/>
            </div>
            <div>
              <label class="form-label" for="start">Start Product <span class="info" title="Sản phẩm bắt đầu chạy, tính từ 1.">i</span></label>
              <input class="form-input" id="start" type="number" value="1" min="1"/>
            </div>
            <div>
              <label class="form-label" for="count">Product Count <span class="info" title="Số lượng sản phẩm muốn chạy trong batch.">i</span></label>
              <input class="form-input" id="count" type="number" value="1" min="1"/>
            </div>
            <div>
              <label class="form-label" for="slow-mo">Slow Mo <span class="info" title="Độ trễ giữa các thao tác bot.">i</span></label>
              <input class="form-input" id="slow-mo" type="number" value="400" min="0"/>
            </div>
            <div>
              <label class="form-label" for="wait-timeout">Video Timeout <span class="info" title="Thời gian tối đa đợi video tạo xong.">i</span></label>
              <input class="form-input" id="wait-timeout" type="number" value="180" min="30"/>
            </div>
            <div>
              <label class="form-label" for="video-model">Video Model</label>
              <select class="form-input" id="video-model">
                <option value="auto">Auto (Recommended)</option>
                <option value="Omni Flash">Omni Flash</option>
                <option value="Veo 3.1 - Lite" selected>Veo 3.1 - Lite</option>
                <option value="Veo 3.1 - Fast">Veo 3.1 - Fast</option>
                <option value="Veo 3.1 - Quality">Veo 3.1 - Quality</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="aspect-ratio">Aspect Ratio</label>
              <select class="form-input" id="aspect-ratio" data-ui-field="aspect-ratio">
                <option value="9:16" selected>9:16</option>
                <option value="16:9">16:9</option>
                <option value="1:1">1:1</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="multi-clip-mode">Multi-Clip Mode</label>
              <select class="form-input" id="multi-clip-mode" data-ui-field="multi-clip-mode">
                <option value="auto" selected>auto</option>
                <option value="off">off</option>
                <option value="2">2 clips</option>
                <option value="3">3 clips</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="scene-builder-mode">Scene Builder Mode</label>
              <select class="form-input" id="scene-builder-mode" data-ui-field="scene-builder-mode">
                <option value="native_flow" selected>native_flow</option>
                <option value="bot_merge">bot_merge</option>
                <option value="off">off</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="target-final-duration">Target Final Duration</label>
              <select class="form-input" id="target-final-duration" data-ui-field="target-final-duration">
                <option value="15">15s</option>
                <option value="20" selected>20s</option>
                <option value="24">24s</option>
                <option value="30">30s</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="download-mode">Download Mode</label>
              <select class="form-input" id="download-mode" data-ui-field="download-mode">
                <option value="capture_only">capture_only</option>
                <option value="save_local" selected>save_local</option>
                <option value="save_local_and_zip">save_local_and_zip</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="max-generate-retries">Max Generate Retries</label>
              <input class="form-input" id="max-generate-retries" data-ui-field="max-generate-retries" type="number" value="1" min="0" max="5"/>
            </div>
            <div class="span-all" style="display:flex;align-items:center;gap:.5rem;margin-top:.25rem">
              <input type="checkbox" id="continue-on-error" data-ui-field="continue-on-error"/>
              <label for="continue-on-error" style="color: var(--text); font-size: 0.875rem; cursor: pointer; user-select: none;">Continue on error</label>
            </div>
            <div class="span-all" style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.25rem;">
              <input type="checkbox" id="auto-download-zip" checked/>
              <label for="auto-download-zip" style="color: var(--text); font-size: 0.875rem; cursor: pointer; user-select: none;">Tự động tải file ZIP chứa tất cả video (đã sắp xếp theo folder) khi batch hoàn thành</label>
            </div>
            <div>
              <label class="form-label" for="download-resolution">Download Resolution</label>
              <select class="form-input" id="download-resolution">
                <option value="1080p" selected>1080p</option>
                <option value="720p">720p</option>
                <option value="1440p">1440p</option>
                <option value="2160p">2160p</option>
                <option value="original">Original</option>
              </select>
            </div>
            <div class="span-all" style="display:flex;align-items:center;gap:.5rem;margin-top:.25rem">
              <input type="checkbox" id="enable-subtitles" checked/>
              <label for="enable-subtitles" style="color: var(--text); font-size: 0.875rem; cursor: pointer; user-select: none;">Generate subtitles</label>
            </div>
            <div>
              <label class="form-label" for="subtitle-source">Subtitle Source</label>
              <select class="form-input" id="subtitle-source">
                <option value="voiceover" selected>voiceover</option>
                <option value="caption">caption</option>
                <option value="final_prompt">final prompt</option>
                <option value="short_description">short description</option>
                <option value="auto">auto fallback</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="subtitle-font-size">Subtitle Font Size</label>
              <input class="form-input" id="subtitle-font-size" type="number" value="18" min="10" max="48"/>
            </div>
            <div class="span-all" style="display:flex;align-items:center;gap:.5rem;margin-top:.25rem">
              <input type="checkbox" id="enable-product-image-cleanup" data-ui-field="enable-product-image-cleanup" checked/>
              <label for="enable-product-image-cleanup" style="color: var(--text); font-size: 0.875rem; cursor: pointer; user-select: none;">Product Image Cleanup</label>
            </div>
            <div>
              <label class="form-label" for="cleanup-mode">Cleanup Mode</label>
              <select class="form-input" id="cleanup-mode" data-ui-field="cleanup-mode">
                <option value="auto" selected>auto</option>
                <option value="remove_background">remove_background</option>
                <option value="sharpen_only">sharpen_only</option>
                <option value="none">none</option>
              </select>
            </div>
            <div class="span-all" style="display:flex;align-items:center;gap:.5rem;margin-top:.25rem">
              <input type="checkbox" id="enable-logo-overlay" data-ui-field="enable-logo-overlay" checked/>
              <label for="enable-logo-overlay" style="color: var(--text); font-size: 0.875rem; cursor: pointer; user-select: none;">Enable Logo Overlay</label>
            </div>
            <div class="span-all">
              <label class="form-label" for="logo-file-path">Logo File Path</label>
              <input class="form-input" id="logo-file-path" data-ui-field="logo-file-path" placeholder="Path to logo image; auto-filled after Upload Logo"/>
            </div>
            <div>
              <label class="form-label" for="logo-position">Logo Position</label>
              <select class="form-input" id="logo-position" data-ui-field="logo-position">
                <option value="top-left">top-left</option>
                <option value="top-right" selected>top-right</option>
                <option value="bottom-left">bottom-left</option>
                <option value="bottom-right">bottom-right</option>
              </select>
            </div>
            <div>
              <label class="form-label" for="logo-width-percent">Logo Width Percent</label>
              <input class="form-input" id="logo-width-percent" data-ui-field="logo-width-percent" type="number" value="12" min="5" max="25"/>
            </div>
            <div>
              <label class="form-label" for="logo-margin">Logo Margin</label>
              <input class="form-input" id="logo-margin" data-ui-field="logo-margin" type="number" value="32" min="0"/>
            </div>
            <div class="span-all" style="display:flex;align-items:center;gap:.5rem;margin-top:.25rem">
              <input type="checkbox" id="auto-logo-overlay-after-batch" data-ui-field="auto-logo-overlay-after-batch"/>
              <label for="auto-logo-overlay-after-batch" style="color: var(--text); font-size: 0.875rem; cursor: pointer; user-select: none;">Auto logo overlay after batch</label>
            </div>
            <div class="span-all">
              <div id="logo-overlay-preview" style="position:relative;aspect-ratio:16/9;max-width:420px;border-radius:8px;overflow:hidden;background:linear-gradient(135deg,#111827,#334155);border:1px solid var(--border);">
                <div style="position:absolute;inset:0;background:linear-gradient(90deg,rgba(255,255,255,.08) 1px,transparent 1px),linear-gradient(0deg,rgba(255,255,255,.08) 1px,transparent 1px);background-size:36px 36px;"></div>
                <div style="position:absolute;left:5%;bottom:8%;color:white;font-weight:800;font-size:.8rem;text-shadow:0 1px 8px rgba(0,0,0,.6)">Video demo</div>
                <div id="logo-overlay-preview-mark" style="position:absolute;display:flex;align-items:center;justify-content:center;aspect-ratio:2.4/1;background:rgba(255,255,255,.94);color:#111827;border:1px solid rgba(15,23,42,.15);font-weight:900;font-size:.68rem;border-radius:4px;box-shadow:0 4px 18px rgba(0,0,0,.25);">LOGO</div>
              </div>
            </div>
          </div>
        </div>

        <div class="section-card">
          <div class="section-head" style="margin-bottom:.875rem">
            <div>
              <h2 style="font-size:.95rem">Scene Settings Mode</h2>
              <p>Chọn cách bot xử lý bước Scene Settings sau khi bấm next-step.</p>
            </div>
            <span class="badge badge-muted" id="scene-mode-badge">Skip</span>
          </div>

          <div class="scene-mode-grid" data-ui-field="scene-mode">
            <label class="scene-mode-option" data-ui-option="scene-mode-manual-pause">
              <input type="radio" name="scene-mode" value="manual_pause"/>
              <div class="scene-mode-card">
                <div class="scene-mode-title">
                  <span>Manual Pause</span>
                  <span class="badge badge-mini badge-outline">Pause</span>
                </div>
                <div class="scene-mode-desc">Bot dừng tại Scene Settings để bạn tự chỉnh trên Flow, rồi tiếp tục khi bấm Continue / Done.</div>
              </div>
            </label>

            <label class="scene-mode-option" data-ui-option="scene-mode-skip">
              <input type="radio" name="scene-mode" value="skip" checked/>
              <div class="scene-mode-card">
                <div class="scene-mode-title">
                  <span>Skip Scene Settings</span>
                  <span class="badge badge-mini badge-muted">Default</span>
                </div>
                <div class="scene-mode-desc">Bot bỏ qua toàn bộ scene fields và đi thẳng từ next-step sang brainstorm.</div>
              </div>
            </label>

            <label class="scene-mode-option" data-ui-option="scene-mode-auto-excel">
              <input type="radio" name="scene-mode" value="auto_excel"/>
              <div class="scene-mode-card">
                <div class="scene-mode-title">
                  <span>Auto Fill From Excel</span>
                  <span class="badge badge-mini badge-outline">Excel</span>
                </div>
                <div class="scene-mode-desc">Bot chỉ fill scene fields nếu Excel có cột scene được map sẵn; field nào bị che sẽ log warning và bỏ qua.</div>
              </div>
            </label>
          </div>

          <div id="scene-mode-status" class="scene-mode-status">Scene mode mặc định là Skip. Bot sẽ bỏ qua Scene Settings cho tới khi bạn đổi chế độ.</div>

          <div class="btn-row" style="margin-top:.875rem; display:none">
            <button
              class="btn btn-primary"
              id="continue-scene-btn"
              data-ui-action="continue-after-scene-manual"
              onclick="continueAfterSceneManual()"
              disabled
            >
              Continue / Done
            </button>
          </div>
        </div>

        <div class="btn-row">
          <button class="btn btn-danger" onclick="stopStream()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="18" height="18" rx="2"></rect></svg>
            Stop Stream
          </button>
        </div>
      </section>

      <section id="section-mapping" class="section">
        <div class="section-head">
          <div>
            <h2>Mapping Excel → Flow Step 1</h2>
            <p>Chọn cột Excel cho từng field Step 1. Mapping đã lưu sẽ được gửi kèm khi chạy batch.</p>
          </div>
          <span class="badge badge-muted" id="mapping-status-badge">Not ready</span>
        </div>

        <div class="section-card">
          <div id="mapping-fields" class="form-grid"></div>
        </div>

        <div class="btn-row">
          <button class="btn btn-outline" onclick="autoMap()">Auto Map</button>
          <button class="btn btn-primary" onclick="saveMapping()">Save Mapping</button>
          <button class="btn btn-outline" onclick="resetMapping()">Reset Mapping</button>
          <button class="btn btn-outline" onclick="previewMapping()">Preview Mapping</button>
        </div>
      </section>

      <section id="section-preset" class="section">
        <div class="section-head">
          <div>
            <h2>Preset & Logo Step 1</h2>
            <p>Import preset JSON bằng file hoặc paste trực tiếp, kèm logo website để bot fill ở Step 1.</p>
          </div>
          <span class="badge badge-muted" id="preset-status-badge">Optional</span>
        </div>

        <div class="preset-grid">
          <div class="section-card">
            <label class="form-label" for="preset-json">
              Preset JSON
              <span class="info" title="Dán JSON preset hoặc import từ file .json. Bot sẽ fill vào Flow Step 1.">i</span>
            </label>
            <textarea class="form-textarea" id="preset-json" spellcheck="false" placeholder='{"preset_version":"1.2","preset_name":"..."}'></textarea>
            <div class="btn-row" style="margin-top:.75rem">
              <button class="btn btn-primary" onclick="validatePresetJson(true)">Validate Preset</button>
              <button class="btn btn-outline" onclick="formatPresetJson()">Format JSON</button>
              <button class="btn btn-outline" onclick="clearPresetJson()">Clear Preset</button>
            </div>
            <div id="preset-status" class="inline-status">Preset là optional. Khi có JSON hợp lệ, bot sẽ import vào Flow trước khi điền sản phẩm.</div>
            <div id="preset-summary" class="preset-summary"></div>
          </div>

          <div class="preset-side">
            <div class="section-card">
              <label class="form-label" for="preset-file">
                Import preset file
                <span class="info" title="Chọn file .json để tự động đưa nội dung vào ô Preset JSON.">i</span>
              </label>
              <div class="file-row">
                <label class="file-picker">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M12 18v-6"></path><path d="m9 15 3 3 3-3"></path></svg>
                  Choose JSON
                  <input type="file" id="preset-file" accept=".json,application/json" style="display:none"/>
                </label>
                <span id="preset-file-name" class="file-name">No preset file</span>
              </div>
            </div>

            <div class="section-card">
              <div class="section-head" style="margin-bottom:.75rem">
                <div>
                  <h2 style="font-size:.9rem">Website Logo</h2>
                  <p>Upload logo local để bot đưa vào Flow Step 1.</p>
                </div>
                <span class="badge badge-muted" id="logo-status-badge">No logo</span>
              </div>
              <label class="form-label" for="logo-file">
                Logo file
                <span class="info" title='Bot sẽ dùng data-flow-field="website-logo-upload-input" để upload file này.'>i</span>
              </label>
              <div class="file-row">
                <label class="file-picker">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="3" rx="2"></rect><circle cx="9" cy="9" r="2"></circle><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"></path></svg>
                  Choose logo
                  <input type="file" id="logo-file" accept="image/png,image/jpeg,image/webp,image/gif" style="display:none"/>
                </label>
                <span id="logo-file-name" class="file-name">No logo selected</span>
              </div>
              <div class="btn-row" style="margin-top:.75rem">
                <button class="btn btn-primary" onclick="uploadLogo()">Upload Logo</button>
                <button class="btn btn-outline" onclick="clearLogo()">Clear Logo</button>
              </div>
              <div id="logo-status" class="inline-status">Logo là optional. Nếu chọn file mà chưa upload, nút Run sẽ tự upload trước.</div>
            </div>
          </div>
        </div>
      </section>

      <section id="section-log" class="section log-section">
        <div class="log-toolbar">
          <div>
            <h2 style="margin:0;font-size:1rem">Realtime Log</h2>
            <p style="margin:2px 0 0;color:var(--muted);font-size:.875rem">Live output from bot execution.</p>
          </div>
          <div class="btn-row">
            <button class="btn btn-outline" onclick="copyLog()">Copy Log</button>
            <button class="btn btn-outline" onclick="downloadLog()">Download Log</button>
            <button class="btn btn-danger" onclick="clearLog()">Clear Log</button>
          </div>
        </div>
        <div class="filter-tabs" id="log-filter">
          <button class="filter-tab active" data-filter="ALL" onclick="setLogFilter('ALL', this)">All</button>
          <button class="filter-tab" data-filter="INFO" onclick="setLogFilter('INFO', this)">Info</button>
          <button class="filter-tab" data-filter="SUCCESS" onclick="setLogFilter('SUCCESS', this)">Success</button>
          <button class="filter-tab" data-filter="WARNING" onclick="setLogFilter('WARNING', this)">Warning</button>
          <button class="filter-tab" data-filter="ERROR" onclick="setLogFilter('ERROR', this)">Error</button>
        </div>
        <div class="postprocess-panel" id="postprocess-panel">
          <div class="postprocess-head">
            <div>
              <div class="postprocess-title" id="postprocess-title">Post-processing ready</div>
              <div id="postprocess-detail">Waiting for generated videos.</div>
            </div>
            <strong id="postprocess-percent">0%</strong>
          </div>
          <div class="postprocess-track"><div class="postprocess-fill" id="postprocess-fill"></div></div>
          <div class="postprocess-steps" id="postprocess-steps"></div>
        </div>
        <div id="log-box" class="log-box"><div class="empty">Waiting for batch...</div></div>
      </section>

      <section id="section-results" class="section">
        <div class="section-head">
          <div>
            <h2>Batch Video Storage</h2>
            <p>Video đã lưu theo từng batch, có preview, tải lẻ và tải cả batch ZIP.</p>
          </div>
          <span class="badge badge-muted" id="results-status-badge">No batch</span>
        </div>

        <div class="results-layout">
          <div class="section-card">
            <div class="batch-summary" style="margin-bottom:.75rem">
              <strong style="font-size:.85rem">Saved batches</strong>
              <button class="btn btn-outline" onclick="loadVideoBatches(selectedBatchId)">Refresh</button>
            </div>
            <div id="batch-list" class="batch-list"><div class="empty">No saved batch yet.</div></div>
          </div>

          <div class="batch-detail">
            <div class="section-card">
              <div id="batch-detail-head" class="batch-summary">
                <div>
                  <h2 style="font-size:.95rem;margin:0 0 .25rem">Select a batch</h2>
                  <div class="batch-card-meta">Chọn batch bên trái để xem video đã lưu.</div>
                </div>
                <div id="batch-detail-actions" class="btn-row"></div>
              </div>
            </div>

            <div id="batch-detail-grid" class="video-grid"></div>
          </div>
        </div>
      </section>
    </main>
  </div>
</div>

<button id="floating-run-btn" class="floating-run" type="button" title="Run Bot" aria-label="Run Bot" disabled>
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
</button>
<div id="floating-run-hint" class="floating-run-hint">Run Bot</div>

<script>
  const STORAGE = {
    mapping: 'flowBot.mapping',
    cdpPort: 'flowBot.cdpPort',
    slowMo: 'flowBot.slowMo',
    timeout: 'flowBot.timeout',
    start: 'flowBot.start',
    count: 'flowBot.count',
    sceneMode: 'flowBot.sceneMode',
    presetJson: 'flowBot.presetJson',
    logoPath: 'flowBot.logoPath',
    logoName: 'flowBot.logoName',
    floatingRunPos: 'flowBot.floatingRunPos',
    autoDownloadZip: 'flowBot.autoDownloadZip',
    downloadResolution: 'flowBot.downloadResolution',
    videoModel: 'flowBot.videoModel',
    aspectRatio: 'flowBot.aspectRatio',
    multiClipMode: 'flowBot.multiClipMode',
    sceneBuilderMode: 'flowBot.sceneBuilderMode',
    targetFinalDuration: 'flowBot.targetFinalDuration',
    downloadMode: 'flowBot.downloadMode',
    continueOnError: 'flowBot.continueOnError',
    maxGenerateRetries: 'flowBot.maxGenerateRetries',
    enableLogoOverlay: 'flowBot.enableLogoOverlay',
    logoFilePath: 'flowBot.logoFilePath',
    logoPosition: 'flowBot.logoPosition',
    logoWidthPercent: 'flowBot.logoWidthPercent',
    logoMargin: 'flowBot.logoMargin',
    autoLogoOverlayAfterBatch: 'flowBot.autoLogoOverlayAfterBatch',
    enableSubtitles: 'flowBot.enableSubtitles',
    subtitleSource: 'flowBot.subtitleSource',
    subtitleFontSize: 'flowBot.subtitleFontSize',
    enableProductImageCleanup: 'flowBot.enableProductImageCleanup',
    cleanupMode: 'flowBot.cleanupMode'
  };
  const FIELDS = [
    {key:'product_image', label:'product_image', help:'Cột chứa link ảnh sản phẩm.', required:false},
    {key:'product_name', label:'product_name', help:'Cột chứa tên sản phẩm.', required:true},
    {key:'short_description', label:'short_description', help:'Cột chứa mô tả ngắn.', required:true},
    {key:'long_description', label:'long_description', help:'Cột chứa mô tả dài hoặc chi tiết sản phẩm.', required:true}
  ];
  const PIPELINE = ['Excel Loaded','Mapping Ready','Chrome Connected','Step 1 Filled','Brainstorm Done','Video Generated','Create Next'];
  const SCENE_FIELDS = ['scene_group_id','scene_number','scene_total','scene_role','scene_title','scene_continuity_notes'];
  let evtSource = null;
  let currentRunId = null;
  let currentDataset = null;
  let logEntries = [];
  let logFilter = 'ALL';
  let pipelineIndex = -1;
  let chromeAlertShown = false;
  let terminalAlertShown = false;
  let uploadedLogoPath = null;
  let uploadedLogoName = '';
    let videoBatches = [];
    let selectedBatchId = null;
  let floatingRunDrag = null;
  let floatingRunSuppressClickUntil = 0;
  let floatingRunWasDragged = false;
  const POSTPROCESS_STEPS = ['Generate','Logo','Subtitle','Upscale','Done'];
  let postprocessTicker = null;
  let postprocessDuration = 0;
  let postprocessSecond = 0;

  document.addEventListener('DOMContentLoaded', () => {
    renderPipeline();
    renderMappingFields();
    loadSettings();
    initFloatingRunButton();
    document.getElementById('file').addEventListener('change', event => {
      const file = event.target.files && event.target.files[0];
      document.getElementById('file-name').textContent = file ? file.name : 'No file selected';
    });
    document.getElementById('preset-file').addEventListener('change', importPresetFile);
    document.getElementById('preset-json').addEventListener('input', () => {
      localStorage.setItem(STORAGE.presetJson, document.getElementById('preset-json').value);
      updatePresetState(false);
    });
    document.getElementById('logo-file').addEventListener('change', event => {
      const file = event.target.files && event.target.files[0];
      uploadedLogoPath = null;
      uploadedLogoName = file ? file.name : '';
      document.getElementById('logo-file-name').textContent = file ? file.name : 'No logo selected';
      localStorage.removeItem(STORAGE.logoPath);
      localStorage.removeItem(STORAGE.logoName);
      updateLogoState();
    });
    document.getElementById('dataset-id').addEventListener('blur', () => {
      const dsId = document.getElementById('dataset-id').value.trim();
      if (dsId) loadDatasetById(dsId, false);
    });
    document.getElementById('cdp-port').addEventListener('input', () => {
      document.getElementById('cdp-chip').textContent = 'CDP ' + (document.getElementById('cdp-port').value || '9222');
      persistSettings();
    });
    document.querySelectorAll('input[name="scene-mode"]').forEach(input => {
      input.addEventListener('change', () => {
        updateSceneModeAvailability(false);
        persistSettings();
      });
    });
    ['slow-mo','wait-timeout','start','count','logo-width-percent','logo-margin','logo-file-path','subtitle-font-size'].forEach(id => {
      document.getElementById(id).addEventListener('input', persistSettings);
    });
    document.getElementById('auto-download-zip').addEventListener('change', persistSettings);
    document.getElementById('download-resolution').addEventListener('change', persistSettings);
    document.getElementById('video-model').addEventListener('change', persistSettings);
    document.getElementById('aspect-ratio').addEventListener('change', persistSettings);
    document.getElementById('multi-clip-mode').addEventListener('change', persistSettings);
    document.getElementById('scene-builder-mode').addEventListener('change', persistSettings);
    document.getElementById('target-final-duration').addEventListener('change', persistSettings);
    document.getElementById('download-mode').addEventListener('change', persistSettings);
    document.getElementById('continue-on-error').addEventListener('change', persistSettings);
    document.getElementById('max-generate-retries').addEventListener('change', persistSettings);
    document.getElementById('enable-subtitles').addEventListener('change', persistSettings);
    document.getElementById('subtitle-source').addEventListener('change', persistSettings);
    document.getElementById('enable-product-image-cleanup').addEventListener('change', persistSettings);
    document.getElementById('cleanup-mode').addEventListener('change', persistSettings);
    document.getElementById('enable-logo-overlay').addEventListener('change', persistSettings);
    document.getElementById('logo-position').addEventListener('change', persistSettings);
    document.getElementById('auto-logo-overlay-after-batch').addEventListener('change', persistSettings);
    ['logo-position','logo-width-percent','logo-margin'].forEach(id => {
      const input = document.getElementById(id);
      input.addEventListener('input', updateLogoOverlayPreview);
      input.addEventListener('change', updateLogoOverlayPreview);
    });
    updateSceneModeAvailability(false);
    updateLogoOverlayPreview();
    resetPostprocessProgress();
    updateFloatingRunState();
    loadVideoBatches();
    loadDatasetHistory();
  });

  function switchSection(id, btn) {
    document.querySelectorAll('.section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
    const target = document.getElementById('section-' + id);
    if (target) target.classList.add('active');
    const navButton = btn || document.getElementById('nav-' + id);
    if (navButton) navButton.classList.add('active');
  }

  function alertBox(icon, title, text) {
    if (window.Swal) {
      return Swal.fire({icon,title,text,confirmButtonColor:icon === 'error' ? '#dc2626' : '#4f46e5'});
    }
    alert(`${title}${text ? ': ' + text : ''}`);
    return Promise.resolve();
  }

  function toast(icon, title) {
    if (window.Swal) {
      return Swal.fire({toast:true,position:'top-end',timer:2200,showConfirmButton:false,icon,title});
    }
    return Promise.resolve();
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  }

  function setStatus(msg, ok=true) {
    const bar = document.getElementById('status-bar');
    bar.className = 'status-bar ' + (ok ? 'ok' : 'err');
    bar.textContent = msg;
  }

  function updateBadge(id, text, cls='badge-muted') {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'badge badge-mini ' + cls;
    el.textContent = text;
  }

  function updateHeaderBadge(id, text, cls='badge-muted') {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'badge ' + cls;
    el.textContent = text;
  }

  function formatFileSize(bytes) {
    const size = Number(bytes || 0);
    if (!size) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = size;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }
    return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
  }

  async function loadVideoBatches(preferredBatchId=null) {
    const resp = await fetch('/api/storage/batches');
    const data = await resp.json().catch(() => ({items:[]}));
    videoBatches = Array.isArray(data.items) ? data.items : [];
    updateBadge('results-chip', `${videoBatches.length} batch`, videoBatches.length ? 'badge-success' : 'badge-muted');
    updateHeaderBadge('results-status-badge', videoBatches.length ? `${videoBatches.length} batch` : 'No batch', videoBatches.length ? 'badge-success' : 'badge-muted');
    const nextBatchId = preferredBatchId || selectedBatchId || videoBatches[0]?.batch_id || null;
    selectedBatchId = nextBatchId;
    renderBatchList();
    if (selectedBatchId) {
      await renderBatchDetail(selectedBatchId);
    } else {
      renderEmptyBatchDetail();
    }
  }

  async function loadDatasetHistory() {
    const select = document.getElementById('dataset-history');
    if (!select) return;
    const resp = await fetch('/api/datasets');
    const data = await resp.json().catch(() => ({items:[]}));
    const items = data.items || [];
    
    items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    if (items.length === 0) {
      select.innerHTML = '<option value="">Không có file cũ</option>';
      select.disabled = true;
      return;
    }
    
    select.disabled = false;
    select.innerHTML = '<option value="">-- Chọn file đã upload --</option>' + items.map(item => {
      const dateStr = item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : '';
      return `<option value="${escapeHtml(item.dataset_id)}">${escapeHtml(item.original_name)} (${escapeHtml(item.row_count)} rows) - ${dateStr}</option>`;
    }).join('');
  }

  async function selectHistoryDataset() {
    const dsId = document.getElementById('dataset-history').value;
    if (!dsId) return alertBox('warning', 'Chưa chọn file', 'Vui lòng chọn một file từ danh sách.');
    const ok = await loadDatasetById(dsId, true);
    if (ok) {
      document.getElementById('dataset-id').value = dsId;
      toast('success', 'Đã tải file cũ');
    }
  }

  function renderBatchList() {
    const target = document.getElementById('batch-list');
    if (!target) return;
    if (!videoBatches.length) {
      target.innerHTML = '<div class="empty">No saved batch yet.</div>';
      return;
    }
    target.innerHTML = videoBatches.map(batch => `
      <button class="batch-card ${batch.batch_id === selectedBatchId ? 'active' : ''}" onclick="selectBatch('${escapeHtml(batch.batch_id)}')">
        <div class="batch-card-title">${escapeHtml(batch.batch_id)}</div>
        <div class="batch-card-meta">
          ${escapeHtml(batch.item_count || 0)} video • ${escapeHtml(batch.completed_count || 0)} completed<br>
          Updated: ${escapeHtml(batch.updated_at || batch.created_at || '-')}
        </div>
      </button>
    `).join('');
  }

  async function selectBatch(batchId) {
    selectedBatchId = batchId;
    renderBatchList();
    await renderBatchDetail(batchId);
  }

  function renderEmptyBatchDetail() {
    const head = document.getElementById('batch-detail-head');
    const actions = document.getElementById('batch-detail-actions');
    const grid = document.getElementById('batch-detail-grid');
    if (head) {
      head.innerHTML = `
        <div>
          <h2 style="font-size:.95rem;margin:0 0 .25rem">Select a batch</h2>
          <div class="batch-card-meta">Chọn batch bên trái để xem video đã lưu.</div>
        </div>
      `;
    }
    if (actions) actions.innerHTML = '';
    if (grid) grid.innerHTML = '<div class="empty" style="grid-column:1/-1">No video selected.</div>';
  }

  async function renderBatchDetail(batchId) {
    const resp = await fetch(`/api/storage/batches/${encodeURIComponent(batchId)}`);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.batch_id) {
      renderEmptyBatchDetail();
      return;
    }
    selectedBatchId = data.batch_id;
    renderBatchList();
    const head = document.getElementById('batch-detail-head');
    const actions = document.getElementById('batch-detail-actions');
    const grid = document.getElementById('batch-detail-grid');
    if (head) {
      head.innerHTML = `
        <div>
          <h2 style="font-size:.95rem;margin:0 0 .25rem">${escapeHtml(data.batch_id)}</h2>
          <div class="batch-summary-meta">
            <span class="badge badge-success">${escapeHtml(data.completed_count || 0)} completed</span>
            <span class="badge badge-error">${escapeHtml(data.failed_count || 0)} failed</span>
            <span class="badge badge-outline">${escapeHtml(data.item_count || 0)} items</span>
            <span class="badge badge-muted">${escapeHtml(data.updated_at || data.created_at || '-')}</span>
          </div>
        </div>
      `;
    }
    if (actions) {
      actions.innerHTML = data.zip_url
        ? `<button class="btn btn-outline" onclick="testBatchLogoOverlay('${escapeHtml(data.batch_id)}')">Test Logo Overlay</button>
           <button class="btn btn-primary" onclick="downloadBatchZip('${escapeHtml(data.batch_id)}')">Download Batch ZIP</button>`
        : '';
    }
    const items = Array.isArray(data.items) ? data.items : [];
    if (!grid) return;
    if (!items.length) {
      grid.innerHTML = '<div class="empty" style="grid-column:1/-1">Batch này chưa có video.</div>';
      return;
    }
    grid.innerHTML = items.map(item => {
      const overlayStatus = item.logo_overlay_status || (item.logo_overlay_enabled ? 'pending' : 'disabled');
      const overlayBadgeClass = overlayStatus === 'success' ? 'badge-success' : (overlayStatus === 'failed' ? 'badge-error' : 'badge-muted');
      const subtitleStatus = item.subtitle_status || (item.subtitle_enabled ? 'pending' : 'disabled');
      const subtitleBadgeClass = subtitleStatus === 'success' ? 'badge-success' : (subtitleStatus === 'failed' ? 'badge-error' : 'badge-muted');
      const cleanupStatus = item.image_cleanup_status || '-';
      const cleanupBadgeClass = ['rembg','pillow','cached'].includes(cleanupStatus) ? 'badge-success' : (cleanupStatus === 'failed' ? 'badge-error' : 'badge-muted');
      const clips = Array.isArray(item.clips) ? item.clips : [];
      const clipsZipUrl = item.multi_clip && item.scene_group_id
        ? `/api/storage/batches/${encodeURIComponent(data.batch_id)}/clips/${encodeURIComponent(item.scene_group_id)}/zip`
        : '';
      const sceneSummary = item.multi_clip
        ? `Multi-clip - ${escapeHtml(item.clip_total || clips.length || 0)} clips - ${escapeHtml(item.merge_method || '-')}`
        : `Scene ${escapeHtml(item.scene_number || 0)} / ${escapeHtml(item.scene_total || 0)} - ${escapeHtml(item.scene_role || 'single')}`;
      const sceneIdHtml = item.scene_id ? `Native scene: ${escapeHtml(item.scene_id)}<br>` : '';
      const clipListHtml = clips.length ? `
        <div class="video-card-meta" style="display:grid;gap:.35rem">
          ${clips.map(clip => `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem">
              <span>Clip ${escapeHtml(clip.clip_index || '')}: ${escapeHtml(clip.clip_role || 'clip')}</span>
              <span>
                ${clip.download_url ? `<button class="btn btn-outline" style="min-height:26px;padding:.2rem .5rem;font-size:.7rem" onclick="downloadBatchVideo('${escapeHtml(clip.download_url)}')">Clip</button>` : ''}
                ${clip.last_frame_url ? `<button class="btn btn-outline" style="min-height:26px;padding:.2rem .5rem;font-size:.7rem" onclick="window.open('${escapeHtml(clip.last_frame_url)}','_blank')">Frame</button>` : ''}
              </span>
            </div>
          `).join('')}
        </div>
      ` : '';
      return `
      <div class="video-card">
        ${item.preview_url && item.status === 'completed'
          ? `<video controls preload="metadata" src="${escapeHtml(item.preview_url)}"></video>`
          : `<div class="empty" style="min-height:220px">${escapeHtml(item.status || 'pending')}</div>`}
        <div class="video-card-body">
          <p class="video-card-title">${escapeHtml(item.product_name || item.scene_title || 'Untitled video')}</p>
          <div class="video-card-meta">
            ${sceneSummary}<br>
            ${escapeHtml(item.scene_group_id || '')}<br>
            ${sceneIdHtml}
            ${escapeHtml(item.created_at || '')}<br>
            ${escapeHtml(formatFileSize(item.file_size || 0))}
          </div>
          <div class="video-card-meta">
            <span class="badge ${overlayBadgeClass}">Logo ${escapeHtml(overlayStatus)}</span>
            <span class="badge badge-outline">${escapeHtml(item.logo_position || '-')}</span>
            <span class="badge ${subtitleBadgeClass}">Subtitle ${escapeHtml(subtitleStatus)}</span>
            <span class="badge badge-outline">${escapeHtml(item.subtitle_source || '-')}</span>
            <span class="badge ${cleanupBadgeClass}">Image ${escapeHtml(cleanupStatus)}</span>
          </div>
          ${clipListHtml}
          <div class="video-card-actions">
            ${item.preview_url && item.status === 'completed'
              ? `<button class="btn btn-outline" onclick="previewBatchVideo('${escapeHtml(item.preview_url)}', '${escapeHtml(item.product_name || item.scene_title || 'Video preview')}')">View</button>
                 <button class="btn btn-outline" onclick="testBatchLogoOverlay('${escapeHtml(data.batch_id)}')">Test Logo</button>
                 ${item.raw_download_url ? `<button class="btn btn-outline" onclick="downloadBatchVideo('${escapeHtml(item.raw_download_url)}')">Raw</button>` : ''}
                 ${item.subtitle_download_url ? `<a class="btn btn-outline" href="${escapeHtml(item.subtitle_download_url)}" download>SRT</a>` : ''}
                 ${clipsZipUrl ? `<a class="btn btn-outline" href="${escapeHtml(clipsZipUrl)}" download>All Clips</a>` : ''}
                 ${item.final_download_url ? `<button class="btn btn-primary" onclick="downloadBatchVideo('${escapeHtml(item.final_download_url)}')">Final</button>` : ''}`
              : `<span class="badge badge-error">${escapeHtml(item.error || item.status || 'Unavailable')}</span>`}
          </div>
        </div>
      </div>
    `}).join('');
  }

  function previewBatchVideo(url, title) {
    if (window.Swal) {
      Swal.fire({
        title,
        width: 420,
        html: `<video controls autoplay style="width:100%;border-radius:12px;background:#111827" src="${url}"></video>`,
        confirmButtonColor: '#4f46e5'
      });
      return;
    }
    window.open(url, '_blank');
  }

  function getDownloadResolution() {
    const input = document.getElementById('download-resolution');
    return input ? (input.value || '1080p') : '1080p';
  }

  async function downloadBatchVideo(url) {
    const resolution = getDownloadResolution();
    const separator = url.includes('?') ? '&' : '?';
    const resolvedUrl = `${url}${separator}resolution=${encodeURIComponent(resolution)}`;
    const isOriginal = resolution === 'original';
    const loadingText = isOriginal
      ? 'Äang táº£i video...'
      : `Äang tÄƒng Ä‘á»™ phÃ¢n giáº£i video lÃªn ${resolution}...`;
    setStatus(loadingText);
    setPostprocessProgress(3, 82, isOriginal ? 'Downloading video' : 'Upscaling video', loadingText);
    try {
      const resp = await fetch(resolvedUrl);
      if (!resp.ok) {
        let message = `HTTP ${resp.status}`;
        try {
          const data = await resp.json();
          message = data.detail || message;
        } catch {}
        throw new Error(message);
      }
      const blob = await resp.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = decodeURIComponent((new URL(url, window.location.origin)).pathname.split('/').pop() || 'video.mp4');
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 5000);
      setPostprocessProgress(4, 100, 'Video download ready', isOriginal ? 'Original video downloaded.' : `${resolution} upscale completed.`);
      setStatus('ÄÃ£ táº£i video.');
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      setStatus('Táº£i video tháº¥t báº¡i: ' + message, false);
      alertBox('error', 'Download failed', message);
    }
  }

  function updateLogoOverlayPreview() {
    const mark = document.getElementById('logo-overlay-preview-mark');
    const preview = document.getElementById('logo-overlay-preview');
    if (!mark || !preview) return;
    const position = document.getElementById('logo-position')?.value || 'top-right';
    const widthPercent = Math.min(25, Math.max(5, Number(document.getElementById('logo-width-percent')?.value || 12)));
    const margin = Math.max(0, Number(document.getElementById('logo-margin')?.value || 32));
    const marginPercent = Math.min(14, Math.max(1.5, margin / 16));
    mark.style.width = `${widthPercent}%`;
    mark.style.left = '';
    mark.style.right = '';
    mark.style.top = '';
    mark.style.bottom = '';
    if (position.includes('right')) mark.style.right = `${marginPercent}%`;
    else mark.style.left = `${marginPercent}%`;
    if (position.includes('bottom')) mark.style.bottom = `${marginPercent}%`;
    else mark.style.top = `${marginPercent}%`;
  }

  async function downloadBatchZip(batchId) {
    const resolution = getDownloadResolution();
    const isOriginal = resolution === 'original';
    const loadingText = isOriginal
      ? 'Đang đóng gói video...'
      : `Đang tăng độ phân giải video lên ${resolution}...`;
    setStatus(loadingText);
    setPostprocessProgress(3, 84, isOriginal ? 'Packaging ZIP' : 'Upscaling ZIP videos', loadingText);
    if (window.Swal) {
      Swal.fire({
        title: loadingText,
        allowOutsideClick: false,
        allowEscapeKey: false,
        didOpen: () => Swal.showLoading()
      });
    }
    try {
      const url = `/api/storage/batches/${encodeURIComponent(batchId)}/zip?resolution=${encodeURIComponent(resolution)}`;
      const resp = await fetch(url);
      if (!resp.ok) {
        let message = `HTTP ${resp.status}`;
        try {
          const data = await resp.json();
          message = data.detail || message;
        } catch {}
        throw new Error(message);
      }
      const blob = await resp.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = `${batchId}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 5000);
      if (window.Swal) Swal.close();
      setPostprocessProgress(4, 100, 'ZIP download ready', isOriginal ? 'Original videos packaged.' : `${resolution} upscale completed.`);
      setStatus('Đã tải ZIP video.');
    } catch (err) {
      if (window.Swal) Swal.close();
      const message = err && err.message ? err.message : String(err);
      setStatus('Tải ZIP thất bại: ' + message, false);
      alertBox('error', 'Download failed', message);
    }
  }

  async function testBatchLogoOverlay(batchId) {
    persistSettings();
    const selectedLogo = document.getElementById('logo-file').files[0];
    if (selectedLogo) {
      setStatus('Đang upload logo mới trước khi test overlay...');
      const ready = await uploadLogo(true);
      if (!ready) {
        return alertBox('error', 'Upload logo failed', 'Không thể upload logo mới trước khi test overlay.');
      }
    }
    const logoPath = document.getElementById('logo-file-path').value.trim() || uploadedLogoPath || '';
    if (!logoPath) {
      return alertBox('warning', 'Missing logo path', 'Upload logo hoặc nhập Logo File Path trước khi test overlay.');
    }
    const payload = {
      logo_file_path: logoPath,
      logo_position: document.getElementById('logo-position').value || 'top-right',
      logo_width_percent: Number(document.getElementById('logo-width-percent').value || 12),
      logo_margin: Number(document.getElementById('logo-margin').value || 32)
    };
    const loadingText = 'Đang test logo overlay trên video đã có...';
    setStatus(loadingText);
    if (window.Swal) {
      Swal.fire({
        title: loadingText,
        allowOutsideClick: false,
        allowEscapeKey: false,
        didOpen: () => Swal.showLoading()
      });
    }
    try {
      const resp = await fetch(`/api/storage/batches/${encodeURIComponent(batchId)}/logo-overlay/test`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || `HTTP ${resp.status}`);
      }
      if (window.Swal) Swal.close();
      const processed = data.logo_overlay_processed || 0;
      const failed = data.logo_overlay_failed || 0;
      setStatus(`Logo overlay test xong: ${processed} success, ${failed} failed.`);
      await loadVideoBatches(batchId);
      await renderBatchDetail(batchId);
      toast(failed ? 'warning' : 'success', `Overlay test: ${processed} success, ${failed} failed`);
    } catch (err) {
      if (window.Swal) Swal.close();
      const message = err && err.message ? err.message : String(err);
      setStatus('Logo overlay test thất bại: ' + message, false);
      alertBox('error', 'Overlay test failed', message);
    }
  }

  function updateFloatingRunState() {
    const button = document.getElementById('floating-run-btn');
    if (!button) return;
    const datasetReady = Boolean(currentDataset?.dataset_id);
    button.disabled = !datasetReady;
    button.title = datasetReady ? 'Run Bot' : 'Upload Excel first';
    button.setAttribute('aria-label', datasetReady ? 'Run Bot' : 'Upload Excel first');
    const hint = document.getElementById('floating-run-hint');
    if (hint) hint.textContent = datasetReady ? 'Run Bot' : 'Upload Excel first';
  }

  function datasetHasSceneColumns() {
    if (!currentDataset?.mapping) return false;
    return SCENE_FIELDS.some(key => Boolean(currentDataset.mapping[key]));
  }

  function getSceneMode() {
    return document.querySelector('input[name="scene-mode"]:checked')?.value || 'skip';
  }

  function setSceneMode(mode) {
    const input = document.querySelector(`input[name="scene-mode"][value="${mode}"]`) || document.querySelector('input[name="scene-mode"][value="skip"]');
    if (input) input.checked = true;
    updateSceneModeAvailability(false);
  }

  function setSceneManualPauseState(paused, message='') {
    const button = document.getElementById('continue-scene-btn');
    if (button) button.disabled = !paused || !currentRunId;
    const status = document.getElementById('scene-mode-status');
    if (!status) return;
    status.classList.remove('is-warning', 'is-paused');
    if (paused) {
      status.classList.add('is-paused');
      status.textContent = message || 'Paused for manual scene setup.';
      setStatus(message || 'Paused for manual scene setup.');
      return;
    }
    updateSceneModeAvailability(false);
  }

  function updateSceneModeAvailability(showWarning=false) {
    const autoInput = document.querySelector('input[name="scene-mode"][value="auto_excel"]');
    const hasSceneColumns = datasetHasSceneColumns();
    if (autoInput) autoInput.disabled = currentDataset ? !hasSceneColumns : false;
    if (autoInput?.disabled && autoInput.checked) {
      document.querySelector('input[name="scene-mode"][value="skip"]').checked = true;
      if (showWarning) {
        alertBox('warning', 'Không có cột scene', 'Excel không có cột scene, vui lòng chọn Manual Pause hoặc Skip.');
      }
    }
    const mode = getSceneMode();
    const badgeMap = {
      manual_pause: ['Manual Pause', 'badge-warning'],
      skip: ['Skip', 'badge-muted'],
      auto_excel: ['Auto Excel', 'badge-success']
    };
    updateHeaderBadge('scene-mode-badge', badgeMap[mode]?.[0] || 'Skip', badgeMap[mode]?.[1] || 'badge-muted');
    const status = document.getElementById('scene-mode-status');
    const continueButton = document.getElementById('continue-scene-btn');
    if (!status || (continueButton && !continueButton.disabled)) return;
    status.classList.remove('is-warning', 'is-paused');
    if (mode === 'auto_excel' && !hasSceneColumns) {
      status.classList.add('is-warning');
      status.textContent = 'Excel không có cột scene, vui lòng chọn Manual Pause hoặc Skip.';
      return;
    }
    if (mode === 'manual_pause') {
      status.textContent = 'Bot sẽ dừng tại Scene Settings và chờ nút Continue / Done trong UI này.';
      return;
    }
    if (mode === 'auto_excel') {
      status.textContent = 'Bot sẽ fill scene fields từ Excel nếu Flow có field tương ứng. Field nào bị che hoặc không tìm thấy sẽ được bỏ qua kèm warning log.';
      return;
    }
    status.textContent = 'Bot sẽ bỏ qua Scene Settings và đi thẳng sang brainstorm.';
  }

  function initFloatingRunButton() {
    const button = document.getElementById('floating-run-btn');
    const hint = document.getElementById('floating-run-hint');
    if (!button || !hint) return;

    const saved = localStorage.getItem(STORAGE.floatingRunPos);
    if (saved) {
      try {
        const pos = JSON.parse(saved);
        if (typeof pos.left === 'number' && typeof pos.top === 'number') {
          setFloatingRunPosition(pos.left, pos.top);
        }
      } catch {}
    } else {
      updateFloatingRunHintPosition();
    }

    button.addEventListener('pointerdown', event => {
      if (button.disabled) return;
      floatingRunWasDragged = false;
      const rect = button.getBoundingClientRect();
      floatingRunDrag = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
        moved: false
      };
      button.classList.add('dragging');
      button.setPointerCapture(event.pointerId);
    });

    button.addEventListener('pointermove', event => {
      if (!floatingRunDrag || floatingRunDrag.pointerId !== event.pointerId) return;
      const nextLeft = event.clientX - floatingRunDrag.offsetX;
      const nextTop = event.clientY - floatingRunDrag.offsetY;
      if (Math.abs(event.clientX - floatingRunDrag.startX) > 6 || Math.abs(event.clientY - floatingRunDrag.startY) > 6) {
        floatingRunDrag.moved = true;
        floatingRunWasDragged = true;
      }
      setFloatingRunPosition(nextLeft, nextTop);
    });

    const stopDrag = event => {
      if (!floatingRunDrag || floatingRunDrag.pointerId !== event.pointerId) return;
      const moved = floatingRunDrag.moved;
      floatingRunDrag = null;
      button.classList.remove('dragging');
      localStorage.setItem(STORAGE.floatingRunPos, JSON.stringify({
        left: parseFloat(button.style.left || '0'),
        top: parseFloat(button.style.top || '0')
      }));
      if (moved) {
        floatingRunSuppressClickUntil = Date.now() + 350;
        event.preventDefault();
        event.stopPropagation();
      }
    };

    button.addEventListener('pointerup', stopDrag);
    button.addEventListener('pointercancel', stopDrag);
    button.addEventListener('click', event => {
      if (floatingRunWasDragged || Date.now() < floatingRunSuppressClickUntil) {
        event.preventDefault();
        event.stopPropagation();
        floatingRunWasDragged = false;
        return;
      }
      startRun();
    });
    window.addEventListener('resize', () => {
      const rect = button.getBoundingClientRect();
      setFloatingRunPosition(rect.left, rect.top);
    });
  }

  function setFloatingRunPosition(left, top) {
    const button = document.getElementById('floating-run-btn');
    if (!button) return;
    const maxLeft = Math.max(12, window.innerWidth - button.offsetWidth - 12);
    const maxTop = Math.max(12, window.innerHeight - button.offsetHeight - 12);
    const safeLeft = Math.min(Math.max(12, left), maxLeft);
    const safeTop = Math.min(Math.max(12, top), maxTop);
    button.style.left = `${safeLeft}px`;
    button.style.top = `${safeTop}px`;
    button.style.right = 'auto';
    updateFloatingRunHintPosition();
  }

  function updateFloatingRunHintPosition() {
    const button = document.getElementById('floating-run-btn');
    const hint = document.getElementById('floating-run-hint');
    if (!button || !hint) return;
    const rect = button.getBoundingClientRect();
    hint.style.left = `${Math.max(12, rect.left - 8)}px`;
    hint.style.top = `${Math.max(12, rect.bottom + 8)}px`;
  }

  function loadSettings() {
    [['cdp-port',STORAGE.cdpPort],['slow-mo',STORAGE.slowMo],['wait-timeout',STORAGE.timeout],['start',STORAGE.start],['count',STORAGE.count]].forEach(([id,key]) => {
      const value = localStorage.getItem(key);
      if (value !== null) document.getElementById(id).value = value;
    });
    const autoZip = localStorage.getItem(STORAGE.autoDownloadZip);
    if (autoZip !== null) {
      document.getElementById('auto-download-zip').checked = (autoZip === 'true');
    }
    const downloadResolution = localStorage.getItem(STORAGE.downloadResolution);
    if (downloadResolution !== null) {
      document.getElementById('download-resolution').value = downloadResolution;
    }
    const videoModel = localStorage.getItem(STORAGE.videoModel);
    if (videoModel !== null) {
      document.getElementById('video-model').value = videoModel;
    }
    [
      ['aspect-ratio', STORAGE.aspectRatio],
      ['multi-clip-mode', STORAGE.multiClipMode],
      ['scene-builder-mode', STORAGE.sceneBuilderMode],
      ['target-final-duration', STORAGE.targetFinalDuration],
      ['download-mode', STORAGE.downloadMode],
      ['max-generate-retries', STORAGE.maxGenerateRetries],
    ].forEach(([id, key]) => {
      const value = localStorage.getItem(key);
      if (value !== null) document.getElementById(id).value = value;
    });
    const continueOnError = localStorage.getItem(STORAGE.continueOnError);
    if (continueOnError !== null) {
      document.getElementById('continue-on-error').checked = (continueOnError === 'true');
    }
    const enableLogoOverlay = localStorage.getItem(STORAGE.enableLogoOverlay);
    if (enableLogoOverlay !== null) {
      document.getElementById('enable-logo-overlay').checked = (enableLogoOverlay === 'true');
    }
    const enableSubtitles = localStorage.getItem(STORAGE.enableSubtitles);
    if (enableSubtitles !== null) {
      document.getElementById('enable-subtitles').checked = (enableSubtitles === 'true');
    }
    const subtitleSource = localStorage.getItem(STORAGE.subtitleSource);
    if (subtitleSource !== null) {
      document.getElementById('subtitle-source').value = subtitleSource;
    }
    const subtitleFontSize = localStorage.getItem(STORAGE.subtitleFontSize);
    if (subtitleFontSize !== null) {
      document.getElementById('subtitle-font-size').value = subtitleFontSize;
    }
    const enableProductImageCleanup = localStorage.getItem(STORAGE.enableProductImageCleanup);
    if (enableProductImageCleanup !== null) {
      document.getElementById('enable-product-image-cleanup').checked = (enableProductImageCleanup === 'true');
    }
    const cleanupMode = localStorage.getItem(STORAGE.cleanupMode);
    if (cleanupMode !== null) {
      document.getElementById('cleanup-mode').value = cleanupMode;
    }
    const autoLogoOverlayAfterBatch = localStorage.getItem(STORAGE.autoLogoOverlayAfterBatch);
    if (autoLogoOverlayAfterBatch !== null) {
      document.getElementById('auto-logo-overlay-after-batch').checked = (autoLogoOverlayAfterBatch === 'true');
    }
    [
      ['logo-file-path', STORAGE.logoFilePath],
      ['logo-position', STORAGE.logoPosition],
      ['logo-width-percent', STORAGE.logoWidthPercent],
      ['logo-margin', STORAGE.logoMargin],
    ].forEach(([id, key]) => {
      const value = localStorage.getItem(key);
      if (value !== null) document.getElementById(id).value = value;
    });
    setSceneMode(localStorage.getItem(STORAGE.sceneMode) || 'skip');
    document.getElementById('cdp-chip').textContent = 'CDP ' + (document.getElementById('cdp-port').value || '9222');
    const presetJson = localStorage.getItem(STORAGE.presetJson);
    if (presetJson) document.getElementById('preset-json').value = presetJson;
    uploadedLogoPath = localStorage.getItem(STORAGE.logoPath);
    uploadedLogoName = localStorage.getItem(STORAGE.logoName) || '';
    if (uploadedLogoName) document.getElementById('logo-file-name').textContent = uploadedLogoName;
    updatePresetState(false);
    updateLogoState();
    updateSceneModeAvailability(false);
    updateLogoOverlayPreview();
    updateFloatingRunState();
  }

  function persistSettings() {
    localStorage.setItem(STORAGE.cdpPort, document.getElementById('cdp-port').value);
    localStorage.setItem(STORAGE.slowMo, document.getElementById('slow-mo').value);
    localStorage.setItem(STORAGE.timeout, document.getElementById('wait-timeout').value);
    localStorage.setItem(STORAGE.start, document.getElementById('start').value);
    localStorage.setItem(STORAGE.count, document.getElementById('count').value);
    localStorage.setItem(STORAGE.sceneMode, getSceneMode());
    localStorage.setItem(STORAGE.autoDownloadZip, document.getElementById('auto-download-zip').checked);
    localStorage.setItem(STORAGE.downloadResolution, document.getElementById('download-resolution').value);
    localStorage.setItem(STORAGE.videoModel, document.getElementById('video-model').value);
    localStorage.setItem(STORAGE.aspectRatio, document.getElementById('aspect-ratio').value);
    localStorage.setItem(STORAGE.multiClipMode, document.getElementById('multi-clip-mode').value);
    localStorage.setItem(STORAGE.sceneBuilderMode, document.getElementById('scene-builder-mode').value);
    localStorage.setItem(STORAGE.targetFinalDuration, document.getElementById('target-final-duration').value);
    localStorage.setItem(STORAGE.downloadMode, document.getElementById('download-mode').value);
    localStorage.setItem(STORAGE.continueOnError, document.getElementById('continue-on-error').checked);
    localStorage.setItem(STORAGE.maxGenerateRetries, document.getElementById('max-generate-retries').value);
    localStorage.setItem(STORAGE.enableSubtitles, document.getElementById('enable-subtitles').checked);
    localStorage.setItem(STORAGE.subtitleSource, document.getElementById('subtitle-source').value);
    localStorage.setItem(STORAGE.subtitleFontSize, document.getElementById('subtitle-font-size').value);
    localStorage.setItem(STORAGE.enableProductImageCleanup, document.getElementById('enable-product-image-cleanup').checked);
    localStorage.setItem(STORAGE.cleanupMode, document.getElementById('cleanup-mode').value);
    localStorage.setItem(STORAGE.enableLogoOverlay, document.getElementById('enable-logo-overlay').checked);
    localStorage.setItem(STORAGE.logoFilePath, document.getElementById('logo-file-path').value);
    localStorage.setItem(STORAGE.logoPosition, document.getElementById('logo-position').value);
    localStorage.setItem(STORAGE.logoWidthPercent, document.getElementById('logo-width-percent').value);
    localStorage.setItem(STORAGE.logoMargin, document.getElementById('logo-margin').value);
    localStorage.setItem(STORAGE.autoLogoOverlayAfterBatch, document.getElementById('auto-logo-overlay-after-batch').checked);
  }

  function sanitizePresetObject(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
    const next = {...value};
    delete next.website_logo;
    return next;
  }

  function syncPresetTextarea(parsed, preserveRaw=false) {
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return parsed;
    const sanitized = sanitizePresetObject(parsed);
    const formatted = JSON.stringify(sanitized, null, 2);
    if (!preserveRaw || formatted !== document.getElementById('preset-json').value.trim()) {
      document.getElementById('preset-json').value = formatted;
    }
    localStorage.setItem(STORAGE.presetJson, formatted);
    return sanitized;
  }

  function parsePresetJson(showAlert=false) {
    const textarea = document.getElementById('preset-json');
    const raw = textarea.value.trim();
    if (!raw) {
      updatePresetState(false);
      if (showAlert) alertBox('warning', 'Preset empty', 'Bạn có thể dán JSON preset hoặc bỏ trống nếu không cần import preset.');
      return null;
    }
    try {
      const parsed = syncPresetTextarea(JSON.parse(raw), true);
      updatePresetState(false, parsed);
      return parsed;
    } catch (error) {
      updatePresetState(false, null, error.message);
      if (showAlert) alertBox('error', 'Preset JSON invalid', error.message);
      return null;
    }
  }

  function updatePresetState(showSuccess=false, parsed=null, errorMessage='') {
    const raw = document.getElementById('preset-json').value.trim();
    const status = document.getElementById('preset-status');
    const summary = document.getElementById('preset-summary');
    if (!raw) {
      updateBadge('preset-chip', uploadedLogoPath ? 'Logo ready' : 'Optional', uploadedLogoPath ? 'badge-success' : 'badge-muted');
      updateHeaderBadge('preset-status-badge', uploadedLogoPath ? 'Logo Ready' : 'Optional', uploadedLogoPath ? 'badge-success' : 'badge-muted');
      status.textContent = 'Preset là optional. Khi có JSON hợp lệ, bot sẽ import vào Flow trước khi điền sản phẩm.';
      summary.innerHTML = '';
      return;
    }
    if (!parsed && !errorMessage) {
      try { parsed = JSON.parse(raw); }
      catch (error) { errorMessage = error.message; }
    }
    if (errorMessage) {
      updateBadge('preset-chip', 'Invalid', 'badge-error');
      updateHeaderBadge('preset-status-badge', 'Preset Invalid', 'badge-error');
      status.textContent = 'Preset JSON đang lỗi: ' + errorMessage;
      summary.innerHTML = '';
      return;
    }
    updateBadge('preset-chip', uploadedLogoPath ? 'Preset + Logo' : 'Preset ready', 'badge-success');
    updateHeaderBadge('preset-status-badge', uploadedLogoPath ? 'Preset + Logo Ready' : 'Preset Ready', 'badge-success');
    status.innerHTML = `<strong>${escapeHtml(parsed.preset_name || 'Preset')}</strong> sẵn sàng import vào Flow Step 1.`;
    summary.innerHTML = [
      ['Tone', parsed.brand_tone || ''],
      ['Audience', parsed.target_audience || ''],
      ['Platform', parsed.platform || ''],
      ['Aspect', parsed.aspect_ratio || ''],
      ['Style', parsed.style || ''],
      ['Duration', parsed.duration ? `${parsed.duration}s` : '']
    ].filter(([,value]) => value !== '').map(([label,value]) => (
      `<div class="preset-summary-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
    )).join('');
    if (showSuccess) toast('success', 'Preset JSON ready');
  }

  function validatePresetJson(showAlert=false) {
    const parsed = parsePresetJson(showAlert);
    if (parsed && showAlert) alertBox('success', 'Preset ready', 'Preset JSON hợp lệ và đã sẵn sàng import.');
    return parsed;
  }

  function formatPresetJson() {
    const parsed = parsePresetJson(true);
    if (!parsed) return;
    syncPresetTextarea(parsed);
    updatePresetState(true, parsed);
  }

  function clearPresetJson() {
    document.getElementById('preset-json').value = '';
    document.getElementById('preset-file').value = '';
    document.getElementById('preset-file-name').textContent = 'No preset file';
    localStorage.removeItem(STORAGE.presetJson);
    updatePresetState(false);
    toast('success', 'Preset cleared');
  }

  function importPresetFile(event) {
    const file = event.target.files && event.target.files[0];
    document.getElementById('preset-file-name').textContent = file ? file.name : 'No preset file';
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || '');
      try {
        const parsed = syncPresetTextarea(JSON.parse(raw));
        updatePresetState(false, parsed);
        alertBox('success', 'Preset imported', `${file.name} đã được nạp vào textarea.`);
      } catch (error) {
        updatePresetState(false, null, error.message);
        alertBox('error', 'Preset JSON invalid', error.message);
      }
    };
    reader.onerror = () => alertBox('error', 'Cannot read preset file', file.name);
    reader.readAsText(file, 'utf-8');
  }

  function updateLogoState() {
    const status = document.getElementById('logo-status');
    const selected = document.getElementById('logo-file').files[0];
    if (uploadedLogoPath) {
      updateHeaderBadge('logo-status-badge', 'Logo Ready', 'badge-success');
      status.innerHTML = `<strong>${escapeHtml(uploadedLogoName || 'Logo')}</strong> đã upload. Bot sẽ dùng file này ở Step 1.`;
    } else if (selected) {
      updateHeaderBadge('logo-status-badge', 'Selected', 'badge-warning');
      status.textContent = `${selected.name} đã chọn. Nút Run sẽ tự upload nếu bạn chưa bấm Upload Logo.`;
    } else {
      updateHeaderBadge('logo-status-badge', 'No logo', 'badge-muted');
      status.textContent = 'Logo là optional. Nếu chọn file mà chưa upload, nút Run sẽ tự upload trước.';
    }
    updatePresetState(false);
  }

  async function uploadLogo(silent=false) {
    const input = document.getElementById('logo-file');
    const file = input.files && input.files[0];
    if (!file) {
      if (uploadedLogoPath) return true;
      if (!silent) alertBox('warning', 'Chưa chọn logo', 'Chọn file ảnh logo trước khi upload.');
      return false;
    }
    const form = new FormData();
    form.append('file', file);
    const resp = await fetch('/api/assets/logo', {method:'POST', body:form});
    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data.file_path) {
      uploadedLogoPath = data.file_path;
      uploadedLogoName = data.original_name || file.name;
      localStorage.setItem(STORAGE.logoPath, uploadedLogoPath);
      localStorage.setItem(STORAGE.logoName, uploadedLogoName);
      document.getElementById('logo-file-path').value = uploadedLogoPath;
      localStorage.setItem(STORAGE.logoFilePath, uploadedLogoPath);
      document.getElementById('logo-file-name').textContent = uploadedLogoName;
      updateLogoState();
      updateLogoOverlayPreview();
      if (!silent) toast('success', 'Logo uploaded');
      return true;
    }
    const message = data.detail || JSON.stringify(data);
    if (!silent) alertBox('error', 'Upload logo failed', message);
    return false;
  }

  function clearLogo() {
    document.getElementById('logo-file').value = '';
    document.getElementById('logo-file-name').textContent = 'No logo selected';
    uploadedLogoPath = null;
    uploadedLogoName = '';
    if (document.getElementById('logo-file-path').value === localStorage.getItem(STORAGE.logoPath)) {
      document.getElementById('logo-file-path').value = '';
      localStorage.removeItem(STORAGE.logoFilePath);
    }
    localStorage.removeItem(STORAGE.logoPath);
    localStorage.removeItem(STORAGE.logoName);
    updateLogoState();
    toast('success', 'Logo cleared');
  }

  function clearLog() {
    logEntries = [];
    renderLogs();
    resetPostprocessProgress();
  }

  function appendLog(time, level, message) {
    const entry = {time, level:String(level || 'INFO').toUpperCase(), message};
    logEntries.push(entry);
    renderLogs();
    updatePipelineFromLog(entry);
    updatePostprocessFromLog(entry);
  }

  function renderLogs() {
    const box = document.getElementById('log-box');
    const visible = logFilter === 'ALL' ? logEntries : logEntries.filter(item => item.level === logFilter);
    box.innerHTML = '';
    if (!visible.length) {
      box.innerHTML = '<div class="empty">No log entries</div>';
      return;
    }
    visible.forEach(item => {
      const level = ['INFO','SUCCESS','WARNING','ERROR'].includes(item.level) ? item.level : 'INFO';
      const line = document.createElement('div');
      line.className = 'log-line';
      line.innerHTML = `<span class="log-time">${escapeHtml(item.time)}</span><span class="log-badge log-badge-${level}">${level}</span><span class="log-msg">${escapeHtml(item.message)}</span>`;
      box.appendChild(line);
    });
    box.scrollTop = box.scrollHeight;
  }

  function setLogFilter(filter, btn) {
    logFilter = filter;
    document.querySelectorAll('#log-filter button').forEach(button => {
      button.classList.toggle('active', button.dataset.filter === filter);
    });
    if (btn) btn.classList.add('active');
    renderLogs();
  }

  async function copyLog() {
    const text = logEntries.map(item => `[${item.time}] [${item.level}] ${item.message}`).join('\\n');
    if (!text) return toast('warning', 'Log đang trống');
    await navigator.clipboard.writeText(text);
    toast('success', 'Đã copy log');
  }

  function downloadLog() {
    const text = logEntries.map(item => `[${item.time}] [${item.level}] ${item.message}`).join('\\n');
    if (!text) return toast('warning', 'Log đang trống');
    const blob = new Blob([text], {type:'text/plain;charset=utf-8'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${currentRunId || 'flow-bot'}-log.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function setBadge(status) {
    const text = status ? status.toUpperCase() : 'IDLE';
    const map = {running:'badge-warning',completed:'badge-success',failed:'badge-error',queued:'badge-muted'};
    updateHeaderBadge('run-status-badge', text, map[status] || 'badge-muted');
    updateBadge('nav-batch-badge', status || 'Idle', map[status] || 'badge-muted');
  }

  function renderPipeline() {
    const target = document.getElementById('pipeline');
    target.innerHTML = '';
    PIPELINE.forEach((label, index) => {
      const chip = document.createElement('span');
      chip.className = 'pipeline-step pipeline-idle';
      if (index < pipelineIndex) chip.className = 'pipeline-step pipeline-done';
      if (index === pipelineIndex) chip.className = 'pipeline-step pipeline-active';
      chip.textContent = label;
      target.appendChild(chip);
    });
  }

  function setPipeline(index, note) {
    pipelineIndex = Math.max(pipelineIndex, index);
    renderPipeline();
    const title = document.getElementById('pipeline-note-title');
    const body = document.getElementById('pipeline-note');
    if (title) title.textContent = PIPELINE[Math.max(0, pipelineIndex)] || 'Ready';
    if (body && note) body.textContent = note;
  }

  function resetPipeline() {
    pipelineIndex = -1;
    chromeAlertShown = false;
    terminalAlertShown = false;
    renderPipeline();
    document.getElementById('pipeline-note-title').textContent = 'Waiting for Excel';
    document.getElementById('pipeline-note').textContent = 'Upload a file to start.';
  }

  function updatePipelineFromLog(entry) {
    const message = String(entry.message || '').toLowerCase();
    if (message.includes('connected to existing chrome')) {
      setPipeline(2, 'Chrome connected');
      if (!chromeAlertShown) {
        chromeAlertShown = true;
        toast('success', 'Chrome connected');
      }
    }
    if (message.includes('filled long_description') || message.includes('clicked next step')) setPipeline(3, 'Step 1 filled');
    if (message.includes('clicked brainstorm idea') || message.includes('generate video step is ready')) setPipeline(4, 'Brainstorm done');
    if (message.includes('clicked generate video') || message.includes('waiting for video generation')) setPipeline(5, 'Video generation in progress');
    if (message.includes('clicked create next product') || message.includes('step 1 is ready for next product')) setPipeline(6, 'Ready to create next product');
  }

  function resetPostprocessProgress() {
    stopPostprocessTicker();
    postprocessDuration = 0;
    postprocessSecond = 0;
    setPostprocessProgress(0, 0, 'Post-processing ready', 'Waiting for generated videos.');
  }

  function setPostprocessProgress(stepIndex, percent, title, detail) {
    const fill = document.getElementById('postprocess-fill');
    const percentEl = document.getElementById('postprocess-percent');
    const titleEl = document.getElementById('postprocess-title');
    const detailEl = document.getElementById('postprocess-detail');
    if (fill) fill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    if (percentEl) percentEl.textContent = `${Math.round(Math.max(0, Math.min(100, percent)))}%`;
    if (titleEl) titleEl.textContent = title;
    if (detailEl) detailEl.textContent = detail;
    renderPostprocessSteps(stepIndex);
  }

  function renderPostprocessSteps(activeIndex=0) {
    const target = document.getElementById('postprocess-steps');
    if (!target) return;
    target.innerHTML = POSTPROCESS_STEPS.map((label, index) => {
      const cls = index < activeIndex ? 'done' : (index === activeIndex ? 'active' : '');
      return `<div class="postprocess-step ${cls}">${escapeHtml(label)}</div>`;
    }).join('');
  }

  function updatePostprocessFromLog(entry) {
    const message = String(entry.message || '').toLowerCase();
    const rawMessage = String(entry.message || '');
    const durationMatch = rawMessage.match(/duration\\s+([0-9]+(?:\\.[0-9]+)?)s/i);
    if (durationMatch) postprocessDuration = Number(durationMatch[1]) || 0;
    if (message.includes('saved raw scene video')) {
      setPostprocessProgress(0, 22, 'Video saved', 'Preparing post-processing pipeline.');
    }
    if (message.includes('applying missing logo overlays') || message.includes('applied logo overlay')) {
      setPostprocessProgress(1, 42, 'Logo overlay complete', 'Logo layer is ready for subtitle burn-in.');
    }
    if (message.includes('subtitle generation')) {
      setPostprocessProgress(2, 58, 'Generating SRT subtitles', `Detected duration ${postprocessDuration || '?'}s.`);
    }
    if (message.includes('adding subtitles to')) {
      startSubtitleTicker();
    }
    if (message.includes('added subtitles')) {
      stopPostprocessTicker();
      setPostprocessProgress(2, 74, 'Subtitles added', 'Final video now includes burned-in Vietnamese subtitles.');
    }
    if (message.includes('subtitle skipped')) {
      stopPostprocessTicker();
      setPostprocessProgress(2, 66, 'Subtitles skipped', rawMessage);
    }
    if (message.includes('subtitle burn failed')) {
      stopPostprocessTicker();
      setPostprocessProgress(2, 66, 'Subtitle burn failed', 'Kept video without subtitles and saved the error.');
    }
    if (message.includes('batch completed')) {
      stopPostprocessTicker();
      setPostprocessProgress(4, 100, 'Batch completed', 'Videos are ready.');
    }
  }

  function startSubtitleTicker() {
    stopPostprocessTicker();
    postprocessSecond = 0;
    const total = Math.max(1, Math.ceil(postprocessDuration || 8));
    setPostprocessProgress(2, 62, 'Burning subtitles', `Dang them subtitle cho giay thu 0/${total}.`);
    postprocessTicker = setInterval(() => {
      postprocessSecond = Math.min(total, postprocessSecond + 1);
      const percent = 62 + Math.min(10, (postprocessSecond / total) * 10);
      setPostprocessProgress(2, percent, 'Burning subtitles', `Dang them subtitle cho giay thu ${postprocessSecond}/${total}.`);
      if (postprocessSecond >= total) stopPostprocessTicker();
    }, 700);
  }

  function stopPostprocessTicker() {
    if (postprocessTicker) {
      clearInterval(postprocessTicker);
      postprocessTicker = null;
    }
  }

  function renderMappingFields() {
    const target = document.getElementById('mapping-fields');
    const columns = currentDataset?.columns || [];
    target.innerHTML = '';
    FIELDS.forEach(field => {
      const wrapper = document.createElement('div');
      const disabled = columns.length ? '' : 'disabled';
      const options = ['<option value="">Select Excel column</option>'].concat(columns.map(col => `<option value="${escapeHtml(col)}">${escapeHtml(col)}</option>`)).join('');
      wrapper.innerHTML = `
        <label class="form-label" for="map-${field.key}">
          ${field.label}${field.required ? ' <span class="required">*</span>' : ''}
          <span class="info" title="${escapeHtml(field.help)}">i</span>
        </label>
        <select class="form-select" id="map-${field.key}" ${disabled}>${options}</select>
      `;
      target.appendChild(wrapper);
      wrapper.querySelector('select').addEventListener('change', () => {
        updateMappingReady();
        persistMappingDraft();
      });
    });
    if (currentDataset) applyInitialMapping();
    updateMappingReady();
  }

  function getSavedMapping() {
    try { return JSON.parse(localStorage.getItem(STORAGE.mapping) || '{}'); }
    catch { return {}; }
  }

  function getCurrentMapping() {
    const mapping = {};
    FIELDS.forEach(field => {
      const select = document.getElementById(`map-${field.key}`);
      mapping[field.key] = select ? (select.value || null) : null;
    });
    return mapping;
  }

  function setMappingValues(mapping) {
    const columns = currentDataset?.columns || [];
    FIELDS.forEach(field => {
      const select = document.getElementById(`map-${field.key}`);
      if (!select) return;
      const value = mapping?.[field.key] || '';
      select.value = columns.includes(value) ? value : '';
    });
    updateMappingReady();
  }

  function applyInitialMapping() {
    const saved = getSavedMapping();
    const hasSaved = FIELDS.some(field => saved[field.key]);
    setMappingValues(hasSaved ? saved : (currentDataset.mapping || {}));
  }

  function getMissingRequiredMapping() {
    const mapping = getCurrentMapping();
    return FIELDS.filter(field => field.required && !mapping[field.key]).map(field => field.key);
  }

  function updateMappingReady() {
    const missing = getMissingRequiredMapping();
    if (currentDataset && missing.length === 0) {
      updateBadge('mapping-chip', 'Ready', 'badge-success');
      updateHeaderBadge('mapping-status-badge', 'Mapping Ready', 'badge-success');
      setPipeline(1, 'Mapping ready');
      return true;
    }
    const label = currentDataset ? `Missing ${missing.length || 1}` : 'Not ready';
    updateBadge('mapping-chip', label, 'badge-muted');
    updateHeaderBadge('mapping-status-badge', currentDataset ? `Missing: ${missing.join(', ') || 'mapping'}` : 'Not ready', 'badge-muted');
    return false;
  }

  function persistMappingDraft() {
    if (!currentDataset) return;
    localStorage.setItem(STORAGE.mapping, JSON.stringify(getCurrentMapping()));
  }

  function autoMap() {
    if (!currentDataset) return alertBox('warning', 'Chưa có Excel', 'Upload file trước khi Auto Map.');
    setMappingValues(currentDataset.mapping || {});
    persistMappingDraft();
    toast('success', 'Auto Map applied');
  }

  function saveMapping() {
    if (!currentDataset) return alertBox('warning', 'Chưa có Excel', 'Upload file trước khi lưu mapping.');
    const missing = getMissingRequiredMapping();
    if (missing.length) return alertBox('error', 'Required mapping missing', `Thiếu: ${missing.join(', ')}`);
    localStorage.setItem(STORAGE.mapping, JSON.stringify(getCurrentMapping()));
    setPipeline(1, 'Mapping saved');
    alertBox('success', 'Mapping saved', 'Mapping đã được lưu vào localStorage.');
  }

  function resetMapping() {
    if (!currentDataset) return alertBox('warning', 'Chưa có Excel', 'Upload file trước khi reset mapping.');
    localStorage.removeItem(STORAGE.mapping);
    setMappingValues(currentDataset.mapping || {});
    toast('success', 'Mapping reset');
  }

  function previewMapping() {
    if (!currentDataset) return alertBox('warning', 'Chưa có Excel', 'Upload file trước khi preview mapping.');
    const missing = getMissingRequiredMapping();
    if (missing.length) return alertBox('error', 'Required mapping missing', `Thiếu: ${missing.join(', ')}`);
    const mapping = getCurrentMapping();
    const rows = currentDataset.raw_preview || [];
    const body = rows.slice(0, 3).map((row, index) => {
      const cells = FIELDS.map(field => {
        const column = mapping[field.key];
        const value = column ? (row[column] || '') : '';
        return `<td><strong>${escapeHtml(field.label)}</strong><br>${escapeHtml(String(value).slice(0, 160))}</td>`;
      }).join('');
      return `<tr><th>Row ${index + 1}</th>${cells}</tr>`;
    }).join('');
    const html = body ? `<table class="mapping-preview"><tbody>${body}</tbody></table>` : '<p>Không có dữ liệu preview.</p>';
    if (window.Swal) {
      Swal.fire({title:'Preview Mapping',html,width:900,confirmButtonColor:'#4f46e5'});
    } else {
      alert('Preview Mapping');
    }
  }

  function stopStream() {
    if (evtSource) { evtSource.close(); evtSource = null; }
    setBadge('queued');
    setSceneManualPauseState(false);
  }

  function startLogStream(runId) {
    stopStream();
    currentRunId = runId;
    clearLog();
    evtSource = new EventSource(`/api/runs/${runId}/stream`);
    evtSource.addEventListener('log', e => {
      const d = JSON.parse(e.data);
      appendLog(d.time, d.level, d.message);
    });
    evtSource.addEventListener('status', e => {
      const d = JSON.parse(e.data);
      setBadge(d.status);
      setSceneManualPauseState(Boolean(d.paused), d.pause_message || 'Paused for manual scene setup.');
      if (d.status === 'running') setPipeline(2, 'Batch running');
      if (d.status === 'completed') {
        setPipeline(6, 'Batch completed');
        loadVideoBatches(currentRunId);
        setStatus('Batch hoàn thành!');
        if (!terminalAlertShown) {
          terminalAlertShown = true;
          alertBox('success', 'Batch completed', 'Batch đã chạy xong.');
        }
        stopStream();
        setBadge('completed');
        
        if (document.getElementById('auto-download-zip').checked) {
          setTimeout(() => {
            downloadBatchZip(currentRunId);
          }, 1000);
        }
      } else if (d.status === 'failed') {
        setStatus('Batch thất bại: ' + (d.error || ''), false);
        if (!terminalAlertShown) {
          terminalAlertShown = true;
          alertBox('error', 'Batch failed', d.error || 'Có lỗi khi chạy batch.');
        }
        stopStream();
        setBadge('failed');
      }
    });
    evtSource.onerror = () => {
      if (!currentRunId && evtSource) evtSource.close();
    };
  }

  async function uploadFile() {
    const input = document.getElementById('file');
    if (!input.files[0]) {
      setStatus('Chọn file trước!', false);
      return alertBox('warning', 'Chưa chọn file', 'Chọn file Excel hoặc CSV trước khi upload.');
    }
    resetPipeline();
    setStatus('Đang upload...');
    const form = new FormData();
    form.append('file', input.files[0]);
    const resp = await fetch('/api/datasets/upload', {method:'POST',body:form});
    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data.dataset_id) {
      currentDataset = data;
      document.getElementById('dataset-id').value = data.dataset_id;
      document.getElementById('dataset-info').innerHTML =
        `<strong>${escapeHtml(data.original_name)}</strong> - <span style="color:var(--success-text);font-weight:700">${data.row_count} dòng</span> - Sheet: ${escapeHtml(data.sheet_name || 'N/A')} - ID: ${escapeHtml(data.dataset_id)}`;
      updateBadge('dataset-chip', `${data.row_count} rows`, 'badge-success');
      updateHeaderBadge('upload-status-badge', `${data.row_count} rows loaded`, 'badge-success');
      renderMappingFields();
      setPipeline(0, 'Excel loaded');
      updateSceneModeAvailability(false);
      setStatus(`Upload thành công: ${data.row_count} dòng`);
      updateFloatingRunState();
      alertBox('success', 'Upload success', `${data.original_name} đã được tải lên.`);
      loadDatasetHistory();
    } else {
      currentDataset = null;
      updateFloatingRunState();
      const message = data.detail || JSON.stringify(data);
      setStatus('Upload thất bại: ' + message, false);
      alertBox('error', 'Upload failed', message);
    }
  }

  async function loadDatasetById(dsId, showErrors=true) {
    if (currentDataset?.dataset_id === dsId) return true;
    const resp = await fetch(`/api/datasets/${encodeURIComponent(dsId)}`);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.dataset_id) {
      currentDataset = null;
      updateFloatingRunState();
      if (showErrors) alertBox('error', 'Dataset not found', data.detail || dsId);
      return false;
    }
    currentDataset = data;
    document.getElementById('dataset-info').innerHTML =
      `<strong>${escapeHtml(data.original_name)}</strong> - <span style="color:var(--success-text);font-weight:700">${data.row_count} dòng</span> - Sheet: ${escapeHtml(data.sheet_name || 'N/A')} - ID: ${escapeHtml(data.dataset_id)}`;
    updateBadge('dataset-chip', `${data.row_count} rows`, 'badge-success');
    updateHeaderBadge('upload-status-badge', `${data.row_count} rows loaded`, 'badge-success');
    renderMappingFields();
    setPipeline(0, 'Excel loaded');
    updateSceneModeAvailability(false);
    updateFloatingRunState();
    return true;
  }

  async function continueAfterSceneManual() {
    if (!currentRunId) return;
    const button = document.getElementById('continue-scene-btn');
    if (!button || button.disabled) return;
    button.disabled = true;
    const resp = await fetch(`/api/runs/${currentRunId}/continue`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'continue_after_scene_manual'})
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok) {
      setStatus('Da gui tin hieu Continue / Done.');
      toast('success', 'Continue sent');
      setSceneManualPauseState(false);
      return;
    }
    button.disabled = false;
    alertBox('error', 'Continue failed', data.detail || 'Khong the tiep tuc run nay.');
  }

  async function startRun() {
    const dsId = document.getElementById('dataset-id').value.trim();
    if (!dsId) {
      setStatus('Nhập Dataset ID!', false);
      return alertBox('warning', 'Thiếu Dataset ID', 'Dataset ID là bắt buộc.');
    }
    const datasetReady = await loadDatasetById(dsId, true);
    if (!datasetReady) return;
    const missing = getMissingRequiredMapping();
    if (missing.length) {
      setStatus('Required mapping missing: ' + missing.join(', '), false);
      return alertBox('error', 'Required mapping missing', `Thiếu: ${missing.join(', ')}`);
    }
    let presetJson = null;
    if (document.getElementById('preset-json').value.trim()) {
      const parsedPreset = parsePresetJson(false);
      if (!parsedPreset) {
        setStatus('Preset JSON invalid.', false);
        return alertBox('error', 'Preset JSON invalid', 'Kiểm tra lại JSON preset trước khi chạy bot.');
      }
      presetJson = JSON.stringify(parsedPreset);
      localStorage.setItem(STORAGE.presetJson, document.getElementById('preset-json').value);
    }
    const logoFile = document.getElementById('logo-file').files[0];
    if (logoFile && !uploadedLogoPath) {
      setStatus('Đang upload logo...');
      const logoReady = await uploadLogo(true);
      if (!logoReady) {
        setStatus('Upload logo thất bại.', false);
        return alertBox('error', 'Upload logo failed', 'Không thể upload logo trước khi chạy bot.');
      }
    }
    persistSettings();
    persistMappingDraft();
    updateSceneModeAvailability(false);
    clearLog();
    terminalAlertShown = false;
    chromeAlertShown = false;
    setStatus('Đang khởi động bot...');
    const floatingRunButton = document.getElementById('floating-run-btn');
    if (floatingRunButton) floatingRunButton.disabled = true;
    setBadge('queued');
    setSceneManualPauseState(false);
    const sceneMode = getSceneMode();
    if (sceneMode === 'auto_excel' && !datasetHasSceneColumns()) {
      setStatus('Excel khong co cot scene, chuyen sang Skip.');
    }
    const payload = {
      dataset_id: dsId,
      mapping: getCurrentMapping(),
      start: Number(document.getElementById('start').value || 1),
      count: Number(document.getElementById('count').value || 1),
      slow_mo: Number(document.getElementById('slow-mo').value || 400),
      wait_timeout_seconds: Number(document.getElementById('wait-timeout').value || 180),
      cdp_port: Number(document.getElementById('cdp-port').value || 9222),
      scene_mode: sceneMode === 'auto_excel' && !datasetHasSceneColumns() ? 'skip' : sceneMode,
      video_model: document.getElementById('video-model').value || 'Veo 3.1 - Lite',
      aspect_ratio: document.getElementById('aspect-ratio').value || '9:16',
      multi_clip_mode: document.getElementById('multi-clip-mode').value || 'auto',
      scene_builder_mode: document.getElementById('scene-builder-mode').value || 'native_flow',
      target_final_duration: Number(document.getElementById('target-final-duration').value || 20),
      download_mode: document.getElementById('download-mode').value || 'save_local',
      continue_on_error: document.getElementById('continue-on-error').checked,
      max_generate_retries: Number(document.getElementById('max-generate-retries').value || 1),
      enable_subtitles: document.getElementById('enable-subtitles').checked,
      subtitle_source: document.getElementById('subtitle-source').value || 'voiceover',
      subtitle_position: 'bottom',
      subtitle_font_size: Number(document.getElementById('subtitle-font-size').value || 18),
      subtitle_style: 'clean',
      enable_product_image_cleanup: document.getElementById('enable-product-image-cleanup').checked,
      cleanup_mode: document.getElementById('cleanup-mode').value || 'auto',
      cleanup_background: 'transparent',
      cleanup_sharpen: true,
      cleanup_white_background_fallback: true,
      cleanup_cache_enabled: true,
      enable_logo_overlay: document.getElementById('enable-logo-overlay').checked,
      logo_file_path: document.getElementById('logo-file-path').value.trim() || uploadedLogoPath || null,
      logo_position: document.getElementById('logo-position').value || 'top-right',
      logo_width_percent: Number(document.getElementById('logo-width-percent').value || 12),
      logo_margin: Number(document.getElementById('logo-margin').value || 32),
      auto_logo_overlay_after_batch: document.getElementById('auto-logo-overlay-after-batch').checked,
      ui_base_url: window.location.origin,
      preset_json: presetJson,
      website_logo_path: uploadedLogoPath || null,
      user_data_dir: "C:/Users/acer/AppData/Local/Google/Chrome/User Data",
      profile_directory: "Profile 12"
    };
    const resp = await fetch('/api/runs', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await resp.json().catch(() => ({}));
    updateFloatingRunState();
    if (resp.ok && data.run_id) {
      setStatus(`Run started: ${data.run_id}`);
      startLogStream(data.run_id);
      switchSection('log');
    } else {
      const message = data.detail || JSON.stringify(data);
      setStatus('Lỗi: ' + message, false);
      alertBox('error', 'Batch failed', message);
      setBadge('failed');
    }
  }
</script>
</body>
</html>"""
    return html.replace("__FLOW_URL__", flow_url)
