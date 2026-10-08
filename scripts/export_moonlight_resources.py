#!/usr/bin/env python3
"""Export revision-matched app resources, never Apple SDKs or app executables."""
import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
from pathlib import Path

REVISION = '02dc9780496eeeac6d01c8bbdccb8b6fe71ef28a'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--derived', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    revision = subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip()
    if revision != REVISION:
        raise SystemExit('Unexpected upstream revision')
    app = a.derived/'Build/Products/Release-iphoneos/Moonlight.app'
    metadata = plistlib.loads((app/'Info.plist').read_bytes())
    a.output.mkdir(parents=True,exist_ok=False)
    resources = a.output/'resources'; resources.mkdir()
    excluded = {metadata['CFBundleExecutable'], 'Info.plist', 'Frameworks', '_CodeSignature', 'embedded.mobileprovision', 'PkgInfo'}
    for p in app.iterdir():
        if p.name in excluded: continue
        if p.is_dir(): shutil.copytree(p,resources/p.name)
        else: shutil.copy2(p,resources/p.name)
    for needed in ['iPhone.storyboardc','iPad.storyboardc','Limelight.momd','Assets.car']:
        if not (resources/needed).exists(): raise SystemExit('Missing resource '+needed)
    generated = a.output/'generated'; generated.mkdir()
    for p in a.derived.rglob('*+CoreData*'):
        if p.suffix in ('.h','.m') and p.is_file() and 'CoreDataGenerated' in p.parts:
            dst=generated/p.name
            if dst.exists() and dst.read_bytes()!=p.read_bytes(): raise SystemExit('Conflicting generated model '+p.name)
            shutil.copy2(p,dst)
    if not (generated/'Host+CoreDataClass.h').exists(): raise SystemExit('No Objective-C model code')
    (a.output/'app-info.plist').write_bytes(plistlib.dumps(metadata))
    shutil.copy2(a.source/'LICENSE.txt',a.output/'Moonlight-LICENSE.txt')
    # Reject native executables/libraries even if Xcode adds an unexpected path.
    magics={bytes.fromhex(h) for h in ['cffaedfe','cefaedfe','feedfacf','feedface','cafebabe','bebafeca']}
    for p in resources.rglob('*'):
        if p.is_file() and p.read_bytes()[:4] in magics:
            raise SystemExit('Unexpected Mach-O in resource output: '+str(p))
    hashes={str(p.relative_to(a.output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(a.output.rglob('*')) if p.is_file()}
    source_hashes={str(p.relative_to(a.source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(a.source.rglob('*')) if p.is_file() and (p.suffix in ('.storyboard','.xib') or 'Limelight.xcdatamodeld' in p.parts or 'Images.xcassets' in p.parts)}
    (a.output/'manifest.json').write_text(json.dumps({'repository':'https://github.com/moonlight-stream/moonlight-ios','revision':revision,'xcode':subprocess.check_output(['xcodebuild','-version'],text=True).strip(),'sdk':metadata.get('DTSDKName'),'source_sha256':source_hashes,'files':hashes},indent=2)+'\n')

if __name__ == '__main__': main()
