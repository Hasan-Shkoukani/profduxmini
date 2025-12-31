import operator
import os
from typing import TypedDict, Annotated
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from agent.tools.tools import fetch_drive_file, query_google_sheet, email_students, build_file_catalog, create_google_meet_link, fetch_weekly_calendar_events, web_search
from agent.prompts.system import SYSTEM_PROMPT
from dotenv import load_dotenv
from typing import TypedDict, Annotated, List

class AgentState(TypedDict):
    messages: Annotated[List, operator.add]

load_dotenv()

api_key = os.environ["OPENAI_API"]

tools = [web_search, fetch_drive_file, query_google_sheet, email_students, build_file_catalog, create_google_meet_link, fetch_weekly_calendar_events]

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    timeout=30,
    max_retries=5,
    api_key=api_key
)

llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)

def assistant(state: AgentState):
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return 'end'

workflow = StateGraph(AgentState)
workflow.add_node("agent", assistant)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "end": END}
)

workflow.add_edge("tools", "agent")

app = workflow.compile()

def run(query: str):
    """Run the agent with a given query."""
    initial_state = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=query)]
    }
    result = app.invoke(initial_state)
    try:
        response = result["messages"][-1].content[0]["text"]
    except:
        return result["messages"][-1].content
    else:
        return response

print(run("Hello, can you search for tom?"))
