"""Build with the bundled Codex Python runtime. Source dossiers remain separate."""
from pathlib import Path
from collections import defaultdict
import json, re, hashlib, subprocess
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/Kaggle_Agent_Research_Findings.docx'
GROUPS=[('S','Machine learning systems','system_sources.json'),('E','Evaluation risks and operating boundaries','evaluation_sources.json'),('P','Earlier architecture references and competition accounts','prior_sources.json'),('V','Visual explanation and documentation','visual_sources.json')]
all_sources=[]
for prefix,title,file in GROUPS:
    entries=json.loads((ROOT/'docs/research'/file).read_text(encoding='utf-8'))
    for i,s in enumerate(entries,1):
        s['code']=f'{prefix}{i:02}';s['group']=title;all_sources.append(s)
BY_ID={s['id']:s for s in all_sources}
assert len(all_sources)==36
for s in all_sources:
    assert len(s['findings'])==2
    assert sum(len(f['quote'].split()) for f in s['findings'])<=25,s['id']
    for f in s['findings']:
        assert f['quote'] and f['locator']
        assert not re.search(r'\whttps?://',f['title']+f['application']+f['strengths'])

doc=Document();sec=doc.sections[0]
sec.page_width=Inches(8.5);sec.page_height=Inches(11)
sec.top_margin=Inches(.72);sec.bottom_margin=Inches(.72)
sec.left_margin=Inches(.8);sec.right_margin=Inches(.8)
sec.header_distance=Inches(.28);sec.footer_distance=Inches(.3)
styles=doc.styles
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Heading 3','Quote','Caption','List Bullet']:
    st=styles[name];st.font.name='Arial';st.font.color.rgb=RGBColor(0,0,0)
    st.paragraph_format.widow_control=True
styles['Normal'].font.size=Pt(11)
styles['Normal'].paragraph_format.line_spacing=1.06
styles['Normal'].paragraph_format.space_after=Pt(5)
for name,size,before,after in [('Title',26,0,16),('Subtitle',13,0,9),('Heading 1',17,15,9),('Heading 2',14,14,7),('Heading 3',11.5,10,5)]:
    st=styles[name];st.font.size=Pt(size);st.font.bold=name!='Subtitle'
    st.paragraph_format.space_before=Pt(before);st.paragraph_format.space_after=Pt(after)
    st.paragraph_format.keep_with_next=True
styles['Quote'].font.size=Pt(11);styles['Quote'].font.italic=True
styles['Quote'].paragraph_format.left_indent=Inches(.25)
styles['Quote'].paragraph_format.right_indent=Inches(.15)
styles['Quote'].paragraph_format.space_after=Pt(3)
styles['Quote'].paragraph_format.keep_with_next=True
styles['Caption'].font.size=Pt(9)
styles['Caption'].paragraph_format.space_after=Pt(6)
styles['List Bullet'].font.size=Pt(11)
for name in ['Title','Subtitle']:
    for border in list(styles[name].element.xpath('./w:pPr/w:pBdr')):
        border.getparent().remove(border)
header=sec.header.paragraphs[0];header.text='KAGGLE AGENT SYSTEM  |  RESEARCH ASSESSMENT'
header.runs[0].font.size=Pt(8);header.runs[0].font.color.rgb=RGBColor(0,0,0)
footer=sec.footer.paragraphs[0];footer.paragraph_format.tab_stops.add_tab_stop(Inches(6.85),WD_ALIGN_PARAGRAPH.RIGHT)
footer.text='26 November 2026\t'
footer.runs[0].font.size=Pt(9)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)

bookmark_id=1
def bookmark(p,name):
    global bookmark_id
    a=OxmlElement('w:bookmarkStart');a.set(qn('w:id'),str(bookmark_id));a.set(qn('w:name'),name)
    b=OxmlElement('w:bookmarkEnd');b.set(qn('w:id'),str(bookmark_id));bookmark_id+=1
    p._p.insert(0,a);p._p.append(b)
def hyperlink(p,label,url=None,anchor=None):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    h=OxmlElement('w:hyperlink')
    if anchor:h.set(qn('w:anchor'),anchor)
    else:h.set(qn('r:id'),p.part.relate_to(url,RT.HYPERLINK,is_external=True))
    r=OxmlElement('w:r');pr=OxmlElement('w:rPr');col=OxmlElement('w:color');col.set(qn('w:val'),'244A68');pr.append(col)
    u=OxmlElement('w:u');u.set(qn('w:val'),'single');pr.append(u);r.append(pr)
    t=OxmlElement('w:t');t.text=label;r.append(t);h.append(r);p._p.append(h)
def clean_heading(t):
    t=re.sub(r'[^\w\s]',' ',t,flags=re.UNICODE)
    return re.sub(r'\s+',' ',t).strip()
def heading(text,level=1,newpage=False):
    p=doc.add_paragraph(clean_heading(text),f'Heading {level}')
    if newpage:p.paragraph_format.page_break_before=True
    return p
def para(text='',lead=None,style=None):
    p=doc.add_paragraph(style=style)
    if lead:p.add_run(lead+' ').bold=True
    p.add_run(text)
    return p
def ref(id):return BY_ID[id]['code']
def reflist(ids):
    p=doc.add_paragraph();p.paragraph_format.space_after=Pt(8)
    p.add_run('Evidence entries: ').italic=True
    for i,id in enumerate(ids):
        if i:p.add_run(' · ')
        hyperlink(p,ref(id),anchor=ref(id))
    return p
def table(headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for i,w in enumerate(widths):t.columns[i].width=Inches(w)
    for cell,text in zip(t.rows[0].cells,headers):cell.text=text
    for row in rows:
        for c,text in zip(t.add_row().cells,row):c.text=str(text)
    for i,row in enumerate(t.rows):
        for j,cell in enumerate(row.cells):
            cell.width=Inches(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcPr=cell._tc.get_or_add_tcPr();b=OxmlElement('w:tcBorders')
            for side in ['top','left','bottom','right','insideH','insideV']:
                el=OxmlElement('w:'+side);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');b.append(el)
            tcPr.append(b)
            mar=OxmlElement('w:tcMar')
            for side in ['top','left','bottom','right']:
                el=OxmlElement('w:'+side);el.set(qn('w:w'),'100');el.set(qn('w:type'),'dxa');mar.append(el)
            tcPr.append(mar)
            if i==0:
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'F2F2F2');tcPr.append(sh)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(2);p.paragraph_format.line_spacing=1
                for r in p.runs:r.font.size=Pt(9.5);r.bold=i==0
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t

doc.add_paragraph('Research findings for the Kaggle agent system','Title')
doc.add_paragraph('Evidence transferability and implementation choices','Subtitle')
para('Prepared for Alex · Research retrieved 26 November 2026')
para('The most useful near-term improvements are stronger evaluation boundaries, evidence-aware memory, bounded search, and clearer explanations. These can be developed and tested with the local CPU-first supervisor. Large GPU pools, pretrained agent experience banks, and high-volume model campaigns should be treated as resource-dependent research settings rather than capabilities our current project inherits.',lead='Main assessment.')
para('This report reviews all fourteen labels in your screenshot, the original links you subsequently supplied, and the earlier architecture and animation resources. It contains 36 source assessments and 72 detailed findings. Each finding includes a short exact quotation, a source location, an explanation, project-specific benefits and drawbacks, and a proposed validation step.')
para('The operating baseline is the user-stated absence of available GPU computation. It is not a fresh hardware inventory. Agent inference through a selected subscription CLI, local model training, and search parallelism are assessed separately. No new paid jobs, API calls for experimentation, competition submissions, or architecture changes were performed to prepare this report.')
para('Use the screenshot index to find a named resource, the detailed assessments to inspect the evidence, and the proposed implementation plan to decide what to test. A recommendation in this report is not a claim that its proposed change is already implemented or has improved the project.')
heading('Reading the evidence',1)
para('Quoted text is reproduced in an indented block. The line beneath it identifies a paper section, page, repository heading, or comment item and links to the original. Short excerpts are kept narrow so that the reader can inspect the full surrounding passage at its source. Interpretations, fit assessments, and proposed tests are our analysis, not words attributed to the source authors.')
para('Primary paper results, repository instructions, first-person competition accounts, a secondary AI-written review, and practitioner design advice have different evidential strength. A claim reported by its author is not a result reproduced in this project. Indexed primary text is identified when the original page did not yield a readable body. Unknown compute or price is recorded as unknown, never as zero.')

heading('Screenshot source index',1,newpage=True)
rows=[
('MLE-bench',ref('mle-bench'),'Official benchmark repository'),('AIDE',ref('aide'),'Official agent and paper'),('MLE-STAR',ref('mle-star'),'Version-specific primary sources'),('AIRA-dojo long-horizon ML engineering',ref('aira-dojo'),'Primary paper and official repository'),('AIRA-dojo review',ref('aira-review'),'Your Moonlight link; AI-written secondary review'),('ML-Master 2.0',ref('ml-master-2'),'Versioned primary paper'),('R&D-Agent',ref('rd-agent'),'Primary paper and official repository'),('Agent K',ref('agent-k'),'Versioned Agent K paper; AITopics record retained'),('autoresearch ehmo',ref('ehmo-autoresearch'),'ehmo skill; distinct from Karpathy project'),('zzsi benchmark',ref('zzsi-benchmark'),'Author benchmark blog on Spooky task'),('NVIDIA playground win',ref('nvidia-playground'),'Chris Deotte S6E8 primary write-up'),('BenchJack',ref('benchjack'),'benchjack benchmark scanner'),('Leaderboard Illusion',ref('leaderboard-illusion'),'Primary benchmark audit paper'),('Kaggle AUP',ref('kaggle-aup'),'Official platform policy')]
index_table=table(['Screenshot label','Entry','Resolved resource'],rows,[2.3,.55,4.05])
for row,record in zip(index_table.rows[1:],rows):
    p=row.cells[1].paragraphs[0];p.clear();hyperlink(p,record[1],anchor=record[1])
para('The Moonlight review body was retrieved through the same article’s Spanish-locale route, which exposed English text; the English URL you supplied remains recorded. The AITopics entry did not open successfully, so its URL is preserved and the Agent K assessment uses a separately retrieved versioned primary paper. The identity confidence and access limitation remain visible in that entry.')
para('Additional resources include AIRA 2 as a separately labeled follow-up, Karpathy’s distinct autoresearch, eleven earlier architecture references and competition accounts, and nine visual-explanation sources. The report does not merge different versions, workloads, or resource budgets into a single ranking.')

heading('Project baseline and transfer criteria',1,newpage=True)
para('The working tree was inspected as a local implementation, not assumed to be identical to a public repository revision. The full reference HEAD and file hashes are recorded in the local source appendix. The revision is an identification aid rather than proof that local edits are committed.')
para('The current project supports tabular classification and regression, mathematical optimization, and occasional forecasting. The automatic code loop invokes the selected coding agent with a brief, writes an experiment in a workspace, smoke-tests it with bounded repairs, runs eligible evaluation stages, scores outputs independently, and records outcomes. Independent scoring is an existing capability. Strong operating-system isolation is not established by this arrangement.')
para('The script provider explicitly says its pattern checks are not a sandbox: same-user code can still perform actions available to that OS user. This is the most important qualification when borrowing proposals for hidden labels or protected scoring. Prompt instructions and evaluator hashes help detect errors but cannot replace actual access separation.')
para('The branch portfolio limits active directions to five and includes exploration turns. The code’s conditional blending is described as conditional meta-validation over a frozen prediction library, not complete nested evaluation of the entire upstream search. Retrieved public research is treated as data and is not automatically executed. Paid or remote providers are rejected by the current launch gate; cloud results can instead be imported through a separately managed workflow.')
para('Source configuration defaults are not current user settings. The limits module defines 1,800 seconds, 2,048 MB, one thread, a 900-second agent session, and a 0.25 screen fraction as defaults, while stored settings and stricter profile constraints may differ. We did not inspect secret-bearing account settings or certify available quotas or current billing totals.')
table(['Question','How this report evaluates a proposal'],[
('Structural fit','Can it improve the existing brief, portfolio, evaluator, ledger, or artifact contract without replacing the whole system?'),
('Training compute','Does the method require accelerators, large memory, multiple days, or a large prior task corpus?'),
('Agent inference','Does it add model conversations, independent teams, a new model service, or unverified inference charges?'),
('Evidence quality','Is the finding an ablation, a stated protocol, a first-person account, a review, or a design opinion?'),
('Permission and access','Does it rely on an allowed dataset or interface, and does it preserve the user’s selected agent and spending constraints?'),
('Acceptance','What bounded local test would establish useful behavior without claiming a medal or universal agent ranking?')],[1.35,5.55])

heading('Recommended implementation sequence',1,newpage=True)
para('The following are proposed changes or audits, not work performed by this document. Prioritize their ability to improve the quality of measured evidence before increasing the volume of generated experiments.')
heading('First establish trustworthy evaluation',2)
para('Audit the boundary between generated code, training labels, validation labels, score extraction, and promotion. Replay synthetic candidates that claim perfect metrics, omit rows, reorder IDs, or attempt to alter scorer files. Independent scoring must ignore an agent’s claimed result and reject malformed output. If a final-selection partition is added, preserve group and time restrictions and account for the reduction in training data. Never copy a random split from another benchmark into a forecasting task by default.')
reflist(['benchjack','leaderboard-illusion','aira2','prior-harness'])
heading('Then make comparisons reproducible and affordable',2)
para('Evaluate one scaffold change at a time on a small frozen set of representative in-scope CPU tasks. Match agent choice, model effort, wall-clock and RAM caps, data, folds, seeds, and tool permissions. Log failures, invalid artifacts, partial work, and quota stops as outcomes. Compare paired results and distributions instead of selecting the best trajectory. A narrow local evaluation is useful, provided it is described as narrow rather than presented as a reproduction of a full benchmark.')
reflist(['mle-bench','zzsi-benchmark','aira-dojo'])
heading('Improve memory before expanding the agent population',2)
para('Attach evidence status, originating task, experiment identity, and conditions to retained lessons. Preserve contradictions and distinguish a proposed idea from a reproduced improvement. Consolidate at campaign boundaries under a fixed brief size, retaining raw evidence outside the conversation. Compare the current retrieval against the changed memory policy on repeated invalid attempts and evidence traceability. Only consider a temporary independent reviewer when there is a concrete unresolved failure, not as another permanent agent for every trial.')
reflist(['ml-master-2','prior-evomaster','ehmo-autoresearch'])
heading('Adapt search methods to CPU scale',2)
para('Use targeted component changes and small ablations with timeouts. A more elaborate search policy earns its complexity only when it improves results under the same resource envelope. Retain the portfolio cap and exploration behavior while testing one priority rule. Model diversity can be evaluated from already aligned prediction files; a useful ensemble candidate is not necessarily the strongest standalone model. GPU-heavy historical campaigns are sources of hypotheses, not budget templates.')
reflist(['aide','mle-star','prior-mlevolve','prior-deotte-s6e5','nvidia-playground'])
heading('Keep documentation truthful and inspectable',2)
para('Use the README GIFs to explain concrete invariants and decision mechanics. Keep setup output explicitly simulated and preserve complete, copyable commands in text. Review transitions and endings at normal display size, not only high-resolution stills. Attribution supports the explanation; it does not imply that a creator reviewed or endorsed the asset. This documentation work should remain separate from evidence that an ML experiment actually improved.')
reflist(['visual-faq','visual-grace','visual-diagrams','visual-forum'])
heading('Defer resource dependent replication',2)
para('Do not reproduce full H200 or multi-4090 agent experiments, multi-day GPU search, broad experience-bank construction, or GPU language-model training merely because their architecture is interesting. First isolate a CPU-feasible control-plane idea. A future accelerator experiment would need a separately authorized provider, price and resource cap, task contract, checkpoint and stop plan, and a matched comparison. No paper’s headline result supplies those project-specific facts.')
reflist(['ml-master-2','aira2','agent-k','rd-agent','karpathy-autoresearch'])

heading('Detailed source assessments',1,newpage=False)
para('Entry codes are used throughout the report. Each detailed finding has its own quotation and location. Fit, drawbacks, and suggested tests are our project analysis. Hardware descriptions remain source-specific and do not constitute a cross-study price comparison.')
for prefix,group,file in GROUPS:
    heading(group,1,newpage=False)
    for s in [x for x in all_sources if x['group']==group]:
        p=heading(s['code']+' '+s['title'],2);bookmark(p,s['code'])
        meta=para(s['authors']+' · '+s['kind']+' · '+s['identity_status'],style='Caption')
        meta.paragraph_format.keep_with_next=True
        p=para();p.paragraph_format.keep_with_next=True;hyperlink(p,'Open original source',s['url'])
        para(s['summary'])
        for j,f in enumerate(s['findings'],1):
            p=heading(f"{s['code']} Finding {j} {f['title']}",3);bookmark(p,f"{s['code']}F{j}")
            para('“'+f['quote']+'”',style='Quote')
            loc=f['locator'];urls=re.findall(r'https?://[^\s;]+',loc)
            display=re.sub(r'https?://[^\s;]+','',loc).strip(' ;—–-')
            if not display:
                from urllib.parse import urlsplit, unquote
                fragment=unquote(urlsplit(urls[-1]).fragment).replace('-',' ') if urls else ''
                display='README heading '+fragment if fragment else s['locator']
            p=para('Location: '+display+'  ',style='Caption');p.paragraph_format.keep_with_next=True
            hyperlink(p,'Passage',urls[-1] if urls else s['url'])
            para(f['meaning'],lead='What the source establishes.')
            para(f['application'],lead='Application to our project.')
            para(f['strengths'],lead='What fits.')
            para(f['limitations'],lead='Drawbacks and limits.')
            para(f['action'],lead='Proposed validation.')
        heading('Resources and evidence limits',3)
        c=s['compute']
        if prefix=='V':
            para(c.get('training','Not established.')+' Local authoring and review still take time; this source does not establish a monetary budget or competition performance gain.',lead='Resources.')
        else:
            para(c.get('training','Not established.'),lead='Training and local compute.')
            para(c.get('agent_inference','Not established.'),lead='Agent inference.')
            para(c.get('observed_budget','Not established.')+' '+c.get('caveat',''),lead='Budget and transfer caution.')
        para(s.get('evidence_limits',''),lead='Retrieval and interpretation limits.')
        if s.get('related_links'):
            p=para();p.add_run('Related originals and supplied links: ').italic=True
            for j,item in enumerate(s['related_links']):
                if j:p.add_run(' · ')
                url=item if isinstance(item,str) else item.get('url','')
                if url:hyperlink(p,'Link '+str(j+1),url)

heading('Local implementation evidence',1,newpage=True)
para('These are inspection references for project-fit judgments. They are not external literature claims or proof that the whole system is secure. Paths are relative to the project checkout. Historical planning and review files that were absent from the working tree were not used as the sole authority for a literature claim.')
paths={
'kaggle_agent/loop.py':'Brief construction, bounded repairs, eligible smoke and full stages, screen agreement and outcome handling.',
'kaggle_agent/supervisor/controller.py':'Durable launch intent, controller ownership and lifecycle integration.',
'kaggle_agent/supervisor/watchdog.py':'Process-tree resource checks and stop behavior.',
'kaggle_agent/supervisor/limits.py':'Configured resource limits, defaults and stricter profile bounds.',
'kaggle_agent/supervisor/budget.py':'Authorization and pricing preconditions for reservations and ledger accounting.',
'kaggle_agent/agents/base.py':'Selected CLI adapter, environment filtering, result normalization and stop classification.',
'kaggle_agent/research/branches.py':'Five active directions, heuristic priorities and exploration turns.',
'kaggle_agent/research/retrieval.py':'Discovery records and retrieval into briefs.',
'kaggle_agent/agents/session_manager.py':'Checkpoint and session rotation.',
'kaggle_agent/execution/script.py':'Copied code snapshot and explicit statement that checks are not a sandbox.',
'kaggle_agent/execution/gates.py':'Allowed local provider set and disabled paid execution gate.',
'kaggle_agent/evaluation/validation.py':'Row alignment, independent score evaluation and comparison.',
'kaggle_agent/evaluation/ensemble.py':'Conditional meta-validation and prediction provenance requirements.',
'kaggle_agent/research/public.py':'Read-only public material collection through documented routes.',
'docs/tools/readme_scenes.py':'Original README diagram geometry and explanatory transitions.',
'docs/tools/render_setup.py':'Explicitly simulated terminal setup without executing displayed commands.'}
try:revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
except Exception:revision='Not available'
para(revision,lead='Reference HEAD.')
manifest=[]
local_rows=[]
for path,description in paths.items():
    p=ROOT/path
    if not p.exists():continue
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    local_rows.append((path,description,digest[:12]))
    manifest.append(dict(path=path,sha256=digest,reason=description))
para('Complete SHA256 hashes are retained in the source manifest used to generate this report. The table identifies each inspected file and its role in the project-fit analysis.')
table(['Local path','Reason for inspection'],[(r[0],r[1]) for r in local_rows],[2.8,4.1])

heading('Source register',1,newpage=True)
para('The links below are the primary report entry points. Versioned paper URLs take precedence over an unversioned title when methods or resource figures changed. Access and interpretation qualifications are retained in each assessment.')
for s in all_sources:
    p=para();p.paragraph_format.space_after=Pt(2);p.paragraph_format.keep_with_next=True
    hyperlink(p,s['code']+' '+s['title'],anchor=s['code'])
    p=para(style='Caption');p.add_run(s['authors']+' · ');hyperlink(p,'Original source',s['url'])

doc.core_properties.title='Research findings for the Kaggle agent system'
doc.core_properties.subject='Quoted source analysis and project transferability'
doc.core_properties.author='Prepared for Alex'
doc.core_properties.keywords='Kaggle CPU agent evaluation memory search documentation research'
doc.save(OUT)
(ROOT/'output/research_report/source_manifest.json').write_text(json.dumps(dict(date='2026-11-26',revision=revision,sources=all_sources,local_files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
print(OUT)
print('Sources:',len(all_sources),'Findings:',sum(len(s['findings']) for s in all_sources))
print('Body words:',sum(len(p.text.split()) for p in doc.paragraphs))
