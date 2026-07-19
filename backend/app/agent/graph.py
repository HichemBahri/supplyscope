"""The agent's LangGraph state machine (Phase 2.2 scope: NL -> SQL -> answer).

    generate_sql -> execute_sql --ok--------------------> synthesize_answer
                        | error                                   ^
                        v                                         |
                     fix_sql -> execute_sql ... (<= MAX attempts) +--(gave up)
"""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import build_nodes
from app.agent.state import AgentState


def _route_after_execute(state: AgentState) -> str:
    if "columns" in state:            # success
        return "answer"
    if state.get("error"):            # attempts exhausted
        return "answer"
    return "fix"                      # failed, retry available


def build_graph(llm: BaseChatModel):
    generate_sql, execute_sql, fix_sql, synthesize_answer = build_nodes(llm)
    g = StateGraph(AgentState)
    g.add_node("generate_sql", generate_sql)
    g.add_node("execute_sql", execute_sql)
    g.add_node("fix_sql", fix_sql)
    g.add_node("synthesize_answer", synthesize_answer)
    g.add_edge(START, "generate_sql")
    g.add_edge("generate_sql", "execute_sql")
    g.add_conditional_edges("execute_sql", _route_after_execute,
                            {"fix": "fix_sql", "answer": "synthesize_answer"})
    g.add_edge("fix_sql", "execute_sql")
    g.add_edge("synthesize_answer", END)
    return g.compile()
