import os
import json
import uuid
import boto3
import psycopg2
import psycopg2.extras
import numpy as np
from psycopg2.extensions import register_adapter, AsIs
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import fitz  # pymupdf

from app.database import get_connection, rollback_if_aborted
from app.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# numpy adapter for psycopg2
# ---------------------------------------------------------------------------
def adapt_numpy_array(arr):
    return AsIs(repr(arr.tolist()))

register_adapter(np.ndarray, adapt_numpy_array)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TABLE         = "rag_documents"
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
AWS_REGION    = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID      = os.getenv("MODEL_ID", "us.meta.llama4-maverick-17b-instruct-v1:0")

VALID_DIMENSIONS = (256, 512, 1024)


# ---------------------------------------------------------------------------
# RAGService
# ---------------------------------------------------------------------------
class RAGService:

    def __init__(self):
        if EMBEDDING_DIM not in VALID_DIMENSIONS:
            raise ValueError(f"EMBEDDING_DIM must be one of {VALID_DIMENSIONS}")

        self.embedding_dim = EMBEDDING_DIM
        self.model_id      = MODEL_ID

        self.bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
        )

        self._conn = None
        logger.info(f"RAGService initialized | embedding_dim={EMBEDDING_DIM} | model={MODEL_ID}")

    # -- DB connection -------------------------------------------------------

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=os.getenv("PG_HOST", "localhost"),
                port=int(os.getenv("PG_PORT", "5432")),
                dbname=os.getenv("PG_DB", "ragdb"),
                user=os.getenv("PG_USER", "postgres"),
                password=os.getenv("PG_PASSWORD", ""),
            )
            self._conn.autocommit = False
            logger.info("PostgreSQL connection established")
        return self._conn

    # -- Book management -----------------------------------------------------

    def generate_book_id(self) -> str:
        book_id = str(uuid.uuid4())
        logger.info(f"Generated book_id: {book_id}")
        return book_id

    def book_exists(self, book_id: str) -> bool:
        conn = get_connection()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT EXISTS (SELECT 1 FROM {TABLE} WHERE book_id = %s);",
                    (book_id,)
                )
                exists = cur.fetchone()[0]
                logger.info(f"book_exists check | book_id={book_id} | exists={exists}")
                return exists
        except Exception as e:
            logger.error(f"book_exists failed | book_id={book_id} | error={e}")
            raise
        finally:
            conn.close()

    def get_chunk_count(self, book_id: str) -> int:
        conn = get_connection()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM {TABLE} WHERE book_id = %s;",
                    (book_id,)
                )
                count = cur.fetchone()[0]
                logger.info(f"Chunk count | book_id={book_id} | chunks={count}")
                return count
        except Exception as e:
            logger.error(f"get_chunk_count failed | book_id={book_id} | error={e}")
            raise
        finally:
            conn.close()

    def list_books(self) -> list:
        conn = get_connection()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        book_id,
                        metadata->>'book' AS book_name,
                        COUNT(*)          AS chunks
                    FROM {TABLE}
                    GROUP BY book_id, metadata->>'book'
                    ORDER BY book_name;
                """)
                rows = cur.fetchall()
            books = [{"book_id": r[0], "book_name": r[1], "chunks": r[2]} for r in rows]
            logger.info(f"list_books | total={len(books)}")
            return books
        except Exception as e:
            logger.error(f"list_books failed | error={e}")
            raise
        finally:
            conn.close()

    def delete_book(self, book_id: str):
        logger.info(f"Deleting book | book_id={book_id}")
        conn = self._get_conn()
        rollback_if_aborted(conn)
        try:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {TABLE} WHERE book_id = %s;", (book_id,))
            conn.commit()
            logger.info(f"Book deleted successfully | book_id={book_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"delete_book failed | book_id={book_id} | error={e}")
            raise

    # -- Embedding -----------------------------------------------------------

    def get_embedding(self, text: str) -> list:
        try:
            response = self.bedrock_client.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=json.dumps({
                    "inputText": text,
                    "dimensions": self.embedding_dim,
                }),
            )
            return json.loads(response["body"].read())["embedding"]
        except Exception as e:
            logger.error(f"get_embedding failed | error={e}")
            raise

    # -- PDF processing ------------------------------------------------------

    def extract_and_chunk_pdf(self, pdf_path: str, book_id: str) -> list:
        book_name = os.path.splitext(os.path.basename(pdf_path))[0]
        docs = []

        logger.info(f"Extracting PDF | book='{book_name}' | path={pdf_path}")

        try:
            with fitz.open(pdf_path) as pdf:
                total_pages = len(pdf)
                logger.info(f"PDF opened | pages={total_pages} | book='{book_name}'")

                for i, page in enumerate(pdf):
                    page_text = page.get_text()
                    if not page_text.strip():
                        continue
                    for chunk in self._chunk_text(page_text):
                        docs.append(Document(
                            page_content=chunk,
                            metadata={"book_id": book_id, "book": book_name, "page": i + 1}
                        ))
        except Exception as e:
            logger.error(f"PDF extraction failed | book='{book_name}' | error={e}")
            raise

        if not docs:
            logger.warning(f"No text extracted from PDF | book='{book_name}'")
            raise ValueError("No text could be extracted from the PDF.")

        logger.info(f"PDF extraction complete | book='{book_name}' | chunks={len(docs)}")
        return docs

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> list:
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
        ).split_text(text)

    # -- Indexing ------------------------------------------------------------

    def index_book(self, pdf_path: str, book_id: str, batch_size: int = 50) -> int:
        logger.info(f"Indexing started | book_id={book_id} | path={pdf_path}")

        try:
            docs  = self.extract_and_chunk_pdf(pdf_path, book_id)
            conn  = self._get_conn()
            total = len(docs)

            logger.info(f"Embedding {total} chunks | book_id={book_id}")

            for start in range(0, total, batch_size):
                batch = docs[start: start + batch_size]
                rows  = []

                for doc in batch:
                    emb = self.get_embedding(doc.page_content)
                    rows.append((
                        doc.metadata["book_id"],
                        doc.page_content,
                        emb,
                        json.dumps(doc.metadata),
                    ))

                rollback_if_aborted(conn)
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(
                        cur,
                        f"INSERT INTO {TABLE} (book_id, content, embedding, metadata) VALUES %s",
                        rows,
                        template="(%s, %s, %s::vector, %s::jsonb)",
                    )
                conn.commit()
                logger.info(f"Indexed batch | {min(start + batch_size, total)}/{total} | book_id={book_id}")

            logger.info(f"Indexing complete | book_id={book_id} | total_chunks={total}")
            return total

        except Exception as e:
            logger.error(f"Indexing failed | book_id={book_id} | error={e}")
            raise

    # -- Retrieval -----------------------------------------------------------

    def vector_search(self, query: str, book_id: str, k: int = 8) -> list:
        logger.info(f"Vector search | book_id={book_id} | query='{query[:60]}...'")
        try:
            emb  = self.get_embedding(query)
            conn = self._get_conn()
            rollback_if_aborted(conn)
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT content, metadata,
                           1 - (embedding <=> %s::vector) AS score
                    FROM   {TABLE}
                    WHERE  book_id = %s
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  %s;
                    """,
                    (emb, book_id, emb, k),
                )
                rows = cur.fetchall()
            logger.info(f"Vector search returned {len(rows)} results | book_id={book_id}")
            return [
                Document(page_content=r[0], metadata={**(r[1] or {}), "score": float(r[2])})
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Vector search failed | book_id={book_id} | error={e}")
            raise

    def keyword_search(self, query: str, book_id: str, k: int = 10) -> list:
        logger.info(f"Keyword search | book_id={book_id} | query='{query[:60]}...'")
        try:
            conn = self._get_conn()
            rollback_if_aborted(conn)
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT content, metadata,
                           ts_rank(tsv, plainto_tsquery('english', %s)) AS rank
                    FROM   {TABLE}
                    WHERE  book_id = %s
                      AND  tsv @@ plainto_tsquery('english', %s)
                    ORDER  BY rank DESC
                    LIMIT  %s;
                    """,
                    (query, book_id, query, k),
                )
                rows = cur.fetchall()
            logger.info(f"Keyword search returned {len(rows)} results | book_id={book_id}")
            return [
                Document(page_content=r[0], metadata={**(r[1] or {}), "rank": float(r[2])})
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Keyword search failed | book_id={book_id} | error={e}")
            raise

    def hybrid_search(self, query: str, book_id: str) -> list:
        logger.info(f"Hybrid search | book_id={book_id}")
        seen, merged = set(), []
        for doc in self.vector_search(query, book_id) + self.keyword_search(query, book_id):
            if doc.page_content not in seen:
                seen.add(doc.page_content)
                merged.append(doc)
        logger.info(f"Hybrid search merged {len(merged)} unique chunks | book_id={book_id}")
        return merged

    # -- Generation ----------------------------------------------------------

    # def process_query_with_history(
    #     self,
    #     query: str,
    #     book_id: str,
    #     history: list[dict],
    # ) -> str:
    #     logger.info(f"Processing query | book_id={book_id} | history_turns={len(history)} | query='{query[:80]}...'")

    #     try:
    #         retrieved = self.hybrid_search(query, book_id)

    #         if not retrieved:
    #             logger.warning(f"No chunks retrieved | book_id={book_id} | query='{query[:80]}'")
    #             return "No relevant content found in this book for your query."

    #         context = "\n\n".join(
    #             f"[Book: {d.metadata.get('book', 'Unknown')} | Page: {d.metadata.get('page', '?')}]\n{d.page_content}"
    #             for d in retrieved
    #         )

    #         system_prompts = [{
    #             "text": (
    #                 "You are an intelligent reading assistant specialized in answering questions "
    #                 "strictly based on the content of uploaded books.\n\n"

    #                 "## IDENTITY\n"
    #                 "- You are a book assistant created to help users understand book content.\n"
    #                 "- You are NOT ChatGPT, Claude, Gemini, or any other general AI assistant.\n"
    #                 "- If asked about your identity, say: 'I am a book reading assistant. "
    #                 "I can only help you with questions about the uploaded books.'\n\n"

    #                 "## YOUR TASK\n"
    #                 "- Answer the user's question using ONLY the provided book context chunks.\n"
    #                 "- Each context chunk is labeled with [Book: <name> | Page: <number>].\n"
    #                 "- Always cite the page number when referencing specific information.\n\n"

    #                 "## RESPONSE FORMAT — ADAPT TO THE QUESTION\n"
    #                 "- Use the most natural format for the question being asked.\n"
    #                 "- For factual or direct questions → give a concise paragraph answer.\n"
    #                 "- For explanations or concepts → use short paragraphs with clear flow.\n"
    #                 "- For comparisons or multiple items → use bullet points or numbered lists.\n"
    #                 "- For summaries → give a structured overview with key points.\n"
    #                 "- For quotes or specific passages → quote directly and cite the page.\n"
    #                 "- For follow-up or conversational questions → keep the tone natural and brief.\n"
    #                 "- Always match the length of your response to the complexity of the question. "
    #                 "Short questions deserve short answers. Complex questions deserve thorough answers.\n\n"

    #                 "## STRICT GUARDRAILS\n"
    #                 "- NEVER answer from your own training knowledge or outside information.\n"
    #                 "- NEVER make up, infer, or assume information not present in the context.\n"
    #                 "- NEVER answer questions unrelated to the provided book context.\n"
    #                 "- If the answer is NOT found in the context, respond exactly with:\n"
    #                 "  'I could not find information about this in the provided book content. "
    #                 "Please try rephrasing your question or ask about a different topic from the book.'\n"
    #                 "- If the user asks something harmful, offensive, or inappropriate, respond with:\n"
    #                 "  'I am only able to assist with questions related to the book content.'\n\n"

    #                 "## CONVERSATION RULES\n"
    #                 "- Maintain context across the conversation — refer to previous messages when relevant.\n"
    #                 "- If a follow-up question is ambiguous, relate it to the most recent book topic discussed.\n"
    #                 "- Keep your tone professional, helpful, and reader-friendly.\n"
    #             )
    #         }]

    #         messages = []
    #         for msg in history:
    #             messages.append({
    #                 "role": msg["role"],
    #                 "content": [{"text": msg["content"]}],
    #             })

    #         messages.append({
    #             "role": "user",
    #             "content": [{"text": f"{query}\n\nContext:\n{context}"}],
    #         })

    #         logger.info(f"Calling Bedrock | model={self.model_id} | messages={len(messages)}")

    #         response = self.bedrock_client.converse_stream(
    #             modelId=self.model_id,
    #             messages=messages,
    #             system=system_prompts,
    #             inferenceConfig={"temperature": 0.5, "maxTokens": 512},
    #         )

    #         output = ""
    #         for event in response["stream"]:
    #             if "contentBlockDelta" in event:
    #                 delta = event["contentBlockDelta"]["delta"]
    #                 if "text" in delta:
    #                     output += delta["text"]

    #         logger.info(f"Query processed successfully | book_id={book_id} | response_length={len(output)}")
    #         return output

    #     except Exception as e:
    #         logger.error(f"process_query_with_history failed | book_id={book_id} | error={e}")
    #         raise


    # -- Streaming Generation ------------------------------------------------

    def stream_query_with_history(
        self,
        query: str,
        book_id: str,
        history: list[dict],
    ):
        """
        Generator that yields SSE tokens from Bedrock one by one.
        Frontend reads these via fetch ReadableStream.
        Final event contains done=True and full answer for DB saving.
        """
        logger.info(f"Stream query | book_id={book_id} | history_turns={len(history)} | query='{query[:80]}...'")

        retrieved = self.hybrid_search(query, book_id)

        if not retrieved:
            logger.warning(f"No chunks retrieved | book_id={book_id}")
            yield f"data: {json.dumps({'token': 'No relevant content found in this book for your query.'})}\n\n"
            yield f"data: {json.dumps({'done': True, 'answer': 'No relevant content found in this book for your query.'})}\n\n"
            return

        context = "\n\n".join(
            f"[Book: {d.metadata.get('book', 'Unknown')} | Page: {d.metadata.get('page', '?')}]\n{d.page_content}"
            for d in retrieved
        )

        system_prompts = [{
            "text": (
                "You are an intelligent reading assistant specialized in answering questions "
                "strictly based on the content of uploaded books.\n\n"

                "## IDENTITY\n"
                "- You are a book assistant created to help users understand book content.\n"
                "- You are NOT ChatGPT, Claude, Gemini, or any other general AI assistant.\n"
                "- If asked about your identity, say: I am a book reading assistant. "
                "I can only help you with questions about the uploaded books.\n\n"

                "## YOUR TASK\n"
                "- Answer the user question using ONLY the provided book context chunks.\n"
                "- Each context chunk is labeled with [Book: name | Page: number].\n"
                "- Always cite the page number when referencing specific information.\n\n"

                "## RESPONSE FORMAT — ADAPT TO THE QUESTION\n"
                "- Use the most natural format for the question being asked.\n"
                "- For factual or direct questions give a concise paragraph answer.\n"
                "- For explanations or concepts use short paragraphs with clear flow.\n"
                "- For comparisons or multiple items use bullet points or numbered lists.\n"
                "- For summaries give a structured overview with key points.\n"
                "- For quotes or specific passages quote directly and cite the page.\n"
                "- Always match the length of your response to the complexity of the question.\n\n"

                "## STRICT GUARDRAILS\n"
                "- NEVER answer from your own training knowledge or outside information.\n"
                "- NEVER make up infer or assume information not present in the context.\n"
                "- NEVER answer questions unrelated to the provided book context.\n"
                "- If the answer is NOT found in the context respond with: "
                "I could not find information about this in the provided book content. "
                "Please try rephrasing your question or ask about a different topic from the book.\n"
                "- If the user asks something harmful or inappropriate respond with: "
                "I am only able to assist with questions related to the book content.\n\n"

                "## CONVERSATION RULES\n"
                "- Maintain context across the conversation refer to previous messages when relevant.\n"
                "- If a follow-up question is ambiguous relate it to the most recent book topic discussed.\n"
                "- Keep your tone professional helpful and reader-friendly.\n"
            )
        }]

        messages = []
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": [{"text": msg["content"]}],
            })
        messages.append({
            "role": "user",
            "content": [{"text": f"{query}\n\nContext:\n{context}"}],
        })

        logger.info(f"Calling Bedrock stream | model={self.model_id} | messages={len(messages)}")

        response = self.bedrock_client.converse_stream(
            modelId=self.model_id,
            messages=messages,
            system=system_prompts,
            inferenceConfig={"temperature": 0.5, "maxTokens": 512},
        )

        full_output = ""
        for event in response["stream"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    token = delta["text"]
                    full_output += token
                    yield f"data: {json.dumps({'token': token})}\n\n"

        # Final event — signals done and carries full answer for DB saving
        yield f"data: {json.dumps({'done': True, 'answer': full_output})}\n\n"
        logger.info(f"Stream complete | book_id={book_id} | length={len(full_output)}")

    # -- Cleanup -------------------------------------------------------------

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("PostgreSQL connection closed")


# Single shared instance
rag_service = RAGService()