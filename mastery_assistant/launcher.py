"""Launch the review-only GUI and provide a no-network packaged-build smoke test."""
from __future__ import annotations

import sys


def _self_test() -> None:
    """Import runtime dependencies and verify core review-only invariants."""
    import keyring  # noqa: F401
    import mss  # noqa: F401
    import pynput  # noqa: F401
    import cv2  # noqa: F401
    from PIL import Image  # noqa: F401

    if sys.platform == "win32":
        import win32api  # noqa: F401
        import win32con  # noqa: F401
        import win32gui  # noqa: F401

    import app  # noqa: F401 — verify the packaged UI module imports cleanly
    from providers import DEFAULT_MODELS, PROVIDERS, ProviderError, ask_provider
    from routine import build_review
    from video_learning import MAX_VIDEO_FRAMES

    if set(DEFAULT_MODELS) != set(PROVIDERS):
        raise RuntimeError("Every provider must have a default model.")
    if MAX_VIDEO_FRAMES != 6:
        raise RuntimeError("The maximum frame-sampling bound changed unexpectedly.")

    review = build_review(
        "Review the visible fruit demonstration and note uncertainties.",
        "Fruit",
        allow_movement_setting=False,
    )
    if not review.ready_for_review or review.live_execution_enabled or review.movement_allowed:
        raise RuntimeError("Review-only safety invariants failed.")
    if review.reset_if_stuck:
        raise RuntimeError("A reset must not be assumed when the prompt does not ask for one.")

    try:
        ask_provider("Unsupported provider", "", "", "", "")
    except ProviderError:
        pass
    else:
        raise RuntimeError("Provider validation unexpectedly accepted an unsupported provider.")


def main() -> None:
    if "--self-test" in sys.argv[1:]:
        _self_test()
        return
    from app import main as run_gui
    run_gui()


if __name__ == "__main__":
    main()
