from io import BytesIO
from zipfile import ZipFile

import pytest

from sheetcheck import FileSpec, Side, read_source
from sheetcheck.errors import InputError


@pytest.mark.parametrize("prefix", [b"", b"plain-prefix"])
def test_empty_zip_with_csv_like_comment_cannot_be_imported_as_csv(prefix):
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.comment = b",amount\nA,1\n"
    with pytest.raises(InputError, match="FILE_SIGNATURE_INVALID"):
        read_source(prefix + data.getvalue(), FileSpec("disguised.csv", Side.ORDER))
