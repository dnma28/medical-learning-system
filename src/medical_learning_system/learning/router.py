from enum import Enum

from pydantic import BaseModel


class LearningRoute(str, Enum):
    SOURCE_RETRIEVAL = "source_retrieval"
    CONCEPT_EXPLANATION = "concept_explanation"
    ACTIVE_RECALL = "active_recall"
    ERROR_REMEDIATION = "error_remediation"


class LearningRequest(BaseModel):
    query: str
    wants_quiz: bool = False
    known_error_id: str | None = None
    needs_source_lookup: bool = True


class LearningRouter:
    def route(self, request: LearningRequest) -> LearningRoute:
        if request.known_error_id:
            return LearningRoute.ERROR_REMEDIATION
        if request.wants_quiz:
            return LearningRoute.ACTIVE_RECALL
        if request.needs_source_lookup:
            return LearningRoute.SOURCE_RETRIEVAL
        return LearningRoute.CONCEPT_EXPLANATION
