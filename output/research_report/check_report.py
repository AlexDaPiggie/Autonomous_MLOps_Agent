from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import json,re
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'output/Kaggle_Agent_Research_Findings.docx'
n={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(p) as z:
    r=E.fromstring(z.read('word/document.xml'))
    st=E.fromstring(z.read('word/styles.xml'))
    quotes=r.xpath('//w:p[w:pPr/w:pStyle[@w:val="Quote"]]',namespaces=n)
    actual=[''.join(x.xpath('.//w:t/text()',namespaces=n)) for x in quotes]
    expected=[]
    for f in ['system_sources.json','evaluation_sources.json','prior_sources.json','visual_sources.json']:
        sources=json.loads((ROOT/'docs/research'/f).read_text(encoding='utf-8'))
        for s in sources:
            assert sum(len(x['quote'].split()) for x in s['findings'])<=25
            expected += ['“'+x['quote']+'”' for x in s['findings']]
    assert actual==expected,'Quote blocks differ from the verified source dossiers'
    assert len(quotes)==72
    assert not st.xpath('//w:style[@w:styleId="Title"]/w:pPr/w:pBdr',namespaces=n)
    names=set(r.xpath('//w:bookmarkStart/@w:name',namespaces=n))
    refs=r.xpath('//w:hyperlink/@w:anchor',namespaces=n)
    assert all(a in names for a in refs)
    paragraphs=[''.join(x.xpath('.//w:t/text()',namespaces=n)) for x in r.xpath('//w:body/w:p',namespaces=n)]
    locations=[x for x in paragraphs if x.startswith('Location:')]
    assert len(locations)==72
    assert all(len(x.replace('Location:','').replace('Passage','').strip())>8 for x in locations)
    assert not any(re.search(r'\whttps?://',x) for x in paragraphs)
print('Verified 72 exact quote blocks and visible locations')
print('All',len(refs),'internal references resolve; title has no border')
print('Final file bytes:',p.stat().st_size)
