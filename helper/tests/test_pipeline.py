import pytest
from dataclasses import asdict
import numpy as np
import soundfile as sf
from cue.core import Cue, CueError, Settings, Unit
from cue.media import Media
from cue.pipeline import Pipeline

class StubVad:
    """Answers the pipeline's speech question without the Silero model."""
    def __init__(self,speech=True):
        self.speech=speech; self.calls=0
    def has_speech(self,audio):
        self.calls+=1
        return self.speech,{'vad_max_prob':.9 if self.speech else .02,'vad_speech_ms':500 if self.speech else 0}

def setup_pipeline(monkeypatch,tmp_path,silent=False,speech=True):
    def extract(media,start,end,dest):
        samples=np.zeros((end-start)*16,dtype='float32') if silent else np.full((end-start)*16,.01,dtype='float32')
        sf.write(dest,samples,16000,subtype='FLOAT')
        return {'sample_count':len(samples),'sample_zero_media_ms':start}
    monkeypatch.setattr('cue.pipeline.extract',extract)
    p=Pipeline(tmp_path/'models',tmp_path/'temp')
    class Backend:
        calls=[];hints=[];contexts=[];previous=[]
        def load(self): self.calls.append('load')
        def transcribe(self,a,source='auto',names=(),previous=''):self.calls.append(('asr',source));self.hints.append(tuple(names));self.previous.append(previous);return 'one two'
        def language(self,t,s):return {'code':'en','status':'manual'}
        def align(self,a,t,l,partial=False,left_ms=0):
            self.calls.append('align');units=[Unit(500,800,'one'),Unit(8500,9500,'two')]
            return (units,None,[]) if partial else units
        def translate(self,c,t,l,context=None):self.calls.append('translate');self.contexts.append(context);return c,{}
    p.backend=Backend()
    p.vad=StubVad(speech)
    job={'media':asdict(Media('/fixture','s',1,'key',30000,0,1,1)),
         'settings':asdict(Settings(target='original')),'range':[0,10000],'source_profile':'p'}
    return p,job

def test_unresolved_word_does_not_advance_coverage(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    result=p.run(job)
    assert result['committed_range']==[0,8500]
    assert [c['text'] for c in result['source']]==['one']

def test_cached_source_skips_asr_and_alignment(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['cached_source']={'cues':[{'id':'stable','start_ms':500,'end_ms':800,'text':'hello'}],'language':{'code':'en'}}
    result=p.run(job)
    assert p.backend.calls==['load','translate']
    assert result['committed_range']==[0,10000]

def test_pipeline_restores_asr_sentence_breaks_lost_by_aligner(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':'Hello world. Next sentence.'
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([
        Unit(500,800,'Hello'),Unit(850,1200,'world'),Unit(1250,1600,'Next'),Unit(1650,2000,'sentence')],None,[])
    result=p.run(job)
    assert [c['text'] for c in result['source']]==['Hello world.','Next sentence.']
    assert [(c['start_ms'],c['end_ms']) for c in result['source']]==[(500,1200),(1250,2000)]
    assert result['timings']['transcript_punctuation_restored'] is True

def test_exact_silence_requires_no_model(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,True)
    result=p.run(job)
    assert p.backend.calls==[]
    assert result['coverage_kind']=='verified_no_speech'
    assert result['source']==[] and result['committed_range']==[0,10000]

def test_existing_right_coverage_seals_draft_without_reprocessing_forever(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['following_source']=[{'id':'next','start_ms':10500,'end_ms':11500,'text':'next'}]
    result=p.run(job)
    assert result['committed_range']==[0,10000]
    assert [c['text'] for c in result['source']]==['one','two']

def test_crossing_word_at_cached_right_edge_is_not_given_an_invented_end(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':'one different draft'
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(500,800,'one'),Unit(8500,10500,'different draft')],None,[])
    job['following_source']=[{'id':'next','start_ms':10500,'end_ms':11500,'text':'already cached'}]
    result=p.run(job)
    assert result['committed_range']==[0,10000]
    assert [c['text'] for c in result['source']]==['one']
    assert result['timings']['boundary_discarded_units']==1

def test_unsupported_auto_lid_retries_without_loading_aligner(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.language=lambda text,source:{'code':'pl','status':'tentative','method':'original_asr_text_lid'}
    progress=[]
    try:
        p.run(job,lambda stage,language=None:progress.append((stage,language)))
    except CueError as exc:
        assert exc.code=='LANGUAGE_UNCERTAIN'
    else:
        assert False, 'unsupported auto LID must remain uncertain'
    assert p.backend.calls==['load',('asr','auto')]
    assert progress[-1][1]['code']=='pl'


def test_window_without_speech_skips_asr_and_is_verified_no_speech(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,speech=False)
    result=p.run(job)
    assert p.backend.calls==[]
    assert p.vad.calls==1
    assert result['coverage_kind']=='verified_no_speech'
    assert result['committed_range']==[0,10000]
    assert result['source']==[] and result['rendered']==[]
    assert result['language']=={'code':'und','status':'unknown','method':'voice_activity'}
    assert result['timings']['vad_speech_ms']==0

def test_window_with_speech_goes_through_asr_as_before(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,speech=True)
    result=p.run(job)
    assert p.vad.calls==1
    assert ('asr','auto') in p.backend.calls
    assert result['coverage_kind']=='complete'

def test_digital_silence_needs_no_voice_activity_model(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,silent=True)
    result=p.run(job)
    assert p.vad.calls==0
    assert result['coverage_kind']=='verified_no_speech'

def test_cached_transcript_is_not_checked_again(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,speech=False)
    job['cached_source']={'cues':[{'id':'stable','start_ms':500,'end_ms':800,'text':'hello'}],'language':{'code':'en'}}
    result=p.run(job)
    assert p.vad.calls==0
    assert result['coverage_kind']=='complete'

def test_missing_voice_activity_model_is_a_setup_error(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.vad=None
    p.vad_model=tmp_path/'missing.onnx'
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='SETUP_REQUIRED'
    assert p.backend.calls==[]


def test_a_collapsed_window_commits_its_aligned_part_and_leaves_the_rest_for_the_next(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    # Transcript "one two three": the aligner placed "one two"; "three" collapsed at 6.2 s of the span.
    p.backend.transcribe=lambda a,source='auto',names=(),previous='':'one two three'
    p.backend.align=lambda a,t,l,partial=False,left_ms=0:([Unit(500,800,'one'),Unit(1500,1900,'two')],6200,[])
    result=p.run(job)
    # The span starts at 0 here, so the cut is at 6.2 s of media time.
    assert result['committed_range']==[0,6200]
    assert [c['text'] for c in result['source']]==['one','two']
    assert result['timings']['alignment_cut_ms']==6200
    boundaries={0+t for u in [Unit(500,800,''),Unit(1500,1900,'')] for t in (u.start_ms,u.end_ms)}
    assert all(c['start_ms'] in boundaries and c['end_ms'] in boundaries for c in result['source'])

def test_too_little_before_the_collapse_fails_the_window_as_before(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.transcribe=lambda a,source='auto',names=(),previous='':'one two'
    p.backend.align=lambda a,t,l,partial=False,left_ms=0:([Unit(500,800,'one')],1500,[])
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='ALIGNMENT_FAILED'

def test_nothing_aligned_before_the_collapse_fails_the_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.align=lambda a,t,l,partial=False,left_ms=0:([],300,[])
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='ALIGNMENT_FAILED'

def test_an_unfinished_trailing_sentence_is_held_back_for_the_next_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[0,8000];job['min_commit_ms']=2000
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':"Not one of us. He's"
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(500,800,'Not'),Unit(900,1200,'one'),Unit(1300,1600,'of'),Unit(1700,2500,'us'),Unit(3000,3800,"He's")],None,[])
    result=p.run(job)
    assert result['committed_range']==[0,3000]
    assert [c['text'] for c in result['source']]==['Not one of us.']
    assert result['timings']['held_back_ms']==4000

def test_no_hold_back_below_the_startup_floor_or_when_the_right_side_is_already_cached(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[0,8000]
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':"Not one of us. He's"
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(500,800,'Not'),Unit(900,1200,'one'),Unit(1300,1600,'of'),Unit(1700,2500,'us'),Unit(3000,3800,"He's")],None,[])
    job['min_commit_ms']=8000
    result=p.run(job)
    assert result['committed_range']==[0,7000] and [c['text'] for c in result['source']]==['Not one of us.',"He's"]
    assert 'held_back_ms' not in result['timings']
    job['min_commit_ms']=2000
    job['following_source']=[{'id':'r','start_ms':8000,'end_ms':8500,'text':'later'}]
    result=p.run(job)
    assert result['committed_range']==[0,8000] and len(result['source'])==2

def test_no_hold_back_after_a_collapse(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[0,8000];job['min_commit_ms']=2000
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':"Not one of us. He's going"
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(500,800,'Not'),Unit(900,1200,'one'),Unit(1300,1600,'of'),Unit(1700,2500,'us'),Unit(3000,3800,"He's")],6200,[])
    result=p.run(job)
    assert result['committed_range']==[0,6200] and len(result['source'])==2

def test_translation_merges_sentence_units_and_passes_context_and_names_back(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['settings']=asdict(Settings(target='zh-TW'));job['range']=[10000,18000];job['min_commit_ms']=2000
    job['previous_source']=[{'id':'p','start_ms':8000,'end_ms':9500,'text':'We block each other.'}]
    job['previous_rendered']=[{'id':'r','start_ms':8000,'end_ms':9500,'text':'我們互相阻擋。'}]
    job['glossary']={'user':{'Nash':'納許'},'learned':[['Hansen','漢森',100]]}
    # No period after "us": the assembler splits the long group at 4.5 s, and the two source cues
    # are one sentence for the translator.
    seen={}
    def transcribe(audio,source='auto',names=(),previous=''):
        seen['hint']=tuple(names);return "Not one of us He's going to get her."
    p.backend.transcribe=transcribe
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(1500,1800,'Not'),Unit(1900,2200,'one'),Unit(2300,2600,'of'),Unit(2700,3500,'us'),
        Unit(4000,4800,"He's"),Unit(4900,5300,'going'),Unit(5400,5700,'to'),Unit(5800,6100,'get'),Unit(6200,6600,'her')],None,[])
    def translate(c,t,l,context=None):
        seen['units']=c;seen['context']=context;return c,{'Sol':'索爾'}
    p.backend.translate=translate
    result=p.run(job)
    assert [c['text'] for c in result['source']]==["Not one of us He's going","to get her."]
    assert [(c['start_ms'],c['end_ms'],c['text']) for c in result['rendered']]==[(10500,15600,"Not one of us He's going to get her.")]
    assert result['rendered'][0]['id'] not in {c['id'] for c in result['source']}
    assert result['names']=={'Sol':'索爾'} and result['timings']['translation_units']==1 and result['timings']['names_learned']==1
    assert seen['hint']==('Nash','Hansen')
    context=seen['context']
    assert context.previous==(('We block each other.','我們互相阻擋。'),)
    assert context.glossary=={'Hansen':'漢森'} and context.variants=={} and context.new_names==() and context.continues==frozenset()

def test_original_captions_keep_the_fine_cues_and_skip_context(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    result=p.run(job)
    assert p.backend.contexts==[None] and result['names']=={} and p.backend.hints==[()]

def test_build_context_reports_new_names_and_misheard_spellings():
    from cue.pipeline import build_context
    units=[Cue('u1',0,1000,'Thank you, Mr. Hanson.'),Cue('u2',1100,2000,'I think Bender is here.')]
    job={'glossary':{'user':{'Nash':'納許'},'learned':[['Hansen','漢森',0]]},'previous_source':[],'previous_rendered':[]}
    context=build_context(units,frozenset({'u2'}),job,'en')
    assert context.new_names==('Bender',) and context.variants=={'Hanson':'Hansen'}
    assert context.glossary=={'Hansen':'漢森'} and context.continues==frozenset({'u2'})
    assert build_context(units,frozenset(),job,'ja').new_names==()

def test_build_context_marks_every_ledger_rendering_as_taken():
    from cue.pipeline import build_context
    job={'glossary':{'user':{'Nash':'納許'},'learned':[['John','約翰',0],['Bender','本德',5]]},'previous_source':[],'previous_rendered':[]}
    context=build_context([Cue('u1',0,1000,'Hey, Nash.')],frozenset(),job,'en')
    assert context.taken==frozenset({'納許','約翰','本德'})

def test_a_phantom_word_squeezed_onto_the_seam_is_not_shown(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[10000,25000];job['min_commit_ms']=2000
    # Fresh ASR over the left context misheard "Adam" and the aligner squeezed it into a
    # 40 ms bin at the core start, 7.8 s before the words that were actually said.
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':"I'm Smith needs revision."
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(1000,1040,"I'm"),Unit(8800,9200,'Smith'),Unit(9300,9600,'needs'),Unit(9700,10400,'revision')],None,[])
    result=p.run(job)
    assert [c['text'] for c in result['source']]==['Smith needs revision.']
    assert result['timings']['seam_dropped']==1 and result['committed_range']==[10000,24000]

def test_a_phantom_after_left_context_words_is_not_shown_either(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[10000,25000];job['min_commit_ms']=2000
    job['previous_source']=[{'id':'p','start_ms':9000,'end_ms':9990,'text':'History book.'}]
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':"History book. I'm Smith needs revision."
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(200,600,'History'),Unit(650,990,'book'),Unit(1000,1040,"I'm"),Unit(8800,9200,'Smith'),Unit(9300,9600,'needs'),Unit(9700,10400,'revision')],None,[])
    result=p.run(job)
    assert [c['text'] for c in result['source']]==['Smith needs revision.']
    assert result['timings']['seam_dropped']==1

def test_build_context_uses_the_builtin_table_as_known_names_and_taken_renderings():
    from cue.pipeline import build_context
    job={'glossary':{'user':{},'builtin':{'John':'約翰','Hansen':'漢森'},'learned':[]},'previous_source':[],'previous_rendered':[]}
    context=build_context([Cue('u1',0,1000,'Thank you, Mr. Hanson. John is here.')],frozenset(),job,'en')
    # Built-in names never claim a near miss: Hanson is a new name here, and only John appears as written.
    assert context.new_names==('Hanson',) and context.variants=={}
    assert context.glossary=={'John':'約翰'} and '約翰' in context.taken

def test_rejected_name_reports_reach_the_timings(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['settings']=asdict(Settings(target='zh-TW'));job['range']=[10000,18000];job['min_commit_ms']=2000
    p.backend.transcribe=lambda audio,source='auto',names=(),previous='':"Come on, Bender."
    p.backend.align=lambda audio,text,language,partial=False,left_ms=0:([Unit(1500,1800,'Come'),Unit(1900,2200,'on'),Unit(2300,2900,'Bender')],None,[])
    def translate(c,t,l,context=None):
        p.backend.names_report={'reported':{'Bender':'班德'},'accepted':{},'rejected':{'Bender':'班德'}};return c,{}
    p.backend.translate=translate
    result=p.run(job)
    assert result['timings']['names_reported']==['Bender'] and result['timings']['names_rejected']=={'Bender':'班德'}

def test_build_context_never_treats_a_new_name_as_a_misheard_builtin_name():
    from cue.pipeline import build_context
    job={'glossary':{'user':{},'builtin':{'Becker':'貝克'},'learned':[]},'previous_source':[],'previous_rendered':[]}
    context=build_context([Cue('u1',0,1000,'Come on, Bender.')],frozenset(),job,'en')
    assert context.new_names==('Bender',) and context.variants=={} and context.glossary=={}

def test_build_context_keeps_the_ten_most_recent_previous_units():
    from cue.pipeline import build_context
    job={'glossary':{'user':{},'builtin':{},'learned':[]},
         'previous_source':[{'id':f's{i}','start_ms':i*1000,'end_ms':i*1000+500,'text':f'line {i}'} for i in range(12)],
         'previous_rendered':[{'id':f'r{i}','start_ms':i*1000,'end_ms':i*1000+500,'text':f'譯{i}'} for i in range(12)]}
    context=build_context([Cue('u1',20000,21000,'Hello.')],frozenset(),job,'en')
    assert len(context.previous)==10 and context.previous[0]==('line 2','譯2') and context.previous[-1]==('line 11','譯11')

def test_pipeline_hands_a_dedicated_asr_engine_to_its_backend(tmp_path):
    marker=object()
    assert Pipeline(tmp_path/'models',tmp_path/'temp',asr=marker).backend.asr is marker
    assert Pipeline(tmp_path/'models',tmp_path/'temp').backend.asr is None

def test_the_transcriber_gets_the_text_heard_before_the_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[10000,20000]
    job['previous_source']=[asdict(Cue(id='a',start_ms=8000,end_ms=8500,text='Earlier line.')),asdict(Cue(id='b',start_ms=8500,end_ms=9000,text='And another.'))]
    p.run(job)
    assert p.backend.previous[-1]=='Earlier line. And another.'
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.run(job)
    assert p.backend.previous[-1]==''

def test_words_placed_past_the_audio_end_are_left_out_instead_of_failing_the_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    # The span is 0-11 s. The aligner works in 80 ms bins, so it can end the last word
    # a bin past the audio; that word lies in the right context and is never committed.
    p.backend.transcribe=lambda a,source='auto',names=(),previous='':'one two three'
    p.backend.align=lambda a,t,l,partial=False,left_ms=0:([Unit(500,800,'one'),Unit(1500,1900,'two'),Unit(10900,11080,'three')],None,[])
    result=p.run(job)
    assert 'three' not in ' '.join(c['text'] for c in result['source'])
    assert 'one' in ' '.join(c['text'] for c in result['source'])
    assert result['timings']['units_past_audio_end']==1
    assert 'alignment_cut_ms' not in result['timings']


def test_words_skipped_in_the_left_context_leave_the_rest_of_the_transcript_to_the_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[10000,20000]; seen={}
    p.backend.transcribe=lambda a,source='auto',names=(),previous='':"Nash. Who's winning? You or you?"
    def align(a,t,l,partial=False,left_ms=0):
        seen['left_ms']=left_ms
        return ([Unit(1600,1760,"Who's"),Unit(1760,2080,'winning'),Unit(2160,2560,'You'),Unit(2560,2640,'or'),Unit(2720,2960,'you')],None,[Unit(0,0,'Nash')])
    p.backend.align=align
    result=p.run(job)
    assert seen['left_ms']==1000
    text=' '.join(c['text'] for c in result['source'])
    assert 'Nash' not in text and "Who's winning?" in text
    assert result['timings']['left_context_skipped']==1

def test_skipped_words_that_do_not_open_the_transcript_fail_the_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[10000,20000]
    p.backend.transcribe=lambda a,source='auto',names=(),previous='':"Who's winning?"
    p.backend.align=lambda a,t,l,partial=False,left_ms=0:([Unit(1600,1760,"Who's"),Unit(1760,2080,'winning')],None,[Unit(0,0,'Nash')])
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='ALIGNMENT_FAILED'

def test_a_first_word_straddling_the_previous_cue_end_starts_at_that_end(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    # "At Marcellus' request.": the previous window committed up to "Marcellus'" and
    # measured "request" starting at its end; this window places the word 580 ms earlier.
    job['range']=[10000,20000]; job['previous_source']=[asdict(Cue(id='p',start_ms=8000,end_ms=9900,text="At Marcellus'"))]
    p.backend.transcribe=lambda a,source='auto',names=(),previous='':'request. Have you met Mia?'
    p.backend.align=lambda a,t,l,partial=False,left_ms=0:([Unit(320,1680,'request'),Unit(4400,4560,'Have'),Unit(4560,4700,'you'),Unit(4700,4900,'met'),Unit(4900,5300,'Mia')],None,[])
    result=p.run(job)
    assert result['source'][0]['start_ms']==9900 and result['source'][0]['text'].startswith('request')
    assert result['timings']['start_from_previous_cue_ms']==580

def test_a_first_word_stretched_far_past_the_previous_cue_still_fails_the_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['range']=[10000,20000]; job['previous_source']=[asdict(Cue(id='p',start_ms=8000,end_ms=9900,text='The game is flawed.'))]
    p.backend.transcribe=lambda a,source='auto',names=(),previous='':'Gentlemen, the great John Nash.'
    p.backend.align=lambda a,t,l,partial=False,left_ms=0:([Unit(0,8640,'Gentlemen'),Unit(8720,8800,'the'),Unit(8960,9200,'great'),Unit(9360,9760,'John'),Unit(9840,9990,'Nash')],None,[])
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='ALIGNMENT_FAILED'
