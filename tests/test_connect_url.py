import pytest
from scripts.connect_from_url import extract_code, folder_id


def test_extract_code():
    assert extract_code("http://localhost/?state=x&code=4/abc&scope=a%20b") == "4/abc"


def test_extract_code_error():
    with pytest.raises(SystemExit):
        extract_code("http://localhost/?error=access_denied")
    with pytest.raises(SystemExit):
        extract_code("http://localhost/")


def test_folder_id():
    assert folder_id("https://drive.google.com/drive/folders/1AbC_d-9?usp=sharing") == "1AbC_d-9"
    assert folder_id("1AbC") == "1AbC"
    assert folder_id("") is None
