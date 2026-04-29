"""
Abstract base class for dataset loaders.

All dataset implementations must inherit from DatasetLoader and implement
the required methods to provide a unified interface for the benchmark runner.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional


class DatasetLoader(ABC):
    """
    Abstract base class for SQL benchmark dataset loaders.
    
    Each dataset (BIRD, Spider, etc.) must implement this interface to:
    - Download and prepare the dataset
    - Load questions with their metadata
    - Resolve database file paths
    - Format hints/evidence for the agent
    - Provide dataset-specific metadata
    """

    @abstractmethod
    def download(self, data_dir: Path, force: bool = False) -> Path:
        """
        Download and extract the dataset.
        
        Args:
            data_dir: Directory to store the dataset
            force: Force re-download even if already present
            
        Returns:
            Path to the extracted dataset directory
        """
        pass

    @abstractmethod
    def load_questions(self, dev_dir: Path) -> List[Dict]:
        """
        Load questions from the dataset.
        
        Returns a list of dicts with keys:
            - question_id: Unique identifier
            - db_id: Database identifier
            - question: Natural language question
            - gold_sql: Ground truth SQL query
            - difficulty: Difficulty level (dataset-specific)
            - evidence: Optional hints/evidence for the question
            
        Args:
            dev_dir: Path to the dataset directory
            
        Returns:
            List of question dictionaries
        """
        pass

    @abstractmethod
    def get_db_path(self, dev_dir: Path, db_id: str) -> Path:
        """
        Resolve the SQLite database path for a given db_id.
        
        Args:
            dev_dir: Path to the dataset directory
            db_id: Database identifier
            
        Returns:
            Path to the SQLite database file
        """
        pass

    @abstractmethod
    def format_hints(self, question: str, evidence: str) -> str:
        """
        Format the question with hints/evidence for the agent.
        
        Args:
            question: The natural language question
            evidence: Hints/evidence from the dataset
            
        Returns:
            Formatted query string with hints
        """
        pass

    @abstractmethod
    def get_difficulty_levels(self) -> List[str]:
        """
        Get the valid difficulty levels for this dataset.
        
        Returns:
            List of difficulty level strings
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Get the dataset name.
        
        Returns:
            Dataset name
        """
        raise NotImplementedError

    @abstractmethod
    def get_database_type(self) -> str:
        """
        Get the database type for this dataset.
        
        Returns:
            Database type (e.g., "sqlite", "postgresql", "mysql")
        """
        raise NotImplementedError

    @abstractmethod
    def get_database_base_path(self, dev_dir: Path) -> Path:
        """
        Get the base directory containing all databases.
        
        Args:
            dev_dir: Path to the dataset directory
            
        Returns:
            Base path for databases
        """
        raise NotImplementedError

    def get_database_metadata(self, dev_dir: Path, db_id: str) -> dict:
        """
        Get metadata about a specific database.
        
        Args:
            dev_dir: Path to the dataset directory
            db_id: Database identifier
            
        Returns:
            Dictionary with database metadata including:
            - type: Database type
            - path: Full path to database
            - base_path: Base directory for databases
            - connection_params: Additional connection parameters if needed
        """
        return {
            "type": self.get_database_type(),
            "path": str(self.get_db_path(dev_dir, db_id)),
            "base_path": str(self.get_database_base_path(dev_dir)),
            "connection_params": {}
        }


def get_dataset_loader(dataset_name: str) -> DatasetLoader:
    """
    Factory function to get a dataset loader by name.
    
    Args:
        dataset_name: Name of the dataset ("bird", "spider", etc.)
        
    Returns:
        DatasetLoader instance
        
    Raises:
        ValueError: If dataset name is not recognized
    """
    from .bird import BirdDatasetLoader
    from .spider import SpiderDatasetLoader

    loaders = {
        "bird": BirdDatasetLoader,
        "spider": SpiderDatasetLoader,
    }

    loader_class = loaders.get(dataset_name.lower())
    if loader_class is None:
        raise ValueError(
            f"Unknown dataset: {dataset_name}. "
            f"Available datasets: {', '.join(loaders.keys())}"
        )
    
    return loader_class()
