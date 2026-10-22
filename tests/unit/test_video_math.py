"""Actual offline typesetting, pagination and encoded math-video regressions."""
import json
import subprocess

import cv2
import pytest
from PIL import Image

from common.knowledge_paths import PROJECT_ROOT
from common.models.learning import Resource
from services.agent_service.app.services.resource_artifacts import render_video, resource_video_path

FORMULAS = r"""## 步骤2：求左极限
$x\to0^-$ 时 $x<0$，$f(x)=\frac{-x}{x}=-1$，故 $f(0^-)=-1$。
## 步骤3：比较左右极限
$f(0^+)=1\ne-1=f(0^-)$，两侧趋势不同。
**最终结果**：
$$
\displaystyle\lim_{x\to0}\frac{|x|}{x}
$$
不存在。
核验：取 \(x=0.001\) 得 $1$，取 \(x=-0.001\) 得 $-1$。
\[
\frac{x^2-1}{x-1}=x+1\quad(x\ne1)
\]
"""


def test_actual_math_frames_are_typeset_and_paginated(tmp_path):
    source = tmp_path / 'source.json'
    source.write_text(json.dumps({'title': '函数极限个性化课件', 'content': FORMULAS * 3}), encoding='utf-8')
    frames = tmp_path / 'frames'
    result = subprocess.run(['node', str(PROJECT_ROOT / 'scripts/render_courseware_frames.mjs'), str(source), str(frames)],
                            capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    layout = json.loads((frames / 'layout.json').read_text())
    assert layout['formulas'] == 33
    assert layout['errors'] == 0
    assert len(layout['slices']) > 3
    assert all(0 < end - start <= 440 for start, end in layout['slices'])
    assert all(a[1] == b[0] for a, b in zip(layout['slices'], layout['slices'][1:], strict=False))
    for frame in frames.glob('frame-*.png'):
        with Image.open(frame) as image:
            assert image.size == (960, 600)


def test_invalid_formula_blocks_bad_video(tmp_path):
    source = tmp_path / 'source.json'
    source.write_text(json.dumps({'content': r'$\frac{1}{$'}), encoding='utf-8')
    result = subprocess.run(['node', str(PROJECT_ROOT / 'scripts/render_courseware_frames.mjs'), str(source), str(tmp_path / 'frames')],
                            capture_output=True, timeout=60)
    assert result.returncode != 0
    assert '无效公式' in result.stderr.decode('utf-8', errors='replace')


def test_actual_math_video_decodes(tmp_path):
    target = tmp_path / 'formula.webm'
    target.write_bytes(render_video('函数极限', FORMULAS))
    capture = cv2.VideoCapture(str(target))
    try:
        ok, frame = capture.read()
        assert ok and frame.shape[:2] == (600, 960)
        assert capture.get(cv2.CAP_PROP_FRAME_COUNT) >= 24
    finally:
        capture.release()


def test_old_plain_text_video_is_not_reused():
    resource = Resource(id=234, type='courseware', content=FORMULAS, generated_for_user_id=6)
    assert resource_video_path(resource).name.endswith('-math-v2.webm')


def test_empty_video_source_is_rejected():
    with pytest.raises(ValueError, match='正文为空'):
        render_video('空课件', '  ')
