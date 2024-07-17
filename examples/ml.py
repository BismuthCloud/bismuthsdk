from bismuth.ml.connectors import FileConnector
from bismuth.ml.tasks.classify import Classifier, Algorithm

import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    connector = FileConnector("src/bismuth/ml/connectors/testdata/iris.csv")
    inputs = connector[["sepal.length", "sepal.width", "petal.length", "petal.width"]]
    label = connector[["variety"]]

    classifier = Classifier("iris", inputs, label, override_algorithm=Algorithm.DECISION_TREE)
    print(classifier.predict([[5.1, 3.5, 1.4, 0.2]]))