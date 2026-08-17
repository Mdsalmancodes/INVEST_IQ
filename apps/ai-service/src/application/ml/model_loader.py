# src/application/ml/model_loader.py

class ModelLoader:
    async def load_all_models(self, symbol: str):
        """
        Temporary mock model loader.
        Later we will load:
        - LSTM
        - ARIMA
        - Prophet
        - XGBoost
        - RandomForest
        """

        return {
            "lstm": None,
            "arima": None,
            "prophet": None,
            "xgboost": None,
            "random_forest": None
        }