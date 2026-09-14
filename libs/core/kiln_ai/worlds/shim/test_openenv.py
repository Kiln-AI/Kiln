from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from contextlib import contextmanager

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .conftest import FIXED_NOW
from .ctx import Ctx
from .errors import WorldBug
from .openenv import app, free_port, serve_in_thread

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


@contextmanager
def serve(built):
    """Run an already-built app on a free port, so a test can choose its options."""
    import uvicorn

    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(built, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            raise RuntimeError("test world server did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def ws_url(base_url: str) -> str:
    return base_url.replace("http://", "ws://") + "/ws"


async def request(socket, message: dict) -> dict:
    await socket.send(json.dumps(message))
    return json.loads(await asyncio.wait_for(socket.recv(), timeout=30))


async def reset(socket, **data) -> dict:
    return await request(socket, {"type": "reset", "data": data})


async def call(socket, tool_name: str, **arguments) -> dict:
    return await request(
        socket,
        {
            "type": "step",
            "data": {
                "type": "call_tool",
                "tool_name": tool_name,
                "arguments": arguments,
            },
        },
    )


@pytest.fixture
def served(toy_world, frozen):
    with serve_in_thread(toy_world) as base_url:
        yield base_url


async def test_metadata_and_health(served):
    async with httpx.AsyncClient(base_url=served) as client:
        assert (await client.get("/health")).json() == {"status": "healthy"}
        meta = (await client.get("/metadata")).json()
    assert meta["name"] == "toy" and meta["version"] == "1.0.0"
    assert meta["description"] == ""
    # A client sizing a concurrent run has to be able to read the cap before it starts.
    assert meta["max_concurrent_envs"] == 500


async def test_metadata_description_is_the_readme_first_paragraph(toy_world, frozen):
    package = toy_world.fixtures_dir.parent
    package.mkdir(parents=True, exist_ok=True)
    (package / "README.md").write_text(
        "# Toy world\n\nA world of items and tags.\n\nMore detail below.\n"
    )
    with serve_in_thread(toy_world) as base_url:
        async with httpx.AsyncClient(base_url=base_url) as client:
            meta = (await client.get("/metadata")).json()
    assert meta["description"] == "A world of items and tags."


async def test_metadata_reflects_set_version_at_request_time(toy_world, served):
    async with httpx.AsyncClient(base_url=served) as client:
        assert (await client.get("/metadata")).json()["version"] == "1.0.0"
        toy_world.set_version("1.0.0+fault.drop_last_assignee")
        assert (await client.get("/metadata")).json()["version"] == (
            "1.0.0+fault.drop_last_assignee"
        )


async def test_reset_frame_carries_facts_in_result_metadata_and_top_level(served):
    async with connect(ws_url(served)) as socket:
        frame = await reset(socket, fixture="base", episode_id="ep_1")
    facts = {"fixture": "base", "now": FIXED_NOW, "tools": 3}
    assert frame["type"] == "observation"
    assert frame["data"]["observation"]["result"] == facts
    assert frame["data"]["observation"]["metadata"] == facts
    assert frame["data"]["metadata"] == facts
    assert frame["data"]["observation"]["tool_name"] == ""
    assert frame["data"]["observation"]["error"] is None
    assert frame["data"]["reward"] is None and frame["data"]["done"] is False


async def test_blank_reset_reports_null_fixture(served):
    async with connect(ws_url(served)) as socket:
        frame = await reset(socket, now=FIXED_NOW)
    assert frame["data"]["metadata"] == {"fixture": None, "now": FIXED_NOW, "tools": 3}


async def test_list_tools_without_reset(served):
    async with connect(ws_url(served)) as socket:
        frame = await request(socket, {"type": "step", "data": {"type": "list_tools"}})
    tools = frame["data"]["observation"]["tools"]
    assert [t["name"] for t in tools] == ["add_item", "tag_item", "finish_item"]
    assert set(tools[0]) == {"name", "description", "input_schema"}
    assert frame["data"]["reward"] is None and frame["data"]["done"] is False


async def test_call_tool_before_reset_is_no_episode_error_frame(served):
    async with connect(ws_url(served)) as socket:
        frame = await call(socket, "add_item", name="x")
        assert frame == {
            "type": "error",
            "data": {
                "message": "no episode on this session; send a reset first",
                "code": "no_episode",
            },
        }
        survivor = await request(
            socket, {"type": "step", "data": {"type": "list_tools"}}
        )
    assert survivor["type"] == "observation"


@pytest.mark.parametrize(
    "data, expected_in_message",
    [
        (None, "'data'"),
        ([], "'data'"),
        ({"type": "dance"}, "'data.type'"),
        ({"type": "call_tool"}, "'data.tool_name'"),
        ({"type": "call_tool", "tool_name": 3}, "'data.tool_name'"),
        (
            {"type": "call_tool", "tool_name": "add_item", "arguments": []},
            "'data.arguments'",
        ),
    ],
)
async def test_malformed_step_is_invalid_action_and_session_survives(
    served, data, expected_in_message
):
    message = {"type": "step"}
    if data is not None:
        message["data"] = data
    async with connect(ws_url(served)) as socket:
        frame = await request(socket, message)
        assert frame["type"] == "error"
        assert frame["data"]["code"] == "invalid_action"
        assert expected_in_message in frame["data"]["message"]
        survivor = await request(
            socket, {"type": "step", "data": {"type": "list_tools"}}
        )
    assert survivor["type"] == "observation"


async def test_invalid_json_and_unknown_type_keep_session(served):
    async with connect(ws_url(served)) as socket:
        await socket.send("{not json")
        frame = json.loads(await socket.recv())
        assert frame["data"]["code"] == "invalid_json"
        frame = await request(socket, {"type": "dance"})
        assert frame["data"]["code"] == "unknown_type"
        await socket.send(json.dumps([1, 2]))
        frame = json.loads(await socket.recv())
        assert frame["data"]["code"] == "invalid_json"
        survivor = await request(
            socket, {"type": "step", "data": {"type": "list_tools"}}
        )
    assert survivor["type"] == "observation"


async def test_tool_error_observation_shape_done_false_reward_null(served):
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        good = await call(socket, "add_item", name="fresh")
        bad = await call(socket, "finish_item", item_id="nope")
        invalid = await call(socket, "add_item", name=3)

    assert good["data"]["observation"]["error"] is None
    assert good["data"]["observation"]["result"]["name"] == "fresh"
    assert good["data"]["observation"]["tool_name"] == "add_item"
    assert bad["data"]["observation"] == {
        "tool_name": "finish_item",
        "result": None,
        "error": {
            "code": "not_found",
            "message": "no item nope",
            "details": {"id": "nope"},
        },
    }
    assert invalid["data"]["observation"]["error"]["code"] == "invalid_arguments"
    for frame in (good, bad, invalid):
        assert frame["data"]["reward"] is None and frame["data"]["done"] is False


async def test_unknown_tool_and_control_tool_without_flag(toy_world, frozen):
    with serve(app(toy_world, include_control_tools=False)) as base_url:
        async with connect(ws_url(base_url)) as socket:
            await reset(socket, fixture="base")
            unknown = await call(socket, "dance")
            control = await call(socket, "controller_changes")
    assert unknown["data"]["observation"]["error"] == {
        "code": "unknown_tool",
        "message": "unknown tool: dance",
        "details": None,
    }
    assert control["data"]["observation"]["error"]["code"] == "unknown_tool"


async def test_control_tools_with_flag_never_listed(served):
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        listed = await request(socket, {"type": "step", "data": {"type": "list_tools"}})
        control = await call(socket, "controller_changes")
    assert "controller_changes" not in {
        t["name"] for t in listed["data"]["observation"]["tools"]
    }
    assert control["data"]["observation"]["error"] is None
    assert control["data"]["observation"]["result"] == []


async def test_control_call_does_not_increment_step_count(served):
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base", episode_id="ep_steps")
        await call(socket, "add_item", name="one")
        await call(socket, "add_item", name="two")
        await call(socket, "controller_changes")
        state = await request(socket, {"type": "state"})
    assert state["data"]["step_count"] == 2


async def test_unknown_reset_kwarg_and_now_with_fixture_keep_session_open(served):
    async with connect(ws_url(served)) as socket:
        frame = await reset(socket, nonsense=1)
        assert frame["data"]["code"] == "reset_failed"
        assert "unknown reset argument" in frame["data"]["message"]

        frame = await reset(socket, fixture="base", now=FIXED_NOW)
        assert frame["data"]["code"] == "reset_failed"
        assert "blank instances only" in frame["data"]["message"]

        frame = await reset(socket, fixture="missing")
        assert frame["data"]["code"] == "reset_failed"

        recovered = await reset(socket, fixture="base")
    assert recovered["type"] == "observation"


async def test_startup_hook_failure_is_reset_failed(tmp_path, capsys):
    """A hook that raises something other than a WorldBug still leaves the session usable."""
    from .conftest import build_toy_world

    world = build_toy_world(tmp_path / "hooks", with_hook=True)

    @world.instance_startup
    def explodes(ctx: Ctx, *, boom: bool = False) -> None:
        if boom:
            raise RuntimeError("the hook failed")

    with serve_in_thread(world) as base_url:
        async with connect(ws_url(base_url)) as socket:
            frame = await reset(socket, boom=True)
            assert frame["data"]["code"] == "reset_failed"
            assert "the hook failed" in frame["data"]["message"]
            recovered = await reset(socket)
    assert recovered["type"] == "observation"


async def test_non_ascii_travels_as_itself(toy_world, served):
    """The wire is the only place a world's own text is serialised; escaping it to \\uXXXX
    would ship mangled issue titles on every frame."""
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        await socket.send(
            json.dumps(
                {
                    "type": "step",
                    "data": {
                        "type": "call_tool",
                        "tool_name": "add_item",
                        "arguments": {"name": "café — 日本語"},
                    },
                }
            )
        )
        raw = await asyncio.wait_for(socket.recv(), timeout=30)
    assert "café — 日本語" in raw
    assert "\\u" not in raw
    assert json.loads(raw)["data"]["observation"]["result"]["name"] == "café — 日本語"


async def test_failed_reset_clears_the_previous_episode(served):
    """A reset that fails destroys the old instance, so `state` must not go on advertising
    the episode id and step count that belonged to it."""
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base", episode_id="ep_gone")
        await call(socket, "add_item", name="one")
        failed = await reset(socket, fixture="missing", episode_id="ep_new")
        assert failed["data"]["code"] == "reset_failed"
        state = await request(socket, {"type": "state"})
    assert state["data"] == {
        "episode_id": None,
        "step_count": 0,
        "fixture": None,
        "now": None,
        "world": "toy",
    }


async def test_world_bug_logged_and_session_survives(toy_world, served, caplog):
    @toy_world.tool
    def explodes(ctx: Ctx) -> None:
        """Raise a programmer error."""
        raise WorldBug("the world is broken")

    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        frame = await call(socket, "explodes")
        assert frame == {
            "type": "error",
            "data": {"message": "the world is broken", "code": "world_bug"},
        }
        survivor = await call(socket, "add_item", name="still working")
    assert survivor["data"]["observation"]["error"] is None
    assert any("world bug in tool" in record.message for record in caplog.records)


async def test_internal_error_hides_traceback(toy_world, served):
    @toy_world.tool
    def breaks(ctx: Ctx) -> None:
        """Raise something that is not a ToolError."""
        raise ValueError("a secret internal detail")

    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        frame = await call(socket, "breaks")
    assert frame["data"]["observation"]["error"] == {
        "code": "internal",
        "message": "internal error",
        "details": None,
    }
    assert "secret" not in json.dumps(frame)


async def test_state_before_and_after_reset(served):
    async with connect(ws_url(served)) as socket:
        before = await request(socket, {"type": "state"})
        assert before["data"] == {
            "episode_id": None,
            "step_count": 0,
            "fixture": None,
            "now": None,
            "world": "toy",
        }
        await reset(socket, fixture="base", episode_id="ep_state")
        await call(socket, "add_item", name="one")
        after = await request(socket, {"type": "state"})
    assert after["data"] == {
        "episode_id": "ep_state",
        "step_count": 1,
        "fixture": "base",
        "now": FIXED_NOW,
        "world": "toy",
    }


async def test_reset_without_episode_id_mints_one(served):
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        state = await request(socket, {"type": "state"})
    assert state["data"]["episode_id"]


async def test_second_reset_destroys_first_instance_dir(toy_world, served):
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        first = list(toy_world.work_dir.iterdir())
        assert len(first) == 1
        await reset(socket, fixture="base")
        second = list(toy_world.work_dir.iterdir())
    assert len(second) == 1 and second != first


async def test_close_destroys_and_socket_closes_cleanly(toy_world, served):
    async with connect(ws_url(served)) as socket:
        await reset(socket, fixture="base")
        await socket.send(json.dumps({"type": "close"}))
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(socket.recv(), timeout=10)
    await wait_for_empty(toy_world.work_dir)


async def test_disconnect_destroys_instance(toy_world, served):
    socket = await connect(ws_url(served))
    await reset(socket, fixture="base")
    assert len(list(toy_world.work_dir.iterdir())) == 1
    await socket.close()
    await wait_for_empty(toy_world.work_dir)


async def test_session_timeout_reaps(toy_world, frozen):
    with serve(app(toy_world, include_control_tools=True, session_timeout=0.2)) as url:
        async with connect(ws_url(url)) as socket:
            await reset(socket, fixture="base")
            with pytest.raises(ConnectionClosed):
                await asyncio.wait_for(socket.recv(), timeout=10)
        await wait_for_empty(toy_world.work_dir)


async def test_capacity_reached_frame_and_close(toy_world, frozen):
    with serve(app(toy_world, max_concurrent_envs=1)) as url:
        async with connect(ws_url(url)) as first:
            await reset(first, fixture="base")
            second = await connect(ws_url(url))
            frame = json.loads(await asyncio.wait_for(second.recv(), timeout=10))
            assert frame["data"]["code"] == "capacity_reached"
            with pytest.raises(ConnectionClosed):
                await asyncio.wait_for(second.recv(), timeout=10)
            still_alive = await request(
                first, {"type": "step", "data": {"type": "list_tools"}}
            )
    assert still_alive["type"] == "observation"


async def test_25_concurrent_sessions_no_cross_talk(served):
    async def episode(index: int) -> tuple[list, str]:
        async with connect(ws_url(served)) as socket:
            await reset(socket, fixture="base", seed=index % 2)
            await call(socket, "add_item", name=f"worker-{index % 2}")
            changes = await call(socket, "controller_changes")
            digest = await call(socket, "controller_digest")
            return (
                changes["data"]["observation"]["result"],
                digest["data"]["observation"]["result"],
            )

    results = await asyncio.gather(*(episode(i) for i in range(25)))
    for index, (changes, _) in enumerate(results):
        assert [c["after"]["name"] for c in changes] == [f"worker-{index % 2}"]
    digests = {index % 2: digest for index, (_, digest) in enumerate(results)}
    assert len(digests) == 2
    for index, (_, digest) in enumerate(results):
        assert digest == digests[index % 2]


async def test_serve_in_thread_free_port(toy_world, frozen):
    with serve_in_thread(toy_world) as first:
        with serve_in_thread(toy_world) as second:
            assert first != second
            async with httpx.AsyncClient() as client:
                for url in (first, second):
                    assert (await client.get(f"{url}/health")).status_code == 200


async def test_conformance_under_kiln_session_manager(tmp_path, toy_world, frozen):
    """The real Kiln session manager, end to end, against this app."""
    from kiln_ai.datamodel.project import Project
    from kiln_ai.datamodel.world import World as WorldRecord
    from kiln_ai.worlds.session_manager import OpenEnvSessionManager

    project = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    project.path.parent.mkdir(parents=True)
    project.save_to_file()

    with serve_in_thread(toy_world) as base_url:
        record = WorldRecord(name="toy", parent=project, env_url=base_url)
        record.save_to_file()
        session_manager = OpenEnvSessionManager()
        try:
            assert await session_manager.world_version(record, {}) == "toy@1.0.0"
            tools = await session_manager.list_tools(record)
            assert [t.name for t in tools] == ["add_item", "tag_item", "finish_item"]
            assert tools[0].input_schema["required"] == ["name"]

            episode = await session_manager.start_episode(record, {"fixture": "base"})
            assert episode.reset_metadata == {
                "fixture": "base",
                "now": FIXED_NOW,
                "tools": 3,
            }
            created = await session_manager.call_tool(
                episode, "add_item", {"name": "from kiln"}
            )
            assert created.error is None and created.result["name"] == "from kiln"
            failed = await session_manager.call_tool(
                episode, "finish_item", {"item_id": "nope"}
            )
            assert failed.error == "no item nope" and failed.result is None
            assert failed.error_code == "not_found"
            assert failed.error_details == {"id": "nope"}

            # This server serves control tools, so ending the episode settles the
            # world's own account of what the episode changed into the record.
            ended = await session_manager.end_episode(episode)
            changes = ended.final_state.pop("changes")
            digest = ended.final_state.pop("state_digest")
            assert ended.final_state == {
                "episode_id": episode.episode_id,
                "step_count": 2,
                "fixture": "base",
                "now": FIXED_NOW,
                "world": "toy",
            }
            assert [(c["table"], c["op"], c["after"]["name"]) for c in changes] == [
                ("items", "insert", "from kiln")
            ]
            assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
            await session_manager.release(ended)
        finally:
            await session_manager.shutdown()

    await wait_for_empty(toy_world.work_dir)


async def wait_for_empty(directory, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not directory.exists() or not list(directory.iterdir()):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"{directory} still holds {list(directory.iterdir())}")


def test_unserved_control_tool_error_is_not_a_step(toy_world, frozen):
    """A control tool refused because the flag is off must not count as a decision step."""

    async def run() -> int:
        with serve(app(toy_world, include_control_tools=False)) as base_url:
            async with connect(ws_url(base_url)) as socket:
                await reset(socket, fixture="base")
                await call(socket, "controller_changes")
                state = await request(socket, {"type": "state"})
                return state["data"]["step_count"]

    assert asyncio.run(run()) == 0
