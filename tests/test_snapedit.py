import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import snapedit


@pytest.fixture
def work_tmp():
    path = ROOT / "test-artifacts"
    path.mkdir(exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def sample_image(work_tmp):
    image = Image.new("RGBA", (40, 20), (20, 40, 80, 255))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "must not survive")
    path = work_tmp / "input.png"
    image.save(path, pnginfo=metadata)
    return path


def test_info_reports_dimensions(sample_image):
    result = subprocess.run(
        [sys.executable, str(ROOT / "snapedit.py"), "info", str(sample_image)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"width": 40, "height": 20}


def test_edit_respects_input_coordinates_and_scaling(sample_image, work_tmp):
    output = work_tmp / "edited.png"
    result = snapedit.edit(
        str(sample_image),
        [{"crop": [0, 0, 20, 10]}, {"zoom": 2}, {"max_width": 30}],
    )
    snapedit.save(result, str(output))

    with Image.open(output) as edited:
        assert edited.size == (30, 15)
        assert not edited.info


def test_grid_and_gif_write_usable_images(sample_image, work_tmp):
    grid_output = work_tmp / "grid.png"
    snapedit.grid(str(sample_image), str(grid_output), 10)
    with Image.open(grid_output) as grid:
        assert grid.size == (40, 20)

    second = work_tmp / "second.png"
    Image.new("RGBA", (20, 10), (120, 30, 40, 255)).save(second)
    gif_output = work_tmp / "steps.gif"
    snapedit.gif([str(sample_image), str(second)], str(gif_output), 100, 40)
    with Image.open(gif_output) as animation:
        assert animation.size == (40, 20)
        assert animation.n_frames == 2


def test_find_text_uses_cached_ocr_sidecar(sample_image):
    sidecar = Path(str(sample_image) + ".ocr.json")
    sidecar.write_text(
        json.dumps(
            {
                "lines": [
                    {
                        "words": [
                            {"t": "Start", "x": 2, "y": 3, "w": 10, "h": 5},
                            {"t": "a", "x": 14, "y": 3, "w": 4, "h": 5},
                            {"t": "trace", "x": 20, "y": 3, "w": 12, "h": 5},
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert snapedit.find_text(str(sample_image), "start a trace") == [[2, 3, 30, 5]]


@pytest.fixture(scope="session")
def native_executable():
    executable = ROOT / "snap.exe"
    if not executable.exists():
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "build.ps1"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(result.stdout + result.stderr)
    return executable


def run_native(native_executable, *args):
    return subprocess.run(
        [str(native_executable), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_native_list_is_read_only_json(native_executable):
    result = run_native(native_executable, "-List")
    assert result.returncode == 0
    assert isinstance(json.loads(result.stdout), list)


def test_native_missing_app_uses_documented_exit_code(native_executable):
    result = run_native(native_executable, "-App", "__focus_snap_missing_window__")
    assert result.returncode == 1
    assert "error" in json.loads(result.stdout)


def test_native_invalid_region_is_a_json_error(native_executable):
    result = run_native(native_executable, "-Region", "bad")
    assert result.returncode == 1
    assert "error" in json.loads(result.stdout)


def test_native_invalid_mode_is_rejected(native_executable):
    result = run_native(native_executable, "-Mode", "unknown")
    assert result.returncode == 1
    assert "error" in json.loads(result.stdout)
