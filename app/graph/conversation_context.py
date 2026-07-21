from __future__ import annotations

import unicodedata
from typing import TypedDict

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised through fallback path
    END = START = StateGraph = InMemorySaver = None


class ConversationContextState(TypedDict, total=False):
    current_topic: str | None
    mentions_card_limit: bool
    requests_limit_change: bool


class ConversationContextGraph:
    """Stores only structured, non-sensitive conversation context by session."""

    def __init__(self) -> None:
        self._fallback_topics: dict[str, str] = {}
        self._compiled_graph = self._build_graph()

    def observe(self, session_id: str, message: str) -> ConversationContextState:
        signals: ConversationContextState = self._signals(message)
        if self._compiled_graph is None:
            prior_topic = self._fallback_topics.get(session_id)
            result = self._context_node({"current_topic": prior_topic, **signals})
            topic = result.get("current_topic")
            if topic:
                self._fallback_topics[session_id] = topic
            return {**signals, **result}

        return self._compiled_graph.invoke(
            signals,
            config={"configurable": {"thread_id": session_id}},
        )

    def _build_graph(self):  # noqa: ANN202
        if StateGraph is None or InMemorySaver is None:
            return None
        graph = StateGraph(ConversationContextState)
        graph.add_node("remember_topic", self._context_node)
        graph.add_edge(START, "remember_topic")
        graph.add_edge("remember_topic", END)
        return graph.compile(checkpointer=InMemorySaver())

    @staticmethod
    def _context_node(state: ConversationContextState) -> ConversationContextState:
        topic = state.get("current_topic")
        if state.get("mentions_card_limit"):
            topic = "card_limit"
        return {"current_topic": topic}

    @classmethod
    def _signals(cls, message: str) -> ConversationContextState:
        normalized = cls._normalize(message)
        change_terms = {"aumenta", "aumentar", "aumente", "aumento", "elevar", "subir", "alterar"}
        return {
            "mentions_card_limit": "limite" in normalized,
            "requests_limit_change": any(term in normalized for term in change_terms),
        }

    @staticmethod
    def _normalize(message: str) -> str:
        return "".join(
            char
            for char in unicodedata.normalize("NFKD", message.lower())
            if not unicodedata.combining(char)
        )
