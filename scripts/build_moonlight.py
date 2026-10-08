#!/usr/bin/env python3
"""Build the pinned Moonlight iOS application in Linux using an Xcode resource kit.

This is a project-specific builder, not a replacement for arbitrary Xcode builds.
No signing identity, device access, or account login is used.
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import importlib.util
import json
import os
import plistlib
import shlex
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REVISION='02dc9780496eeeac6d01c8bbdccb8b6fe71ef28a'
SSL_URL='https://github.com/krzyzanowskim/OpenSSL/releases/download/3.6.3000/OpenSSL.xcframework.zip'
SSL_SHA='6c4b064d12b8de2ae77ac59fbcbbd1c20b4fecfb7fc50b8ab326347c52ecbf0c'
PARSER_SHA='c22f8713a9808bd580eaa852ccf96ff4edcc19233e91667753197c0b3efcd295'

def digest(p):
    with open(p,'rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def run(command, log, cwd=None, env=None):
    with open(log,'w') as f:
        f.write('$ '+shlex.join(map(str,command))+'\n');f.flush()
        r=subprocess.run(list(map(str,command)),cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
    if r.returncode:
        raise RuntimeError(f'Command failed ({r.returncode}); see {log}\n'+Path(log).read_text()[-5000:])

def safe_path(root, name):
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve()): raise ValueError('Path escapes input root: '+name)
    return p

def verify_kit(kit, source):
    manifest=json.loads((kit/'manifest.json').read_text())
    if manifest['revision']!=REVISION: raise ValueError('Resource kit revision mismatch')
    for name,sha in manifest['files'].items():
        if digest(safe_path(kit,name))!=sha: raise ValueError('Corrupt resource: '+name)
    for name,sha in manifest['source_sha256'].items():
        if digest(safe_path(source,name))!=sha: raise ValueError('Resources do not match source: '+name)
    return manifest

def get_ssl(cache):
    archive=cache/'OpenSSL-3.6.3000.zip'
    if not archive.exists():
        tmp=archive.with_suffix('.download')
        urllib.request.urlretrieve(SSL_URL,tmp)
        if digest(tmp)!=SSL_SHA: raise ValueError('OpenSSL download checksum mismatch')
        tmp.rename(archive)
    if digest(archive)!=SSL_SHA: raise ValueError('OpenSSL cache checksum mismatch')
    dest=cache/'openssl-3.6.3000'
    # Re-extract only the device framework from the verified archive.
    dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if not entry.filename.startswith('OpenSSL.xcframework/ios-arm64/'): continue
            target=safe_path(dest,entry.filename)
            if entry.is_dir(): target.mkdir(parents=True,exist_ok=True);continue
            if stat.S_ISLNK(entry.external_attr>>16): raise ValueError('Unexpected OpenSSL symlink')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(z.read(entry))
    framework=dest/'OpenSSL.xcframework/ios-arm64/OpenSSL.framework'
    if not (framework/'OpenSSL').exists(): raise ValueError('OpenSSL arm64 slice missing')
    return framework

def sources(parser, project, target_name):
    gen=parser.Generator(str(project))
    target=next(o for o in gen.objs.values() if o.get('isa')=='PBXNativeTarget' and o.get('name')==target_name)
    parents=gen.build_parent_map();out=[]
    for phase_id in target['buildPhases']:
        phase=gen.objs[phase_id]
        if phase['isa']=='PBXShellScriptBuildPhase': raise ValueError('Review run-script phase before using this builder')
        if phase['isa']!='PBXSourcesBuildPhase': continue
        for bid in phase['files']:
            build=gen.objs[bid];ref=gen.objs[build['fileRef']]
            if ref.get('isa')=='XCVersionGroup' and ref.get('path','').endswith('.xcdatamodeld'):
                continue  # validated compiled model and generated classes come from the kit
            if build.get('settings',{}).get('COMPILER_FLAGS'): raise ValueError('Review per-file compiler flags')
            rel=ref.get('path') if ref.get('sourceTree')=='SOURCE_ROOT' else gen.resolved_ref_path(build['fileRef'],parents)
            if not rel: raise ValueError('Unresolved source reference')
            p=safe_path(project.parent,rel)
            if p.suffix in ('.c','.m','.swift'):out.append(p)
            elif p.suffix!='.xcdatamodeld':raise ValueError('Unsupported source '+str(p))
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',type=Path,required=True)
    ap.add_argument('--resource-kit',type=Path,required=True)
    ap.add_argument('--omarchy',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--sdk-bundle',type=Path,default=Path.home()/'.swiftpm/swift-sdks/darwin.artifactbundle')
    ap.add_argument('--swift-bin',type=Path,default=Path('/usr/lib/swift/usr/bin'))
    ap.add_argument('--cache-dir',type=Path,default=Path.home()/'.cache/moonlight-ios-build')
    ap.add_argument('--bundle-id',default='com.moonlight-stream.Moonlight')
    ap.add_argument('--build-number',default=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S'))
    a=ap.parse_args()
    source=a.project.resolve();kit=a.resource_kit.resolve();bundle=a.sdk_bundle.resolve()
    source_info=plistlib.loads((source/'Limelight/Limelight-Info.plist').read_bytes())
    if not source_info.get('UIApplicationSceneManifest',{}).get('UISceneConfigurations'):
        raise ValueError('UIScene lifecycle is required by the verified iOS 27 SDK. Apply patches/moonlight-scene-lifecycle.patch as documented before building.')
    manifest=verify_kit(kit,source)
    parser_path=a.omarchy/'tools/xcodeproj2xtool.py'
    if digest(parser_path)!=PARSER_SHA: raise ValueError('Unsupported Xcode project parser; use the documented omarchy revision')
    spec=importlib.util.spec_from_file_location('moonlight_pbx',parser_path)
    parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
    app_sources=sources(parser,source/'Moonlight.xcodeproj','Moonlight')
    common_sources=sources(parser,source/'moonlight-common/moonlight-common.xcodeproj','moonlight-common')
    sdk=next((bundle/'Developer/Platforms/iPhoneOS.platform/Developer/SDKs').glob('iPhoneOS*.*.sdk'))
    swift_resources=bundle/'Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift'
    clang=a.swift_bin/'clang';swiftc=a.swift_bin/'swiftc';linker=bundle/'toolset/bin/ld64.lld'
    for p in [sdk,clang,swiftc,linker]:
        if not p.exists():raise ValueError('Missing tool: '+str(p))
    a.cache_dir.mkdir(parents=True,exist_ok=True)
    ssl=get_ssl(a.cache_dir)
    ssl_include=a.cache_dir/'openssl-include';ssl_include.mkdir(exist_ok=True)
    alias=ssl_include/'openssl'
    if not alias.exists():alias.symlink_to(ssl/'Headers',target_is_directory=True)
    if alias.resolve()!=(ssl/'Headers').resolve():raise ValueError('Unexpected OpenSSL include alias')
    out=a.output_dir.resolve()/('Moonlight-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir(parents=True,exist_ok=False)
    logs=out/'logs';logs.mkdir();objects=out/'objects';objects.mkdir()
    app=out/'Payload/Moonlight.app';app.mkdir(parents=True)
    shutil.copytree(kit/'resources',app,dirs_exist_ok=True)
    shutil.copytree(ssl,app/'Frameworks/OpenSSL.framework')
    os.chmod(app/'Frameworks/OpenSSL.framework/OpenSSL',0o755)
    generated=kit/'generated'
    target=['-target','arm64-apple-ios15.0','-isysroot',str(sdk)]
    # Do not add every vendor subdirectory: libavutil/time.h would shadow the
    # SDK's <time.h> and hide Darwin clock declarations.
    headers={p.parent for p in (source/'Limelight').rglob('*.h')}
    headers|={objects,generated,ssl_include,source/'libs/SDL2/include',source/'libs/FFmpeg/include',source/'libs/opus/include/opus',source/'moonlight-common/moonlight-common-c/src',source/'moonlight-common/moonlight-common-c/enet/include',source/'moonlight-common/moonlight-common-c/nanors',source/'moonlight-common/moonlight-common-c/nanors/deps/obl',sdk/'usr/include/libxml2'}
    includes=[x for p in sorted(headers) for x in ['-I',str(p)]]+['-F',str(ssl.parent)]
    swift_files=[p for p in app_sources if p.suffix=='.swift']
    swift_obj=objects/'Swift.o'
    print('Compile Swift and generate Objective-C interface',flush=True)
    run([swiftc,'-target','arm64-apple-ios15.0','-sdk',sdk,'-resource-dir',swift_resources,'-swift-version','5','-O','-parse-as-library','-module-name','Moonlight','-import-objc-header',source/'Limelight/Input/Moonlight-Bridging-Header.h','-whole-module-optimization','-emit-object','-emit-objc-header','-emit-objc-header-path',objects/'Moonlight-Swift.h',*swift_files,'-o',swift_obj],logs/'swift.log')
    c_sources=[p for p in app_sources+common_sources if p.suffix in ('.c','.m')]+sorted(generated.glob('*.m'))
    def compile_one(pair):
        i,p=pair;obj=objects/f'{i:03d}-{p.stem}.o'
        flags=[*target,'-O2','-DNDEBUG','-D__APPLE_USE_RFC_3542','-std=gnu11',*includes]
        if p.name=='Platform.c':flags+=['-include','time.h']
        if p.suffix=='.m':flags+=['-fobjc-arc','-fmodules','-fmodules-cache-path='+str(a.cache_dir/'modules'),'-include',str(source/'Limelight/Limelight-Prefix.pch')]
        run([clang,*flags,'-c',p,'-o',obj],logs/f'{i:03d}-{p.stem}.log')
        return obj
    print(f'Compile {len(c_sources)} Objective-C/C sources',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        c_objects=list(pool.map(compile_one,enumerate(c_sources)))
    archives=[]
    bridge=source/'TailscaleBridge'
    if bridge.exists():
        print('Build embedded Tailscale',flush=True)
        run(['bash',bridge/'build-apple.sh'],logs/'tailscale.log')
        archives.append(bridge/'build/iphoneos/libMoonlightTailscale.a')
        run(['go','run','./cmd/notices',app/'Tailscale-LICENSES.txt'],logs/'licenses.log',cwd=bridge)
    archives += [source/'libs/SDL2/lib/iOS/libSDL2.a',source/'libs/opus/lib/iOS/libopus.a',*sorted((source/'libs/FFmpeg/lib/iOS').glob('*.a')),ssl/'OpenSSL']
    frameworks=['UIKit','Foundation','CoreFoundation','CoreGraphics','CoreData','CoreMotion','GameController','CoreHaptics','CoreBluetooth','AVFoundation','AVKit','AudioToolbox','VideoToolbox','QuartzCore','Metal','OpenGLES','CoreMedia','Security','SafariServices','Network']
    builtins=next((bundle/'Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/clang').glob('*/lib/darwin/libclang_rt.ios.a'))
    print('Link arm64 iOS executable',flush=True)
    run([clang,*target,'-mlinker-version=907','-fuse-ld='+str(linker),'-Wl,-rpath,/usr/lib/swift','-Wl,-rpath,@executable_path/Frameworks',*c_objects,swift_obj,*archives,builtins,*[x for f in frameworks for x in ['-framework',f]],'-lxml2','-lz','-liconv','-lresolv','-lc++','-L'+str(swift_resources/'iphoneos'),'-L'+str(sdk/'usr/lib/swift'),'-o',app/'Moonlight'],logs/'link.log')
    metadata=plistlib.loads((kit/'app-info.plist').read_bytes())
    if 'UIApplicationSceneManifest' in source_info:
        metadata['UIApplicationSceneManifest']=source_info['UIApplicationSceneManifest']
        metadata.pop('UIMainStoryboardFile',None)
        metadata.pop('UIMainStoryboardFile~ipad',None)
    # Xcode's resource build is not the provenance of the locally linked code.
    for key in list(metadata):
        if key.startswith('DT') or key=='BuildMachineOSBuild': metadata.pop(key)
    metadata.update(CFBundleIdentifier=a.bundle_id,CFBundleExecutable='Moonlight',CFBundleVersion=a.build_number,MinimumOSVersion='15.0')
    if bridge.exists():metadata['CFBundleDisplayName']='Moonlight TS'
    (app/'Info.plist').write_bytes(plistlib.dumps(metadata))
    shutil.copy2(source/'LICENSE.txt',app/'Moonlight-LICENSE.txt')
    os.chmod(app/'Moonlight',0o755)
    ipa=out/'Moonlight-9.0.2-unsigned.ipa'
    with zipfile.ZipFile(ipa,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted((out/'Payload').rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(out)))
    with zipfile.ZipFile(ipa) as z:
        if z.testzip():raise ValueError('IPA CRC check failed')
    run([a.swift_bin/'llvm-objdump','--macho','--private-headers',app/'Moonlight'],logs/'macho.log')
    run([a.swift_bin/'llvm-objdump','--macho','--dylibs-used',app/'Moonlight'],logs/'dependencies.log')
    report={'ipa':str(ipa),'sha256':digest(ipa),'bytes':ipa.stat().st_size,'bundle_id':a.bundle_id,'version':metadata['CFBundleShortVersionString'],'build':a.build_number,'source_revision_for_resources':manifest['revision'],'resource_xcode':manifest['xcode'],'resource_manifest_sha256':digest(kit/'manifest.json'),'openssl_sha256':SSL_SHA,'parser_sha256':digest(parser_path),'source_files':len(c_sources)+len(swift_files),'sdk':str(sdk),'unverified':['LiveContainer import and execution','real tailnet login and streaming']}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'SHA256SUMS.txt').write_text(report['sha256']+'  '+ipa.name+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
