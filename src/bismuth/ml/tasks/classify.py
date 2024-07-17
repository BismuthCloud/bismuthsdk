from typing import Any, Optional
from enum import Enum
import datetime
import logging
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .base import Task, TaskConfig
from ..connectors.base import DataConnector, DataConnectorView

class Algorithm(Enum):
    DECISION_TREE = "decision_tree"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    ANN = "ann"
    SVM = "svm"
    LLM = "llm"

class Classifier(Task):
    model: Any
    
    def __init__(self, identifier: str, inputs: DataConnectorView, label: DataConnectorView, override_algorithm: Optional[Algorithm] = None, seed: Optional[int] = None):
        assert inputs.connector == label.connector, "DataConnector for input and label must be the same."

        super().__init__(identifier, seed)
        self.log = logging.getLogger(__name__)
        self.connector = inputs.connector
        self.inputs = inputs
        self.label = label
        
        if override_algorithm is not None:
            config = self.get_config()
            if config is not None and config.selected_algorithm != override_algorithm.value:
                self.log.warning(f"override_algorithm set, but chosen algorithm is {config.selected_algorithm}.")
            self.model = self.load_model(override_algorithm.value)
            if self.model is None:
                self.log.info(f"Model for {override_algorithm} not found.")
                self.model, score = self.train(override_algorithm)
                self.persist_model(override_algorithm.value, self.model)
        #self.set_config(TaskConfig(selected_algorithm=algorithm.value, score=score, last_updated=datetime.datetime.now().isoformat()))
    
    def train(self, algorithm: Algorithm) -> tuple[Any, float]:
        match algorithm:
            case Algorithm.DECISION_TREE:
                model = make_pipeline(StandardScaler(), DecisionTreeClassifier(max_depth=5, random_state=self.seed))
            case _:
                raise ValueError(f"Unknown algorithm {algorithm}.")

        data = self.connector.sample(self.connector.approx_count, seed=self.seed)
        train, test = train_test_split(data, test_size=0.3, random_state=self.seed)
        self.log.info(f"Training {algorithm} model on {len(train)} samples.")
        model.fit(train[self.inputs.columns], train[self.label.columns])
        score = model.score(test[self.inputs.columns], test[self.label.columns])
        self.log.info(f"Model trained with score {score}.")
        return model, score

    def predict(self, inputs: list[Any]) -> Any:
        return self.model.predict(inputs)