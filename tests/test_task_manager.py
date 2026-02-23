"""Tests for the TaskManager lifecycle helper."""

from __future__ import annotations

import asyncio
import unittest

from ollama_chat.task_manager import TaskManager


class TaskManagerTests(unittest.IsolatedAsyncioTestCase):
    """Validate named and anonymous task lifecycle management."""

    async def test_add_anonymous_and_cancel_all(self) -> None:
        tm = TaskManager()
        cancelled: list[bool] = []

        async def _worker() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        task = asyncio.create_task(_worker())
        tm.add(task)
        await asyncio.sleep(0)  # Let the task start.
        await tm.cancel_all()
        self.assertTrue(task.done())
        self.assertTrue(cancelled)

    async def test_add_named_and_cancel_by_name(self) -> None:
        tm = TaskManager()
        cancelled: list[bool] = []

        async def _worker() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        task = asyncio.create_task(_worker())
        tm.add(task, name="my_task")
        await asyncio.sleep(0)  # Let the task start.
        self.assertIs(tm.get("my_task"), task)

        await tm.cancel("my_task")
        self.assertTrue(task.done())
        self.assertTrue(cancelled)
        self.assertIsNone(tm.get("my_task"))

    async def test_cancel_nonexistent_name_is_noop(self) -> None:
        tm = TaskManager()
        await tm.cancel("does_not_exist")

    async def test_discard_removes_without_cancelling(self) -> None:
        tm = TaskManager()

        async def _worker() -> None:
            await asyncio.sleep(9999)

        task = asyncio.create_task(_worker())
        tm.add(task, name="x")
        tm.discard("x")
        self.assertIsNone(tm.get("x"))
        self.assertFalse(task.done())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_anonymous_tasks_self_clean(self) -> None:
        tm = TaskManager()

        async def _quick() -> None:
            pass

        task = asyncio.create_task(_quick())
        tm.add(task)
        await task
        # After completion, anonymous tasks remove themselves.
        # cancel_all should not fail.
        await tm.cancel_all()

    async def test_cancel_all_handles_mixed_tasks(self) -> None:
        tm = TaskManager()
        results: list[str] = []

        async def _named_worker() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                results.append("named")
                raise

        async def _anon_worker() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                results.append("anon")
                raise

        tm.add(asyncio.create_task(_named_worker()), name="n1")
        tm.add(asyncio.create_task(_anon_worker()))
        await asyncio.sleep(0)  # Let the tasks start.
        await tm.cancel_all()
        self.assertIn("named", results)
        self.assertIn("anon", results)


if __name__ == "__main__":
    unittest.main()
