"""Offline runtime path for a package installed outside the source checkout."""

import asyncio
import os
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path

import librus_python_api
from tests.http_support import serve
from tests.reads_support import ReadsFixture


def main() -> None:
    location = Path(librus_python_api.__file__).resolve()
    if not location.is_relative_to(Path(os.environ["ARTIFACT_ENV"]).resolve()):
        raise RuntimeError("Smoke imported source instead of installed artifact")
    metadata = distribution("librus-python-api")
    assert metadata.version == librus_python_api.__version__
    assert metadata.metadata["License-Expression"] == "MIT"
    assert files("librus_python_api").joinpath("py.typed").is_file()
    asyncio.run(reads())
    print(f"Installed {metadata.version} smoke passed: {location}")


async def reads() -> None:
    fixture = ReadsFixture()
    async with serve(fixture.app()) as origin:
        fixture.origin = origin
        async with fixture.service(("fixture",)) as service:
            client = service.account("fixture")
            profile = await client.student_information()
            grades = await client.final_grades()
            assert profile.identity.owner.id == "fixture" and grades.items
            assert len(client.context.identifier) == 64
        assert len(fixture.reads) == 2


if __name__ == "__main__":
    main()
