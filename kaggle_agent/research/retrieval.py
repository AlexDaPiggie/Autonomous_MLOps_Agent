"""FTS over attributed summaries only. Retrieved text is data, never instructions."""
import json
import re
import uuid
from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import utcnow

EVIDENCE = {"literature","hypothesis","locally_validated","reproduced","failed"}


class Knowledge:
    def __init__(self, store):
        self.store = store

    def add(self,title,summary,metadata,competition=None):
        required = {"source_url","provenance","source_date","domain","applicability","risk","evidence",
                    "conditions","validation_requirements","outcomes","license"}
        require(required <= metadata.keys(),"Incomplete knowledge provenance")
        require(metadata["evidence"] in EVIDENCE,"Unknown evidence level")
        require(len(summary)<=6000,"Summarize source rather than storing full documents")
        key=uuid.uuid4().hex
        with self.store.transaction() as db:
            db.execute("INSERT INTO discoveries VALUES(?,?,?,?,?,?)",(key,competition,title,summary,json.dumps(metadata),utcnow()))
            db.execute("INSERT INTO knowledge_fts(id,title,summary) VALUES(?,?,?)",(key,title,summary))
        return key

    def search(self,query,*,domain=None,limit=5,external_allowed=False):
        terms=re.findall(r"[\w]+",query)[:20]
        if not terms:return []
        match=" OR ".join('"'+term+'"' for term in terms)
        rows=self.store.rows("SELECT d.*,bm25(knowledge_fts) AS rank FROM knowledge_fts JOIN discoveries d ON d.id=knowledge_fts.id WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT 50",(match,))
        result=[]
        for row in rows:
            metadata=json.loads(row["metadata"])
            if domain and metadata["domain"]!=domain:continue
            if not external_allowed and metadata.get("requires_external_data",False):continue
            row["metadata"]=metadata
            row["untrusted_data"]=True
            row["summary"]=row["summary"][:2000]
            result.append(row)
        # Own discoveries first; negative results remain searchable.
        result.sort(key=lambda r:(r["competition"] is None,r["rank"]))
        return result[:min(max(limit,0),10)]

    def outcome(self,key,experiment,outcome):
        with self.store.transaction() as db:
            row=db.execute("SELECT metadata FROM discoveries WHERE id=?",(key,)).fetchone()
            require(row is not None,"Unknown discovery")
            metadata=json.loads(row[0]);metadata["outcomes"].append(dict(experiment=experiment,outcome=outcome))
            db.execute("UPDATE discoveries SET metadata=? WHERE id=?",(json.dumps(metadata),key))
