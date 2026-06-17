import math

from ml.model_trainer import load_model
from utils.logger import logger


def predict_probability(feature_vector):
    """
    Score the setup as a probability-like percentage.
    """

    try:
        model = load_model()
        linear_value = model.get("bias", 0.0)
        for feature_name, weight in model.get("weights", {}).items():
            linear_value += feature_vector.get(feature_name, 0.0) * weight

        probability = 1 / (1 + math.exp(-linear_value))
        return round(probability * 100, 2)

    except Exception as exc:
        logger.error(f"Prediction failed: {exc}")
        return 0.0
