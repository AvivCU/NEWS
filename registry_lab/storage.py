"""Version-pinned Release asset restore; no publication or CRM access."""
import gzip, hashlib, json, os, re, subprocess, tempfile
from contextlib import closing
from pathlib import Path
from resolver import connect

def digest(path):
    with open(path,'rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def fetch(manifest, target):
    subprocess.run(['gh','release','download',manifest['tag'],'--repo',manifest['repo'],'--pattern',manifest['asset'],'--output',str(target)],check=True,timeout=120)

def ensure(manifest, target, downloader=fetch):
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    for key in ('db_sha256','asset_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}',manifest[key]):
            raise ValueError('Invalid hash')
    if not 0 < manifest['db_bytes'] <= 2_000_000_000 or not 0 < manifest['count']:
        raise ValueError('Invalid manifest limits')
    if not re.fullmatch(r'[a-zA-Z0-9._-]+',manifest['asset']) or not re.fullmatch(r'[a-zA-Z0-9._/-]+',manifest['tag']):
        raise ValueError('Invalid asset/tag')
    def verify(path):
        if path.stat().st_size!=manifest['db_bytes'] or digest(path)!=manifest['db_sha256']:
            raise ValueError('Database size/hash mismatch')
        with closing(connect(path)) as db:
            if db.execute('SELECT count(*) FROM companies').fetchone()[0]!=manifest['count']:
                raise ValueError('Registry count mismatch')
    if target.exists():
        try:
            verify(target)
            return 'cache_hit'
        except (OSError, ValueError):
            pass
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        asset=Path(tmp)/'asset.gz'; db=Path(tmp)/'registry.sqlite'
        downloader(manifest,asset)
        if digest(asset)!=manifest['asset_sha256']:
            raise ValueError('Release asset hash mismatch')
        total=0
        with gzip.open(asset,'rb') as src, open(db,'wb') as dst:
            while chunk:=src.read(1024*1024):
                total+=len(chunk)
                if total>manifest['db_bytes']:
                    raise ValueError('Decompression limit exceeded')
                dst.write(chunk)
        verify(db)
        os.replace(db,target)
    return 'restored'

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('manifest'); p.add_argument('target'); a=p.parse_args()
    print(ensure(json.loads(Path(a.manifest).read_text()),a.target))
