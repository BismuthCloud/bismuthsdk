from typing import Any, Optional
from dataclasses import dataclass, asdict
import numpy as np
import pickle
import random

from ...codeblocks.persistent_data_storage_code_block import PersistentDataStorageCodeBlock

@dataclass
class TaskConfig:
    selected_algorithm: str
    score: float
    last_updated: str

class Task:
    identifier: str
    seed: Optional[int]
    
    def __init__(self, identifier: str, seed: Optional[int] = None):
        self.identifier = identifier
        self.seed = seed
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        self._model_config = PersistentDataStorageCodeBlock()
        self._model_storage = PersistentDataStorageCodeBlock()
    
    def get_config(self) -> Optional[TaskConfig]:
        config = self._model_config.retrieve(self.identifier)
        if config is None:
            return None
        return TaskConfig(**config)
    
    def set_config(self, config: TaskConfig):
        self._model_config.create(self.identifier, asdict(config))
    
    def load_model(self, algorithm: str) -> Optional[Any]:
        data = self._model_storage.retrieve(f"{self.identifier}_{algorithm}")
        if data is None:
            return None

        try:
            return pickle.loads(data)
        except Exception as e:
            print(e)
            return None
        
    def persist_model(self, algorithm: str, model):
        self._model_storage.create(f"{self.identifier}_{algorithm}", pickle.dumps(model))