import logging
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from ..eval.regression import run_regression_eval
from ..rag import query_rag

logger = logging.getLogger(__name__)

router = APIRouter()


class RegressionEvalRequest(BaseModel):
    top_k: int = 3


@router.post("/eval/regression")
def regression_eval(req: RegressionEvalRequest) -> Dict[str, Any]:
    logger.info("Received regression eval request top_k=%s", req.top_k)
    summary = run_regression_eval(query_fn=query_rag, top_k=req.top_k)
    logger.info("Regression eval summary run_id=%s", summary.get("run_id"))
    return summary
