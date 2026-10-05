import os
from datetime import date
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from album_journal.storage import Album, Library, Track


@pytest.fixture
def album():
    return Album(
        id=str(uuid4()),
        provider="youtube_music",
        provider_id="MPREb_test",
        source_url="https://music.youtube.com/browse/MPREb_test",
        title="Álbum Example",
        artists=["Björk"],
        tracks=[Track("First song", ["Björk"], 181)],
        added_on=date.today().isoformat(),
    )


@pytest.fixture
def library(tmp_path):
    library = Library(tmp_path / "journal")
    yield library
    library.close()
