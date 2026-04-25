import asyncio
import hashlib
import json
import os
import re 
from langgraph.graph import StateGraph,END,START
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_huggingface import HuggingFaceEmbeddings

from langchain_core.messages import HumanMessage, RemoveMessage, BaseMessage, SystemMessage, AIMessage
from dotenv import load_dotenv
import sqlite3
from langchain_groq import ChatGroq
from config import *
from state import State
from typing import Any,Optional
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
from tavily import TavilyClient
import nest_asyncio

load_dotenv()
TAVILY_KEY=os.getenv("TAVILY_KEY")
GROQ_API_KEY=os.getenv("GROQ_API_KEY")

model= ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.2,
    max_tokens=1024,
    groq_api_key=GROQ_API_KEY
)

embeddings=HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
)

CHECKPOINT_DB = Path("data/checkpoints.sqlite3")
CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)

RAG_DB=Path("data/Rag.sqlite3")
RAG_DB.parent.mkdir(parents=True, exist_ok=True)

def json_parser(text:str)->Any:
    
    text=re.sub(r"```json\s*","",text)
    text=re.sub(r"```\s*","",text).strip()
 
    for open_ch,close_ch in [('{','}'),('[',']')]:
        start=text.find(open_ch)
        if start==-1:
            continue
        depth=end=0
        for i,ch in enumerate(text[start:],start):
            if ch==open_ch:
                depth+=1
            elif ch==close_ch:
                depth-=1
                if depth==0:
                    end=i+1
                    break
        if end:
            chunk=text[start:end]
            try:
                return json.loads(chunk)
            except json.JSONDecodeError:
                cleaned=re.sub(r",\s*([}\]])" ,r"\1",chunk)
                return json.loads(cleaned)
    raise ValueError(f"No JSON object found")
 

def deduplication(queries:list[str],visited:list[str]):
    out:list[str]=[]
    all_texts=queries+visited
    all_embed=embeddings.embed_documents(all_texts)
    query_embeds=all_embed[:len(queries)]
    visited_embed=all_embed[len(queries):]
    visited_embed_dup=list(visited_embed)
    
    for query,query_embed in zip(queries,query_embeds):
        if visited_embed_dup:
            sim=cosine_similarity([query_embed],visited_embed_dup)[0]
            sim=max(sim)
        else:
            sim=0.0
        if sim<.8:
            out.append(query)
            visited_embed_dup.append(query_embed)
            
    return out


class SQLiteRAG:
    
    instance: Optional["SQLiteRAG"] = None

    def __init__(self):
        self.conn=sqlite3.connect(str(RAG_DB), check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id      TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL,
                source  TEXT,
                step    TEXT
            )
        """)
        self.conn.commit()

    @classmethod
    def get(cls)->"SQLiteRAG":
        if cls.instance is None:
            cls.instance=cls()
        return cls.instance

  

    @staticmethod
    def doc_id(content: str) -> str: 
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def all_rows(self):
        cur = self.conn.execute("SELECT id, content, embedding, source FROM documents")
        return cur.fetchall()

  

    def store(self, content: str, metadata: dict):
     
        doc_id = self.doc_id(content)
        exists = self.conn.execute(
            "SELECT 1 FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        if exists:
            return
        try:
            emb=embeddings.embed_documents([content])[0]
            self.conn.execute(
                "INSERT INTO documents(id, content, embedding, source, step) VALUES (?,?,?,?,?)",
                (doc_id, content, json.dumps(emb),
                 metadata.get("source", ""), metadata.get("step", ""))
            )
            self.conn.commit()
        except Exception as e:
            print(f"SQLiteRAG.store error: {e}")

    def search(self, query: str, n: int = 4) -> list[dict]:
       
        rows=self.all_rows()
        if not rows:
            return []
        try:
            query_emb=embeddings.embed_documents([query])[0]
            stored_embs=[json.loads(row[2]) for row in rows]
            sims=cosine_similarity([query_emb], stored_embs)[0]

            scored=sorted(
                zip(sims, rows), key=lambda x: x[0], reverse=True
            )
            results=[]
            for sim, row in scored[:n]:
                if float(sim) >= RAG_MIN_SCORE:
                    results.append({
                        "source": row[3] or "memory",
                        "content": row[1],
                        "relevance": float(sim),
                    })
            return results
        except Exception as e:
            print(f"SQLiteRAG.search error: {e}")
            return []


async def websearch(query:str,api_key:str)->list[dict]:
    try:
        event_loop=asyncio.get_event_loop()
        tc=TavilyClient(api_key=api_key)
        results=await event_loop.run_in_executor(
            None,lambda: tc.search(query,max_results=3)
        )
        return [
            {
                "source":r["url"],
                "content":r["content"],
                "relevance":float(r.get("score",.8))
            }
            for r in results.get("results",[])
            
        ]
    except Exception as e:
        print(f"Error:{e}")
        return []
        
def run_async(coroutine):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        nest_asyncio.apply()
        return loop.run_until_complete(coroutine)
    else:
        return loop.run_until_complete(coroutine)
                        


async def parallel_search(queries:list[str],api_key:str)->list[dict]:
    batches=await asyncio.gather(*[websearch(query,api_key) for query in queries])
    return [doc for batch in batches for doc in batch]

def stm_summarize(state:State)->State:
    if len(state.get("messages",[]))>6:
        existing_summary=state.get("summary")
        
        if existing_summary:
            prompt=f"Existing Summary: {existing_summary}\n\nExtend the summary using the conversation above"
        else:
            prompt="Summarize the conversation above."
        sys_prompt=SystemMessage(content="""You are a short-term memory summarization module for a conversational system.

Your task:
- Compress the recent conversation into a concise, factual summary.
- Preserve information that is REQUIRED to correctly answer future user questions.
- Remove verbosity, phrasing, and stylistic elements.

Rules:
- Do NOT invent facts.
- Do NOT add interpretation or opinion.
- Do NOT include assistant reasoning steps.
- Do NOT include greetings, confirmations, or filler.
- Do NOT repeat the full conversation.

What to keep:
- User-provided facts (names, preferences, constraints, decisions)
- Open questions or unresolved goals
- Definitions or explanations the user explicitly asked for
- References to documents or topics that may be needed later

What to remove:
- Small talk
- Politeness
- Repeated questions
- Explanations already understood
- Assistant verbosity

Format:
- Write in third person.
- Use bullet points.
- Be concise and information-dense.
- No markdown, no headings, no code blocks.

Length constraint:
- The summary must be short enough to fit in short-term memory.
- If information is redundant, keep only the most recent version.

If no useful memory exists, output:
"NO_MEMORY"
""")
        conv="\n".join(f"{m.type}:{m.content}" for m in state["messages"][:-2])
        if not conv.strip():
            return {}
        
        msg=f"""
        
        conversation:{conv}
        
        prompt:{prompt}
        
        """
        response=model.invoke([sys_prompt,HumanMessage(content=msg)])
        summary=response.content
        message_to_delete=state["messages"][:-2]
        if summary == "NO_MEMORY":
            return {}
        return {"messages":[RemoveMessage(id=m.id) for m in message_to_delete],"summary":summary}
    
    else:
        return {}

def analyze_query(state:State)->State:

    
    query=state["query"]
    llm_output_raw=model.invoke([
        SystemMessage("You are a research planning assistant. Return ONLY valid JSON — no markdown."),
        HumanMessage(f"""Analyze this research query and build a structured retrieval plan.
Summary of previous research: {state.get("summary","")} 
Return EXACTLY this JSON shape:
{{
  "research_type": "definition|comparison|technical_analysis|literature_review",
  "complexity": "low|medium|high",
  "plan": [
    {{
      "step": "Short label for what this step researches",
      "queries": ["specific search query 1", "specific search query 2"]
    }}
  ]
}} 
Rules:
- 3 steps for low complexity, 4 for medium, 5 for high
- Each step has exactly 2 queries
- Queries must be specific and non-overlapping across steps
- Steps must logically build on each other toward answering the query
 
Query: {query}""")
    ])
    try:
        output_llm=json_parser(llm_output_raw.content)
    except Exception as e:
        print(f"Analysis failed,error:{e}")
        output_llm={
            "research_type":"general",
            "complexity":"medium",
            "plan": [
                {"step": "Initial overview","queries": [query,f"{query} overview"]},
                {"step": "Deep dive","queries": [f"{query} in depth",f"{query} examples"]},
                {"step": "Limitations","queries": [f"{query} problems",f"{query} criticism"]}
            ]
        }
    plan=output_llm.get("plan",[])
    first_queries=deduplication(plan[0]["queries"] if plan else query,[])
    return {
        "research_type":output_llm["research_type"],
        "complexity":output_llm["complexity"],
        "plan":plan,
        "plan_step_index":0,
        "gap_mode":False,
        "gap_step_index":0,
        "current_queries":first_queries,
        "visited_queries":[],
        "documents":[],
        "findings":[],
        "confidence":0.0,
        "missing_topics":[],
        "contradictions":[],
        "unresolved_gaps":[],
        "final_output":"",
        "skip_summarize":False
    }
    
    
def execute_plan(state:State)->State:
    queries=state["current_queries"]
    visited=state["visited_queries"]
    fresh=deduplication(queries=queries,visited=visited)
    if not fresh:
        return {"skip_summarize":True}
    
    rag=SQLiteRAG.get()
    api_key=os.environ.get("TAVILY_KEY")
    gap_mode=state["gap_mode"]
    tag=f"gap_{state['gap_step_index']}" if gap_mode else f"{state['plan_step_index']}"
    if gap_mode:
        rag_docs=[]
        for q in fresh:
            rag_docs.extend(rag.search(q,n=3))
        
        if rag_docs:
            all_docs=rag_docs
        else:
            web_docs=run_async(parallel_search(queries=fresh,api_key=api_key))
            for docs in web_docs:
                rag.store(docs["content"],{"source":docs["source"],"step":tag})
            all_docs=web_docs
    else:
        web_docs=run_async(parallel_search(queries=fresh,api_key=api_key))
        for docs in web_docs:
            rag.store(docs["content"],{"source":docs["source"],"step":tag})
        all_docs=web_docs
    
    for doc in all_docs:
        doc["step_index"]=tag
    
    return {
        "documents":state["documents"]+all_docs,
        "visited_queries":state["visited_queries"]+fresh,
        "skip_summarize":False
    }

def summarize_plan(state:State)->State:
    
    gap_idx=state["gap_step_index"]
    plan=state["plan"]
    gap_mode=state["gap_mode"]
    step_idx=state["plan_step_index"]
    
    
    tag=f"gap_{gap_idx}" if state["gap_mode"] else f"{state['plan_step_index']}"
    step_label=(
        f"gap-fill pass {gap_idx + 1}"
        if gap_mode
        else (plan[step_idx]["step"] if step_idx < len(plan) else f"step-{step_idx}")
    )
    
    
    step_docs=[d for d in state["documents"] if d.get("step_index")==tag]
    step_docs=sorted(step_docs,key=lambda d:d.get("relevance",0),reverse=True)[:DOCS_PER_STEP]
    if not step_docs:
        return {}
    
    combined="\n\n".join(f"[content={d['content'][:700]}]\nscore={d['relevance']}\nsource={d['source']}" for d in step_docs) 
    
    response=model.invoke([
        SystemMessage(content="You extract structured research findings. Return ONLY valid JSON."),
        HumanMessage(content=f"""Extract findings for this research step from the documents below.
 
Return this JSON:
{{
  "key_findings":       ["concise finding 1", "finding 2"],
  "important_concepts": ["concept 1", "concept 2"],
  "numerical_data":     ["any stat, benchmark, or number found"],
  "limitations":        ["any caveat or limitation noted"],
  "source_agreement":   "agree|disagree|mixed"
}}
 
Step: {step_label}
Query: {state['query']}
 
Documents:
{combined}""")
    ])    
    try:
        data=json_parser(response.content)
    except Exception as e:
        print(f"Error:{e}")
        data={"key_findings":[],
              "important_concepts":[],
              "limitations":[]
              }
        
    finding={
        "tag":tag,
        "step_label":step_label,
        "gap_mode":gap_mode,
        **data
    }
    
    return {"findings":state["findings"]+[finding]}


def reflect(state:State)->State:
    plan=state["plan"]
    step_idx=state["plan_step_index"]
    gap_mode=state["gap_mode"]
    
    done=[p["step"] for p in plan[:step_idx+1]]
    pending=[p["step"] for p in plan[step_idx+1:]]
    
    response=model.invoke([
        SystemMessage(content="You evaluate research completeness. Return ONLY valid JSON."),
        HumanMessage(content=f"""Evaluate how completely the current findings answer the query.
 
Return this JSON:
{{
  "confidence":     0.0,
  "missing_topics": ["topic still needing research"],
  "contradictions": ["source A says X, source B says Y"],
  "reasoning":      "one sentence"
}}
 
Confidence scale:
  0.0–0.3  major aspects untouched
  0.3–0.6  core covered, clear gaps remain
  0.6–0.8  mostly complete, minor gaps
  0.8–1.0  query fully answered
 
Query:           {state['query']}
Steps completed: {done}
Steps pending:   {pending}
Gap-fill active: {state['gap_mode']}
Gap pass:        {state['gap_step_index']} / {MAX_GAP_LOOPS}
 
Findings so far:
{json.dumps(state['findings'], indent=2)}""")
    ])

    try:
        data=json_parser(response.content)
    except Exception as e:
        print(f"Error in reflect:{e}")
        data={
            "confidence":.4,
            "missing_topics":[],
            "contradictions":[]
        }
    return {
        "confidence":data.get("confidence",0.4),
        "missing_topics":data.get("missing_topics",[]),
        "contradictions":data.get("contradictions",[]),
        "skip_summarize":False
    }
        
    
def advance_plan(state:State)->State:
    next_idx=state["plan_step_index"]+1
    new_queries=deduplication(state["plan"][next_idx]["queries"],state["visited_queries"])
    return{
        "plan_step_index":next_idx,
        "current_queries":new_queries
    }
    

def generate_gap_queries(state:State)->State:
    missing=state["missing_topics"]
    visited=state["visited_queries"]
    
    response=model.invoke([
        SystemMessage(content="You generate targeted search queries. Return ONLY a JSON array of strings."),
        HumanMessage(f"""Convert missing research topics into 2 specific search queries.
 
Return ONLY: ["query 1", "query 2"]
 
Missing topics:  {missing}
Already searched (do NOT repeat): {visited}""")
    ])  
    try:
        data=json_parser(response.content)
        if not isinstance(data,list):
            data=[]
    except(ValueError,json.JSONDecodeError):
        data=[]
    fresh=deduplication(data,visited)
    gp_index=state["gap_step_index"]+1
    return{
        "current_queries":fresh,
        "gap_mode":True,
        "gap_step_index":gp_index
    }
    

def generate_report(state:State)->State:
    step_block=""
    for f in state["findings"]:
        label=f.get("step_label",f"tag_{f.get('tag','')}")
        key_findings="\n".join(f"{x}" for x in f.get("key_findings",[]) if x)
        numerical_data="\n".join(f"{x}" for x in f.get("numerical_data",[]) if x)
        step_block+=f"\n#{label}\n{key_findings}\n{numerical_data}"
    unresolved=state.get("unresolved_gaps",[])
    gap_section=""
    if unresolved:
        gap_section="\n\n### Unresolved Gaps\n" + "\n".join([f"- {g}" for g in unresolved])
        
    step_block=""
    for step in state.get("findings",[]):
        step_block+=f"\n### {step['step_label']}\n" + "\n".join(step.get("key_findings", [])) + "\n"

  
    sources = set()
    for doc in state.get("documents", []):
        if doc.get("source"):
            sources.add(doc["source"])
    
    ref_section = ""
    if sources:
        ref_section = "\n\n## References\n" + "\n".join([f"- {s}" for s in sorted(list(sources))])
    
    unresolved=state.get("unresolved_gaps",[])
    gap_section=""
    if unresolved:
        gap_section="\n\n### Unresolved Gaps\n" + "\n".join([f"- {g}" for g in unresolved])
        
    response=model.bind(max_tokens=2000).invoke([
        SystemMessage(content="You are a senior research analyst. Write clearly; every claim must be grounded in evidence."),
        HumanMessage(f"""Write a research report using EXACTLY this structure:
 
# [Descriptive title]
 
## Executive Summary
[2–3 sentences — the most direct answer to the query]
 
## Key Findings
- [finding — note which plan step surfaced it]
- ...
 
## Detailed Analysis
[3–4 paragraphs, one major theme per paragraph.]
 
## Contradictions & Limitations
[Conflicts between sources. Confidence caveats.]
 
## Conclusion
[1 paragraph. Direct answer to the query based solely on gathered evidence.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Query:           {state['query']}
Confidence:      {state['confidence']:.0%}
{gap_section}
 
Per-step findings:
{step_block}""")
    ])
    
    final_report = response.content + ref_section
    
    return {"final_output":final_report,"messages":[
        HumanMessage(content=state["query"]),
        AIMessage(content=final_report)
    ]}
         
def route_after_reflect(state:State)->str:
    step_idx=state["plan_step_index"]
    conf=state["confidence"]
    missing=state["missing_topics"]
    gap_step_index=state["gap_step_index"]
    
    if step_idx+1<len(state["plan"]):
        return "advance_plan"
    
    if conf>=CONF_THRESHOLD:
        return "generate_report"
    
    if gap_step_index>=MAX_GAP_LOOPS:
        return "generate_report"
    
    
    if missing:
        return "generate_gap_queries"
    
    return "generate_report"

def route_after_execute(state:State)->str:
    if(state.get("skip_summarize")):
        return "reflect"
    return "summarize_findings"



def router_node(state: State) -> str:
    prompt = f"""Analyze this query: "{state['query']}"
Previous chat summary: {state.get("summary","")}
Previous chat history: {state.get("messages", [])}

Rules:
1. If the user asks to summarize, explain, or discuss the EXISTING findings/research above, return "chat".
2. If the user asks a simple greeting or general question that doesn't need new web data, return "chat".
3. ONLY if the user asks a complex new topic that requires deep web research, data gathering, or multi-step analysis, return "research".

Return ONLY "research" or "chat"."""
    response = model.invoke([HumanMessage(content=prompt)])
    decision = response.content.strip().lower()
    return "analyze_query" if "research" in decision else "chat_response"

def chat_response(state: State) -> State:
    findings_context = ""
    if state.get("findings"):
        findings_context = "\n\nExisting Research Findings:\n" + json.dumps(state["findings"], indent=2)
    
    response = model.invoke([
        SystemMessage(content=f"You are a helpful research assistant. Answer based on current context and findings if available. Summary: {state.get('summary','')}{findings_context}"),
        HumanMessage(content=state["query"])
    ])
    return {"final_output": response.content, "messages": [
        HumanMessage(content=state["query"]),
        AIMessage(content=response.content)
    ], "skip_summarize": True}

graph=StateGraph(State)
graph.add_node("stm_summarize",stm_summarize)
graph.add_node("analyze_query",analyze_query)
graph.add_node("chat_response",chat_response)
graph.add_node("execute_plan",execute_plan)
graph.add_node("summarize_findings",summarize_plan)
graph.add_node("reflect",reflect)
graph.add_node("advance_plan",advance_plan)
graph.add_node("generate_gap_queries",generate_gap_queries)
graph.add_node("generate_report",generate_report)

graph.add_edge(START,"stm_summarize")
graph.add_conditional_edges(
    "stm_summarize",
    router_node,
    {
        "analyze_query": "analyze_query",
        "chat_response": "chat_response"
    }
)
graph.add_edge("chat_response", END)
graph.add_edge("analyze_query","execute_plan")
graph.add_conditional_edges(
    "execute_plan",
    route_after_execute,
    {
      "summarize_findings":"summarize_findings",
      "reflect":"reflect"
    }
)
graph.add_edge("summarize_findings","reflect")
graph.add_conditional_edges(
    "reflect",
    route_after_reflect,
    {
        "advance_plan":"advance_plan",
        "generate_report":"generate_report",
        "generate_gap_queries":"generate_gap_queries"
    }
)
graph.add_edge("advance_plan","execute_plan")
graph.add_edge("generate_gap_queries","execute_plan")
graph.add_edge("generate_report",END)



conn=sqlite3.connect(str(CHECKPOINT_DB),check_same_thread=False)
checkpointer=SqliteSaver(conn)

wf=graph.compile(checkpointer=checkpointer)

def get_thread_history(thread_id: str):
    
    config = {"configurable": {"thread_id": thread_id}}
    state = wf.get_state(config)
    if not state or not state.values or "messages" not in state.values:
        return []
    
    history = []
    for msg in state.values["messages"]:
        if isinstance(msg, HumanMessage):
            history.append({"type": "user", "text": msg.content})
        elif isinstance(msg, AIMessage):
            history.append({"type": "report", "text": msg.content})
            
    return history
