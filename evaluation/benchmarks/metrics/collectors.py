"""Optional observers installed only in the isolated benchmark process."""
import threading, time

class Collector:
    def __init__(self,mode): self.mode=mode;self.events=[];self.lock=threading.Lock()
    def add(self,**event):
        with self.lock: self.events.append({'wall_time':time.time(),**event})
    def snapshot(self):
        with self.lock: return list(self.events)
    def install(self):
        from metrics import GLOBAL_METRICS as m
        for name,kind in [('record_lock_wait','sqlite_lock_wait'),('record_tx_duration','sqlite_transaction'),('record_vlm_duration','vlm_client')]:
            original=getattr(m,name)
            def wrapped(seconds,_original=original,_kind=kind):
                _original(seconds); self.add(kind=_kind,duration_ms=seconds*1000,mode=self.mode)
            setattr(m,name,wrapped)
        import vlm_inspector as vi
        original_generate=vi.ollama_generate
        def observed(payload,**kw):
            start=time.perf_counter()
            try:
                body=original_generate(payload,**kw)
                import json
                try:
                    raw=json.loads(body.get('response') or '{}');raw_valid=isinstance(raw,dict)
                except (ValueError,TypeError):raw_valid=False
                self.add(kind='ollama',client_ms=(time.perf_counter()-start)*1000,model=payload.get('model'),
                    options=payload.get('options'),raw_json_valid=raw_valid,
                    mode='real',**{k:body.get(k) for k in ['total_duration','load_duration','prompt_eval_duration','eval_duration','prompt_eval_count','eval_count']})
                return body
            except Exception as e:
                self.add(kind='ollama',client_ms=(time.perf_counter()-start)*1000,model=payload.get('model'),mode='real',error=type(e).__name__)
                raise
        vi.ollama_generate=observed

class GPUSampler:
    def __init__(self):
        self.rows=[];self.stop=threading.Event();self.thread=None
    def start(self):
        def sample():
            import subprocess
            while not self.stop.is_set():
                try:
                    value=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu,memory.used','--format=csv,noheader,nounits'],text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
                    self.rows.append({'timestamp':time.time(),'gpu_util_percent_and_memory_mib':value})
                except (OSError,subprocess.SubprocessError):pass
                self.stop.wait(1)
        self.thread=threading.Thread(target=sample,daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=3)
