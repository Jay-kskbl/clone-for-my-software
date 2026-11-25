from __future__ import annotations

import importlib.util
import resource
import sys
import types
from pathlib import Path


def install_stubs() -> None:
    shared = types.ModuleType("shared")
    shared.__path__ = []
    tasks = types.ModuleType("shared.tasks")
    contracts = types.ModuleType("shared.contracts")

    class Task:
        pass

    class OcrLocator:
        pass

    tasks.Task = Task
    contracts.OcrLocator = OcrLocator
    shared.tasks = tasks
    shared.contracts = contracts
    sys.modules["shared"] = shared
    sys.modules["shared.tasks"] = tasks
    sys.modules["shared.contracts"] = contracts

    pydantic = types.ModuleType("pydantic")

    class TypeAdapter:
        def __init__(self, annotation):
            self.annotation = annotation

    pydantic.TypeAdapter = TypeAdapter
    sys.modules["pydantic"] = pydantic

    ocr_worker = types.ModuleType("ocr_worker")
    ocr_worker.__path__ = []
    engine = types.ModuleType("ocr_worker.engine")
    rendering = types.ModuleType("ocr_worker.rendering")

    class Engine:
        pass

    class RecognizedLine:
        pass

    engine.Engine = Engine
    engine.RecognizedLine = RecognizedLine
    rendering.render = lambda *args, **kwargs: None
    ocr_worker.engine = engine
    ocr_worker.rendering = rendering
    sys.modules["ocr_worker"] = ocr_worker
    sys.modules["ocr_worker.engine"] = engine
    sys.modules["ocr_worker.rendering"] = rendering


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    target = sys.argv[1]
    limit_mb = 256
    install_stubs()

    if target == "worker":
        module = load_module("codex_worker_runner", "/tmp/codex_rlimit_runner2.py")
    elif target == "ocr":
        module = load_module("codex_ocr_engine_process", "/tmp/codex_rlimit_engine_process2.py")
    else:
        raise SystemExit(f"Unknown target: {target}")

    module._limit_memory(limit_mb)
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    expected = limit_mb * 1024 * 1024
    print(f"target={target}")
    print(f"soft={soft}")
    print(f"hard={hard}")
    print(f"expected={expected}")
    print(f"limit_applied={soft == expected and hard == expected}")

    try:
        allocation = bytearray(400 * 1024 * 1024)
    except MemoryError:
        print("allocation_result=MemoryError")
    else:
        allocation[0] = 1
        allocation[-1] = 1
        print(f"allocation_result=allocated:{len(allocation)}")


if __name__ == "__main__":
    main()
