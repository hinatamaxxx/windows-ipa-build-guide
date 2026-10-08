"""Input integrity checks for the Moonlight resource handoff."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('builder',Path(__file__).resolve().parents[1]/'scripts/build_moonlight.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class ResourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.kit=self.root/'kit';self.kit.mkdir()
        self.source=self.root/'source';self.source.mkdir()
        (self.kit/'screen').write_bytes(b'compiled screen')
        (self.source/'screen.storyboard').write_bytes(b'source screen')
        self.manifest={'revision':builder.REVISION,'files':{'screen':builder.digest(self.kit/'screen')},'source_sha256':{'screen.storyboard':builder.digest(self.source/'screen.storyboard')}}
        self.save()

    def save(self):
        (self.kit/'manifest.json').write_text(json.dumps(self.manifest))

    def test_matching_kit_and_source(self):
        self.assertEqual(builder.verify_kit(self.kit,self.source),self.manifest)

    def test_changed_storyboard_rejected(self):
        (self.source/'screen.storyboard').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Resources do not match'):
            builder.verify_kit(self.kit,self.source)

    def test_corrupted_resource_rejected(self):
        (self.kit/'screen').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'Corrupt resource'):
            builder.verify_kit(self.kit,self.source)

    def test_manifest_path_escape_rejected(self):
        self.manifest['files']={'../outside':'unused'};self.save()
        with self.assertRaisesRegex(ValueError,'Path escapes'):
            builder.verify_kit(self.kit,self.source)

if __name__=='__main__':unittest.main()
