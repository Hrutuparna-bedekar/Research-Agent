import asyncio
import hashlib
import json
import os
import re 
from langgraph.graph import StateGraph,END,START
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.messages import HumanMessage, RemoveMessage, BaseMessage, SystemMessage, AIMessage
from dotenv import load_dotenv
import sqlite3
from langchain_groq import ChatGroq
from config import *
from state import State
import re
import json
from typing import Any,Optional
import hashlib
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

import chromadb
from chromadb.config import Settings
from tavily import TavilyClient
import nest_asyncio

model= ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.2,
    max_tokens=512,
)

embeddings=HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
)





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


class ChromaSession:
    instance:Optional["ChromaSession"]=None
    
    def __init__(self):
        self.collection=None
        try:
            self.collection=chromadb.Client().get_or_create_collection(
                name="research_mem",
            )
        except Exception as exc:
            print(f"Error:{exc}")
            
    @classmethod
    def get(cls)->"ChromaSession":
        if cls.instance is None:
            cls.instance=cls()
        return cls.instance
    
    def search(self,query:str,n:int=4)->list[dict]:
        if not self.collection:
            return []
        try:
            res=self.collection.query(query_texts=[query],n_results=n)
            docs=[]
            for doc,score in zip(res["documents"][0],res.get("distances",[[1.0]*n])[0]):
                relevance=1-float(score)
                if relevance>=RAG_MIN_SCORE:
                    docs.append({"source":"memory","content":doc,"relevance":relevance})
            return docs
        except Exception as e:
            print(f"Error:{e}")
            return []
        
    
    def store(self,content:str,metadata:dict):
        if self.collection is None:
            return
        try:
            self.collection.add(documents=[content],metadatas=[metadata])
        except Exception as e:
            print(f"Error:{e}")


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
        loop=asyncio.get_event_loop()
        if loop.is_running():
            nest_asyncio.apply()
        return loop.run_until_complete(coroutine)
    except RuntimeError:
        return asyncio.run(coroutine)
                        


async def parallel_search(queries:list[str],api_key:str)->list[dict]:
    batches=await asyncio.gather(*[websearch(query,api_key) for query in queries])
    return [doc for batch in batches for doc in batch]



def analyze_query(state:State)->State:
    query=state["query"]
    llm_output_raw=model.invoke([
        SystemMessage("You are a research planning assistant. Return ONLY valid JSON — no markdown."),
        HumanMessage(f"""Analyze this research query and build a structured retrieval plan.
 
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
    
    
def exceute_plan(state:State)->State:
    queries=state["current_queries"]
    visited=state["visited_queries"]
    fresh=deduplication(queries=queries,visited=visited)
    if not fresh:
        return {"skip_summarize":True}
    
    chroma=ChromaSession.get()
    api_key=os.environ.get("TAVILY_KEY")
    gap_mode=state["gap_mode"]
    tag=f"gap_{state['gap_step_index']}" if gap_mode else state["plan_step_index"]
    if gap_mode:
        rag_docs=[]
        for q in fresh:
            rag_docs.extend(chroma.search(q,n=3))
        
        if rag_docs:
            all_docs=rag_docs
        else:
            web_docs=run_async(parallel_search(queries=fresh,api_key=api_key))
            for docs in web_docs:
                chroma.store(docs["content"],{"source":docs["source"],"step":tag})
            all_docs=web_docs
    else:
        web_docs=run_async(parallel_search(queries=fresh,api_key=api_key))
        for docs in web_docs:
            chroma.store(docs["content"],{"source":docs["source"],"step":tag})
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
    
    
    tag=f"gap_{gap_idx}" if state["gap_mode"] else state["plan_step_index"]
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
Gap pass:        {state['gap_step_index']} / {MAX_GAP_STEPS}
 
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
    except:
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
    if unresolved:
        gap_section=f"\n Unresolved gaps ramining:\n"+"\n".join(f"  {g}" for g in unresolved) 
    else:
        gap_section=""
    
    
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
[3–4 paragraphs, one major theme per paragraph.
Every claim must be traceable to the per-step findings below.]
 
## Contradictions & Limitations
[Conflicts between sources. Confidence caveats.
{("IMPORTANT — explicitly list these unresolved gaps: " + str(unresolved)) if unresolved else "Any remaining knowledge gaps."}]
 
## Conclusion
[1 paragraph. Direct answer to the query based solely on gathered evidence.]
 
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Query:           {state['query']}
Confidence:      {state['confidence']:.0%}
Plan steps done: {state['plan_step_index'] + 1} / {len(state['plan'])}
Gap passes used: {state['gap_step_index']} / {MAX_GAP_STEPS}
{gap_section}
 
Per-step findings:
{step_block}
 
Contradictions: {state['contradictions']}""")
    ])
    return {"final_output":response.content}
         
         
         
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



graph=StateGraph(State)
graph.add_node("analyze_query",analyze_query)
graph.add_node("execute_plan",exceute_plan)
graph.add_node("summarize_findings",summarize_plan)
graph.add_node("reflect",reflect)
graph.add_node("advance_plan",advance_plan)
graph.add_node("generate_gap_queries",generate_gap_queries)
graph.add_node("generate_report",generate_report)

graph.add_edge(START,"analyze_query")
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

wf=graph.compile()
