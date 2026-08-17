from fastapi import APIRouter, Query

from src.application.prediction.predict_use_case import PredictUseCase

router = APIRouter()


@router.get("/predict")
async def predict(symbol: str = Query(...)):
    use_case = PredictUseCase()
    return await use_case.execute(symbol)