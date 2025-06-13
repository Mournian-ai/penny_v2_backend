import asyncio
import uuid
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from penny_v2_api.config import AppConfig
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import AddMemoryRequest, QueryMemoryRequest, DeleteMemoryRequest

class MemoryService:
    def __init__(self, event_bus: EventBus, settings: AppConfig):
        self.event_bus = event_bus
        self.settings = settings
        self.client = None
        self.collection = None

    async def start(self):
        persist_dir = getattr(self.settings, "CHROMA_DB_DIR", "./chroma_memory")
        self.client = chromadb.Client(Settings(persist_directory=persist_dir))

        embedding_fn = None
        if getattr(self.settings, "OPENAI_API_KEY", None):
            embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
                api_key=self.settings.OPENAI_API_KEY,
                model_name="text-embedding-ada-002"
            )

        self.collection = self.client.get_or_create_collection(
            name="penny_memory",
            embedding_function=embedding_fn
        )

        self.event_bus.subscribe_async(AddMemoryRequest, self.handle_add_memory)
        self.event_bus.subscribe_async(QueryMemoryRequest, self.handle_query_memory)
        self.event_bus.subscribe_async(DeleteMemoryRequest, self.handle_delete_memory)

    async def handle_add_memory(self, event: AddMemoryRequest):
        try:
            text = event.text
            metadata = event.metadata or {}
            mem_id = str(uuid.uuid4())
            self.collection.add(documents=[text], metadatas=[metadata], ids=[mem_id])
            event.response_future.set_result(mem_id)
        except Exception as ex:
            event.response_future.set_exception(ex)

    async def handle_query_memory(self, event: QueryMemoryRequest):
        try:
            results = self.collection.query(
                query_texts=[event.query_text],
                n_results=event.n_results,
                include=["documents", "metadatas", "distances", "ids"]
            )
            memories = []
            if results.get("ids"):
                for idx, mem_id in enumerate(results["ids"][0]):
                    memory_entry = {
                        "id": mem_id,
                        "text": results["documents"][0][idx] if results.get("documents") else None,
                        "metadata": results["metadatas"][0][idx] if results.get("metadatas") else None,
                        "distance": results["distances"][0][idx] if results.get("distances") else None
                    }
                    memories.append(memory_entry)
            event.response_future.set_result(memories)
        except Exception as ex:
            event.response_future.set_exception(ex)

    async def handle_delete_memory(self, event: DeleteMemoryRequest):
        try:
            self.collection.delete(ids=[event.memory_id])
            event.response_future.set_result(True)
        except Exception as ex:
            event.response_future.set_exception(ex)
