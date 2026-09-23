from pydantic import BaseModel, Field


class SessionStage(BaseModel):
    name: str
    minutes: int = Field(gt=0)
    objective: str


class Hoc90Session(BaseModel):
    topic: str
    target_outcome: str
    stages: list[SessionStage]

    @property
    def total_minutes(self) -> int:
        return sum(stage.minutes for stage in self.stages)

    def is_90_minutes(self) -> bool:
        return self.total_minutes == 90
