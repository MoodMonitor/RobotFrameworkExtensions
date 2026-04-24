"""Assertions about the library's reversibility."""

from robot.api.deco import keyword

from robot.output import librarylogger as _ll


# Snapshot the original callable the very first time this module is imported
# (which happens before any test starts). If the ThreadLogger cleanup works,
# librarylogger.write will compare equal to this snapshot at the end of a test.
_ORIGINAL_WRITE = _ll.write


@keyword("Assert No Patches Installed")
def assert_no_patches_installed() -> None:
    if _ll.write is not _ORIGINAL_WRITE:
        raise AssertionError(
            "librarylogger.write is still monkey-patched - reversibility failed."
        )
