"""
Dataset loaders for different SQL benchmark datasets.

This module provides a modular interface for loading and processing
different SQL-to-text benchmark datasets (BIRD, Spider, etc.).
"""
from .base import DatasetLoader, get_dataset_loader
from .bird import BirdDatasetLoader
from .spider import SpiderDatasetLoader

__all__ = [
    "DatasetLoader",
    "get_dataset_loader",
    "BirdDatasetLoader",
    "SpiderDatasetLoader",
]
