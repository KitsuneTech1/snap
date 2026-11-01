import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import snapedit


@pytest.fixture
def work_tmp(request):
    root = ROOT / "tests"
    prefix = ".snap-test-" + uuid.uuid4().hex + "-"

    def cleanup():
        for path in root.glob(prefix + "*"):
            if path.is_file() or path.is_symlink():
                path.unlink()

    request.addfinalizer(cleanup)
    return _TestWorkspace(root, prefix)


class _TestWorkspace:
    def __init__(self, root, prefix):
        self.root = root
        self.prefix = prefix

    def __truediv__(self, name):
        return self.root / (self.prefix + str(name))


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
    output = sample_image.with_name(sample_image.stem + "-edited.png")
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


def test_ocr_sidecar_masks_secret_words(work_tmp):
    image = work_tmp / "ocr-input.png"
    Image.new("RGBA", (40, 20), (20, 40, 80, 255)).save(image)
    token = "sk_live_1234567890123456"
    fixture = work_tmp / "ocr-result.json"
    fixture.write_text(
        json.dumps(
            {
                "width": 40,
                "height": 20,
                "lines": [
                    {
                        "Text": "token " + token,
                        "Words": [
                            {"Text": "token", "X": 2, "Y": 3, "Width": 10, "Height": 5},
                            {"Text": token, "X": 14, "Y": 3, "Width": 20, "Height": 5},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "ocr.ps1"),
            "-Path",
            str(image),
            "-TestResultJson",
            str(fixture),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    sidecar_text = Path(str(image) + ".ocr.json").read_text(encoding="utf-8-sig")
    sidecar = json.loads(sidecar_text)
    assert token not in sidecar_text
    assert sidecar["secrets"] == 1
    assert sidecar["lines"][0]["words"][1]["t"] == "[SECRET HIDDEN]"
    assert "[SECRET HIDDEN]" in sidecar["lines"][0]["text"]
    assert token not in result.stdout


@pytest.mark.parametrize("ops", ["[{}]", "[{\"unknown\": true}]", "[{\"crop\": [0, 0, 0]}]"])
def test_edit_rejects_malformed_operations_without_traceback(sample_image, ops):
    result = subprocess.run(
        [sys.executable, str(ROOT / "snapedit.py"), "edit", str(sample_image), "-o", str(sample_image.with_name(sample_image.stem + "-out.png")), "--ops", ops],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        ["grid", "{image}", "-o", "{output}", "--step", "0"],
        ["gif", "{image}", "-o", "{output}", "--max-width", "0"],
    ],
)
def test_cli_rejects_invalid_dimensions_without_traceback(sample_image, command):
    output = sample_image.parent / "invalid-output"
    args = [part.format(image=sample_image, output=output) for part in command]
    result = subprocess.run([sys.executable, str(ROOT / "snapedit.py"), *args], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_false_secret_redaction_is_a_no_op(sample_image):
    assert snapedit.edit(str(sample_image), [{"redact_secrets": False}]).size == (40, 20)


@pytest.fixture(scope="session")
def native_executable(request):
    prefix = ".native-build-" + uuid.uuid4().hex + "-"
    executable = ROOT / "tests" / (prefix + "snap.exe")

    def cleanup():
        for path in executable.parent.glob(prefix + "*"):
            if path.is_file() or path.is_symlink():
                path.unlink()

    request.addfinalizer(cleanup)
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "build.ps1"),
            "-OutputPath",
            str(executable),
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


def test_native_capture_failure_is_structured(native_executable, work_tmp):
    result = run_native(native_executable, "-Region", "0,0,800,600", "-Out", str(work_tmp / "missing" / "out.png"))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error"].startswith("capture failed:")


def test_powershell_wrapper_preserves_native_error_code(native_executable):
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "snap.ps1"),
            "-App",
            "__focus_snap_missing_window__",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "error" in json.loads(result.stdout)
