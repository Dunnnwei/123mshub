from mshub import __version__
from mshub.native import NATIVE_VERSION
from mshub.native.branding import icon_path


def test_native_branding_assets_and_version():
    assert __version__ == "1.9.1"
    assert NATIVE_VERSION == __version__
    assert icon_path("light").name == "123mshublogo.ico"
    assert icon_path("dark").name == "123mshublogohei.ico"
    assert icon_path("light").is_file()
    assert icon_path("dark").is_file()
