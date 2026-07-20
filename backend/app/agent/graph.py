"""The agent's LangGraph state machine (Phase 2.2 scope: NL -> SQL -> answer).

    generate_sql -> execute_sql --ok--> decide_chart --> synthesize_answer
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
    if "columns" in state:            # success -> visualization decision
        return "chart"
    if state.get("error"):            # attempts exhausted
        return "answer"
    return "fix"                      # failed, retry available


def build_graph(llm: BaseChatModel):
    (generate_sql, execute_sql, fix_sql,
     decide_chart, synthesize_answer) = build_nodes(llm)
    g = StateGraph(AgentState)
    g.add_node("generate_sql", generate_sql)
    g.add_node("execute_sql", execute_sql)
    g.add_node("fix_sql", fix_sql)
    g.add_node("decide_chart", decide_chart)
    g.add_node("synthesize_answer", synthesize_answer)
    g.add_edge(START, "generate_sql")
    g.add_edge("generate_sql", "execute_sql")
    g.add_conditional_edges("execute_sql", _route_after_execute,
                            {"fix": "fix_sql", "chart": "decide_chart",
                             "answer": "synthesize_answer"})
    g.add_edge("decide_chart", "synthesize_answer")
    g.add_edge("fix_sql", "execute_sql")
    g.add_edge("synthesize_answer", END)
    return g.compile()
