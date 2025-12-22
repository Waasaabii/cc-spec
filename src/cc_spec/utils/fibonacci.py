"""Utility to compute Fibonacci numbers."""


def fibonacci(n: int) -> int:
    """Return the nth Fibonacci number (0-indexed).

    Args:
        n: Non-negative integer index.

    Raises:
        TypeError: If n is not an int.
        ValueError: If n is negative.
    """
    if not isinstance(n, int):
        raise TypeError("n must be an int")
    if n < 0:
        raise ValueError("n must be non-negative")

    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
