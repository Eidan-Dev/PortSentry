#!/usr/bin/env python3
"""
PortSentry Mini — a terminal dashboard for hunting down stale listening ports.

Dependencies : pip install textual psutil
Run          : python portsentry.py
               (sudo recommended on Linux/macOS to see every process,
                including those owned by root or Docker)

Keys:
  k / Enter  kill the process on the selected row (SIGTERM, then SIGKILL if needed)
  /          filter (port, name, command...)   Escape: close the filter
  r          refresh now
  q          quit
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import psutil
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Input, Static

KIND_STYLE = {
    "Node": "bold #9ece6a",
    "Python": "bold #e0af68",
    "Docker": "bold #7dcfff",
    "Other": "#a9b1d6",
}

CSS = """
Screen {
    background: #0b0d10;
}
#filter {
    display: none;
    margin: 0 1;
    border: tall #7aa2f7;
}
#filter.show {
    display: block;
}
DataTable {
    height: 1fr;
    border: round #2a2f3a;
    background: #0b0d10;
}
DataTable > .datatable--header {
    background: #161a22;
    color: #7aa2f7;
    text-style: bold;
}
DataTable > .datatable--cursor {
    background: #1f2937;
    color: #e5e7eb;
}
DataTable > .datatable--even-row {
    background: #0f1217;
}
#banner {
    height: 3;
    padding: 1 2;
    margin: 0 1;
    background: #11141a;
    color: #6b7280;
    border: round #2a2f3a;
}
#banner.dark {
    background: #2a0000;
    color: #ff8a80;
    border: round #b71c1c;
}
#banner.bright {
    background: #ff1744;
    color: #ffffff;
    text-style: bold;
    border: round #ff8a80;
}
"""


@dataclass
class Listener:
    port: int
    pid: Optional[int]
    name: str
    cmd: str
    user: str
    kind: str


def classify(name: str, cmd: str) -> str:
    """Guess the process type from its name and command line."""
    n = name.lower()
    c = cmd.lower()
    if "docker" in n or "containerd" in n or "docker-proxy" in c:
        return "Docker"
    if "node" in n or "bun" in n or "deno" in n or "npm" in n or "node " in c:
        return "Node"
    if "python" in n or any(k in c for k in ("uvicorn", "gunicorn", "flask", "django")):
        return "Python"
    return "Other"


def scan() -> list[Listener]:
    """List TCP listening ports, deduplicated (IPv4 + IPv6 -> one row)."""
    try:
        conns = psutil.net_connections(kind="tcp")
    except psutil.AccessDenied:
        return []

    seen: set[tuple[int, Optional[int]]] = set()
    out: list[Listener] = []
    for c in conns:
        if c.status != psutil.CONN_LISTEN or c.laddr is None:
            continue
        key = (c.laddr.port, c.pid)
        if key in seen:
            continue
        seen.add(key)

        name, cmd, user = "?", "", "?"
        if c.pid:
            try:
                p = psutil.Process(c.pid)
                name = p.name()
                cmd = " ".join(p.cmdline())
                user = p.username()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        out.append(Listener(
            port=c.laddr.port,
            pid=c.pid,
            name=name,
            cmd=cmd,
            user=user,
            kind=classify(name, cmd),
        ))
    return sorted(out, key=lambda l: (l.port, l.pid or 0))


def kill_pid(pid: int) -> str:
    """Send SIGTERM, wait briefly, then SIGKILL if the process is still alive."""
    try:
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=1.5)
            return "terminated (SIGTERM)"
        except psutil.TimeoutExpired:
            p.kill()
            p.wait(timeout=1)
            return "force-killed (SIGKILL)"
    except psutil.NoSuchProcess:
        return "already gone"
    except psutil.AccessDenied:
        return "access denied, re-run with sudo"
    except psutil.TimeoutExpired:
        return "still alive after SIGKILL"


class PortSentry(App):
    TITLE = "PortSentry Mini"
    CSS = CSS
    BINDINGS = [
        Binding("k", "kill", "Kill"),
        Binding("r", "refresh", "Refresh"),
        Binding("slash", "filter", "Filter"),
        Binding("escape", "close_filter", "Close filter", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.listeners: list[Listener] = []
        self._by_key: dict[str, Listener] = {}
        self.filter_text = ""
        self._flash_timer = None
        self._flash_ticks = 0
        self._flash_base = ""

    # ---------- layout ----------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="filter: port, name, command...", id="filter")
        yield DataTable(id="table")
        yield Static("Ready. Select a port and press k.", id="banner")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("PORT", "PROTO", "PID", "PROCESS", "TYPE", "COMMAND", "USER")
        self.reload()
        self.set_interval(2.0, self.reload)

    # ---------- data ----------
    def reload(self) -> None:
        self.listeners = scan()
        self.render_table()
        unknown = sum(1 for l in self.listeners if l.pid is None)
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        hint = ""
        if unknown and not is_root:
            hint = f" · ⚠ {unknown} without PID, re-run with sudo"
        self.sub_title = f"{len(self.listeners)} listening port(s){hint}"

    def _current_key(self) -> Optional[str]:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    def render_table(self) -> None:
        table = self.query_one(DataTable)
        keep = self._current_key()
        table.clear()
        self._by_key.clear()

        q = self.filter_text.strip().lower()
        for l in self.listeners:
            blob = f"{l.port} {l.name} {l.kind} {l.cmd} {l.pid}".lower()
            if q and q not in blob:
                continue
            key = f"{l.port}-{l.pid}"
            self._by_key[key] = l
            table.add_row(
                Text(str(l.port), style="bold #f7768e"),
                "TCP",
                str(l.pid) if l.pid else "-",
                l.name,
                Text(l.kind, style=KIND_STYLE[l.kind]),
                l.cmd[:60],
                l.user,
                key=key,
            )

        if keep and keep in self._by_key:
            table.move_cursor(row=table.get_row_index(keep))

    # ---------- actions ----------
    def action_refresh(self) -> None:
        self.reload()

    def action_filter(self) -> None:
        inp = self.query_one("#filter", Input)
        inp.add_class("show")
        inp.focus()

    def action_close_filter(self) -> None:
        inp = self.query_one("#filter", Input)
        if inp.has_class("show"):
            inp.remove_class("show")
            inp.value = ""
            self.filter_text = ""
            self.render_table()
            self.query_one(DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            self.filter_text = event.value
            self.render_table()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_kill()

    def action_kill(self) -> None:
        key = self._current_key()
        if not key or key not in self._by_key:
            return
        l = self._by_key[key]
        if l.pid is None:
            self.notify("Unknown PID: re-run PortSentry with sudo.", severity="warning")
            return
        self.start_flash(f"☠  KILL {l.name} · PID {l.pid} · port {l.port}")
        self.kill_worker(l)

    # ---------- red animation ----------
    def start_flash(self, text: str) -> None:
        banner = self.query_one("#banner", Static)
        self._flash_base = text
        banner.update(text)
        self._flash_ticks = 0
        if self._flash_timer:
            self._flash_timer.stop()
        self._flash_timer = self.set_interval(0.12, self._flash_tick)

    def _flash_tick(self) -> None:
        self._flash_ticks += 1
        banner = self.query_one("#banner", Static)
        on = self._flash_ticks % 2 == 0
        banner.set_class(on, "bright")
        banner.set_class(not on, "dark")
        # progress bar that fills up in a loop
        filled = self._flash_ticks % 16
        bar = "█" * filled + "░" * (16 - filled)
        banner.update(f"{self._flash_base}  ▕{bar}▏")

    def end_flash(self, text: str) -> None:
        if self._flash_timer:
            self._flash_timer.stop()
            self._flash_timer = None
        banner = self.query_one("#banner", Static)
        banner.set_classes("")
        banner.update(text)
        self.set_timer(0.4, self.reload)

    @work(thread=True)
    def kill_worker(self, l: Listener) -> None:
        result = kill_pid(l.pid)
        hint = ""
        if l.name == "docker-proxy":
            hint = "  (tip: docker stop <container>)"
        self.call_from_thread(self.end_flash, f"✔ {l.name} · port {l.port}: {result}{hint}")


if __name__ == "__main__":
    PortSentry().run()
