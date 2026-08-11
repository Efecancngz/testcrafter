from abc import ABC, abstractmethod

from app.schemas import PageStructure, GeneratedScenario


class AIProvider(ABC):
    @abstractmethod
    def generate_scenarios(self, page_structure: PageStructure, description: str) -> list[GeneratedScenario]:
        ...
