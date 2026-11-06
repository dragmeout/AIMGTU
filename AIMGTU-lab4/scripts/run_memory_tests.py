from pathlib import Path
import json,os,subprocess,sys,tempfile,time
import psutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.common import write_json,read_json,file_sha,DATA
from windows_job import MemoryJob

def limited(command,limit,ready,logpath):
    with MemoryJob(limit) as job,logpath.open('w',encoding='utf-8') as log:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        started=time.perf_counter()
        while not ready.exists():
            if proc.poll() is not None:raise RuntimeError('Worker exited before ready: '+str(logpath))
            if time.perf_counter()-started>30:raise TimeoutError('Worker handshake')
            time.sleep(.05)
        root=psutil.Process(proc.pid);tree=[root]+root.children(recursive=True)
        for child in reversed(tree):job.assign(child.pid)
        assert job.info()['limit_bytes']==limit
        proc.stdin.write('GO\n');proc.stdin.flush();proc.stdin.close()
        peak_rss=peak_commit=0;outside=set();seen=set()
        while True:
            info=job.info();peak_commit=max(peak_commit,info['peak_job_commit_bytes'])
            try:
                tree=[root]+root.children(recursive=True);rss=0
                for child in tree:
                    try:
                        rss+=child.memory_info().rss
                        if child.pid not in seen:
                            if not job.contains(child.pid):outside.add(child.pid)
                            seen.add(child.pid)
                    except psutil.NoSuchProcess:pass
                peak_rss=max(peak_rss,rss)
            except psutil.NoSuchProcess:pass
            if proc.poll() is not None:break
            if time.perf_counter()-started>600:proc.terminate();raise TimeoutError('Memory workload')
            time.sleep(.05)
        return {'exit_code':proc.returncode,'limit_bytes':limit,'limit_gib':limit/1024**3,'peak_job_commit_bytes':peak_commit,
                'peak_tree_rss_bytes':peak_rss,'peak_commit_gib':round(peak_commit/1024**3,3),'peak_rss_gib':round(peak_rss/1024**3,3),
                'processes_outside_job':sorted(outside),'checked_processes':len(seen),'elapsed_seconds':time.perf_counter()-started}

def main():
    if sys.platform!='win32':raise SystemExit('Windows Job Object tests require Windows')
    out=ROOT/'experiments/results';results=[]
    with tempfile.TemporaryDirectory(prefix='lab4_limits_') as temp:
        td=Path(temp);probe=td/'probe.py';ready=td/'probe.ready'
        probe.write_text("from pathlib import Path\nimport sys\nPath(sys.argv[1]).touch()\nassert sys.stdin.readline().strip()=='GO'\ntry:\n x=bytearray(256*1024*1024)\nexcept MemoryError:\n print('EXPECTED_MEMORY_ERROR',flush=True)\n sys.exit(23)\n",encoding='utf-8')
        enforcement=limited([sys.executable,str(probe),str(ready)],64*1024**2,ready,out/'memory_probe.log')
        enforcement['allocation_blocked']=enforcement['exit_code']==23 and 'EXPECTED_MEMORY_ERROR' in (out/'memory_probe.log').read_text(encoding='utf-8')
        assert enforcement['allocation_blocked']
        for gib in [8,16]:
            ready=td/f'{gib}.ready';answer_path=out/f'memory_{gib}gib_responses.json'
            print(f'MEM START {gib} GiB',flush=True)
            result=limited([sys.executable,str(ROOT/'scripts/memory_worker.py'),'--ready',str(ready),'--output',str(answer_path)],gib*1024**3,ready,out/f'memory_{gib}gib.log')
            result['status']='passed' if result['exit_code']==0 and not result['processes_outside_job'] else 'failed'
            worker=read_json(answer_path) if result['exit_code']==0 else {}
            assert worker.get('queries')==12 and worker.get('status')=='passed',result
            assert result['peak_job_commit_bytes']<=result['limit_bytes'] and result['peak_tree_rss_bytes']<=result['limit_bytes'],result
            results.append(result)
            write_json(out/'memory_limits.json',{'results':results,'enforcement_probe':enforcement,'host_physical_ram_bytes':psutil.virtual_memory().total,
              'mechanism':'Job-wide committed-memory limit. RSS separately sampled every 0.05 s. Does not emulate physical RAM for Windows.',
              'corpus_sha256':file_sha(DATA/'documents/clean_documents.jsonl'),'worker_sha256':file_sha(ROOT/'scripts/memory_worker.py')})
            print('MEM DONE '+json.dumps(result),flush=True)
if __name__=='__main__':main()
