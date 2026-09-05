"""Synthetic data generation for the X5 hackathon PoC."""

from .generate import generate
from .target import prepare_target_dataset, validate_target_rows

__all__ = ["generate", "prepare_target_dataset", "validate_target_rows"]
