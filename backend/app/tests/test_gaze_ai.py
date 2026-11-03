import numpy as np

from app.services.gaze_ai import GazeAIService


def _logits(peak: int) -> np.ndarray:
    values = np.full((1, 90), -20.0, dtype=np.float32)
    values[0, peak] = 20.0
    return values


def test_mobilegaze_decodes_output_order_and_bins():
    service = GazeAIService()

    # Official output order is yaw first, pitch second.
    # bin 50 => 50*4-180 = +20°, bin 45 => 0°.
    pitch, yaw = service._decode_angles([_logits(50), _logits(45)])

    assert abs(pitch - 0.0) < 0.1
    assert abs(yaw - 20.0) < 0.1


def test_mobilegaze_decodes_vertical_direction():
    service = GazeAIService()

    # yaw=0°, pitch=-20°.
    pitch, yaw = service._decode_angles([_logits(45), _logits(40)])

    assert abs(pitch + 20.0) < 0.1
    assert abs(yaw - 0.0) < 0.1
