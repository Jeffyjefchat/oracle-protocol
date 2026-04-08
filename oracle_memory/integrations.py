"""
Framework integrations — drop-in plugins for LangChain, LlamaIndex, AutoGen.

GPT's VC critique: "Nobody wants primitives. Give opinionated SDKs."

Each integration is a thin adapter. Users don't need the framework
installed — the adapters import lazily and fail gracefully.
"""
from __future__ import annotations

from typing import Any

from .easy import OracleAgent
from .models import MemoryClaim
from .store import InMemoryMemoryStore, MemoryStore


# ── LangChain Integration ──

class LangChainMemory:
    """
    Drop-in replacement for LangChain's BaseMemory.

    Usage with LangChain:
        from oracle_memory.integrations import LangChainMemory
        memory = LangChainMemory(agent_name="my-agent")

        # Use as ConversationBufferMemory replacement:
        chain = ConversationChain(memory=memory)
    """

    def __init__(self, agent_name: str = "langchain-agent",
                 user_id: str = "default",
                 store: MemoryStore | None = None) -> None:
        self._agent = OracleAgent(name=agent_name, user_id=user_id, store=store)
        self.memory_key = "oracle_memory"
        self.input_key = "input"
        self.output_key = "output"

    @property
    def memory_variables(self) -> list[str]:
        return [self.memory_key]

    def load_memory_variables(self, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        context = self._agent.context_for_llm()
        return {self.memory_key: context}

    def save_context(self, inputs: dict[str, Any], outputs: dict[str, str]) -> None:
        human_input = inputs.get(self.input_key, "")
        ai_output = outputs.get(self.output_key, "")
        if human_input or ai_output:
            text = f"User: {human_input}\nAssistant: {ai_output}"
            self._agent.remember(text)

    def clear(self) -> None:
        self._agent = OracleAgent(
            name=self._agent.name,
            user_id=self._agent.user_id,
        )

    @property
    def agent(self) -> OracleAgent:
        return self._agent


# ── LlamaIndex Integration ──

class LlamaIndexMemory:
    """
    Memory module for LlamaIndex chat engines.

    Usage with LlamaIndex:
        from oracle_memory.integrations import LlamaIndexMemory
        memory = LlamaIndexMemory(agent_name="llama-agent")

        # Get context for the chat engine:
        context = memory.get()
        # Store conversation turn:
        memory.put("Paris is the capital of France")
    """

    def __init__(self, agent_name: str = "llama-agent",
                 user_id: str = "default",
                 store: MemoryStore | None = None) -> None:
        self._agent = OracleAgent(name=agent_name, user_id=user_id, store=store)

    def get(self, query: str | None = None) -> str:
        """Retrieve memory context, optionally filtered by query."""
        if query:
            results = self._agent.recall(query)
            return " | ".join(results) if results else ""
        return self._agent.context_for_llm()

    def get_all(self) -> list[dict[str, Any]]:
        """Return all claims as dicts."""
        claims = self._agent.store.list_claims(
            user_id=self._agent.user_id, limit=10000
        )
        return [{"content": c.content, "type": c.memory_type, "id": c.claim_id} for c in claims]

    def put(self, text: str) -> list[MemoryClaim]:
        """Store new knowledge."""
        return self._agent.remember(text)

    def reset(self) -> None:
        self._agent = OracleAgent(
            name=self._agent.name,
            user_id=self._agent.user_id,
        )

    @property
    def agent(self) -> OracleAgent:
        return self._agent


# ── AutoGen Integration ──

class AutoGenMemoryBackend:
    """
    Memory backend for Microsoft AutoGen agents.

    Usage with AutoGen:
        from oracle_memory.integrations import AutoGenMemoryBackend
        backend = AutoGenMemoryBackend(agent_name="autogen-coder")

        # In your agent's message handler:
        context = backend.get_context(query="how to parse JSON")
        backend.store_turn(user_msg="...", assistant_msg="...")
    """

    def __init__(self, agent_name: str = "autogen-agent",
                 user_id: str = "default",
                 store: MemoryStore | None = None) -> None:
        self._agent = OracleAgent(name=agent_name, user_id=user_id, store=store)

    def get_context(self, query: str = "", limit: int = 5) -> str:
        """Get memory context for injection into agent prompts."""
        if query:
            results = self._agent.recall(query, limit=limit)
            return "\n".join(f"- {r}" for r in results) if results else ""
        return self._agent.context_for_llm()

    def store_turn(self, user_msg: str = "", assistant_msg: str = "") -> None:
        """Store a conversation turn."""
        parts = []
        if user_msg:
            parts.append(f"User: {user_msg}")
        if assistant_msg:
            parts.append(f"Assistant: {assistant_msg}")
        if parts:
            self._agent.remember("\n".join(parts))

    def search(self, query: str, limit: int = 5) -> list[str]:
        """Search memory by query."""
        return self._agent.recall(query, limit=limit)

    def feedback(self, positive: bool) -> None:
        """Record feedback on last interaction."""
        if positive:
            self._agent.thumbs_up()
        else:
            self._agent.thumbs_down()

    @property
    def agent(self) -> OracleAgent:
        return self._agent
