class Orchestrator:
    def __init__(self):
        self.providers = {}

    def register_provider(self, name, provider):
        self.providers[name] = provider

    def get_provider(self, name):
        return self.providers.get(name)

    def list_providers(self):
        return list(self.providers.keys())