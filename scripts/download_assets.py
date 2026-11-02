"""Download pinned, hash-checked model/runtime files. No account or API key."""
from pathlib import Path
import argparse,hashlib,json,time,urllib.request,zipfile
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()

def download(asset,offline=False):
    path=ROOT/asset['path'];path.parent.mkdir(parents=True,exist_ok=True)
    if not(path.exists() and path.stat().st_size==asset['bytes'] and sha(path)==asset['sha256']):
        if offline:raise FileNotFoundError(f'Missing or invalid: {path}')
        partial=path.with_suffix(path.suffix+'.part')
        for attempt in range(3):
            try:
                request=urllib.request.Request(asset['url'],headers={'User-Agent':'AIMGTU-Lab3'})
                with urllib.request.urlopen(request,timeout=90) as r,partial.open('wb') as f:
                    while b:=r.read(1024*1024):f.write(b)
                if partial.stat().st_size!=asset['bytes'] or sha(partial)!=asset['sha256']:raise ValueError('Asset hash mismatch')
                partial.replace(path);break
            except Exception:
                if attempt==2:raise
                time.sleep(2)
    if asset.get('extract'):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if not (path.parent/n).resolve().is_relative_to(path.parent.resolve()):raise ValueError('Unsafe archive path')
            z.extractall(path.parent)
    print('OK:',asset['path'],flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true');args=parser.parse_args()
    assets=json.loads((ROOT/'config/assets.json').read_text(encoding='utf-8'))['assets']
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda a:download(a,args.verify_only),assets))
if __name__=='__main__':main()
