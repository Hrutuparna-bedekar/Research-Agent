from typing import TypedDict
from typing import Literal
from typing import Annotated
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
    messages:Annotated[list[BaseMessage],add_messages]

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
    
    
    
    
    