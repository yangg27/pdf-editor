"""后台任务执行器。

界面里所有耗时操作（打开大文件、合并、压缩、导出、渲染）都通过
:class:`TaskRunner` 放到守护线程里执行，主线程只负责更新 UI，从而避免
「界面假死」。

约定：
- ``fn(progress)`` 中调用 ``progress(i, total, text)`` 上报进度；
- ``on_done`` / ``on_error`` / ``on_progress`` 全部在 **主线程** 执行；
- 同一时刻只允许一个独占任务，避免并发修改同一文档造成状态错乱。
"""

from __future__ import annotations

import queue
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

import tkinter as tk

ProgressFn = Callable[..., None]
JobFn = Callable[[ProgressFn], Any]
DoneFn = Callable[[Any], None]
ErrorFn = Callable[[BaseException, str], None]
ProgressCb = Callable[[int, int, str], None]


@dataclass
class _Job:
    name: str
    fn: JobFn
    events: "queue.Queue[tuple]" = field(default_factory=queue.Queue)


class TaskRunner:
    """在主线程之外执行耗时操作，并把结果回投到主线程。"""

    def __init__(self, root: tk.Misc):
        self.root = root
        self._busy = False
        self._current: str | None = None
        self._lock = threading.Lock()
        self._state_handlers: list[Callable[[bool, str | None], None]] = []

    # ------------------------------------------------------------ 状态
    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def current(self) -> str | None:
        return self._current

    def on_state_change(self, handler: Callable[[bool, str | None], None]) -> None:
        """注册忙碌状态变化回调。"""
        self._state_handlers.append(handler)

    def _set_state(self, busy: bool, name: str | None) -> None:
        self._busy = busy
        self._current = name
        for h in self._state_handlers:
            try:
                h(busy, name)
            except Exception:
                traceback.print_exc()

    # ------------------------------------------------------------ 提交
    def submit(
        self,
        name: str,
        fn: JobFn,
        on_done: DoneFn | None = None,
        *,
        on_error: ErrorFn | None = None,
        on_progress: ProgressCb | None = None,
    ) -> bool:
        """提交耗时任务。若已有任务在跑则返回 ``False``（调用方应提示用户）。"""
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self._current = name
        self.root.after(0, lambda: self._set_state(True, name))

        job = _Job(name, fn)

        def progress(*args: Any) -> None:
            job.events.put(("progress", args))

        def worker() -> None:
            try:
                job.events.put(("done", fn(progress)))
            except BaseException as exc:  # noqa: BLE001 — 异常需回投到 UI 展示
                job.events.put(("error", (exc, traceback.format_exc())))

        threading.Thread(target=worker, name=f"pdf-task-{name}", daemon=True).start()
        self.root.after(40, lambda: self._pump(job, on_done, on_error, on_progress))
        return True

    # ------------------------------------------------------------- 轮询
    def _pump(
        self,
        job: _Job,
        on_done: DoneFn | None,
        on_error: ErrorFn | None,
        on_progress: ProgressCb | None,
    ) -> None:
        while True:
            try:
                kind, payload = job.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                if on_progress:
                    self._safe_after(on_progress, payload)
                continue
            if kind == "done":
                self._finish()
                if on_done:
                    self._safe_after(on_done, (payload,))
                return
            if kind == "error":
                self._finish()
                exc, tb = payload
                if on_error:
                    self._safe_after(on_error, (exc, tb))
                else:
                    print(f"[task:{job.name}] failed\n{tb}", flush=True)
                return
        self.root.after(50, lambda: self._pump(job, on_done, on_error, on_progress))

    def _finish(self) -> None:
        with self._lock:
            self._busy = False
            self._current = None
        self._set_state(False, None)

    def _safe_after(self, fn: Callable, args: tuple) -> None:
        def call() -> None:
            try:
                fn(*args)
            except Exception:
                traceback.print_exc()

        try:
            self.root.after(0, call)
        except Exception:
            call()