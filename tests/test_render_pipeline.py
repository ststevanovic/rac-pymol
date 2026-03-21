"""Deployment / integration smoke-test for the simple.py render pipeline.

Marked ``deploy`` — requires a real PyMOL installation and GPU-capable
(or software-renderer) environment.  Not run in the unit-test suite by default.

Run manually:
    pytest -m deploy tests/test_render_pipeline.py -v

Or via the GitHub Actions ``deploy`` workflow.

What is tested
--------------
1. ``simple.py`` runs to completion without error (exit code 0).
2. Expected output files exist.
3. Pixel-level colour consistency between staged and applied renders:
   - Dominant colour pixel-count in ``applied`` is >= COLOUR_RATIO_FLOOR of
     ``staged`` (catches paint-inversion + flush-ordering regressions).
   - Total opaque pixel-count agrees within OPACITY_TOLERANCE (catches
     representation / viewport regressions).
4. Applied PNG for subjects exists and is non-trivial (> MIN_OPAQUE_PIXELS).

The thresholds are intentionally loose so that minor renderer variance across
PyMOL versions/platforms doesn't create false positives.
"""

from __future__ import annotations

import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO = Path(__file__).parent.parent          # rac_pymol/
TEMPLATE = REPO / "pymol-templates" / "simple.py"
OUTPUT_DIR = REPO / ".rendering"

REFERENCE_TAG = "1pdb"
SUBJECT_TAGS = ["1lp3", "6j6j"]

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Applied dominant-colour pixels must be >= this fraction of staged dominant
COLOUR_RATIO_FLOOR = 0.60

# Total opaque pixel count must not differ by more than this fraction
OPACITY_TOLERANCE = 0.20

# A "non-trivial" render has at least this many opaque pixels
MIN_OPAQUE_PIXELS = 500


# ---------------------------------------------------------------------------
# PNG pixel helpers
# ---------------------------------------------------------------------------

def _read_png_rgba(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Return (width, height, flat_pixel_list) for an RGBA PNG.

    Only handles deflated IDAT chunks (standard PNG).  Raises if the file is
    not a valid RGBA PNG.
    """
    data = path.read_bytes()

    sig = data[:8]
    assert sig == b"\x89PNG\r\n\x1a\n", f"Not a PNG: {path}"

    # parse chunks
    idat_chunks: list[bytes] = []
    width = height = 0
    i = 8
    while i < len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        cdata = data[i + 8 : i + 8 + length]
        if ctype == b"IHDR":
            width = struct.unpack(">I", cdata[0:4])[0]
            height = struct.unpack(">I", cdata[4:8])[0]
            bit_depth = cdata[8]
            colour_type = cdata[9]
            assert bit_depth == 8 and colour_type == 6, (
                f"Expected 8-bit RGBA PNG, got bit_depth={bit_depth} "
                f"colour_type={colour_type}: {path}"
            )
        elif ctype == b"IDAT":
            idat_chunks.append(cdata)
        elif ctype == b"IEND":
            break
        i += 12 + length

    raw = zlib.decompress(b"".join(idat_chunks))
    stride = width * 4 + 1  # filter byte + 4 channels

    pixels: list[tuple[int, int, int, int]] = []
    for row in range(height):
        for col in range(width):
            off = row * stride + 1 + col * 4
            pixels.append(
                (raw[off], raw[off + 1], raw[off + 2], raw[off + 3])
            )

    return width, height, pixels


def _dominant_colour(
    pixels: list[tuple[int, int, int, int]],
    alpha_threshold: int = 100,
) -> tuple[str, int]:
    """Return (colour_label, count) for the most common opaque hue bucket.

    Hue buckets: ``blue`` (b > r+50 and b > 150), ``red`` (r > b+50 and r > 150),
    ``green`` (g > r+50 and g > 150), ``other``.
    """
    counts: dict[str, int] = {"blue": 0, "red": 0, "green": 0, "other": 0}
    for r, g, b, a in pixels:
        if a <= alpha_threshold:
            continue
        if b > 150 and b > r + 50 and b > g + 50:
            counts["blue"] += 1
        elif r > 150 and r > b + 50 and r > g + 50:
            counts["red"] += 1
        elif g > 150 and g > r + 50 and g > b + 50:
            counts["green"] += 1
        else:
            counts["other"] += 1
    dominant = max(counts, key=lambda k: counts[k])
    return dominant, counts[dominant]


def _opaque_count(
    pixels: list[tuple[int, int, int, int]],
    alpha_threshold: int = 100,
) -> int:
    return sum(1 for *_, a in pixels if a > alpha_threshold)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """Run simple.py once per test session; yield output dir.

    Uses a temporary copy of the rendering dir so tests don't clobber
    real artefacts.  The template writes to OUTPUT_DIR (hardcoded in
    simple.py), so we can't redirect it — we just let it run and read
    from OUTPUT_DIR directly.
    """
    result = subprocess.run(
        [sys.executable, str(TEMPLATE)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=300,  # 5 min ceiling for slow software-ray renders
    )
    return result, OUTPUT_DIR


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.deploy
class TestRenderPipeline:
    """Pixel-level smoke tests for the full stage → ingest → apply pipeline."""

    def test_simple_py_exits_clean(self, rendered):
        result, _ = rendered
        assert result.returncode == 0, (
            f"simple.py failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )

    def test_reference_outputs_exist(self, rendered):
        _, out = rendered
        for suffix in ["staged.png", "staged.json", "staged.pse", "applied.png"]:
            p = out / f"{REFERENCE_TAG}_{suffix}"
            assert p.exists(), f"Missing expected output: {p.name}"

    def test_subject_applied_outputs_exist(self, rendered):
        _, out = rendered
        for tag in SUBJECT_TAGS:
            p = out / f"{tag}_applied.png"
            assert p.exists(), f"Missing subject applied render: {p.name}"

    def test_reference_staged_vs_applied_dominant_colour(self, rendered):
        """Staged and applied dominant colour pixel-counts must agree within floor.

        This catches both the paint-inversion bug (dominant fills minority) and
        the ray/flush-ordering bug (colours not committed before ray fires).
        """
        _, out = rendered
        _, _, staged_pixels = _read_png_rgba(out / f"{REFERENCE_TAG}_staged.png")
        _, _, applied_pixels = _read_png_rgba(out / f"{REFERENCE_TAG}_applied.png")

        staged_dom, staged_count = _dominant_colour(staged_pixels)
        applied_dom, applied_count = _dominant_colour(applied_pixels)

        assert staged_dom == applied_dom, (
            f"Dominant colour mismatch: staged={staged_dom!r} "
            f"applied={applied_dom!r}.  "
            "Likely a paint-inversion or flush-ordering regression."
        )

        if staged_count > 0:
            ratio = applied_count / staged_count
            assert ratio >= COLOUR_RATIO_FLOOR, (
                f"Applied dominant-colour pixel count too low: "
                f"{applied_count} vs staged {staged_count} "
                f"(ratio={ratio:.2f}, floor={COLOUR_RATIO_FLOOR}).  "
                "Paint or flush regression suspected."
            )

    def test_reference_staged_vs_applied_opaque_pixels(self, rendered):
        """Total opaque pixel counts must agree within OPACITY_TOLERANCE."""
        _, out = rendered
        _, _, staged_pixels = _read_png_rgba(out / f"{REFERENCE_TAG}_staged.png")
        _, _, applied_pixels = _read_png_rgba(out / f"{REFERENCE_TAG}_applied.png")

        n_staged = _opaque_count(staged_pixels)
        n_applied = _opaque_count(applied_pixels)

        assert n_staged > MIN_OPAQUE_PIXELS, "Staged PNG appears blank"
        assert n_applied > MIN_OPAQUE_PIXELS, "Applied PNG appears blank"

        diff_frac = abs(n_staged - n_applied) / max(n_staged, 1)
        assert diff_frac <= OPACITY_TOLERANCE, (
            f"Opaque pixel count differs too much: "
            f"staged={n_staged} applied={n_applied} "
            f"(diff={diff_frac:.1%}, tolerance={OPACITY_TOLERANCE:.0%}).  "
            "Representation or viewport regression suspected."
        )

    @pytest.mark.parametrize("tag", SUBJECT_TAGS)
    def test_subject_applied_non_trivial(self, rendered, tag):
        """Each subject applied PNG must have enough opaque pixels to be real."""
        _, out = rendered
        p = out / f"{tag}_applied.png"
        _, _, pixels = _read_png_rgba(p)
        n = _opaque_count(pixels)
        assert n >= MIN_OPAQUE_PIXELS, (
            f"{p.name}: only {n} opaque pixels — likely a blank render "
            "(apply_scene may have failed silently)."
        )

    @pytest.mark.parametrize("tag", SUBJECT_TAGS)
    def test_subject_applied_matches_reference_dominant_colour(self, rendered, tag):
        """Each subject must share the reference's dominant colour after apply."""
        _, out = rendered
        _, _, ref_pixels = _read_png_rgba(out / f"{REFERENCE_TAG}_staged.png")
        _, _, subj_pixels = _read_png_rgba(out / f"{tag}_applied.png")

        ref_dom, _ = _dominant_colour(ref_pixels)
        subj_dom, subj_count = _dominant_colour(subj_pixels)

        assert subj_dom == ref_dom, (
            f"{tag}_applied dominant colour={subj_dom!r}, "
            f"expected {ref_dom!r} (same as reference staged).  "
            "Scene cross-application colour regression."
        )
        assert subj_count >= MIN_OPAQUE_PIXELS, (
            f"{tag}_applied has too few dominant-colour pixels ({subj_count})."
        )
