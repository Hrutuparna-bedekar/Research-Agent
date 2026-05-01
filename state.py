from typing import TypedDict
from typing import Literal
from typing import Annotated
import operator
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class PlanStep(TypedDict):
    step:str
    queries:list[str]

class State(TypedDict):
    query:str
    research_type:str
    complexity:str
    
    summary:str
    # Prunable short-term memory — used by the LLM for context
    messages:Annotated[list[BaseMessage],add_messages]

    # ── Display history ────────────────────────────────────────────────────────
    # Append-only log of every user query and AI response, never pruned.
    # operator.add means LangGraph concatenates new items onto the list each turn.
    # The frontend reads this field for full conversation history.
    display_history: Annotated[list[dict], operator.add]

    plan:list[PlanStep]
    plan_step_index:int
    
    gap_mode:bool
    gap_step_index:int
    
    skip_summarize:bool
    
    current_queries:list[str]
    visited_queries:list[str]
    
    
    documents:list[dict]
    
    findings:list[dict]
    
    confidence:float
    missing_topics:list[str]
    contradictions:list[str]
    
    unresolved_gaps:list[str]
    
    final_output:str 