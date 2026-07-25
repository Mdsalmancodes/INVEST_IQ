"""FileSystemPredictionRunRepository — implements
src.domain.ml.repositories.PredictionRunRepository.

Per Document 4 §10.2 step 4: "Immutable PredictionRun written to Mongo,
never overwritten." Persisted here as one append-only JSON-lines file per
symbol (`<storage_root>/<SYMBOL>.jsonl`) — appending a line is the local-
filesystem equivalent of Mongo's insert-only collection semantics; no
code path in this repository ever rewrites an existing line, preserving
the "never overwritten" invariant even in this disclosed local substitute
for the frozen architecture's MongoDB collection.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.domain.ml.entities import Forecast, HorizonPoint, PredictionRun
from src.domain.ml.value_objects import (
    Confidence,
    ExplainabilityPayload,
    FeatureContribution,
    ModelVersionId,
    PredictionRunId,
)


class FileSystemPredictionRunRepository:
    def __init__(self, storage_root: str | Path) -> None:
        self._root = Path(storage_root)

    async def save(self, prediction_run: PredictionRun) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{prediction_run.symbol}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_to_json_dict(prediction_run)) + "\n")

    async def get_by_id(self, prediction_run_id: PredictionRunId) -> PredictionRun | None:
        if not self._root.exists():
            return None
        for path in self._root.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if data["id"] == str(prediction_run_id):
                    return _from_json_dict(data)
        return None

    async def list_for_symbol(self, symbol: str, limit: int = 20) -> tuple[PredictionRun, ...]:
        path = self._root / f"{symbol.upper()}.jsonl"
        if not path.exists():
            return ()
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        # Most-recent-first, matching how a caller displaying "prediction
        # history" would want the latest run shown first.
        recent_lines = list(reversed(lines))[:limit]
        return tuple(_from_json_dict(json.loads(line)) for line in recent_lines)


def _to_json_dict(prediction_run: PredictionRun) -> dict[str, Any]:
    return {
        "id": str(prediction_run.id),
        "symbol": prediction_run.symbol,
        "member_forecasts": [_forecast_to_dict(f) for f in prediction_run.member_forecasts],
        "ensemble_price": prediction_run.ensemble_price,
        "ensemble_confidence": prediction_run.ensemble_confidence.value,
        "data_quality": prediction_run.data_quality,
        "explainability": _explainability_to_dict(prediction_run.explainability),
        "created_at": prediction_run.created_at.isoformat(),
        "actual_price": prediction_run.actual_price,
    }


def _forecast_to_dict(forecast: Forecast) -> dict[str, Any]:
    data: dict[str, Any] = asdict(forecast)
    data["id"] = str(forecast.id)
    data["model_version_id"] = str(forecast.model_version_id)
    data["confidence"] = forecast.confidence.value
    data["created_at"] = forecast.created_at.isoformat()
    return data


def _explainability_to_dict(payload: ExplainabilityPayload) -> dict[str, Any]:
    return {
        "top_contributions": [asdict(c) for c in payload.top_contributions],
        "base_value": payload.base_value,
        "method": payload.method,
        "reasoning": payload.reasoning,
    }


def _from_json_dict(data: dict[str, Any]) -> PredictionRun:
    member_forecasts = tuple(
        Forecast(
            id=PredictionRunId.from_string(f["id"]),
            symbol=f["symbol"],
            model_family=f["model_family"],
            model_version_id=ModelVersionId.from_string(f["model_version_id"]),
            points=tuple(HorizonPoint(**p) for p in f["points"]),
            confidence=Confidence(f["confidence"]),
            data_quality=f["data_quality"],
            created_at=datetime.fromisoformat(f["created_at"]),
        )
        for f in data["member_forecasts"]
    )
    explainability_data = data["explainability"]
    explainability = ExplainabilityPayload(
        top_contributions=tuple(
            FeatureContribution(**c) for c in explainability_data["top_contributions"]
        ),
        base_value=explainability_data["base_value"],
        method=explainability_data["method"],
        reasoning=explainability_data["reasoning"],
    )
    return PredictionRun(
        id=PredictionRunId.from_string(data["id"]),
        symbol=data["symbol"],
        member_forecasts=member_forecasts,
        ensemble_price=float(data["ensemble_price"]),
        ensemble_confidence=Confidence(float(data["ensemble_confidence"])),
        data_quality=data["data_quality"],
        explainability=explainability,
        created_at=datetime.fromisoformat(data["created_at"]),
        actual_price=data["actual_price"],
    )
