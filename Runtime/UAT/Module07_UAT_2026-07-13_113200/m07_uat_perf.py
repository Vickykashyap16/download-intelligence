"""
Module 07 UAT — Performance measurement addendum (Release Audit PCV Check 12
continuation). Mirrors Module 05/06's own precedent methodology exactly:
Tests/Large Batch/ (75 synthetic files), isolated /tmp Database/Runtime paths,
instant fixed-answer fake providers for Modules 02/03 (judgment latency is not
what's being measured), a monkeypatched load_source_config()/destination_root
(no edit to the real src/config/sources.yaml). Measures the complete real
Module 01->07 chain including preview() and execute(), comparing against
Module 06's own 40.122s Module 01-06 baseline (same 75-file dataset).
"""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence ")

from src.pipeline.classification import (
    ClassificationProvider, ClassificationResult, ProviderMetadata as CPM, ProviderResponse as CPR,
)
from src.pipeline.metadata import (
    MetadataExtractionProvider, ProviderMetadata as MPM, ProviderResponse as MPR,
)
from src.storage import database as dbmod
from src.storage import runtime_io as riomod
from src import main as mainmod

TMP = Path("/tmp/m07_uat_perf_run")
if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)
SOURCE_DIR = TMP / "downloads"
SOURCE_DIR.mkdir()
LIBRARY_ROOT = TMP / "library"
LIBRARY_ROOT.mkdir()

dbmod._METADATA_STORE_PATH = TMP / "metadata_store.json"
dbmod._HASH_INDEX_PATH = TMP / "hash_index.json"
dbmod._PHASH_INDEX_PATH = TMP / "phash_index.json"
dbmod._NAME_INDEX_PATH = TMP / "name_index.json"
dbmod._VERSION_HISTORY_PATH = TMP / "version_history.json"
dbmod._USER_CORRECTIONS_PATH = TMP / "user_corrections.json"
riomod._ACTION_LOG_PATH = TMP / "action_log.jsonl"
riomod._RUNTIME_TEMP_PATH = TMP / "Temp"

REPO = Path("/sessions/nice-fervent-wozniak/mnt/Download Intelligence ")
LARGE_BATCH = REPO / "Tests/Large Batch"

for f in LARGE_BATCH.iterdir():
    if f.is_file():
        shutil.copy2(f, SOURCE_DIR / f.name)

mainmod.load_source_config = lambda: {"path": str(SOURCE_DIR), "source_id": "downloads"}
SOURCES_YAML = TMP / "sources.yaml"
SOURCES_YAML.write_text(f"destination_root: {LIBRARY_ROOT}\n")
mainmod._SOURCES_CONFIG_PATH = SOURCES_YAML


class ConstantClassificationProvider(ClassificationProvider):
    def classify(self, request):
        return CPR(result=ClassificationResult(category="Document"), metadata=CPM(provider_name="Constant"))


class ConstantMetadataExtractionProvider(MetadataExtractionProvider):
    def extract(self, request):
        fields = {k: None for k in request.fields_requested}
        return MPR(fields=fields, metadata=MPM(provider_name="Constant"))


fake_cls = ConstantClassificationProvider()
fake_meta = ConstantMetadataExtractionProvider()

print(f"Files in Large Batch: {sum(1 for f in SOURCE_DIR.iterdir())}")

t0 = time.time()
mainmod.scan()
mainmod.classify(provider=fake_cls)
mainmod.extract(provider=fake_meta)
mainmod.detect_duplicates()
mainmod.suggest_naming()
mainmod.score_confidence()
t_pipeline16 = time.time()
mainmod.preview()
t_preview = time.time()
mainmod.execute()
t_execute = time.time()

records = dbmod.load_metadata_store()
discovered = len(records)
scored = sum(1 for r in records if r.confidence_score is not None)
executed = sum(1 for r in records if r.processed_at is not None)
by_tier = {}
for r in records:
    by_tier[r.tier] = by_tier.get(r.tier, 0) + 1

print(f"\nDiscovered: {discovered}  Scored: {scored}  Executed: {executed}")
print(f"Tier spread: {by_tier}")
print(f"\nModules 1-6 (scan->score_confidence) time: {t_pipeline16 - t0:.3f}s")
print(f"preview() time: {t_preview - t_pipeline16:.3f}s")
print(f"execute() time: {t_execute - t_preview:.3f}s")
print(f"TOTAL Module 1-7 (scan->execute, includes preview) time: {t_execute - t0:.3f}s")
