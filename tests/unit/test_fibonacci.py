"""Unit tests for Fibonacci utility."""

import pytest

from cc_spec.utils.fibonacci import fibonacci


def test_fibonacci_base_cases() -> None:
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(2) == 1


def test_fibonacci_sequence_values() -> None:
    assert fibonacci(3) == 2
    assert fibonacci(4) == 3
    assert fibonacci(5) == 5
    assert fibonacci(10) == 55


def test_fibonacci_negative_raises() -> None:
    with pytest.raises(ValueError):
        fibonacci(-1)


def test_fibonacci_non_int_raises() -> None:
    with pytest.raises(TypeError):
        fibonacci(1.5)
    with pytest.raises(TypeError):
        fibonacci("3")  # type: ignore[arg-type]
