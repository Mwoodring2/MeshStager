"""Analysis orchestration; publish only after successful, uncanceled completion."""
from .analyzer import analyze_catalog
from .models import checkpoint
from .repository import HousekeepingRepository

class HousekeepingService:
    def __init__(self, repository=None):
        self.repository = repository or HousekeepingRepository()

    def analyze(self, records, root, *, canceled=lambda: False, progress=lambda stage: None, **options):
        findings, stats = analyze_catalog(records, root, canceled=canceled, progress=progress, **options)
        checkpoint(canceled)
        progress("Saving findings…")
        self.repository.publish(root, findings, stats.total_assets, canceled)
        return self.repository.load(root), stats

    def load(self, root):
        return self.repository.load(root)

    def ignore(self, root, findings):
        self.repository.ignore(root, findings)
        return self.repository.load(root)

    def close(self):
        self.repository.close()
