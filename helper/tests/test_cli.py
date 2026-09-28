import json
import pytest
from cue import cli
from cue.media import Media
from cue.storage import Cache

def test_glossary_show_and_export(tmp_path,monkeypatch,capsys):
    video=tmp_path/'film.mp4';video.touch()
    media=Media(str(video),'sig',1,'stream',100000,0,1,1)
    monkeypatch.setattr(cli,'runtime_root',lambda:tmp_path/'runtime')
    monkeypatch.setattr(Media,'open',classmethod(lambda cls,path,hint:media))
    Cache(tmp_path/'runtime'/'cache').add_names('sig','zh-TW',{'Hansen':'漢森'},1000)
    (tmp_path/'film.cue-glossary.json').write_text(json.dumps({'zh-TW':{'Nash':'納許'}}),encoding='utf-8')
    monkeypatch.setattr('sys.argv',['cue-helper','glossary','show','--media',str(video),'--target','zh-TW'])
    cli.main()
    assert json.loads(capsys.readouterr().out)=={'user':{'Nash':'納許'},'learned':[{'source':'Hansen','rendering':'漢森','first_ms':1000}]}
    out=tmp_path/'export.json'
    monkeypatch.setattr('sys.argv',['cue-helper','glossary','export','--media',str(video),'--target','zh-TW','--output',str(out)])
    cli.main()
    assert json.loads(capsys.readouterr().out)=={'path':str(out),'entries':2}
    assert json.loads(out.read_text(encoding='utf-8'))=={'zh-TW':{'Hansen':'漢森','Nash':'納許'}}
    with pytest.raises(SystemExit):
        cli.main()
    assert '"OUTPUT_EXISTS"' in capsys.readouterr().err

def test_judge_writes_a_report_with_exclusive_creation(tmp_path,monkeypatch,capsys):
    from pathlib import Path
    import cue.judge, cue.setupflow
    video=tmp_path/'film.mp4';video.touch()
    media=Media(str(video),'sig',1,'stream',100000,0,1,1)
    monkeypatch.setattr(cli,'runtime_root',lambda:tmp_path/'runtime')
    monkeypatch.setattr(Media,'open',classmethod(lambda cls,path,hint:media))
    monkeypatch.setattr(cue.setupflow,'speech_model_path',lambda models,manifest,model_id:Path('/models/gemma-4-E4B-it.litertlm'))
    report={'media':'sig','target':'zh-TW','judge':'gemma-4-E4B-it.litertlm','language':'en','summary':{'count':1,'unjudged':0,'mean':4.0,'distribution':{'4':1},'source_not_ok':0,'mean_where_source_ok':4.0,'worst':[]},'results':[]}
    monkeypatch.setattr(cue.judge,'judge_captions',lambda *a,**k:report)
    out=tmp_path/'reports'/'judge.json'
    monkeypatch.setattr('sys.argv',['cue-helper','judge','--media',str(video),'--target','zh-TW','--judge','e4b','--output',str(out)])
    cli.main()
    assert json.loads(capsys.readouterr().out)['mean']==4.0 and json.loads(out.read_text(encoding='utf-8'))['summary']['count']==1
    with pytest.raises(SystemExit):
        cli.main()
    assert '"OUTPUT_EXISTS"' in capsys.readouterr().err
