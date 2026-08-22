#!/usr/bin/env python3
"""Windows desktop launcher for the Trader AI Pro signal service."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, END, StringVar, Tk, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable


APP_NAME = "Trader AI Pro"
APP_VERSION = "0.1.0"
DOCKER_DOWNLOAD_URL = "https://www.docker.com/products/docker-desktop/"
SERVICE_NAME = "freqtrade-signal"
CONFIG_CONTAINER_PATH = "/freqtrade/user_data/configs/config.signal.json"
STRATEGY_NAME = "TraderAIProSignalStrategy"
MODEL_NAME = "LightGBMRegressor"

REQUIRED_ASSETS = (
    ".env.example",
    "docker-compose.yml",
    "scripts/prepare_bybit_public_data.py",
    "scripts/run_offline_backtest.py",
    "scripts/validate_backtest.py",
    "user_data/configs/config.backtest-smoke.json",
    "user_data/configs/config.signal.json",
    "user_data/strategies/__init__.py",
    "user_data/strategies/TraderAIProSignalStrategy.py",
)

RUNTIME_DIRECTORIES = (
    "user_data/backtest_results",
    "user_data/data",
    "user_data/logs",
    "user_data/models",
)


class LauncherError(RuntimeError):
    """A user-facing launcher failure."""


def resource_root() -> Path:
    """Return the repository root or PyInstaller extraction directory."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def default_workdir() -> Path:
    """Return a stable per-user runtime directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "TraderAIPro"
    return Path.home() / ".trader-ai-pro"


def parse_env(path: Path) -> dict[str, str]:
    """Parse the small dotenv subset used by this project."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate_telegram(enabled: bool, token: str, chat_id: str) -> None:
    """Validate Telegram values before writing the local secret file."""
    if not enabled:
        return
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
        raise LauncherError("启用 Telegram 后必须填写有效的 Bot Token。")
    if not re.fullmatch(r"-?\d+", chat_id):
        raise LauncherError("Telegram Chat ID 必须是整数，例如 123456789 或 -1001234567890。")


def write_env(path: Path, enabled: bool, token: str, chat_id: str) -> None:
    """Atomically write local runtime settings without logging secrets."""
    validate_telegram(enabled, token, chat_id)
    for value in (token, chat_id):
        if "\n" in value or "\r" in value:
            raise LauncherError("配置值不能包含换行符。")
    content = (
        "# Generated locally by Trader AI Pro Launcher. Never commit this file.\n"
        f"TELEGRAM_ENABLED={'true' if enabled else 'false'}\n"
        f"TELEGRAM_BOT_TOKEN={token if enabled else ''}\n"
        f"TELEGRAM_CHAT_ID={chat_id if enabled else ''}\n"
        "FREQTRADE_IMAGE=freqtradeorg/freqtrade:stable_freqai\n"
        "TZ=Asia/Singapore\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def validate_signal_config(path: Path) -> None:
    """Enforce the signal-only safety contract before Docker is started."""
    config = json.loads(path.read_text(encoding="utf-8"))
    exchange = config.get("exchange", {})
    checks = (
        (config.get("dry_run") is True, "dry_run 必须保持 true"),
        (config.get("trading_mode") == "futures", "trading_mode 必须是 futures"),
        (config.get("margin_mode") == "isolated", "margin_mode 必须是 isolated"),
        (exchange.get("name") == "bybit", "交易所必须是 Bybit"),
        (exchange.get("api_key", "") == "", "信号模式不能包含 Bybit API Key"),
        (exchange.get("secret", "") == "", "信号模式不能包含 Bybit Secret"),
        (config.get("force_entry_enable") is False, "强制开仓必须关闭"),
        (config.get("freqai", {}).get("enabled") is True, "FreqAI 必须启用"),
        (not config.get("api_server", {}).get("enabled", False), "API Server 必须关闭"),
    )
    for condition, message in checks:
        if not condition:
            raise LauncherError(f"安全检查失败：{message}。")


def install_assets(source_root: Path, destination_root: Path) -> None:
    """Install immutable project assets while preserving runtime state and .env."""
    for relative in REQUIRED_ASSETS:
        source = source_root / relative
        if not source.is_file():
            raise LauncherError(f"安装包缺少文件：{relative}")
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for relative in RUNTIME_DIRECTORIES:
        (destination_root / relative).mkdir(parents=True, exist_ok=True)
    env_path = destination_root / ".env"
    if not env_path.exists():
        shutil.copy2(source_root / ".env.example", env_path)
    validate_signal_config(destination_root / "user_data/configs/config.signal.json")


def find_docker() -> str:
    """Resolve docker.exe from PATH or Docker Desktop's standard location."""
    executable = shutil.which("docker")
    if executable:
        return executable
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = Path(program_files) / "Docker/Docker/resources/bin/docker.exe"
        if candidate.is_file():
            return str(candidate)
    raise LauncherError("未检测到 Docker Desktop。请先安装并启动 Docker Desktop。")


def docker_desktop_executable() -> Path | None:
    if os.name != "nt":
        return None
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidate = Path(program_files) / "Docker/Docker/Docker Desktop.exe"
    return candidate if candidate.is_file() else None


def command_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class TraderAIProLauncher:
    """Small Tk desktop front-end around the safe Docker Compose workflow."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("920x700")
        self.root.minsize(760, 580)
        self.source_root = resource_root()
        self.workdir = default_workdir()
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.telegram_enabled = BooleanVar(value=False)
        self.telegram_token = StringVar(value="")
        self.telegram_chat_id = StringVar(value="")
        self.status_text = StringVar(value="准备就绪：当前为模拟信号模式，不会发送真实订单。")
        self._build_ui()
        self._load_settings()
        self.root.after(100, self._drain_messages)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text=APP_NAME, font=("Segoe UI", 20, "bold"))
        title.pack(anchor="w")
        safety = ttk.Label(
            outer,
            text="安全模式：Bybit USDT 永续 · FreqAI · 模拟持仓 · 1× 杠杆 · 不接收交易所密钥",
        )
        safety.pack(anchor="w", pady=(2, 14))

        settings = ttk.LabelFrame(outer, text="Telegram 通知", padding=12)
        settings.pack(fill="x")
        ttk.Checkbutton(
            settings,
            text="启用 Telegram",
            variable=self.telegram_enabled,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(settings, text="Bot Token").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(settings, textvariable=self.telegram_token, show="●").grid(
            row=1, column=1, sticky="ew", pady=(10, 0)
        )
        ttk.Label(settings, text="Chat ID").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.telegram_chat_id).grid(
            row=2, column=1, sticky="ew", pady=(8, 0)
        )
        ttk.Button(settings, text="保存 Telegram 配置", command=self.save_settings).grid(
            row=0, column=1, sticky="e"
        )
        settings.columnconfigure(1, weight=1)

        actions = ttk.LabelFrame(outer, text="运行控制", padding=12)
        actions.pack(fill="x", pady=(12, 0))
        buttons = (
            ("一键安装并启动", self.install_and_start),
            ("启动信号模式", self.start_service),
            ("停止", self.stop_service),
            ("查看状态", self.show_status),
            ("查看最近日志", self.show_logs),
            ("运行完整测试", self.run_smoke_test),
            ("打开数据目录", self.open_data_directory),
            ("安装 Docker Desktop", lambda: webbrowser.open(DOCKER_DOWNLOAD_URL)),
        )
        self.action_buttons: list[ttk.Button] = []
        for index, (label, callback) in enumerate(buttons):
            button = ttk.Button(actions, text=label, command=callback)
            button.grid(row=index // 4, column=index % 4, padx=4, pady=4, sticky="ew")
            actions.columnconfigure(index % 4, weight=1)
            self.action_buttons.append(button)

        ttk.Label(outer, textvariable=self.status_text).pack(anchor="w", pady=(12, 4))
        self.output = ScrolledText(outer, height=20, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True)
        self._append_log(f"运行目录：{self.workdir}")
        self._append_log("首次使用请填写 Telegram 配置，然后点击“一键安装并启动”。")

    def _load_settings(self) -> None:
        values = parse_env(self.workdir / ".env")
        self.telegram_enabled.set(values.get("TELEGRAM_ENABLED", "false").lower() == "true")
        self.telegram_token.set(values.get("TELEGRAM_BOT_TOKEN", ""))
        self.telegram_chat_id.set(values.get("TELEGRAM_CHAT_ID", ""))

    def _append_log(self, message: str) -> None:
        self.output.insert(END, f"{message.rstrip()}\n")
        self.output.see(END)

    def _post_log(self, message: str) -> None:
        self.messages.put(("log", message))

    def _post_status(self, message: str) -> None:
        self.messages.put(("status", message))

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_text.set(str(payload))
                elif kind == "done":
                    self.busy = False
                    self._set_buttons_enabled(True)
                    if isinstance(payload, Exception):
                        self.status_text.set("操作失败，请查看日志。")
                        self._append_log(f"错误：{payload}")
                        messagebox.showerror(APP_NAME, str(payload))
                    else:
                        self.status_text.set(str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._drain_messages)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.action_buttons:
            button.configure(state=state)

    def _run_task(self, label: str, task: Callable[[], str]) -> None:
        if self.busy:
            messagebox.showinfo(APP_NAME, "当前操作尚未完成，请稍候。")
            return
        self.busy = True
        self._set_buttons_enabled(False)
        self.status_text.set(label)
        self._append_log(f"\n== {label} ==")

        def worker() -> None:
            try:
                result = task()
            except Exception as exc:  # noqa: BLE001 - converted to a UI-safe message
                self.messages.put(("done", exc))
            else:
                self.messages.put(("done", result))

        threading.Thread(target=worker, daemon=True).start()

    def _save_settings_now(self) -> None:
        install_assets(self.source_root, self.workdir)
        write_env(
            self.workdir / ".env",
            self.telegram_enabled.get(),
            self.telegram_token.get().strip(),
            self.telegram_chat_id.get().strip(),
        )

    def save_settings(self) -> None:
        try:
            self._save_settings_now()
        except (LauncherError, OSError, json.JSONDecodeError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.status_text.set("Telegram 配置已安全保存到本机。")
        self._append_log("Telegram 配置已保存；Bot Token 未输出到日志。")

    def _run_command(self, args: list[str], *, check: bool = True) -> int:
        safe_display = " ".join(args)
        self._post_log(f"> {safe_display}")
        process = subprocess.Popen(
            args,
            cwd=self.workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=command_flags(),
        )
        assert process.stdout is not None
        for line in process.stdout:
            self._post_log(line.rstrip())
        return_code = process.wait()
        if check and return_code != 0:
            raise LauncherError(f"命令执行失败（退出码 {return_code}）：{safe_display}")
        return return_code

    def _docker_command(self, *args: str) -> list[str]:
        return [find_docker(), *args]

    def _compose_command(self, *args: str) -> list[str]:
        return self._docker_command("compose", "-f", str(self.workdir / "docker-compose.yml"), *args)

    def _ensure_docker_running(self) -> None:
        docker = find_docker()
        if self._docker_is_ready(docker):
            return
        desktop = docker_desktop_executable()
        if desktop is None:
            raise LauncherError("Docker 已安装但服务未运行。请先启动 Docker Desktop。")
        self._post_log("正在启动 Docker Desktop，请稍候……")
        os.startfile(desktop)  # type: ignore[attr-defined]
        for _ in range(60):
            time.sleep(2)
            if self._docker_is_ready(docker):
                self._post_log("Docker Desktop 已就绪。")
                return
        raise LauncherError("Docker Desktop 在 120 秒内未就绪，请打开 Docker Desktop 检查状态。")

    def _docker_is_ready(self, docker: str) -> bool:
        result = subprocess.run(
            [docker, "info"],
            cwd=self.workdir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=command_flags(),
        )
        return result.returncode == 0

    def _prepare(self) -> None:
        self._post_status("正在准备安全运行文件……")
        self._save_settings_now()
        compose = (self.workdir / "docker-compose.yml").read_text(encoding="utf-8")
        if 'FREQTRADE__DRY_RUN: "true"' not in compose:
            raise LauncherError("安全检查失败：Docker Compose 未强制 dry-run。")
        if "FREQTRADE__EXCHANGE__KEY" in compose or "FREQTRADE__EXCHANGE__SECRET" in compose:
            raise LauncherError("安全检查失败：信号模式不能接收交易所密钥。")
        self._ensure_docker_running()
        self._run_command(self._compose_command("config", "--quiet"))

    def install_and_start(self) -> None:
        def task() -> str:
            self._prepare()
            self._post_status("正在下载 Freqtrade/FreqAI 官方镜像……")
            self._run_command(self._compose_command("pull"))
            self._post_status("正在下载最近 90 天 Bybit 行情……")
            self._run_command(
                self._compose_command(
                    "run",
                    "--rm",
                    SERVICE_NAME,
                    "download-data",
                    "--config",
                    CONFIG_CONTAINER_PATH,
                    "--timeframes",
                    "5m",
                    "15m",
                    "1h",
                    "--days",
                    "90",
                )
            )
            self._post_status("正在启动信号服务……")
            self._run_command(self._compose_command("up", "-d"))
            self._run_command(self._compose_command("ps"))
            return "信号模式已启动。首次 FreqAI 训练需要等待，请稍后查看日志。"

        self._run_task("首次安装并启动", task)

    def start_service(self) -> None:
        def task() -> str:
            self._prepare()
            self._run_command(self._compose_command("up", "-d"))
            self._run_command(self._compose_command("ps"))
            return "信号模式已启动。"

        self._run_task("启动信号模式", task)

    def stop_service(self) -> None:
        def task() -> str:
            self._prepare()
            self._run_command(self._compose_command("down"))
            return "Trader AI Pro 已停止；行情、模型和日志仍保存在本机。"

        self._run_task("停止服务", task)

    def show_status(self) -> None:
        def task() -> str:
            self._prepare()
            self._run_command(self._compose_command("ps"))
            return "状态查询完成。"

        self._run_task("查看运行状态", task)

    def show_logs(self) -> None:
        def task() -> str:
            self._prepare()
            self._run_command(self._compose_command("logs", "--tail=200", SERVICE_NAME))
            return "最近 200 行日志已显示。"

        self._run_task("读取最近日志", task)

    def run_smoke_test(self) -> None:
        def task() -> str:
            self._prepare()
            self._run_command(self._compose_command("pull"))
            self._post_status("正在准备 Bybit 官方公开测试数据……")
            self._run_command(
                self._compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "python",
                    SERVICE_NAME,
                    "/freqtrade/scripts/prepare_bybit_public_data.py",
                    "--symbol",
                    "SOLUSDT",
                    "--pair",
                    "SOL/USDT:USDT",
                    "--start",
                    "2021-07-01",
                    "--end",
                    "2021-07-08",
                )
            )
            self._post_status("正在训练小型 FreqAI 模型并回测……")
            self._run_command(
                self._compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "python",
                    SERVICE_NAME,
                    "/freqtrade/scripts/run_offline_backtest.py",
                    "--config",
                    CONFIG_CONTAINER_PATH,
                    "--config",
                    "/freqtrade/user_data/configs/config.backtest-smoke.json",
                    "--strategy",
                    STRATEGY_NAME,
                    "--freqaimodel",
                    MODEL_NAME,
                    "--timerange",
                    "20210705-20210707",
                )
            )
            self._run_command(
                self._compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "python",
                    SERVICE_NAME,
                    "/freqtrade/scripts/validate_backtest.py",
                    "/freqtrade/user_data/backtest_results",
                    "--strategy",
                    STRATEGY_NAME,
                )
            )
            return "完整测试通过。结果位于运行目录的 user_data/backtest_results。"

        self._run_task("运行端到端 FreqAI 测试", task)

    def open_data_directory(self) -> None:
        try:
            install_assets(self.source_root, self.workdir)
            if os.name == "nt":
                os.startfile(self.workdir)  # type: ignore[attr-defined]
            else:
                webbrowser.open(self.workdir.as_uri())
        except (LauncherError, OSError, json.JSONDecodeError) as exc:
            messagebox.showerror(APP_NAME, str(exc))


def self_test() -> int:
    """Verify packaged resources without starting Docker or opening a window."""
    try:
        with tempfile.TemporaryDirectory(prefix="trader-ai-pro-launcher-") as temporary:
            destination = Path(temporary)
            install_assets(resource_root(), destination)
            validate_signal_config(destination / "user_data/configs/config.signal.json")
            write_env(destination / ".env", False, "", "")
    except (LauncherError, OSError, json.JSONDecodeError) as exc:
        print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
        return 1
    print("Windows launcher self-test passed.")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    root = Tk()
    try:
        ttk.Style(root).theme_use("vista" if os.name == "nt" else "clam")
    except Exception:  # noqa: BLE001 - optional platform theme
        pass
    TraderAIProLauncher(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
