from abc import ABC, abstractmethod


class AIProvider(ABC):

    @abstractmethod
    async def generate(self, messages, model=None, **kwargs):
        """
        Generate a response from the AI provider.
        """
        pass

    @abstractmethod
    async def health_check(self):
        """
        Check whether the provider is available.
        """
        pass

