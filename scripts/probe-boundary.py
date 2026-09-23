"""Reproduce the generated video boundary rejection and bounded retry."""
from cue.pipeline import Pipeline
from cue.media import Media
from cue.core import Settings
from cue.storage import Cache
from dataclasses import asdict
from pathlib import Path
import json
c=Cache(Path('.runtime/cache'));previous=[]
for p, in c.db.execute("SELECT profile FROM profiles WHERE target='original'"):
    try:
        _,rows,_=c.read(p)
        matching=[asdict(x) for x in rows if x.end_ms<=88673]
        if matching and matching[-1]['end_ms']==88673:previous=matching[-1:]
    except Exception:pass
pipeline=Pipeline(Path('.runtime/models').resolve(),Path('.runtime/audio-temp').resolve())
results=[]
try:
    for span,context in ((16000,1000),(8000,2000)):
        row={'start_ms':88673,'span_ms':span,'context_ms':context}
        try:
            row['result']=pipeline.run({'media':asdict(Media.open(str(Path('benchmarks/fixtures/generated/cue-player-test.mp4').resolve()),{})), 'settings':asdict(Settings(source='auto',target='zh-TW',context_ms=context)), 'range':[88673,88673+span],'source_profile':'native-diagnostic','previous_source':previous})
            row['status']='pass'
        except Exception as e:row.update(status='failed',code=getattr(e,'code',type(e).__name__),detail=str(e))
        results.append(row);print(row['status'],row.get('detail',''),flush=True)
        Path('benchmarks/results/native-boundary-probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
finally:pipeline.backend.close()
